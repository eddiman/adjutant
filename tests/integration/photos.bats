#!/usr/bin/env bats
# tests/integration/photos.bats — Integration tests for scripts/messaging/telegram/photos.sh
#
# photos.sh is a sourced library providing:
#   tg_download_photo  "file_id" → prints local file path on stdout
#   tg_handle_photo    "from_id" "message_id" "file_id" ["caption"]
#
# tg_download_photo calls curl twice:
#   1. getFile API to get file_path
#   2. Download the file from Telegram's file server
#
# tg_handle_photo orchestrates: authorize → react → download → vision → reply

load "${BATS_TEST_DIRNAME}/../test_helper/setup.bash"
load "${BATS_TEST_DIRNAME}/../test_helper/mocks.bash"

setup_file()    { setup_file_scripts_template; }
teardown_file() { teardown_file_scripts_template; }

setup() {
  setup_test_env
  setup_mocks

  export TELEGRAM_BOT_TOKEN="test-token-123"
  export TELEGRAM_CHAT_ID="99999"
  export ADJ_DIR="${TEST_ADJ_DIR}"

  # Source dependencies
  source "${PROJECT_ROOT}/scripts/common/logging.sh"
  source "${PROJECT_ROOT}/scripts/messaging/telegram/send.sh"

  # Create mock vision.sh that returns analysis text
  mkdir -p "${TEST_ADJ_DIR}/scripts/capabilities/vision"
  cat > "${TEST_ADJ_DIR}/scripts/capabilities/vision/vision.sh" <<'MOCK'
#!/bin/bash
echo "I see a cat sitting on a keyboard."
MOCK
  chmod +x "${TEST_ADJ_DIR}/scripts/capabilities/vision/vision.sh"

  # Source the library under test
  source "${PROJECT_ROOT}/scripts/messaging/telegram/photos.sh"
}

# Poll until the curl mock log contains a pattern (max 2s).
# Replaces unconditional sleep N in background-job tests.
_wait_for_log() {
  local pattern="$1"
  local i=0
  while (( i++ < 40 )); do
    grep -q "${pattern}" "${MOCK_LOG}/curl.log" 2>/dev/null && return 0
    sleep 0.05
  done
  return 1
}

# Poll until the adjutant log contains a pattern (max 1s).
_wait_for_adj_log() {
  local pattern="$1"
  local i=0
  while (( i++ < 20 )); do
    grep -q "${pattern}" "${TEST_ADJ_DIR}/state/adjutant.log" 2>/dev/null && return 0
    sleep 0.05
  done
  return 1
}

teardown() {
  jobs -p 2>/dev/null | xargs kill 2>/dev/null || true
  teardown_mocks
  teardown_test_env
}

# Helper: create a curl mock that handles getFile, file download, and other API calls
_setup_photo_curl() {
  local file_path="${1:-photos/file_0.jpg}"
  _create_mock_custom "curl" '
if echo "$@" | grep -q "getFile"; then
  # getFile API response
  echo "{\"ok\":true,\"result\":{\"file_id\":\"abc123\",\"file_path\":\"'"${file_path}"'\"}}"
elif echo "$@" | grep -q "\-o "; then
  # File download: write fake image data to the -o output file
  outfile=""
  prev=""
  for arg in "$@"; do
    if [ "$prev" = "-o" ]; then
      outfile="$arg"
      break
    fi
    prev="$arg"
  done
  if [ -n "$outfile" ]; then
    echo "FAKE_JPEG_DATA" > "$outfile"
  fi
else
  # Fallback: Telegram API calls (react, sendMessage, typing, etc.)
  echo "{\"ok\":true,\"result\":{\"message_id\":42}}"
fi
'
}

# ===== tg_download_photo =====

@test "tg_download_photo: calls the getFile API with the file_id" {
  _setup_photo_curl "photos/file_0.jpg"
  run tg_download_photo "abc123"
  assert_success
  local first_call
  first_call="$(mock_call_args "curl" 1)"
  [[ "${first_call}" == *"getFile"* ]]
  [[ "${first_call}" == *"abc123"* ]]
}

@test "tg_download_photo: returns a local file path on success" {
  _setup_photo_curl "photos/file_0.jpg"
  run tg_download_photo "abc123"
  assert_success
  # Output should be a path under photos/
  [[ "${output}" == *"/photos/"* ]]
}

@test "tg_download_photo: saves the file preserving the extension from the API response" {
  # jpg
  _setup_photo_curl "photos/file_0.jpg"
  run tg_download_photo "abc123"
  assert_success
  [[ "${output}" == *.jpg ]]
  # png
  _setup_photo_curl "photos/image.png"
  run tg_download_photo "abc123"
  assert_success
  [[ "${output}" == *.png ]]
}

@test "tg_download_photo: fails when getFile returns no file_path" {
  # Mock curl that returns empty result
  _create_mock_custom "curl" '
echo "{\"ok\":false,\"error_code\":400,\"description\":\"Bad Request: invalid file_id\"}"
'
  run tg_download_photo "bad_file_id"
  assert_failure
}

