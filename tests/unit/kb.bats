#!/usr/bin/env bats
# tests/unit/kb.bats — Unit tests for scripts/capabilities/kb/manage.sh
#
# Tests KB CRUD operations: scaffold generation, registry read/write,
# content auto-detection, name validation, and template rendering.

load "${BATS_TEST_DIRNAME}/../test_helper/setup.bash"

setup() {
  setup_test_env
  source "${COMMON}/paths.sh"

  # Create the knowledge_bases directory and registry
  mkdir -p "${TEST_ADJ_DIR}/knowledge_bases"
  cat > "${TEST_ADJ_DIR}/knowledge_bases/registry.yaml" <<'YAML'
knowledge_bases: []
YAML

  # Copy templates
  cp -R "${PROJECT_ROOT}/templates" "${TEST_ADJ_DIR}/templates"

  # Source the library under test
  source "${TEST_ADJ_DIR}/scripts/capabilities/kb/manage.sh"
}

teardown() { teardown_test_env; }

# ===== kb_count =====

@test "kb: kb_count returns 0 for empty registry" {
  run kb_count
  assert_success
  assert_output "0"
}

@test "kb: kb_count returns correct count after registering KBs" {
  kb_register "test-kb" "/tmp/test-kb" "A test KB"
  run kb_count
  assert_success
  assert_output "1"
}

@test "kb: kb_count returns 0 when registry file missing" {
  rm -f "${TEST_ADJ_DIR}/knowledge_bases/registry.yaml"
  run kb_count
  assert_success
  assert_output "0"
}

# ===== kb_exists =====

@test "kb: kb_exists returns false for non-existent KB" {
  run kb_exists "nonexistent"
  assert_failure
}

@test "kb: kb_exists returns true for registered KB" {
  kb_register "my-kb" "/tmp/my-kb" "Test KB"
  run kb_exists "my-kb"
  assert_success
}

# ===== kb_register =====

@test "kb: kb_register adds entry to empty registry" {
  run kb_register "test-kb" "/tmp/test-kb" "Test knowledge base" "inherit" "read-only"
  assert_success
  run kb_exists "test-kb"
  assert_success
}

@test "kb: kb_register appends to non-empty registry" {
  kb_register "first-kb" "/tmp/first" "First KB"
  run kb_register "second-kb" "/tmp/second" "Second KB"
  assert_success
  run kb_count
  assert_output "2"
}

@test "kb: kb_register fails on duplicate name" {
  kb_register "dup-kb" "/tmp/dup" "First"
  run kb_register "dup-kb" "/tmp/dup2" "Second"
  assert_failure
  assert_output --partial "already registered"
}

@test "kb: kb_register writes all fields correctly" {
  kb_register "full-kb" "/tmp/full-kb" "Full description" "anthropic/claude-haiku-4-5" "read-write" "2026-02-27"
  run kb_get_field "full-kb" "path"
  assert_output "/tmp/full-kb"
  run kb_get_field "full-kb" "description"
  assert_output "Full description"
  run kb_get_field "full-kb" "model"
  assert_output "anthropic/claude-haiku-4-5"
  run kb_get_field "full-kb" "access"
  assert_output "read-write"
  run kb_get_field "full-kb" "created"
  assert_output "2026-02-27"
}

# ===== kb_unregister =====

@test "kb: kb_unregister removes entry from registry" {
  kb_register "to-remove" "/tmp/to-remove" "Will be removed"
  run kb_unregister "to-remove"
  assert_success
  run kb_exists "to-remove"
  assert_failure
}

@test "kb: kb_unregister fails for non-existent KB" {
  run kb_unregister "ghost"
  assert_failure
  assert_output --partial "not found"
}

@test "kb: kb_unregister preserves other entries" {
  kb_register "keep-me" "/tmp/keep" "Should stay"
  kb_register "remove-me" "/tmp/remove" "Should go"
  kb_unregister "remove-me"
  run kb_exists "keep-me"
  assert_success
  run kb_exists "remove-me"
  assert_failure
}

@test "kb: kb_unregister restores empty list when last entry removed" {
  kb_register "only-one" "/tmp/only" "The only one"
  kb_unregister "only-one"
  run kb_count
  assert_output "0"
}

# ===== kb_list =====

@test "kb: kb_list outputs nothing for empty registry" {
  run kb_list
  assert_success
  assert_output ""
}

@test "kb: kb_list outputs tab-separated fields" {
  kb_register "list-test" "/tmp/list-test" "For listing" "inherit" "read-only"
  run kb_list
  assert_success
  assert_output --partial "list-test"
  assert_output --partial "For listing"
  assert_output --partial "read-only"
}

