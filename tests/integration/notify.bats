#!/usr/bin/env bats
# tests/integration/notify.bats — Integration tests for scripts/messaging/telegram/notify.sh
#
# notify.sh is a standalone script that sends a plain-text Telegram message via curl.
# It sources paths.sh and env.sh, validates credentials, sanitizes input, calls curl,
# and checks the response for "ok":true.

load "${BATS_TEST_DIRNAME}/../test_helper/setup.bash"
load "${BATS_TEST_DIRNAME}/../test_helper/mocks.bash"

NOTIFY_SCRIPT="${PROJECT_ROOT}/scripts/messaging/telegram/notify.sh"

setup_file()    { setup_file_scripts_template; }
teardown_file() { teardown_file_scripts_template; }

setup() {
  setup_test_env
  setup_mocks
  create_mock_curl_telegram_ok
}

teardown() {
  teardown_mocks
  teardown_test_env
}

# --- Happy path ---

@test "notify: sends a correctly-formed plain-text Telegram API call and prints 'Sent.'" {
  run bash "${NOTIFY_SCRIPT}" "My important message"
  assert_success
  assert_output --partial "Sent."
  assert_mock_called "curl"
  assert_mock_args_contain "curl" "sendMessage"
  assert_mock_args_contain "curl" "test-token-123"
  assert_mock_args_contain "curl" "chat_id=99999"
  assert_mock_args_contain "curl" "text=My important message"
  # notify.sh sends plain text — no parse_mode
  local args
  args="$(mock_last_args "curl")"
  [[ "${args}" != *"parse_mode"* ]]
}

# --- Input validation ---

@test "notify: exits with error and prints usage when no message argument is provided" {
  run bash "${NOTIFY_SCRIPT}"
  assert_failure
  assert_output --partial "Usage:"
}

@test "notify: exits with error when called with an empty string argument" {
  run bash "${NOTIFY_SCRIPT}" ""
  assert_failure
  assert_output --partial "Usage:"
}

# --- Error handling ---

@test "notify: exits with failure and prints error when Telegram returns an error" {
  create_mock_curl_telegram_error "Bad Request: chat not found"
  run bash "${NOTIFY_SCRIPT}" "Will fail"
  assert_failure
  assert_output --partial "Error sending message"
}

@test "notify: exits with failure when curl returns a non-JSON response" {
  create_mock_curl "Connection refused" 0
  run bash "${NOTIFY_SCRIPT}" "Will fail"
  assert_failure
  assert_output --partial "Error sending message"
}

# --- Credential handling ---

@test "notify: exits with failure when TELEGRAM_BOT_TOKEN is missing from .env" {
  cat > "${TEST_ADJ_DIR}/.env" <<'ENV'
TELEGRAM_CHAT_ID=99999
ENV
  run bash "${NOTIFY_SCRIPT}" "No token"
  assert_failure
}

@test "notify: exits with failure when TELEGRAM_CHAT_ID is missing from .env" {
  cat > "${TEST_ADJ_DIR}/.env" <<'ENV'
TELEGRAM_BOT_TOKEN=test-token-123
ENV
  run bash "${NOTIFY_SCRIPT}" "No chat id"
  assert_failure
}

@test "notify: exits with failure when .env file does not exist" {
  rm -f "${TEST_ADJ_DIR}/.env"
  run bash "${NOTIFY_SCRIPT}" "No env file"
  assert_failure
}