@test "tg_download_photo: fails when the downloaded file is empty" {
  _create_mock_custom "curl" '
call_num=$(wc -l < "'"${MOCK_LOG}"'/curl.log" | tr -d " ")
if [ "$call_num" -eq 1 ]; then
  echo "{\"ok\":true,\"result\":{\"file_id\":\"abc\",\"file_path\":\"photos/file.jpg\"}}"
elif echo "$@" | grep -q "\-o "; then
  # Download call: write EMPTY file
  outfile=""
  prev=""
  for arg in "$@"; do
    if [ "$prev" = "-o" ]; then
      outfile="$arg"
      break
    fi
    prev="$arg"
  done
  if [ -n "$outfile" ]; then
    touch "$outfile"  # empty file
  fi
fi
'
  run tg_download_photo "abc123"
  assert_failure
}

@test "tg_download_photo: includes the bot token in the file download URL" {
  _setup_photo_curl "photos/file_0.jpg"
  run tg_download_photo "abc123"
  assert_success
  local second_call
  second_call="$(mock_call_args "curl" 2)"
  [[ "${second_call}" == *"test-token-123"* ]]
}

# ===== tg_handle_photo =====

@test "tg_handle_photo: skips duplicate photos with same file_id (dedup guard)" {
  _setup_photo_curl "photos/file.jpg"
  # First call should proceed normally (logs "Photo received")
  tg_handle_photo "99999" "100" "file_abc" ""
  _wait_for_adj_log "Photo received" || true

  # Second call with the same file_id should be deduped
  tg_handle_photo "99999" "101" "file_abc" ""
  _wait_for_adj_log "Skipping duplicate"

  # Check the log for the dedup message
  grep -q "Skipping duplicate photo file_id=file_abc" "${TEST_ADJ_DIR}/state/adjutant.log"
}

@test "tg_handle_photo: reacts to the message with an emoji" {
  _setup_photo_curl "photos/file.jpg"
  tg_handle_photo "99999" "100" "file_abc" ""
  _wait_for_log "setMessageReaction"
  assert_mock_called "curl"
  local full_log
  full_log="$(cat "${MOCK_LOG}/curl.log")"
  [[ "${full_log}" == *"setMessageReaction"* ]]
}

@test "tg_handle_photo: sends the vision reply when analysis succeeds" {
  _setup_photo_curl "photos/file.jpg"
  tg_handle_photo "99999" "100" "file_abc" ""
  _wait_for_log "cat sitting on a keyboard"
  local full_log
  full_log="$(cat "${MOCK_LOG}/curl.log")"
  [[ "${full_log}" == *"cat sitting on a keyboard"* ]]
}

@test "tg_handle_photo: passes the caption as vision prompt when provided" {
  # Replace vision mock to echo the prompt it received
  cat > "${TEST_ADJ_DIR}/scripts/capabilities/vision/vision.sh" <<'MOCK'
#!/bin/bash
echo "Vision analysis with prompt: $2"
MOCK
  chmod +x "${TEST_ADJ_DIR}/scripts/capabilities/vision/vision.sh"

  _setup_photo_curl "photos/file.jpg"
  tg_handle_photo "99999" "100" "file_abc" "What breed is this cat?"
  _wait_for_log "What breed is this cat"
  local full_log
  full_log="$(cat "${MOCK_LOG}/curl.log")"
  [[ "${full_log}" == *"What breed is this cat?"* ]]
}

@test "tg_handle_photo: sends error message when download fails" {
  # curl mock: react succeeds, getFile fails, sendMessage succeeds
  _create_mock_custom "curl" '
if echo "$@" | grep -q "setMessageReaction"; then
  echo "{\"ok\":true}"
elif echo "$@" | grep -q "getFile"; then
  echo "{\"ok\":false,\"error_code\":400}"
else
  echo "{\"ok\":true,\"result\":{\"message_id\":42}}"
fi
'
  tg_handle_photo "99999" "100" "file_abc" ""
  # Poll for the error message in the curl log
  local i=0
  while (( i++ < 40 )); do
    local full_log
    full_log="$(cat "${MOCK_LOG}/curl.log" 2>/dev/null || true)"
    if [[ "${full_log}" == *"couldn't retrieve"* ]] || [[ "${full_log}" == *"Try again"* ]]; then
      break
    fi
    sleep 0.05
  done
  local full_log
  full_log="$(cat "${MOCK_LOG}/curl.log")"
  [[ "${full_log}" == *"couldn't retrieve"* ]] || [[ "${full_log}" == *"Try again"* ]]
}

@test "tg_handle_photo: sends fallback when vision analysis returns empty" {
  cat > "${TEST_ADJ_DIR}/scripts/capabilities/vision/vision.sh" <<'MOCK'
#!/bin/bash
# Return nothing
exit 1
MOCK
  chmod +x "${TEST_ADJ_DIR}/scripts/capabilities/vision/vision.sh"

  _setup_photo_curl "photos/file.jpg"
  tg_handle_photo "99999" "100" "file_abc" ""
  # Poll for the fallback message (vision failed → fallback sent)
  local i=0
  while (( i++ < 40 )); do
    local full_log
    full_log="$(cat "${MOCK_LOG}/curl.log" 2>/dev/null || true)"
    if [[ "${full_log}" == *"vision analysis failed"* ]] || [[ "${full_log}" == *"saved"* ]]; then
      break
    fi
    sleep 0.05
  done
  local full_log
  full_log="$(cat "${MOCK_LOG}/curl.log")"
  [[ "${full_log}" == *"vision analysis failed"* ]] || [[ "${full_log}" == *"saved"* ]]
}
