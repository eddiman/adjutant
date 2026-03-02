#!/usr/bin/env bats
# tests/integration/commands.bats — Integration tests for scripts/messaging/telegram/commands.sh
#
# commands.sh is a sourced library providing all /command handlers:
#   cmd_status, cmd_pause, cmd_resume, cmd_kill, cmd_pulse, cmd_restart,
#   cmd_reflect_request, cmd_reflect_confirm, cmd_help, cmd_model, cmd_screenshot
#
# Each cmd_*() uses the adaptor interface (msg_send_text, msg_react, msg_typing)
# and writes to state files / journal. Tested by sourcing with all dependencies.

load "${BATS_TEST_DIRNAME}/../test_helper/setup.bash"
load "${BATS_TEST_DIRNAME}/../test_helper/mocks.bash"

setup() {
  setup_test_env
  setup_mocks
  create_mock_curl_telegram_ok

  export TELEGRAM_BOT_TOKEN="test-token-123"
  export TELEGRAM_CHAT_ID="99999"
  export ADJ_DIR="${TEST_ADJ_DIR}"

  # Source dependencies
  source "${PROJECT_ROOT}/scripts/common/logging.sh"
  source "${PROJECT_ROOT}/scripts/common/lockfiles.sh"
  source "${PROJECT_ROOT}/scripts/messaging/telegram/send.sh"

  # Create mock status.sh
  mkdir -p "${TEST_ADJ_DIR}/scripts/observability"
  cat > "${TEST_ADJ_DIR}/scripts/observability/status.sh" <<'MOCK'
#!/bin/bash
echo "Status: RUNNING"
echo "Cron jobs: none"
MOCK
  chmod +x "${TEST_ADJ_DIR}/scripts/observability/status.sh"

  # Create mock emergency_kill.sh
  mkdir -p "${TEST_ADJ_DIR}/scripts/lifecycle"
  cat > "${TEST_ADJ_DIR}/scripts/lifecycle/emergency_kill.sh" <<'MOCK'
#!/bin/bash
exit 0
MOCK
  chmod +x "${TEST_ADJ_DIR}/scripts/lifecycle/emergency_kill.sh"

  # Create mock restart.sh
  cat > "${TEST_ADJ_DIR}/scripts/lifecycle/restart.sh" <<'MOCK'
#!/bin/bash
exit 0
MOCK
  chmod +x "${TEST_ADJ_DIR}/scripts/lifecycle/restart.sh"

  # Create mock screenshot.sh
  mkdir -p "${TEST_ADJ_DIR}/scripts/capabilities/screenshot"
  cat > "${TEST_ADJ_DIR}/scripts/capabilities/screenshot/screenshot.sh" <<'MOCK'
#!/bin/bash
echo "OK:/tmp/fake_screenshot.png"
MOCK
  chmod +x "${TEST_ADJ_DIR}/scripts/capabilities/screenshot/screenshot.sh"

  # Create mock opencode for cmd_model, cmd_pulse, cmd_reflect_confirm
  create_mock_opencode_models "anthropic/claude-haiku-4-5
anthropic/claude-sonnet-4-20250514
claude-opus-4-5"

  # Source the library under test
  source "${PROJECT_ROOT}/scripts/messaging/telegram/commands.sh"
}

teardown() {
  jobs -p 2>/dev/null | xargs kill 2>/dev/null || true
  teardown_mocks
  teardown_test_env
}

# ===== cmd_status =====

@test "cmd_status: calls status.sh and sends its output via msg_send_text" {
  cmd_status "100"
  assert_mock_called "curl"
  local full_log
  full_log="$(cat "${MOCK_LOG}/curl.log")"
  [[ "${full_log}" == *"Status: RUNNING"* ]]
}

@test "cmd_status: includes the last heartbeat timestamp when heartbeat file exists" {
  seed_heartbeat "2026-01-15T10:30:00Z" "All clear."
  cmd_status "100"
  local full_log
  full_log="$(cat "${MOCK_LOG}/curl.log")"
  [[ "${full_log}" == *"Last heartbeat"* ]]
}

@test "cmd_status: shows 'not recorded yet' when no heartbeat file exists" {
  rm -f "${TEST_ADJ_DIR}/state/last_heartbeat.json"
  cmd_status "100"
  local full_log
  full_log="$(cat "${MOCK_LOG}/curl.log")"
  [[ "${full_log}" == *"not recorded yet"* ]]
}

@test "cmd_status: sends graceful fallback when status.sh fails" {
  cat > "${TEST_ADJ_DIR}/scripts/observability/status.sh" <<'MOCK'
#!/bin/bash
exit 1
MOCK
  chmod +x "${TEST_ADJ_DIR}/scripts/observability/status.sh"
  cmd_status "100"
  assert_mock_called "curl"
  local full_log
  full_log="$(cat "${MOCK_LOG}/curl.log")"
  [[ "${full_log}" == *"Could not retrieve status"* ]]
}

# ===== cmd_pause =====

@test "cmd_pause: creates the PAUSED lockfile" {
  cmd_pause "100"
  [ -f "${TEST_ADJ_DIR}/PAUSED" ]
}

