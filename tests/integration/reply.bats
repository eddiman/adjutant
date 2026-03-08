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

@test "reply: sends a correctly-formed Markdown Telegram API call and prints 'Replied.'" {
  run bash "${REPLY_SCRIPT}" "My reply message"
  assert_success
  assert_output --partial "Replied."
  assert_mock_called "curl"
  assert_mock_args_contain "curl" "sendMessage"
  assert_mock_args_contain "curl" "test-token-123"
  assert_mock_args_contain "curl" "chat_id=99999"
  assert_mock_args_contain "curl" "text=My reply message"
  assert_mock_args_contain "curl" "parse_mode=Markdown"
}

# --- reply.sh always succeeds (does not check curl response) ---

@test "reply: prints 'Replied.' even when Telegram returns an error" {
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
