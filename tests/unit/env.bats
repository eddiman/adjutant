#!/usr/bin/env bats
# tests/unit/env.bats — Tests for scripts/common/env.sh

load "${BATS_TEST_DIRNAME}/../test_helper/setup.bash"

setup() {
  setup_test_env
  source "${COMMON}/paths.sh"
}

teardown() { teardown_test_env; }

# --- load_env: checks whether .env file exists ---

@test "env: load_env succeeds when the .env file exists in the project directory" {
  source "${COMMON}/env.sh"
  run load_env
  assert_success
}

@test "env: load_env fails with a 'not found' error when the .env file is missing" {
  rm -f "${TEST_ADJ_DIR}/.env"
  source "${COMMON}/env.sh"
  run load_env
  assert_failure
  assert_output --partial "not found"
}

# --- get_credential: extracts a value from .env by key name ---

@test "env: get_credential extracts the correct value for TELEGRAM_BOT_TOKEN from .env" {
  source "${COMMON}/env.sh"
  run get_credential TELEGRAM_BOT_TOKEN
  assert_success
  assert_output "test-token-123"
}

@test "env: get_credential extracts the correct value for TELEGRAM_CHAT_ID from .env" {
  source "${COMMON}/env.sh"
  run get_credential TELEGRAM_CHAT_ID
  assert_success
  assert_output "99999"
}

@test "env: get_credential returns an empty string when the requested key does not exist in .env" {
  source "${COMMON}/env.sh"
  run get_credential NONEXISTENT_KEY
  assert_success
  assert_output ""
}

@test "env: get_credential strips surrounding single quotes from the value" {
  echo "QUOTED_KEY='quoted-value'" >> "${TEST_ADJ_DIR}/.env"
  source "${COMMON}/env.sh"
  run get_credential QUOTED_KEY
  assert_success
  assert_output "quoted-value"
}

@test "env: get_credential strips surrounding double quotes from the value" {
  echo 'DQUOTED_KEY="double-quoted"' >> "${TEST_ADJ_DIR}/.env"
  source "${COMMON}/env.sh"
  run get_credential DQUOTED_KEY
  assert_success
  assert_output "double-quoted"
}

@test "env: get_credential fails with a 'not found' error when the .env file is missing" {
  rm -f "${TEST_ADJ_DIR}/.env"
  source "${COMMON}/env.sh"
  run get_credential TELEGRAM_BOT_TOKEN
  assert_failure
  assert_output --partial "not found"
}

# --- has_credential: boolean check for whether a key has a non-empty value ---

@test "env: has_credential returns success when the key exists and has a value" {
  source "${COMMON}/env.sh"
  run has_credential TELEGRAM_BOT_TOKEN
  assert_success
}

@test "env: has_credential returns failure when the key does not exist in .env" {
  source "${COMMON}/env.sh"
  run has_credential NONEXISTENT_KEY
  assert_failure
}

@test "env: has_credential returns failure when the key exists but its value is empty" {
  echo "EMPTY_KEY=" >> "${TEST_ADJ_DIR}/.env"
  source "${COMMON}/env.sh"
  run has_credential EMPTY_KEY
  assert_failure
}

# --- require_telegram_credentials: loads and validates both Telegram keys ---

@test "env: require_telegram_credentials succeeds when both TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are present" {
  source "${COMMON}/env.sh"
  run require_telegram_credentials
  assert_success
}

@test "env: require_telegram_credentials exports TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID as environment variables" {
  source "${COMMON}/env.sh"
  require_telegram_credentials
  assert_equal "$TELEGRAM_BOT_TOKEN" "test-token-123"
  assert_equal "$TELEGRAM_CHAT_ID" "99999"
}

@test "env: require_telegram_credentials fails when TELEGRAM_BOT_TOKEN is missing from .env" {
  echo "TELEGRAM_CHAT_ID=99999" > "${TEST_ADJ_DIR}/.env"
  source "${COMMON}/env.sh"
  run require_telegram_credentials
  assert_failure
  assert_output --partial "must be set"
}

@test "env: require_telegram_credentials fails when TELEGRAM_CHAT_ID is missing from .env" {
  echo "TELEGRAM_BOT_TOKEN=test-token-123" > "${TEST_ADJ_DIR}/.env"
  source "${COMMON}/env.sh"
  run require_telegram_credentials
  assert_failure
  assert_output --partial "must be set"
}

@test "env: require_telegram_credentials fails when the .env file does not exist" {
  rm -f "${TEST_ADJ_DIR}/.env"
  source "${COMMON}/env.sh"
  run require_telegram_credentials
  assert_failure
  assert_output --partial "not found"
}

# --- Guard clause: ADJ_DIR must be set before sourcing env.sh ---

@test "env: sourcing env.sh without ADJ_DIR set exits with an error telling you to source paths.sh first" {
  unset ADJ_DIR
  run bash -c "source '${COMMON}/env.sh'"
  assert_failure
  assert_output --partial "ADJ_DIR not set"
}