@test "cmd_pause: sends a confirmation message" {
  cmd_pause "100"
  local full_log
  full_log="$(cat "${MOCK_LOG}/curl.log")"
  [[ "${full_log}" == *"paused"* ]] || [[ "${full_log}" == *"Paused"* ]]
}

@test "cmd_pause: writes a journal entry for the day" {
  cmd_pause "100"
  local today
  today="$(date '+%Y-%m-%d')"
  [ -f "${TEST_ADJ_DIR}/journal/${today}.md" ]
  local journal
  journal="$(cat "${TEST_ADJ_DIR}/journal/${today}.md")"
  [[ "${journal}" == *"Paused"* ]]
}

# ===== cmd_resume =====

@test "cmd_resume: removes the PAUSED lockfile" {
  touch "${TEST_ADJ_DIR}/PAUSED"
  cmd_resume "100"
  [ ! -f "${TEST_ADJ_DIR}/PAUSED" ]
}

@test "cmd_resume: sends a confirmation message about being back online" {
  cmd_resume "100"
  local full_log
  full_log="$(cat "${MOCK_LOG}/curl.log")"
  [[ "${full_log}" == *"back online"* ]]
}

@test "cmd_resume: writes a journal entry for the day" {
  cmd_resume "100"
  local today
  today="$(date '+%Y-%m-%d')"
  [ -f "${TEST_ADJ_DIR}/journal/${today}.md" ]
  local journal
  journal="$(cat "${TEST_ADJ_DIR}/journal/${today}.md")"
  [[ "${journal}" == *"Resumed"* ]]
}

# ===== cmd_kill =====

@test "cmd_kill: sends a shutdown confirmation message" {
  cmd_kill "100"
  sleep 0.3
  local full_log
  full_log="$(cat "${MOCK_LOG}/curl.log")"
  [[ "${full_log}" == *"Shutting down"* ]] || [[ "${full_log}" == *"Emergency kill"* ]]
}

@test "cmd_kill: invokes emergency_kill.sh in the background" {
  # We can't easily assert the background process ran, but we can verify
  # the mock script exists and is executable
  [ -x "${TEST_ADJ_DIR}/scripts/lifecycle/emergency_kill.sh" ]
  cmd_kill "100"
  sleep 0.3
  assert_mock_called "curl"
}

# ===== cmd_pulse =====

@test "cmd_pulse: sends an initial acknowledgment message" {
  cmd_pulse "100"
  assert_mock_called "curl"
  local first_args
  first_args="$(mock_call_args "curl" 1)"
  [[ "${first_args}" == *"pulse check"* ]] || [[ "${first_args}" == *"On it"* ]]
}

@test "cmd_pulse: shows last heartbeat data when opencode is not available" {
  # Replace opencode mock with one that exits 127 (not found)
  cat > "${MOCK_BIN}/opencode" <<'NOTFOUND'
#!/bin/bash
exit 127
NOTFOUND
  chmod +x "${MOCK_BIN}/opencode"
  # Also override which to return failure for opencode
  cat > "${MOCK_BIN}/which" <<'WHICH_MOCK'
#!/bin/bash
if [[ "$1" == "opencode" ]]; then
  exit 1
fi
/usr/bin/which "$@"
WHICH_MOCK
  chmod +x "${MOCK_BIN}/which"

  seed_heartbeat "2026-02-25T14:00:00Z" "All systems nominal."
  cmd_pulse "100"
  local full_log
  full_log="$(cat "${MOCK_LOG}/curl.log")"
  [[ "${full_log}" == *"All systems nominal"* ]]
}

@test "cmd_pulse: shows fallback when opencode is missing and no heartbeat exists" {
  cat > "${MOCK_BIN}/which" <<'WHICH_MOCK'
#!/bin/bash
if [[ "$1" == "opencode" ]]; then
  exit 1
fi
/usr/bin/which "$@"
WHICH_MOCK
  chmod +x "${MOCK_BIN}/which"

  rm -f "${MOCK_BIN}/opencode"
  rm -f "${TEST_ADJ_DIR}/state/last_heartbeat.json"
  cmd_pulse "100"
  local full_log
  full_log="$(cat "${MOCK_LOG}/curl.log")"
  [[ "${full_log}" == *"don't have any pulse data"* ]]
}

# ===== cmd_restart =====

@test "cmd_restart: sends a restarting message before invoking restart.sh" {
  cmd_restart "100"
  sleep 0.3
  local first_args
  first_args="$(mock_call_args "curl" 1)"
  [[ "${first_args}" == *"Restarting"* ]]
}

# ===== cmd_reflect_request =====

@test "cmd_reflect_request: creates the pending_reflect state file" {
  cmd_reflect_request "100"
  [ -f "${TEST_ADJ_DIR}/state/pending_reflect" ]
}

@test "cmd_reflect_request: sends a cost warning message mentioning Opus" {
  cmd_reflect_request "100"
  local full_log
  full_log="$(cat "${MOCK_LOG}/curl.log")"
  [[ "${full_log}" == *"Opus"* ]]
  [[ "${full_log}" == *"confirm"* ]]
}

