#!/usr/bin/env bats
# tests/integration/chat.bats — Integration tests for scripts/messaging/telegram/chat.sh
#
# chat.sh is a standalone script that:
#   - Manages session continuity (session ID in state/telegram_session.json)
#   - Runs opencode with --format json and parses NDJSON output
#   - Detects model-not-found errors and reports them gracefully
#   - Returns the assembled text reply on stdout
#
# No set -e (intentional) — opencode may return non-zero on warnings.

load "${BATS_TEST_DIRNAME}/../test_helper/setup.bash"
load "${BATS_TEST_DIRNAME}/../test_helper/mocks.bash"

CHAT_SCRIPT="${PROJECT_ROOT}/scripts/messaging/telegram/chat.sh"

setup() {
  setup_test_env
  setup_mocks
  create_mock_opencode_reply "Hello from Adjutant" "test-session-abc"
}

teardown() {
  teardown_mocks
  teardown_test_env
}

# --- Happy path ---

@test "chat: returns the text reply assembled from opencode NDJSON output" {
  run bash "${CHAT_SCRIPT}" "Hello"
  assert_success
  assert_output --partial "Hello from Adjutant"
}

@test "chat: calls opencode with the --format json flag" {
  run bash "${CHAT_SCRIPT}" "Test"
  assert_success
  assert_mock_called "opencode"
  assert_mock_args_contain "opencode" "--format json"
}

@test "chat: calls opencode with the --agent adjutant flag" {
  run bash "${CHAT_SCRIPT}" "Test"
  assert_success
  assert_mock_args_contain "opencode" "--agent adjutant"
}

@test "chat: calls opencode with the --dir flag pointing to ADJ_DIR" {
  run bash "${CHAT_SCRIPT}" "Test"
  assert_success
  assert_mock_args_contain "opencode" "--dir ${TEST_ADJ_DIR}"
}

@test "chat: passes the user message as the last argument to opencode" {
  run bash "${CHAT_SCRIPT}" "What is the weather?"
  assert_success
  assert_mock_args_contain "opencode" "What is the weather?"
}

# --- Input validation ---

@test "chat: exits with error and prints usage when no message is provided" {
  run bash "${CHAT_SCRIPT}"
  assert_failure
  assert_output --partial "Usage:"
}

@test "chat: exits with error when called with an empty string argument" {
  run bash "${CHAT_SCRIPT}" ""
  assert_failure
  assert_output --partial "Usage:"
}

# --- Session management ---

@test "chat: creates a new session file when none exists" {
  [ ! -f "${TEST_ADJ_DIR}/state/telegram_session.json" ]
  run bash "${CHAT_SCRIPT}" "First message"
  assert_success
  [ -f "${TEST_ADJ_DIR}/state/telegram_session.json" ]
}

@test "chat: saves the session_id from opencode output into the session file" {
  run bash "${CHAT_SCRIPT}" "Save session"
  assert_success
  local saved_sid
  saved_sid="$(jq -r '.session_id' "${TEST_ADJ_DIR}/state/telegram_session.json")"
  [ "${saved_sid}" = "test-session-abc" ]
}

@test "chat: reuses an existing session when it is within the timeout window" {
  # Seed a session from 30 seconds ago (well within the 7200s timeout)
  local now
  now="$(date +%s)"
  local recent=$((now - 30))
  seed_telegram_session "existing-session-999" "${recent}"

  run bash "${CHAT_SCRIPT}" "Continue conversation"
  assert_success
  # opencode should be called with --session existing-session-999
  assert_mock_args_contain "opencode" "--session existing-session-999"
}

@test "chat: starts a fresh session when the existing one has expired beyond 7200 seconds" {
  # Seed a session from 3 hours ago (well past the 7200s timeout)
  local now
  now="$(date +%s)"
  local old=$((now - 10800))
  seed_telegram_session "expired-session-000" "${old}"

  run bash "${CHAT_SCRIPT}" "Fresh start"
  assert_success
  # opencode should NOT be called with --session expired-session-000
  local args
  args="$(mock_last_args "opencode")"
  [[ "${args}" != *"expired-session-000"* ]]
}

@test "chat: updates the session timestamp (touch) when reusing an existing session" {
  local now
  now="$(date +%s)"
  local recent=$((now - 60))
  seed_telegram_session "touch-session-111" "${recent}"

  run bash "${CHAT_SCRIPT}" "Touch test"
  assert_success

  local updated_epoch
  updated_epoch="$(jq -r '.last_message_epoch' "${TEST_ADJ_DIR}/state/telegram_session.json")"
  # The updated epoch should be more recent than the seeded one
  [ "${updated_epoch}" -ge "${now}" ] || [ "${updated_epoch}" -ge "$((now - 2))" ]
}

# --- Model selection ---

@test "chat: uses the default model (anthropic/claude-haiku-4-5) when no model file exists" {
  run bash "${CHAT_SCRIPT}" "Default model"
  assert_success
  assert_mock_args_contain "opencode" "anthropic/claude-haiku-4-5"
}

@test "chat: uses the model from state/telegram_model.txt when it exists" {
  seed_model_file "anthropic/claude-sonnet-4-20250514"
  run bash "${CHAT_SCRIPT}" "Custom model"
  assert_success
  assert_mock_args_contain "opencode" "anthropic/claude-sonnet-4-20250514"
}

# --- Error handling ---

@test "chat: reports model-not-found error gracefully instead of crashing" {
  create_mock_opencode_model_error
  run bash "${CHAT_SCRIPT}" "Bad model"
  assert_success
  assert_output --partial "no longer available"
  assert_output --partial "/model"
}

@test "chat: returns a fallback message when opencode returns no text output" {
  create_mock_opencode '{"type":"session.create","sessionID":"empty-session"}'
  run bash "${CHAT_SCRIPT}" "Empty reply"
  assert_success
  assert_output --partial "didn't get a response"
}

@test "chat: does not crash when opencode returns an empty response (zero bytes)" {
  create_mock_opencode ""
  run bash "${CHAT_SCRIPT}" "Empty output"
  assert_success
  assert_output --partial "didn't get a response"
}

# --- opencode is called exactly once ---

@test "chat: calls opencode exactly once per invocation" {
  run bash "${CHAT_SCRIPT}" "Single call"
  assert_success
  assert_mock_call_count "opencode" 1
}
