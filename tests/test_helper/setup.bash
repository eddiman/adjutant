#!/bin/bash
# tests/test_helper/setup.bash — Common setup/teardown for all bats tests
#
# Provides:
#   - TEST_ADJ_DIR: isolated temp directory per test
#   - ADJUTANT_HOME: points to TEST_ADJ_DIR (overrides paths.sh resolution)
#   - Seeded adjutant.yaml and .env
#   - PROJECT_ROOT: path to the real project root
#   - COMMON: path to scripts/common/ for sourcing

# Locate the real project root (two levels up from test_helper/)
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
COMMON="${PROJECT_ROOT}/scripts/common"

# Load bats helpers
load "${PROJECT_ROOT}/tests/test_helper/lib/bats-support/load"
load "${PROJECT_ROOT}/tests/test_helper/lib/bats-assert/load"

# ---------------------------------------------------------------------------
# Internal: seed adjutant.yaml, .env, and standard state directories into
# TEST_ADJ_DIR. Called by both setup_test_env variants below.
# ---------------------------------------------------------------------------
_seed_test_env_base() {
  TEST_ADJ_DIR="$(mktemp -d)"
  export ADJUTANT_HOME="${TEST_ADJ_DIR}"

  # Seed the root marker
  cat > "${TEST_ADJ_DIR}/adjutant.yaml" <<'YAML'
name: adjutant-test
version: "1.0"
YAML

  # Seed a test .env file
  cat > "${TEST_ADJ_DIR}/.env" <<'ENV'
TELEGRAM_BOT_TOKEN=test-token-123
TELEGRAM_CHAT_ID=99999
ENV

  # Create standard directories
  mkdir -p "${TEST_ADJ_DIR}/state"
  mkdir -p "${TEST_ADJ_DIR}/journal"
  mkdir -p "${TEST_ADJ_DIR}/identity"
}

# ---------------------------------------------------------------------------
# setup_test_env — for integration tests.
#
# Copies scripts/ into TEST_ADJ_DIR so that subprocess scripts can source
# their dependencies via ${ADJ_DIR}/scripts/...
#
# When called inside a setup_file() that has run setup_file_scripts_template,
# the copy is from a local temp dir (fast APFS clone on macOS). Otherwise it
# falls back to copying directly from PROJECT_ROOT.
# ---------------------------------------------------------------------------
setup_test_env() {
  _seed_test_env_base

  # Copy scripts/ so that ${ADJ_DIR}/scripts/common/*.sh resolves correctly
  # when integration tests run standalone scripts that source from ADJ_DIR.
  # IMPORTANT: We use cp -R (not ln -s) so that tests can safely write mock
  # script stubs into ${TEST_ADJ_DIR}/scripts/ without clobbering production files.
  if [[ -n "${FILE_SCRIPTS_TEMPLATE:-}" && -d "${FILE_SCRIPTS_TEMPLATE}/scripts" ]]; then
    # Fast path: copy from the per-file template (same-volume; APFS clone on macOS)
    cp -R "${FILE_SCRIPTS_TEMPLATE}/scripts" "${TEST_ADJ_DIR}/scripts"
  else
    cp -R "${PROJECT_ROOT}/scripts" "${TEST_ADJ_DIR}/scripts"
  fi
}

# ---------------------------------------------------------------------------
# setup_test_env_no_scripts — for unit tests.
#
# Unit tests source scripts directly from PROJECT_ROOT/scripts/ and never
# invoke subprocesses that need ${TEST_ADJ_DIR}/scripts/. Skipping the copy
# saves ~364KB of I/O per test (× 210 unit tests = significant savings).
# ---------------------------------------------------------------------------
setup_test_env_no_scripts() {
  _seed_test_env_base
}

# ---------------------------------------------------------------------------
# Per-file template helpers — call from setup_file() / teardown_file() in
# integration test files to amortise the scripts/ copy across all tests in
# the file (17 copies) rather than once per test (319 copies).
#
# Usage in an integration .bats file:
#   setup_file()    { setup_file_scripts_template; }
#   teardown_file() { teardown_file_scripts_template; }
# ---------------------------------------------------------------------------
setup_file_scripts_template() {
  FILE_SCRIPTS_TEMPLATE="$(mktemp -d)"
  cp -R "${PROJECT_ROOT}/scripts" "${FILE_SCRIPTS_TEMPLATE}/scripts"
  export FILE_SCRIPTS_TEMPLATE
}

teardown_file_scripts_template() {
  if [[ -n "${FILE_SCRIPTS_TEMPLATE:-}" && -d "${FILE_SCRIPTS_TEMPLATE}" ]]; then
    rm -rf "${FILE_SCRIPTS_TEMPLATE}"
  fi
  unset FILE_SCRIPTS_TEMPLATE
}

# ---------------------------------------------------------------------------
# Clean up the isolated test environment
# ---------------------------------------------------------------------------
teardown_test_env() {
  if [ -n "${TEST_ADJ_DIR:-}" ] && [ -d "${TEST_ADJ_DIR}" ]; then
    rm -rf "${TEST_ADJ_DIR}"
  fi
  unset ADJUTANT_HOME TEST_ADJ_DIR ADJ_DIR ADJUTANT_DIR
}
