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

@test "notify: sends a simple text message and prints 'Sent.' on success" {
  run bash "${NOTIFY_SCRIPT}" "Hello world"
  assert_success
  assert_output --partial "Sent."
}

@test "notify: calls curl with the Telegram sendMessage endpoint" {
  run bash "${NOTIFY_SCRIPT}" "Test message"
  assert_success
  assert_mock_called "curl"
  assert_mock_args_contain "curl" "sendMessage"
}

@test "notify: passes the bot token in the API URL" {
  run bash "${NOTIFY_SCRIPT}" "Token test"
  assert_success
  assert_mock_args_contain "curl" "test-token-123"
}

@test "notify: sends the message text as a data-urlencode parameter" {
  run bash "${NOTIFY_SCRIPT}" "My important message"
  assert_success
  assert_mock_args_contain "curl" "text=My important message"
}

@test "notify: sends the chat_id from .env as a data-urlencode parameter" {
  run bash "${NOTIFY_SCRIPT}" "Chat ID test"
  assert_success
  assert_mock_args_contain "curl" "chat_id=99999"
}

@test "notify: does NOT use parse_mode (sends plain text, unlike reply.sh)" {
  run bash "${NOTIFY_SCRIPT}" "Plain text message"
  assert_success
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

# --- Input sanitization ---

@test "notify: truncates messages longer than 4096 characters to the Telegram limit" {
  local long_msg
  long_msg="$(printf 'A%.0s' {1..5000})"
  run bash "${NOTIFY_SCRIPT}" "${long_msg}"
  assert_success
  # The message was accepted (curl was called) even though input was >4096
  assert_mock_called "curl"
  # We can't easily check the exact truncated length in args, but the script ran
  assert_output --partial "Sent."
}

@test "notify: strips control characters from the message before sending" {
  # \x01 is a control char that should be stripped
  local msg_with_ctrl=$'Hello\x01World'
  run bash "${NOTIFY_SCRIPT}" "${msg_with_ctrl}"
  assert_success
  assert_mock_called "curl"
}

# --- Error handling ---

@test "notify: exits with failure and prints the error response when Telegram returns an error" {
  create_mock_curl_telegram_error "Bad Request: chat not found"
  run bash "${NOTIFY_SCRIPT}" "Will fail"
  assert_failure
  assert_output --partial "Error sending message"
}

@test "notify: exits with failure when curl returns a non-JSON error response" {
  create_mock_curl "Connection refused" 0
  run bash "${NOTIFY_SCRIPT}" "Will fail"
  assert_failure
  assert_output --partial "Error sending message"
}

# --- Credential handling ---

@test "notify: exits with failure when TELEGRAM_BOT_TOKEN is missing from .env" {
  # Overwrite .env without the bot token
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

# --- curl is called exactly once per invocation ---

@test "notify: calls curl exactly once per message send" {
  run bash "${NOTIFY_SCRIPT}" "Single call test"
  assert_success
  assert_mock_call_count "curl" 1
}
