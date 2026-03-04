#!/usr/bin/env bats
# tests/integration/usage_estimate.bats — Integration tests for scripts/observability/usage_estimate.sh
#
# usage_estimate.sh is a standalone script that:
#   - Logs token usage to state/usage_log.jsonl
#   - Calculates session (5h rolling) and weekly (7d rolling) usage
#   - Uses bc for float math and ANSI color codes
#   - Exits 1 with usage help when input_tokens is 0

load "${BATS_TEST_DIRNAME}/../test_helper/setup.bash"
load "${BATS_TEST_DIRNAME}/../test_helper/mocks.bash"

USAGE_SCRIPT="${PROJECT_ROOT}/scripts/observability/usage_estimate.sh"

setup_file()    { setup_file_scripts_template; }
teardown_file() { teardown_file_scripts_template; }

setup() {
  setup_test_env
  setup_mocks
  # usage_estimate.sh needs bc available (real bc, not mocked)
  # but we need to make sure our mock PATH doesn't shadow it
  # bc is a standard utility — ensure it's available
  touch "${TEST_ADJ_DIR}/state/usage_log.jsonl"
}

teardown() {
  teardown_mocks
  teardown_test_env
}

# --- Input validation ---

@test "usage_estimate: prints usage help and exits 1 when input_tokens is 0 (default)" {
  run bash "${USAGE_SCRIPT}" "pulse" 0 0
  assert_failure
  assert_output --partial "Usage:"
  assert_output --partial "Common estimates"
}

@test "usage_estimate: prints usage help when called with no arguments" {
  run bash "${USAGE_SCRIPT}"
  assert_failure
  assert_output --partial "Usage:"
}

# --- Logging ---

@test "usage_estimate: appends a JSONL line to state/usage_log.jsonl" {
  run bash "${USAGE_SCRIPT}" "pulse" 3000 500
  assert_success
  [ -f "${TEST_ADJ_DIR}/state/usage_log.jsonl" ]
  local line_count
  line_count="$(wc -l < "${TEST_ADJ_DIR}/state/usage_log.jsonl" | tr -d ' ')"
  [ "${line_count}" -ge 1 ]
}

@test "usage_estimate: logged entry contains the operation name" {
  run bash "${USAGE_SCRIPT}" "pulse_check" 3000 500
  assert_success
  grep -q '"operation":"pulse_check"' "${TEST_ADJ_DIR}/state/usage_log.jsonl"
}

@test "usage_estimate: logged entry contains the correct total token count" {
  run bash "${USAGE_SCRIPT}" "test_op" 3000 500
  assert_success
  grep -q '"total":3500' "${TEST_ADJ_DIR}/state/usage_log.jsonl"
}

@test "usage_estimate: logged entry contains input and output token counts" {
  run bash "${USAGE_SCRIPT}" "test_op" 2000 800
  assert_success
  grep -q '"input":2000' "${TEST_ADJ_DIR}/state/usage_log.jsonl"
  grep -q '"output":800' "${TEST_ADJ_DIR}/state/usage_log.jsonl"
}

@test "usage_estimate: logged entry uses sonnet as the default model" {
  run bash "${USAGE_SCRIPT}" "test_op" 1000 100
  assert_success
  grep -q '"model":"sonnet"' "${TEST_ADJ_DIR}/state/usage_log.jsonl"
}

@test "usage_estimate: uses opus model when specified as 4th argument" {
  run bash "${USAGE_SCRIPT}" "reflect" 15000 2000 opus
  assert_success
  grep -q '"model":"opus"' "${TEST_ADJ_DIR}/state/usage_log.jsonl"
}

# --- Output display ---

@test "usage_estimate: displays 'Logged:' confirmation with the operation name" {
  run bash "${USAGE_SCRIPT}" "pulse" 3000 500
  assert_success
  assert_output --partial "Logged:"
  assert_output --partial "pulse"
}

@test "usage_estimate: displays session usage percentage" {
  run bash "${USAGE_SCRIPT}" "test" 3000 500
  assert_success
  assert_output --partial "Session usage"
}

@test "usage_estimate: displays weekly usage percentage" {
  run bash "${USAGE_SCRIPT}" "test" 3000 500
  assert_success
  assert_output --partial "Weekly usage"
}

@test "usage_estimate: shows total token count in the logged confirmation" {
  run bash "${USAGE_SCRIPT}" "test" 5000 1000
  assert_success
  assert_output --partial "6000 tokens"
}

# --- Rolling window calculations ---

@test "usage_estimate: session total includes only entries from the last 5 hours" {
  # Seed an old entry (6 hours ago — should be excluded from session)
  local old_ts
  old_ts="$(date -u -v-6H +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || date -u -d '6 hours ago' +"%Y-%m-%dT%H:%M:%SZ")"
  echo "{\"timestamp\":\"${old_ts}\",\"operation\":\"old\",\"model\":\"sonnet\",\"input\":10000,\"output\":5000,\"total\":15000,\"cost_equiv\":0.1}" > "${TEST_ADJ_DIR}/state/usage_log.jsonl"

  run bash "${USAGE_SCRIPT}" "new" 1000 500
  assert_success
  # Session total should be 1500 (only the new entry), not 16500
  assert_output --partial "Session usage (5h rolling): 1500 / 44000"
}

# --- Healthy/moderate/warning thresholds ---

@test "usage_estimate: displays 'healthy' when session usage is below 50 percent" {
  run bash "${USAGE_SCRIPT}" "small" 1000 200
  assert_success
  assert_output --partial "healthy"
}
