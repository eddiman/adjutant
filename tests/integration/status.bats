#!/usr/bin/env bats
# tests/integration/status.bats — Integration tests for scripts/observability/status.sh
#
# status.sh is a standalone script that:
#   - Reports RUNNING/PAUSED/KILLED state using lockfiles.sh
#   - Lists registered cron jobs by parsing crontab -l output
#   - Always exits 0

load "${BATS_TEST_DIRNAME}/../test_helper/setup.bash"
load "${BATS_TEST_DIRNAME}/../test_helper/mocks.bash"

STATUS_SCRIPT="${PROJECT_ROOT}/scripts/observability/status.sh"

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

@test "status: reports RUNNING when neither paused nor killed lockfile exists" {
  run bash "${STATUS_SCRIPT}"
  assert_success
  assert_output --partial "Status: RUNNING"
}

@test "status: reports PAUSED when the PAUSED lockfile exists" {
  touch "${TEST_ADJ_DIR}/PAUSED"
  run bash "${STATUS_SCRIPT}"
  assert_success
  assert_output --partial "Status: PAUSED"
}

@test "status: reports KILLED when the KILLED lockfile exists" {
  touch "${TEST_ADJ_DIR}/KILLED"
  run bash "${STATUS_SCRIPT}"
  assert_success
  assert_output --partial "Status: KILLED"
}

@test "status: KILLED takes precedence over PAUSED when both lockfiles exist" {
  touch "${TEST_ADJ_DIR}/PAUSED"
  touch "${TEST_ADJ_DIR}/KILLED"
  run bash "${STATUS_SCRIPT}"
  assert_success
  assert_output --partial "Status: KILLED"
}

# --- Cron job listing ---

@test "status: shows '(none)' when no adjutant cron jobs are registered" {
  create_mock_crontab "# no adjutant jobs here"
  run bash "${STATUS_SCRIPT}"
  assert_success
  assert_output --partial "(none)"
}

@test "status: detects and displays a news briefing cron job" {
  create_mock_crontab "0 8 * * 1-5 /home/user/.adjutant/scripts/news/briefing.sh"
  run bash "${STATUS_SCRIPT}"
  assert_success
  assert_output --partial "News Briefing"
}

@test "status: recognizes the old news_briefing.sh path as a news briefing job" {
  create_mock_crontab "0 8 * * 1-5 /home/user/.adjutant/scripts/news_briefing.sh"
  run bash "${STATUS_SCRIPT}"
  assert_success
  assert_output --partial "News Briefing"
}

@test "status: formats the common weekday 08:00 schedule as a human-readable string" {
  create_mock_crontab "0 8 * * 1-5 /home/user/.adjutant/scripts/news/briefing.sh"
  run bash "${STATUS_SCRIPT}"
  assert_success
  assert_output --partial "Every weekday at 08:00"
}

@test "status: labels unrecognized adjutant cron jobs as 'Unknown Job'" {
  create_mock_crontab "*/30 * * * * /home/user/.adjutant/scripts/something_else.sh"
  run bash "${STATUS_SCRIPT}"
  assert_success
  assert_output --partial "Unknown Job"
}

# --- Always exits 0 ---

@test "status: always exits 0 even when crontab returns an error" {
  create_mock_crontab "" 1
  run bash "${STATUS_SCRIPT}"
  assert_success
}

@test "status: always exits 0 regardless of system state" {
  touch "${TEST_ADJ_DIR}/KILLED"
  run bash "${STATUS_SCRIPT}"
  assert_success
}
