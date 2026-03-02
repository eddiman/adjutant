#!/usr/bin/env bats
# tests/integration/screenshot.bats — Integration tests for scripts/capabilities/screenshot/screenshot.sh
#
# screenshot.sh is a standalone script that:
#   - Takes a URL and optional caption
#   - Normalizes URL (adds https:// if missing)
#   - Uses python3 to parse domain for filename
#   - Runs npx playwright screenshot to capture the page
#   - Sends via curl sendPhoto, falls back to sendDocument on failure
#   - Outputs "OK:<filepath>" or "ERROR:<reason>"

load "${BATS_TEST_DIRNAME}/../test_helper/setup.bash"
load "${BATS_TEST_DIRNAME}/../test_helper/mocks.bash"

SCREENSHOT_SCRIPT="${PROJECT_ROOT}/scripts/capabilities/screenshot/screenshot.sh"

setup() {
  setup_test_env
  setup_mocks
  create_mock_curl_telegram_ok
  create_mock_npx "" 0
  create_mock_python3 "example.com"
}

teardown() {
  teardown_mocks
  teardown_test_env
}

# --- Happy path ---

@test "screenshot: outputs OK: with a file path on success" {
  run bash "${SCREENSHOT_SCRIPT}" "https://example.com"
  assert_success
  assert_output --partial "OK:"
}

@test "screenshot: calls npx playwright screenshot with the URL" {
  run bash "${SCREENSHOT_SCRIPT}" "https://example.com"
  assert_success
  assert_mock_called "npx"
  assert_mock_args_contain "npx" "playwright"
  assert_mock_args_contain "npx" "screenshot"
  assert_mock_args_contain "npx" "https://example.com"
}

@test "screenshot: creates the screenshot file in the screenshots/ directory" {
  run bash "${SCREENSHOT_SCRIPT}" "https://example.com"
  assert_success
  local screenshot_count
  screenshot_count="$(ls "${TEST_ADJ_DIR}/screenshots/"*.png 2>/dev/null | wc -l | tr -d ' ')"
  [ "${screenshot_count}" -ge 1 ]
}

@test "screenshot: sends the screenshot via curl sendPhoto" {
  run bash "${SCREENSHOT_SCRIPT}" "https://example.com"
  assert_success
  assert_mock_called "curl"
  assert_mock_args_contain "curl" "sendPhoto"
}

@test "screenshot: includes the bot token in the API URL" {
  run bash "${SCREENSHOT_SCRIPT}" "https://example.com"
  assert_success
  assert_mock_args_contain "curl" "test-token-123"
}

# --- URL normalization ---

@test "screenshot: prepends https:// when the URL has no protocol" {
  run bash "${SCREENSHOT_SCRIPT}" "example.com"
  assert_success
  assert_mock_args_contain "npx" "https://example.com"
}

@test "screenshot: preserves http:// URLs without modification" {
  run bash "${SCREENSHOT_SCRIPT}" "http://example.com"
  assert_success
  assert_mock_args_contain "npx" "http://example.com"
}

# --- Caption ---

@test "screenshot: uses the URL as default caption when none is provided" {
  run bash "${SCREENSHOT_SCRIPT}" "https://example.com"
  assert_success
  # The default caption contains the URL
  assert_mock_args_contain "curl" "example.com"
}

@test "screenshot: uses a custom caption when provided as second argument" {
  run bash "${SCREENSHOT_SCRIPT}" "https://example.com" "My custom caption"
  assert_success
  assert_mock_args_contain "curl" "My custom caption"
}

# --- Input validation ---

@test "screenshot: exits with error when no URL is provided" {
  run bash "${SCREENSHOT_SCRIPT}"
  assert_failure
  assert_output --partial "ERROR:"
  assert_output --partial "No URL provided"
}

# --- Playwright failure ---

@test "screenshot: outputs ERROR when playwright screenshot fails" {
  create_mock_npx "Error: page.goto: net::ERR_NAME_NOT_RESOLVED" 1
  run bash "${SCREENSHOT_SCRIPT}" "https://nonexistent.invalid"
  assert_failure
  assert_output --partial "ERROR:"
  assert_output --partial "Screenshot failed"
}

# --- sendPhoto fallback to sendDocument ---

@test "screenshot: falls back to sendDocument when sendPhoto returns an error" {
  # First curl call (sendPhoto) fails, second (sendDocument) succeeds
  _create_mock_custom "curl" '
echo "$@" >> "'"${MOCK_LOG}"'/curl.log"
printf "%s\n" "$@" > "'"${MOCK_LOG}"'/curl.args"
call_num=$(wc -l < "'"${MOCK_LOG}"'/curl.log" | tr -d " ")
if [ "$call_num" -eq 1 ]; then
  echo "{\"ok\":false,\"error_code\":400,\"description\":\"Bad Request: wrong file identifier\"}"
else
  echo "{\"ok\":true,\"result\":{\"message_id\":42}}"
fi
'
  run bash "${SCREENSHOT_SCRIPT}" "https://example.com"
  assert_success
  assert_output --partial "OK:"
  # Should have called curl twice (sendPhoto then sendDocument)
  assert_mock_call_count "curl" 2
}

# --- Credential handling ---

@test "screenshot: exits with error when credentials are missing from .env" {
  rm -f "${TEST_ADJ_DIR}/.env"
  run bash "${SCREENSHOT_SCRIPT}" "https://example.com"
  assert_failure
  assert_output --partial "ERROR:"
}

# --- Viewport configuration ---

@test "screenshot: uses 1280x900 viewport dimensions" {
  run bash "${SCREENSHOT_SCRIPT}" "https://example.com"
  assert_success
  assert_mock_args_contain "npx" "1280,900"
}
