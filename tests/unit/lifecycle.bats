#!/usr/bin/env bats
# tests/unit/lifecycle.bats — Tests for scripts/lifecycle/pause.sh and resume.sh

load "${BATS_TEST_DIRNAME}/../test_helper/setup.bash"

setup()    { setup_test_env; }
teardown() { teardown_test_env; }

# --- pause.sh: pauses Adjutant by creating the PAUSED lockfile ---

@test "lifecycle: running pause.sh creates a PAUSED file in the project directory" {
  run bash "${PROJECT_ROOT}/scripts/lifecycle/pause.sh"
  assert_success
  [ -f "${TEST_ADJ_DIR}/PAUSED" ]
}

@test "lifecycle: running pause.sh prints a confirmation message saying Adjutant is paused" {
  run bash "${PROJECT_ROOT}/scripts/lifecycle/pause.sh"
  assert_success
  assert_output --partial "Adjutant paused"
}

@test "lifecycle: running pause.sh twice does not cause an error (idempotent)" {
  run bash "${PROJECT_ROOT}/scripts/lifecycle/pause.sh"
  assert_success
  run bash "${PROJECT_ROOT}/scripts/lifecycle/pause.sh"
  assert_success
  [ -f "${TEST_ADJ_DIR}/PAUSED" ]
}

# --- resume.sh: resumes Adjutant by removing the PAUSED lockfile ---

@test "lifecycle: running resume.sh removes the PAUSED file from the project directory" {
  touch "${TEST_ADJ_DIR}/PAUSED"
  [ -f "${TEST_ADJ_DIR}/PAUSED" ]

  run bash "${PROJECT_ROOT}/scripts/lifecycle/resume.sh"
  assert_success
  [ ! -f "${TEST_ADJ_DIR}/PAUSED" ]
}

@test "lifecycle: running resume.sh prints a confirmation message saying Adjutant is resumed" {
  touch "${TEST_ADJ_DIR}/PAUSED"
  run bash "${PROJECT_ROOT}/scripts/lifecycle/resume.sh"
  assert_success
  assert_output --partial "Adjutant resumed"
}

@test "lifecycle: running resume.sh when not paused does not cause an error (idempotent)" {
  run bash "${PROJECT_ROOT}/scripts/lifecycle/resume.sh"
  assert_success
}

# --- Round-trip: pause then resume leaves a clean state ---

@test "lifecycle: pausing and then resuming removes the PAUSED file and restores a clean state" {
  run bash "${PROJECT_ROOT}/scripts/lifecycle/pause.sh"
  assert_success
  [ -f "${TEST_ADJ_DIR}/PAUSED" ]

  run bash "${PROJECT_ROOT}/scripts/lifecycle/resume.sh"
  assert_success
  [ ! -f "${TEST_ADJ_DIR}/PAUSED" ]
}

# --- Isolation: ADJUTANT_HOME keeps tests from touching the real project ---

@test "lifecycle: pause.sh creates PAUSED in the test directory, not in the real project root" {
  run bash "${PROJECT_ROOT}/scripts/lifecycle/pause.sh"
  assert_success

  [ -f "${TEST_ADJ_DIR}/PAUSED" ]
  [ ! -f "${PROJECT_ROOT}/PAUSED" ]
}
