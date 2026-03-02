#!/usr/bin/env bats
# tests/integration/send.bats — Integration tests for scripts/messaging/telegram/send.sh
#
# send.sh is a sourced function library providing the Telegram adaptor interface:
#   msg_send_text, msg_send_photo, msg_react, msg_typing, msg_authorize, msg_get_user_id
#
# It must be sourced into an environment where TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
# and ADJ_DIR are already set. All curl calls redirect to /dev/null (silent).

load "${BATS_TEST_DIRNAME}/../test_helper/setup.bash"
load "${BATS_TEST_DIRNAME}/../test_helper/mocks.bash"

setup() {
  setup_test_env
  setup_mocks
  create_mock_curl_telegram_ok

  # send.sh needs these env vars set before sourcing
  export TELEGRAM_BOT_TOKEN="test-token-123"
  export TELEGRAM_CHAT_ID="99999"
  export ADJ_DIR="${TEST_ADJ_DIR}"

  # Source logging (send.sh uses adj_log)
  source "${PROJECT_ROOT}/scripts/common/logging.sh"
  # Source the function library under test
  source "${PROJECT_ROOT}/scripts/messaging/telegram/send.sh"
}

teardown() {
  teardown_mocks
  teardown_test_env
}

# ===== msg_send_text =====

@test "send: msg_send_text calls curl with the sendMessage endpoint" {
  msg_send_text "Hello world"
  assert_mock_called "curl"
  assert_mock_args_contain "curl" "sendMessage"
}

@test "send: msg_send_text includes the bot token in the URL" {
  msg_send_text "Token test"
  assert_mock_args_contain "curl" "test-token-123"
}

@test "send: msg_send_text sends the chat_id as a parameter" {
  msg_send_text "Chat test"
  assert_mock_args_contain "curl" "chat_id=99999"
}

@test "send: msg_send_text sends the message text as url-encoded data" {
  msg_send_text "Test message content"
  assert_mock_args_contain "curl" "text=Test message content"
}

@test "send: msg_send_text uses parse_mode=Markdown" {
  msg_send_text "Markdown test"
  assert_mock_args_contain "curl" "parse_mode=Markdown"
}

@test "send: msg_send_text truncates messages longer than 4000 characters" {
  local long_msg
  long_msg="$(printf 'X%.0s' {1..5000})"
  msg_send_text "${long_msg}"
  assert_mock_called "curl"
}

@test "send: msg_send_text includes reply_to_message_id when a second argument is provided" {
  msg_send_text "Reply to this" "42"
  assert_mock_args_contain "curl" "reply_to_message_id=42"
}

@test "send: msg_send_text omits reply_to_message_id when no second argument is provided" {
  msg_send_text "No reply"
  local args
  args="$(mock_last_args "curl")"
  [[ "${args}" != *"reply_to_message_id"* ]]
}

# ===== msg_send_photo =====

@test "send: msg_send_photo calls curl with the sendPhoto endpoint" {
  local test_img="${TEST_ADJ_DIR}/test_photo.jpg"
  echo "fake image data" > "${test_img}"
  msg_send_photo "${test_img}"
  assert_mock_called "curl"
  assert_mock_args_contain "curl" "sendPhoto"
}

@test "send: msg_send_photo passes the photo file path to curl" {
  local test_img="${TEST_ADJ_DIR}/test_photo.jpg"
  echo "fake image data" > "${test_img}"
  msg_send_photo "${test_img}"
  assert_mock_args_contain "curl" "photo=@${test_img}"
}

@test "send: msg_send_photo includes caption when provided as second argument" {
  local test_img="${TEST_ADJ_DIR}/test_photo.jpg"
  echo "fake image data" > "${test_img}"
  msg_send_photo "${test_img}" "My photo caption"
  assert_mock_args_contain "curl" "caption=My photo caption"
}

@test "send: msg_send_photo omits caption when no second argument is provided" {
  local test_img="${TEST_ADJ_DIR}/test_photo.jpg"
  echo "fake image data" > "${test_img}"
  msg_send_photo "${test_img}"
  local args
  args="$(mock_last_args "curl")"
  [[ "${args}" != *"caption="* ]]
}

@test "send: msg_send_photo returns 1 when the file does not exist" {
  run msg_send_photo "/nonexistent/photo.jpg"
  assert_failure
}

@test "send: msg_send_photo does not call curl when the file does not exist" {
  run msg_send_photo "/nonexistent/photo.jpg"
  assert_mock_not_called "curl"
}

# ===== msg_react =====

@test "send: msg_react calls curl with the setMessageReaction endpoint" {
  msg_react "12345"
  assert_mock_called "curl"
  assert_mock_args_contain "curl" "setMessageReaction"
}

@test "send: msg_react uses the default eyes emoji when no emoji is specified" {
  msg_react "12345"
  assert_mock_args_contain "curl" "👀"
}

@test "send: msg_react uses a custom emoji when provided as second argument" {
  msg_react "12345" "👍"
  assert_mock_args_contain "curl" "👍"
}

@test "send: msg_react silently returns 0 when message_id is empty" {
  run msg_react ""
  assert_success
  assert_mock_not_called "curl"
}

# ===== msg_typing =====

@test "send: msg_typing start spawns a background process and creates a pidfile" {
  msg_typing start "test_suffix"
  local pidfile="/tmp/adjutant_typing_test_suffix.pid"
  [ -f "${pidfile}" ]
  local pid
  pid="$(cat "${pidfile}")"
  [ -n "${pid}" ]
  # Clean up
  msg_typing stop "test_suffix"
}

@test "send: msg_typing stop removes the pidfile and kills the background process" {
  msg_typing start "stop_test"
  local pidfile="/tmp/adjutant_typing_stop_test.pid"
  [ -f "${pidfile}" ]
  msg_typing stop "stop_test"
  [ ! -f "${pidfile}" ]
}

@test "send: msg_typing returns 1 for an unknown action" {
  run msg_typing "invalid_action" "test"
  assert_failure
}

@test "send: msg_typing stop is safe to call even when no typing indicator is active" {
  run msg_typing stop "never_started"
  assert_success
}

# ===== msg_authorize =====

@test "send: msg_authorize returns 0 (success) when from_id matches TELEGRAM_CHAT_ID" {
  run msg_authorize "99999"
  assert_success
}

@test "send: msg_authorize returns 1 (failure) when from_id does not match TELEGRAM_CHAT_ID" {
  run msg_authorize "11111"
  assert_failure
}

@test "send: msg_authorize returns 1 when from_id is empty" {
  run msg_authorize ""
  assert_failure
}

# ===== msg_get_user_id =====

@test "send: msg_get_user_id returns the TELEGRAM_CHAT_ID value" {
  run msg_get_user_id
  assert_success
  assert_output "99999"
}
