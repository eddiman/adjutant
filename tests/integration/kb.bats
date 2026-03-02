#!/usr/bin/env bats
# tests/integration/kb.bats — Integration tests for KB system end-to-end flows
#
# Tests: CLI routing, query pipeline (mocked opencode), /kb telegram command,
# create→list→info→query→remove lifecycle.

load "${BATS_TEST_DIRNAME}/../test_helper/setup.bash"
load "${BATS_TEST_DIRNAME}/../test_helper/mocks.bash"

setup() {
  setup_test_env
  setup_mocks

  export ADJ_DIR="${TEST_ADJ_DIR}"

  # Create the knowledge_bases directory and registry
  mkdir -p "${TEST_ADJ_DIR}/knowledge_bases"
  cat > "${TEST_ADJ_DIR}/knowledge_bases/registry.yaml" <<'YAML'
knowledge_bases: []
YAML

  # Copy templates
  cp -R "${PROJECT_ROOT}/templates" "${TEST_ADJ_DIR}/templates"

  # Source paths first
  source "${COMMON}/paths.sh"
}

teardown() {
  jobs -p 2>/dev/null | xargs kill 2>/dev/null || true
  teardown_mocks
  teardown_test_env
}

# ===== Full lifecycle: create → list → info → remove =====

@test "kb integration: full lifecycle create/list/info/remove" {
  source "${TEST_ADJ_DIR}/scripts/capabilities/kb/manage.sh"

  # Create
  local kb_dir="${TEST_ADJ_DIR}/lifecycle-kb"
  run kb_create "lifecycle" "${kb_dir}" "Lifecycle test KB" "inherit" "read-only"
  assert_success
  [ -d "${kb_dir}" ]
  [ -f "${kb_dir}/kb.yaml" ]
  [ -f "${kb_dir}/opencode.json" ]
  [ -f "${kb_dir}/.opencode/agents/kb.md" ]

  # List
  run kb_list
  assert_success
  assert_output --partial "lifecycle"
  assert_output --partial "Lifecycle test KB"

  # Count
  run kb_count
  assert_output "1"

  # Info
  run kb_info "lifecycle"
  assert_success
  assert_output --partial "name=lifecycle"
  assert_output --partial "path=${kb_dir}"

  # Remove
  run kb_remove "lifecycle"
  assert_success
  run kb_exists "lifecycle"
  assert_failure
  # Files still exist
  [ -d "${kb_dir}" ]

  # Count back to 0
  run kb_count
  assert_output "0"
}

# ===== Multiple KBs =====

@test "kb integration: multiple KBs can coexist" {
  source "${TEST_ADJ_DIR}/scripts/capabilities/kb/manage.sh"

  kb_create "alpha" "${TEST_ADJ_DIR}/alpha" "Alpha KB"
  kb_create "beta" "${TEST_ADJ_DIR}/beta" "Beta KB"
  kb_create "gamma" "${TEST_ADJ_DIR}/gamma" "Gamma KB"

  run kb_count
  assert_output "3"

  # Remove middle one
  kb_remove "beta"
  run kb_count
  assert_output "2"
  run kb_exists "alpha"
  assert_success
  run kb_exists "gamma"
  assert_success
  run kb_exists "beta"
  assert_failure
}

# ===== Scaffold for existing directory =====

@test "kb integration: scaffold works on existing directory with content" {
  source "${TEST_ADJ_DIR}/scripts/capabilities/kb/manage.sh"

  local existing="${TEST_ADJ_DIR}/existing-dir"
  mkdir -p "${existing}/docs"
  echo "# Existing notes" > "${existing}/docs/notes.md"
  echo "Some data" > "${existing}/data.json"

  run kb_create "existing" "${existing}" "Existing dir with content"
  assert_success

  # Scaffold files created
  [ -f "${existing}/kb.yaml" ]
  [ -f "${existing}/opencode.json" ]
  [ -f "${existing}/.opencode/agents/kb.md" ]

  # Original content preserved
  run cat "${existing}/docs/notes.md"
  assert_output "# Existing notes"
  run cat "${existing}/data.json"
  assert_output "Some data"
}

# ===== Query pipeline with mocked opencode =====