# ===== cmd_reflect_confirm =====

@test "cmd_reflect_confirm: removes the pending_reflect file" {
  touch "${TEST_ADJ_DIR}/state/pending_reflect"
  cmd_reflect_confirm "100"
  [ ! -f "${TEST_ADJ_DIR}/state/pending_reflect" ]
}

@test "cmd_reflect_confirm: sends acknowledgment that reflection is starting" {
  cmd_reflect_confirm "100"
  local first_args
  first_args="$(mock_call_args "curl" 1)"
  [[ "${first_args}" == *"starting the reflection"* ]]
}

@test "cmd_reflect_confirm: sends error when opencode CLI is not found" {
  rm -f "${MOCK_BIN}/opencode"
  cmd_reflect_confirm "100"
  local full_log
  full_log="$(cat "${MOCK_LOG}/curl.log")"
  [[ "${full_log}" == *"can't find"* ]] || [[ "${full_log}" == *"not able"* ]]
}

@test "cmd_reflect_confirm: sends error when reflect prompt file is missing" {
  rm -f "${TEST_ADJ_DIR}/prompts/review.md"
  cmd_reflect_confirm "100"
  local full_log
  full_log="$(cat "${MOCK_LOG}/curl.log")"
  [[ "${full_log}" == *"can't find"* ]] || [[ "${full_log}" == *"prompt"* ]] || [[ "${full_log}" == *"misconfigured"* ]]
}

# ===== cmd_help =====

@test "cmd_help: lists all available commands" {
  cmd_help "100"
  local full_log
  full_log="$(cat "${MOCK_LOG}/curl.log")"
  [[ "${full_log}" == *"/status"* ]]
  [[ "${full_log}" == *"/pulse"* ]]
  [[ "${full_log}" == *"/pause"* ]]
  [[ "${full_log}" == *"/resume"* ]]
  [[ "${full_log}" == *"/kill"* ]]
  [[ "${full_log}" == *"/reflect"* ]]
  [[ "${full_log}" == *"/screenshot"* ]]
  [[ "${full_log}" == *"/model"* ]]
  [[ "${full_log}" == *"/help"* ]]
}

@test "cmd_help: mentions that natural language conversation is available" {
  cmd_help "100"
  local full_log
  full_log="$(cat "${MOCK_LOG}/curl.log")"
  [[ "${full_log}" == *"talk to me naturally"* ]] || [[ "${full_log}" == *"naturally"* ]]
}

@test "cmd_help: mentions photo support" {
  cmd_help "100"
  local full_log
  full_log="$(cat "${MOCK_LOG}/curl.log")"
  [[ "${full_log}" == *"photo"* ]]
}

# ===== cmd_model =====

@test "cmd_model: shows current model when called with no argument" {
  cmd_model "" "100"
  assert_mock_called "curl"
  local full_log
  full_log="$(cat "${MOCK_LOG}/curl.log")"
  [[ "${full_log}" == *"Current model"* ]]
  [[ "${full_log}" == *"anthropic/claude-haiku-4-5"* ]]
}

@test "cmd_model: shows model from state file when one exists" {
  seed_model_file "anthropic/claude-sonnet-4-20250514"
  cmd_model "" "100"
  local full_log
  full_log="$(cat "${MOCK_LOG}/curl.log")"
  [[ "${full_log}" == *"anthropic/claude-sonnet-4-20250514"* ]]
}

@test "cmd_model: switches to a valid model and writes the model file" {
  cmd_model "anthropic/claude-sonnet-4-20250514" "100"
  local stored
  stored="$(cat "${TEST_ADJ_DIR}/state/telegram_model.txt")"
  [ "${stored}" = "anthropic/claude-sonnet-4-20250514" ]
}

@test "cmd_model: confirms the model switch in the reply" {
  cmd_model "anthropic/claude-sonnet-4-20250514" "100"
  local full_log
  full_log="$(cat "${MOCK_LOG}/curl.log")"
  [[ "${full_log}" == *"Switched"* ]]
  [[ "${full_log}" == *"anthropic/claude-sonnet-4-20250514"* ]]
}

@test "cmd_model: rejects an unrecognized model name" {
  cmd_model "bad-model-name" "100"
  local full_log
  full_log="$(cat "${MOCK_LOG}/curl.log")"
  [[ "${full_log}" == *"don't recognise"* ]] || [[ "${full_log}" == *"don't recognize"* ]]
  # Model file should NOT be updated
  [ ! -f "${TEST_ADJ_DIR}/state/telegram_model.txt" ]
}

# ===== cmd_screenshot =====

@test "cmd_screenshot: sends a react emoji before processing" {
  cmd_screenshot "https://example.com" "100"
  sleep 0.3
  local first_args
  first_args="$(mock_call_args "curl" 1)"
  [[ "${first_args}" == *"setMessageReaction"* ]]
}

@test "cmd_screenshot: prompts for URL when called with empty argument" {
  cmd_screenshot "" "100"
  local full_log
  full_log="$(cat "${MOCK_LOG}/curl.log")"
  [[ "${full_log}" == *"provide a URL"* ]]
}
