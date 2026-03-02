#!/usr/bin/env bats
# tests/integration/reply.bats — Integration tests for scripts/messaging/telegram/reply.sh
#
# reply.sh is a standalone script that sends a Markdown-formatted Telegram message via curl.
# Key differences from notify.sh:
#   - Uses parse_mode=Markdown
#   - Truncates to 4000 chars (not 4096)
#   - Does NOT check curl response (always prints "Replied." and exits 0)
#   - Redirects curl stdout to /dev/null

load "${BATS_TEST_DIRNAME}/../test_helper/setup.bash"
load "${BATS_TEST_DIRNAME}/../test_helper/mocks.bash"

REPLY_SCRIPT="${PROJECT_ROOT}/scripts/messaging/telegram/reply.sh"

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

@test "reply: sends a message and prints 'Replied.' on success" {
  run bash "${REPLY_SCRIPT}" "Hello world"
  assert_success
  assert_output --partial "Replied."
}

@test "reply: calls curl with the Telegram sendMessage endpoint" {
  run bash "${REPLY_SCRIPT}" "Test message"
  assert_success
  assert_mock_called "curl"
  assert_mock_args_contain "curl" "sendMessage"
}

@test "reply: passes the bot token in the API URL" {
  run bash "${REPLY_SCRIPT}" "Token test"
  assert_success
  assert_mock_args_contain "curl" "test-token-123"
}

@test "reply: sends the chat_id from .env" {
  run bash "${REPLY_SCRIPT}" "Chat ID test"
  assert_success
  assert_mock_args_contain "curl" "chat_id=99999"
}

@test "reply: sends parse_mode=Markdown unlike notify.sh which sends plain text" {
  run bash "${REPLY_SCRIPT}" "Markdown message"
  assert_success
  assert_mock_args_contain "curl" "parse_mode=Markdown"
}

@test "reply: sends the message text as a data-urlencode parameter" {
  run bash "${REPLY_SCRIPT}" "My reply message"
  assert_success
  assert_mock_args_contain "curl" "text=My reply message"
}

# --- reply.sh always succeeds (does not check curl response) ---

@test "reply: prints 'Replied.' even when Telegram returns an error because it does not check the response" {
  create_mock_curl_telegram_error "Bad Request: chat not found"
  run bash "${REPLY_SCRIPT}" "Will not fail"
  assert_success
  assert_output --partial "Replied."
}

@test "reply: prints 'Replied.' even when curl returns garbage output" {
  create_mock_curl "Connection reset by peer" 0
  run bash "${REPLY_SCRIPT}" "Still succeeds"
  assert_success
  assert_output --partial "Replied."
}

# --- Input validation ---

@test "reply: exits with error and prints usage when no message argument is provided" {
  run bash "${REPLY_SCRIPT}"
  assert_failure
  assert_output --partial "Usage:"
}

@test "reply: exits with error when called with an empty string argument" {
  run bash "${REPLY_SCRIPT}" ""
  assert_failure
  assert_output --partial "Usage:"
}

# --- Input sanitization ---

@test "reply: truncates messages longer than 4000 characters (not 4096 like notify.sh)" {
  local long_msg
  long_msg="$(printf 'B%.0s' {1..5000})"
  run bash "${REPLY_SCRIPT}" "${long_msg}"
  assert_success
  assert_mock_called "curl"
  assert_output --partial "Replied."
}

@test "reply: strips control characters from the message before sending" {
  local msg_with_ctrl=$'Hello\x01World'
  run bash "${REPLY_SCRIPT}" "${msg_with_ctrl}"
  assert_success
  assert_mock_called "curl"
}

# --- Credential handling ---

@test "reply: exits with failure when TELEGRAM_BOT_TOKEN is missing from .env" {
  cat > "${TEST_ADJ_DIR}/.env" <<'ENV'
TELEGRAM_CHAT_ID=99999
ENV
  run bash "${REPLY_SCRIPT}" "No token"
  assert_failure
}

@test "reply: exits with failure when TELEGRAM_CHAT_ID is missing from .env" {
  cat > "${TEST_ADJ_DIR}/.env" <<'ENV'
TELEGRAM_BOT_TOKEN=test-token-123
ENV
  run bash "${REPLY_SCRIPT}" "No chat id"
  assert_failure
}

@test "reply: exits with failure when .env file does not exist" {
  rm -f "${TEST_ADJ_DIR}/.env"
  run bash "${REPLY_SCRIPT}" "No env file"
  assert_failure
}

# --- curl is called exactly once ---

@test "reply: calls curl exactly once per message send" {
  run bash "${REPLY_SCRIPT}" "Single call test"
  assert_success
  assert_mock_call_count "curl" 1
}