@test "kb: kb_list outputs multiple entries" {
  kb_register "kb-a" "/tmp/a" "Alpha"
  kb_register "kb-b" "/tmp/b" "Beta"
  local lines
  lines="$(kb_list | wc -l | tr -d ' ')"
  [ "${lines}" -eq 2 ]
}

# ===== kb_info =====

@test "kb: kb_info returns key=value pairs" {
  kb_register "info-test" "/tmp/info" "Info test" "inherit" "read-only" "2026-02-27"
  run kb_info "info-test"
  assert_success
  assert_output --partial "name=info-test"
  assert_output --partial "path=/tmp/info"
  assert_output --partial "description=Info test"
}

@test "kb: kb_info fails for non-existent KB" {
  run kb_info "nope"
  assert_failure
  assert_output --partial "not found"
}

# ===== kb_get_field =====

@test "kb: kb_get_field returns correct field value" {
  kb_register "field-test" "/tmp/field" "Field test" "anthropic/claude-haiku-4-5"
  run kb_get_field "field-test" "model"
  assert_success
  assert_output "anthropic/claude-haiku-4-5"
}

# ===== kb_get_operation_script =====

@test "kb: kb_get_operation_script resolves conventional script path" {
  local kb_dir="${TEST_ADJ_DIR}/ops-kb"
  kb_scaffold "ops-test" "${kb_dir}" "Ops test" "inherit" "read-write"
  mkdir -p "${kb_dir}/scripts"
  printf '#!/bin/bash\necho OK:fetch\n' > "${kb_dir}/scripts/fetch.sh"
  chmod +x "${kb_dir}/scripts/fetch.sh"
  kb_register "ops-test" "${kb_dir}" "Ops test" "inherit" "read-write"

  run kb_get_operation_script "ops-test" "fetch"
  assert_success
  assert_output "${kb_dir}/scripts/fetch.sh"
}

@test "kb: kb_get_operation_script fails when operation script is missing" {
  local kb_dir="${TEST_ADJ_DIR}/missing-op-kb"
  kb_create "missing-op" "${kb_dir}" "Missing op test"

  run kb_get_operation_script "missing-op" "fetch"
  assert_failure
  assert_output --partial "does not implement operation 'fetch'"
}

# ===== kb_scaffold =====

@test "kb: kb_scaffold creates directory structure" {
  local kb_dir="${TEST_ADJ_DIR}/test-scaffold-kb"
  kb_scaffold "scaffold-test" "${kb_dir}" "Test scaffold" "inherit" "read-only"

  [ -d "${kb_dir}" ]
  [ -d "${kb_dir}/.opencode/agents" ]
  [ -d "${kb_dir}/docs" ]
  [ -d "${kb_dir}/docs/reference" ]
  [ -d "${kb_dir}/state" ]
  [ -f "${kb_dir}/kb.yaml" ]
  [ -f "${kb_dir}/opencode.json" ]
  [ -f "${kb_dir}/.opencode/agents/kb.md" ]
  [ -f "${kb_dir}/docs/README.md" ]
}

@test "kb: kb_scaffold renders kb.yaml with correct name" {
  local kb_dir="${TEST_ADJ_DIR}/rendered-kb"
  kb_scaffold "rendered" "${kb_dir}" "Rendered test" "inherit" "read-only"
  run cat "${kb_dir}/kb.yaml"
  assert_output --partial 'name: "rendered"'
  assert_output --partial 'description: "Rendered test"'
}

@test "kb: kb_scaffold renders agent definition with KB name" {
  local kb_dir="${TEST_ADJ_DIR}/agent-kb"
  kb_scaffold "agent-test" "${kb_dir}" "Agent test KB" "inherit" "read-only"
  run cat "${kb_dir}/.opencode/agents/kb.md"
  assert_output --partial "agent-test"
  assert_output --partial "Agent test KB"
}

@test "kb: kb_scaffold sets write=false for read-only KB" {
  local kb_dir="${TEST_ADJ_DIR}/ro-kb"
  kb_scaffold "ro-test" "${kb_dir}" "Read only" "inherit" "read-only"
  run cat "${kb_dir}/.opencode/agents/kb.md"
  assert_output --partial "write: false"
  assert_output --partial "edit: false"
}

