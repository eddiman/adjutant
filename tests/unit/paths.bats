#!/usr/bin/env bats
# tests/unit/paths.bats — Tests for scripts/common/paths.sh

load "${BATS_TEST_DIRNAME}/../test_helper/setup.bash"

setup()    { setup_test_env_no_scripts; }
teardown() { teardown_test_env; }

# --- Resolution strategy 1: ADJUTANT_HOME environment variable ---

@test "paths: when ADJUTANT_HOME is set, ADJ_DIR resolves to that exact directory" {
  source "${COMMON}/paths.sh"
  assert_equal "$ADJ_DIR" "$TEST_ADJ_DIR"
}

@test "paths: ADJ_DIR is exported so child processes can see it" {
  source "${COMMON}/paths.sh"
  run bash -c 'echo "$ADJ_DIR"'
  assert_output "$TEST_ADJ_DIR"
}

@test "paths: ADJUTANT_DIR is exported as a backward-compatible alias pointing to the same directory as ADJ_DIR" {
  source "${COMMON}/paths.sh"
  assert_equal "$ADJUTANT_DIR" "$ADJ_DIR"
  run bash -c 'echo "$ADJUTANT_DIR"'
  assert_output "$TEST_ADJ_DIR"
}

# --- Resolution strategy 2: walk up the directory tree looking for adjutant.yaml ---

@test "paths: when ADJUTANT_HOME is unset, paths.sh walks up from the calling script to find the directory containing adjutant.yaml" {
  unset ADJUTANT_HOME
  # Create a nested dir inside the test home that has adjutant.yaml at root
  local nested="${TEST_ADJ_DIR}/scripts/common"
  mkdir -p "$nested"

  # Create a thin wrapper script inside the nested dir that sources paths.sh
  cat > "${nested}/test_paths_wrapper.sh" <<'SCRIPT'
#!/bin/bash
# Simulate being called from scripts/common/ — BASH_SOURCE[1] will be this file
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../../scripts/common/paths.sh" 2>/dev/null
echo "$ADJ_DIR"
SCRIPT

  # Copy the real paths.sh into the test tree so it can be sourced
  cp "${COMMON}/paths.sh" "${nested}/paths.sh"

  # Also create scripts/common/ relative to adjutant.yaml for the wrapper source
  # (already done — $nested is scripts/common inside TEST_ADJ_DIR)

  # Re-write wrapper to source paths.sh from its own dir
  cat > "${nested}/test_paths_wrapper.sh" <<'SCRIPT'
#!/bin/bash
COMMON_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${COMMON_DIR}/paths.sh"
echo "$ADJ_DIR"
SCRIPT
  chmod +x "${nested}/test_paths_wrapper.sh"

  run bash "${nested}/test_paths_wrapper.sh"
  assert_success
  assert_output "$TEST_ADJ_DIR"
}

# --- Resolution strategy 3: legacy fallback ---

@test "paths: when ADJUTANT_HOME is unset and no adjutant.yaml exists in any parent, it falls back to HOME/.adjutant" {
  unset ADJUTANT_HOME

  # Use a temp dir with no adjutant.yaml anywhere in parents
  local isolated
  isolated="$(mktemp -d)"
  mkdir -p "${isolated}/scripts/common"
  cp "${COMMON}/paths.sh" "${isolated}/scripts/common/paths.sh"

  # Also ensure $HOME/.adjutant exists so the script doesn't error
  local fake_home
  fake_home="$(mktemp -d)"
  mkdir -p "${fake_home}/.adjutant"

  cat > "${isolated}/scripts/common/wrapper.sh" <<SCRIPT
#!/bin/bash
export HOME="${fake_home}"
source "${isolated}/scripts/common/paths.sh"
echo "\$ADJ_DIR"
SCRIPT
  chmod +x "${isolated}/scripts/common/wrapper.sh"

  run bash "${isolated}/scripts/common/wrapper.sh"
  assert_success
  assert_output "${fake_home}/.adjutant"

  rm -rf "$isolated" "$fake_home"
}

# --- Error handling ---

@test "paths: sourcing paths.sh exits with error when the resolved directory does not exist on disk" {
  export ADJUTANT_HOME="/nonexistent/path/that/does/not/exist"

  run bash -c "source '${COMMON}/paths.sh'"
  assert_failure
  assert_output --partial "Error: Adjutant directory not found"
}

# --- Edge cases ---

@test "paths: ADJUTANT_HOME handles directory paths that contain spaces" {
  local spaced
  spaced="$(mktemp -d)/path with spaces"
  mkdir -p "$spaced/state"
  cp "${TEST_ADJ_DIR}/adjutant.yaml" "$spaced/"

  export ADJUTANT_HOME="$spaced"
  source "${COMMON}/paths.sh"
  assert_equal "$ADJ_DIR" "$spaced"

  rm -rf "$(dirname "$spaced")"
}