@test "kb integration: query.sh parses NDJSON and returns text" {
  source "${TEST_ADJ_DIR}/scripts/capabilities/kb/manage.sh"

  # Create a KB
  local kb_dir="${TEST_ADJ_DIR}/query-kb"
  kb_create "query-test" "${kb_dir}" "Query test KB"

  # Create mock opencode that returns NDJSON
  create_mock_opencode '{"type":"session.create","sessionID":"kb-session-001"}
{"type":"text","part":{"text":"The answer is 42."}}
{"type":"text.done"}'

  # Run query
  run bash "${TEST_ADJ_DIR}/scripts/capabilities/kb/query.sh" "query-test" "What is the answer?"
  assert_success
  assert_output "The answer is 42."
}

@test "kb integration: query.sh handles multi-part text responses" {
  source "${TEST_ADJ_DIR}/scripts/capabilities/kb/manage.sh"

  local kb_dir="${TEST_ADJ_DIR}/multi-kb"
  kb_create "multi-test" "${kb_dir}" "Multi-part test"

  create_mock_opencode '{"type":"text","part":{"text":"Part one. "}}
{"type":"text","part":{"text":"Part two."}}
{"type":"text.done"}'

  run bash "${TEST_ADJ_DIR}/scripts/capabilities/kb/query.sh" "multi-test" "Tell me everything"
  assert_success
  assert_output "Part one. Part two."
}

@test "kb integration: query.sh returns fallback for empty response" {
  source "${TEST_ADJ_DIR}/scripts/capabilities/kb/manage.sh"

  local kb_dir="${TEST_ADJ_DIR}/empty-reply-kb"
  kb_create "empty-reply" "${kb_dir}" "Empty reply test"

  create_mock_opencode '{"type":"session.create","sessionID":"kb-session-002"}
{"type":"text.done"}'

  run bash "${TEST_ADJ_DIR}/scripts/capabilities/kb/query.sh" "empty-reply" "What?"
  assert_success
  assert_output --partial "did not return an answer"
}

@test "kb integration: query.sh fails for non-existent KB" {
  run bash "${TEST_ADJ_DIR}/scripts/capabilities/kb/query.sh" "ghost-kb" "Hello?"
  assert_failure
  assert_output --partial "not found"
}

@test "kb integration: query.sh passes correct model to opencode" {
  source "${TEST_ADJ_DIR}/scripts/capabilities/kb/manage.sh"

  local kb_dir="${TEST_ADJ_DIR}/model-kb"
  kb_create "model-test" "${kb_dir}" "Model test" "anthropic/claude-haiku-4-5" "read-only"

  create_mock_opencode '{"type":"text","part":{"text":"ok"}}'

  bash "${TEST_ADJ_DIR}/scripts/capabilities/kb/query.sh" "model-test" "test" >/dev/null 2>&1

  assert_mock_called "opencode"
  assert_mock_args_contain "opencode" "--model anthropic/claude-haiku-4-5"
}

@test "kb integration: query.sh uses inherited model from telegram state" {
  source "${TEST_ADJ_DIR}/scripts/capabilities/kb/manage.sh"

  local kb_dir="${TEST_ADJ_DIR}/inherit-kb"
  kb_create "inherit-test" "${kb_dir}" "Inherit test" "inherit" "read-only"

  # Seed a model file
  echo -n "anthropic/claude-sonnet-4-5" > "${TEST_ADJ_DIR}/state/telegram_model.txt"

  create_mock_opencode '{"type":"text","part":{"text":"ok"}}'

  bash "${TEST_ADJ_DIR}/scripts/capabilities/kb/query.sh" "inherit-test" "test" >/dev/null 2>&1

  assert_mock_called "opencode"
  assert_mock_args_contain "opencode" "--model anthropic/claude-sonnet-4-5"
}

@test "kb integration: query.sh passes --dir flag to opencode" {
  source "${TEST_ADJ_DIR}/scripts/capabilities/kb/manage.sh"

  local kb_dir="${TEST_ADJ_DIR}/dir-kb"
  kb_create "dir-test" "${kb_dir}" "Dir flag test"

  create_mock_opencode '{"type":"text","part":{"text":"ok"}}'

  bash "${TEST_ADJ_DIR}/scripts/capabilities/kb/query.sh" "dir-test" "test" >/dev/null 2>&1

  assert_mock_called "opencode"
  assert_mock_args_contain "opencode" "--dir ${kb_dir}"
}

