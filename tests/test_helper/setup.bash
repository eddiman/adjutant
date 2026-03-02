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

# Create an isolated test environment
# Called automatically by bats before each test
setup_test_env() {
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

  # Copy scripts/ so that ${ADJ_DIR}/scripts/common/*.sh resolves correctly
  # when integration tests run standalone scripts that source from ADJ_DIR.
  # IMPORTANT: We use cp -R (not ln -s) so that tests can safely write mock
  # script stubs into ${TEST_ADJ_DIR}/scripts/ without clobbering production files.
  cp -R "${PROJECT_ROOT}/scripts" "${TEST_ADJ_DIR}/scripts"
}

# Clean up the isolated test environment
teardown_test_env() {
  if [ -n "${TEST_ADJ_DIR:-}" ] && [ -d "${TEST_ADJ_DIR}" ]; then
    rm -rf "${TEST_ADJ_DIR}"
  fi
  unset ADJUTANT_HOME TEST_ADJ_DIR ADJ_DIR ADJUTANT_DIR
}
