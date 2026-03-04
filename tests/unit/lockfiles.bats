#!/usr/bin/env bats
# tests/unit/lockfiles.bats — Tests for scripts/common/lockfiles.sh

load "${BATS_TEST_DIRNAME}/../test_helper/setup.bash"

setup() {
  setup_test_env_no_scripts
  source "${COMMON}/paths.sh"
  source "${COMMON}/lockfiles.sh"
}

teardown() { teardown_test_env; }

# --- set_paused / clear_paused: create and remove the PAUSED lockfile ---

@test "lockfiles: set_paused creates a PAUSED file in the project directory" {
  set_paused
  [ -f "${ADJ_DIR}/PAUSED" ]
}

@test "lockfiles: clear_paused removes the PAUSED file from the project directory" {
  set_paused
  [ -f "${ADJ_DIR}/PAUSED" ]
  clear_paused
  [ ! -f "${ADJ_DIR}/PAUSED" ]
}

@test "lockfiles: calling clear_paused when already unpaused does not cause an error" {
  run clear_paused
  assert_success
}

# --- set_killed / clear_killed: create and remove the KILLED lockfile ---

@test "lockfiles: set_killed creates a KILLED file in the project directory" {
  set_killed
  [ -f "${ADJ_DIR}/KILLED" ]
}

@test "lockfiles: clear_killed removes the KILLED file from the project directory" {
  set_killed
  [ -f "${ADJ_DIR}/KILLED" ]
  clear_killed
  [ ! -f "${ADJ_DIR}/KILLED" ]
}

@test "lockfiles: calling clear_killed when already not killed does not cause an error" {
  run clear_killed
  assert_success
}

# --- is_paused: silent boolean check for PAUSED state ---

@test "lockfiles: is_paused returns success when the system is paused" {
  set_paused
  run is_paused
  assert_success
}

@test "lockfiles: is_paused returns failure when the system is not paused" {
  run is_paused
  assert_failure
}

# --- is_killed: silent boolean check for KILLED state ---

@test "lockfiles: is_killed returns success when the system has been killed" {
  set_killed
  run is_killed
  assert_success
}

@test "lockfiles: is_killed returns failure when the system has not been killed" {
  run is_killed
  assert_failure
}

# --- is_operational: composite check — true only when neither paused nor killed ---

@test "lockfiles: is_operational returns success when the system is neither paused nor killed" {
  run is_operational
  assert_success
}

@test "lockfiles: is_operational returns failure when the system is paused" {
  set_paused
  run is_operational
  assert_failure
}

@test "lockfiles: is_operational returns failure when the system has been killed" {
  set_killed
  run is_operational
  assert_failure
}

@test "lockfiles: is_operational returns failure when the system is both paused and killed" {
  set_paused
  set_killed
  run is_operational
  assert_failure
}

# --- check_killed: verbose check that prints a message to stderr ---

@test "lockfiles: check_killed returns success silently when the system has not been killed" {
  run check_killed
  assert_success
  assert_output ""
}

@test "lockfiles: check_killed returns failure and prints a 'KILLED lockfile exists' warning when killed" {
  set_killed
  run check_killed
  assert_failure
  assert_output --partial "KILLED lockfile exists"
}

# --- check_paused: verbose check that prints a message to stderr ---

@test "lockfiles: check_paused returns success silently when the system is not paused" {
  run check_paused
  assert_success
  assert_output ""
}

@test "lockfiles: check_paused returns failure and prints 'Adjutant is paused' when paused" {
  set_paused
  run check_paused
  assert_failure
  assert_output --partial "Adjutant is paused"
}

# --- check_operational: verbose composite check (killed is tested before paused) ---

@test "lockfiles: check_operational returns success when the system is fully operational" {
  run check_operational
  assert_success
}

@test "lockfiles: check_operational returns failure with KILLED message when the system has been killed" {
  set_killed
  run check_operational
  assert_failure
  assert_output --partial "KILLED"
}

@test "lockfiles: check_operational returns failure with paused message when the system is paused" {
  set_paused
  run check_operational
  assert_failure
  assert_output --partial "paused"
}

@test "lockfiles: check_operational checks killed state first — when both killed and paused, the KILLED message appears" {
  set_killed
  set_paused
  run check_operational
  assert_failure
  # killed is checked first in check_operational
  assert_output --partial "KILLED"
}

# --- Full state transition cycle ---

@test "lockfiles: full lifecycle — clean to paused to killed, then clear killed (still paused), then clear paused (operational again)" {
  # Start clean
  run is_operational
  assert_success

  # Pause
  set_paused
  run is_paused
  assert_success
  run is_operational
  assert_failure

  # Kill (while still paused)
  set_killed
  run is_killed
  assert_success
  run is_paused
  assert_success

  # Clear killed but still paused
  clear_killed
  run is_killed
  assert_failure
  run is_paused
  assert_success
  run is_operational
  assert_failure

  # Clear paused — now operational
  clear_paused
  run is_operational
  assert_success
}

# --- Guard clause: ADJ_DIR must be set before sourcing lockfiles.sh ---

@test "lockfiles: sourcing lockfiles.sh without ADJ_DIR set exits with an error telling you to source paths.sh first" {
  unset ADJ_DIR
  run bash -c "source '${COMMON}/lockfiles.sh'"
  assert_failure
  assert_output --partial "ADJ_DIR not set"
}