@test "kb: kb_scaffold sets write=true for read-write KB" {
  local kb_dir="${TEST_ADJ_DIR}/rw-kb"
  kb_scaffold "rw-test" "${kb_dir}" "Read write" "inherit" "read-write"
  run cat "${kb_dir}/.opencode/agents/kb.md"
  assert_output --partial "write: true"
  assert_output --partial "edit: true"
}

@test "kb: kb_scaffold does not overwrite existing docs" {
  local kb_dir="${TEST_ADJ_DIR}/existing-docs-kb"
  mkdir -p "${kb_dir}/docs"
  echo "Existing content" > "${kb_dir}/docs/my-notes.md"
  kb_scaffold "existing" "${kb_dir}" "Existing dir" "inherit" "read-only"
  # Should NOT create README.md because docs/ has content
  [ -f "${kb_dir}/docs/my-notes.md" ]
  run cat "${kb_dir}/docs/my-notes.md"
  assert_output "Existing content"
}

# ===== kb_create (combined scaffold + register) =====

@test "kb: kb_create scaffolds and registers in one call" {
  local kb_dir="${TEST_ADJ_DIR}/create-test"
  run kb_create "create-test" "${kb_dir}" "Create test" "inherit" "read-only"
  assert_success
  [ -d "${kb_dir}" ]
  [ -f "${kb_dir}/kb.yaml" ]
  run kb_exists "create-test"
  assert_success
}

@test "kb: kb_create rejects invalid name with uppercase" {
  run kb_create "BadName" "/tmp/bad" "Bad"
  assert_failure
  assert_output --partial "lowercase"
}

@test "kb: kb_create rejects invalid name with spaces" {
  run kb_create "bad name" "/tmp/bad" "Bad"
  assert_failure
  assert_output --partial "lowercase"
}

@test "kb: kb_create rejects relative path" {
  run kb_create "rel-kb" "relative/path" "Relative"
  assert_failure
  assert_output --partial "absolute"
}

@test "kb: kb_create rejects duplicate name" {
  local kb_dir="${TEST_ADJ_DIR}/dup-create"
  kb_create "dup-create" "${kb_dir}" "First"
  run kb_create "dup-create" "${kb_dir}2" "Second"
  assert_failure
  assert_output --partial "already registered"
}

@test "kb: kb_create accepts single-character name" {
  local kb_dir="${TEST_ADJ_DIR}/a-kb"
  run kb_create "a" "${kb_dir}" "Single char"
  assert_success
}

# ===== kb_remove =====

@test "kb: kb_remove unregisters but does not delete files" {
  local kb_dir="${TEST_ADJ_DIR}/remove-files-test"
  kb_create "remove-files" "${kb_dir}" "File preservation test"
  run kb_remove "remove-files"
  assert_success
  # Files should still exist
  [ -d "${kb_dir}" ]
  [ -f "${kb_dir}/kb.yaml" ]
  # But not in registry
  run kb_exists "remove-files"
  assert_failure
}

# ===== kb_detect_content =====

@test "kb: kb_detect_content finds markdown files" {
  local dir="${TEST_ADJ_DIR}/detect-md"
  mkdir -p "${dir}"
  touch "${dir}/notes.md"
  run kb_detect_content "${dir}"
  assert_success
  assert_output --partial "markdown"
}

@test "kb: kb_detect_content finds code files" {
  local dir="${TEST_ADJ_DIR}/detect-code"
  mkdir -p "${dir}"
  touch "${dir}/main.py"
  run kb_detect_content "${dir}"
  assert_success
  assert_output --partial "code"
}

@test "kb: kb_detect_content finds data files" {
  local dir="${TEST_ADJ_DIR}/detect-data"
  mkdir -p "${dir}"
  touch "${dir}/config.json"
  run kb_detect_content "${dir}"
  assert_success
  assert_output --partial "data"
}

@test "kb: kb_detect_content returns empty for empty dir" {
  local dir="${TEST_ADJ_DIR}/detect-empty"
  mkdir -p "${dir}"
  run kb_detect_content "${dir}"
  assert_success
  assert_output "empty"
}

@test "kb: kb_detect_content returns multiple types" {
  local dir="${TEST_ADJ_DIR}/detect-multi"
  mkdir -p "${dir}"
  touch "${dir}/readme.md" "${dir}/app.py" "${dir}/data.json"
  run kb_detect_content "${dir}"
  assert_success
  assert_output --partial "markdown"
  assert_output --partial "code"
  assert_output --partial "data"
}

@test "kb: kb_detect_content fails for non-existent dir" {
  run kb_detect_content "/tmp/nonexistent-kb-detect-test"
  assert_failure
}
