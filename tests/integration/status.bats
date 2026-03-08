#!/usr/bin/env bats
# tests/integration/status.bats — Integration tests for scripts/observability/status.sh
#
# status.sh reports operational state (running/paused/killed), scheduled jobs,
# last autonomous cycle, notification count, and recent actions.
# It always exits 0.

load "${BATS_TEST_DIRNAME}/../test_helper/setup.bash"
load "${BATS_TEST_DIRNAME}/../test_helper/mocks.bash"

STATUS_SCRIPT="${PROJECT_ROOT}/scripts/observability/status.sh"

setup_file()    { setup_file_scripts_template; }
teardown_file() { teardown_file_scripts_template; }

setup() {
  setup_test_env
  setup_mocks
  # Default: no cron jobs
  create_mock_crontab ""
}

teardown() {
  teardown_mocks
  teardown_test_env
}

# --- State reporting ---

@test "status: reports running when neither paused nor killed lockfile exists" {
  run bash "${STATUS_SCRIPT}"
  assert_success
  assert_output --partial "up and running"
}

@test "status: reports paused when the PAUSED lockfile exists" {
  touch "${TEST_ADJ_DIR}/PAUSED"
  run bash "${STATUS_SCRIPT}"
  assert_success
  assert_output --partial "paused"
}

@test "status: reports killed when the KILLED lockfile exists" {
  touch "${TEST_ADJ_DIR}/KILLED"
  run bash "${STATUS_SCRIPT}"
  assert_success
  assert_output --partial "killed"
}

@test "status: KILLED takes precedence over PAUSED when both lockfiles exist" {
  touch "${TEST_ADJ_DIR}/PAUSED"
  touch "${TEST_ADJ_DIR}/KILLED"
  run bash "${STATUS_SCRIPT}"
  assert_success
  assert_output --partial "killed"
  # Must not say "paused" when killed
  [[ "${output}" != *"paused"* ]]
}

# --- Scheduled jobs ---

@test "status: reports no scheduled jobs when crontab has no adjutant entries" {
  create_mock_crontab "# no adjutant jobs here"
  run bash "${STATUS_SCRIPT}"
  assert_success
  assert_output --partial "No scheduled jobs configured"
}

@test "status: lists a pulse job from crontab" {
  create_mock_crontab "0 8 * * 1-5 ${TEST_ADJ_DIR}/prompts/pulse.md"
  run bash "${STATUS_SCRIPT}"
  assert_success
  assert_output --partial "Autonomous Pulse"
}

@test "status: lists a review job from crontab" {
  create_mock_crontab "0 20 * * 1-5 ${TEST_ADJ_DIR}/prompts/review.md"
  run bash "${STATUS_SCRIPT}"
  assert_success
  assert_output --partial "Daily Review"
}

# --- Autonomous activity section ---

@test "status: includes autonomous activity section" {
  run bash "${STATUS_SCRIPT}"
  assert_success
  assert_output --partial "Autonomous activity"
}

@test "status: reports no cycles recorded when heartbeat file is absent" {
  run bash "${STATUS_SCRIPT}"
  assert_success
  assert_output --partial "No autonomous cycles recorded yet"
}

@test "status: shows last cycle info when heartbeat file is present" {
  seed_heartbeat "2026-03-08T10:00:00Z" "All systems nominal."
  run bash "${STATUS_SCRIPT}"
  assert_success
  assert_output --partial "Last cycle"
}

# --- Notification count ---

@test "status: shows today's notification count" {
  run bash "${STATUS_SCRIPT}"
  assert_success
  assert_output --partial "Notifications today:"
}

# --- Always exits 0 ---

@test "status: always exits 0 even when crontab returns an error" {
  create_mock_crontab "" 1
  run bash "${STATUS_SCRIPT}"
  assert_success
}

@test "status: always exits 0 when KILLED lockfile is present" {
  touch "${TEST_ADJ_DIR}/KILLED"
  run bash "${STATUS_SCRIPT}"
  assert_success
}