@test "kb integration: query.sh passes --agent kb flag to opencode" {
  source "${TEST_ADJ_DIR}/scripts/capabilities/kb/manage.sh"

  local kb_dir="${TEST_ADJ_DIR}/agent-kb"
  kb_create "agent-test" "${kb_dir}" "Agent flag test"

  create_mock_opencode '{"type":"text","part":{"text":"ok"}}'

  bash "${TEST_ADJ_DIR}/scripts/capabilities/kb/query.sh" "agent-test" "test" >/dev/null 2>&1

  assert_mock_called "opencode"
  assert_mock_args_contain "opencode" "--agent kb"
}

# ===== /kb Telegram command =====

@test "kb integration: cmd_kb list shows registered KBs" {
  export TELEGRAM_BOT_TOKEN="test-token-123"
  export TELEGRAM_CHAT_ID="99999"

  create_mock_curl_telegram_ok

  source "${PROJECT_ROOT}/scripts/common/logging.sh"
  source "${PROJECT_ROOT}/scripts/messaging/telegram/send.sh"
  source "${TEST_ADJ_DIR}/scripts/capabilities/kb/manage.sh"

  kb_register "tg-test" "/tmp/tg-test" "Telegram test KB"

  source "${PROJECT_ROOT}/scripts/messaging/telegram/commands.sh"
  cmd_kb "list" "100"

  assert_mock_called "curl"
  local log_content
  log_content="$(cat "${MOCK_LOG}/curl.log")"
  [[ "${log_content}" == *"tg-test"* ]]
  [[ "${log_content}" == *"Telegram test KB"* ]]
}

@test "kb integration: cmd_kb with no args defaults to list" {
  export TELEGRAM_BOT_TOKEN="test-token-123"
  export TELEGRAM_CHAT_ID="99999"

  create_mock_curl_telegram_ok

  source "${PROJECT_ROOT}/scripts/common/logging.sh"
  source "${PROJECT_ROOT}/scripts/messaging/telegram/send.sh"
  source "${TEST_ADJ_DIR}/scripts/capabilities/kb/manage.sh"

  source "${PROJECT_ROOT}/scripts/messaging/telegram/commands.sh"
  cmd_kb "" "100"

  assert_mock_called "curl"
  local log_content
  log_content="$(cat "${MOCK_LOG}/curl.log")"
  [[ "${log_content}" == *"No knowledge bases registered"* ]]
}

# ===== CLI routing (adjutant kb) =====

@test "kb integration: adjutant kb help shows usage" {
  run bash "${PROJECT_ROOT}/adjutant" kb help
  assert_success
  assert_output --partial "Knowledge Base Management"
  assert_output --partial "create"
  assert_output --partial "list"
  assert_output --partial "remove"
  assert_output --partial "query"
}

@test "kb integration: adjutant kb list shows empty state" {
  run bash "${PROJECT_ROOT}/adjutant" kb list
  assert_success
  assert_output --partial "No knowledge bases registered"
}

# ===== Quick create via wizard =====

@test "kb integration: quick create scaffolds and registers" {
  local kb_dir="${TEST_ADJ_DIR}/quick-kb"

  run bash "${TEST_ADJ_DIR}/scripts/setup/steps/kb_wizard.sh" \
    --quick --name "quick-test" --path "${kb_dir}" --desc "Quick create test"
  assert_success
  assert_output --partial "OK"

  # Verify scaffold
  [ -d "${kb_dir}" ]
  [ -f "${kb_dir}/kb.yaml" ]
  [ -f "${kb_dir}/opencode.json" ]
  [ -f "${kb_dir}/.opencode/agents/kb.md" ]

  # Verify registry
  source "${TEST_ADJ_DIR}/scripts/capabilities/kb/manage.sh"
  run kb_exists "quick-test"
  assert_success
}

@test "kb integration: quick create fails without required args" {
  run bash "${TEST_ADJ_DIR}/scripts/setup/steps/kb_wizard.sh" --quick
  assert_failure
  assert_output --partial "Usage"
}

@test "kb integration: quick create with custom model and access" {
  local kb_dir="${TEST_ADJ_DIR}/custom-kb"

  run bash "${TEST_ADJ_DIR}/scripts/setup/steps/kb_wizard.sh" \
    --quick --name "custom" --path "${kb_dir}" --desc "Custom" \
    --model "anthropic/claude-haiku-4-5" --access "read-write"
  assert_success

  source "${TEST_ADJ_DIR}/scripts/capabilities/kb/manage.sh"
  run kb_get_field "custom" "model"
  assert_output "anthropic/claude-haiku-4-5"
  run kb_get_field "custom" "access"
  assert_output "read-write"
}
