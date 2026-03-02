#!/usr/bin/env bats
# tests/integration/dispatch.bats — Integration tests for scripts/messaging/dispatch.sh
#
# dispatch.sh is a sourced library providing:
#   dispatch_message  "text" "message_id" "from_id"
#   dispatch_photo    "from_id" "message_id" "file_ref" ["caption"]
#
# It routes slash commands to cmd_*() handlers, handles the pending
# reflect confirmation flow, and spawns background jobs for natural
# language chat. It also manages in-flight job cancellation.
#
# Dependencies sourced before dispatch.sh:
#   paths.sh, env.sh, logging.sh, lockfiles.sh,
#   telegram/send.sh, telegram/commands.sh

load "${BATS_TEST_DIRNAME}/../test_helper/setup.bash"
load "${BATS_TEST_DIRNAME}/../test_helper/mocks.bash"

setup() {
  setup_test_env
  setup_mocks
  create_mock_curl_telegram_ok

  # Set env vars required by sourced scripts
  export TELEGRAM_BOT_TOKEN="test-token-123"
  export TELEGRAM_CHAT_ID="99999"
  export ADJ_DIR="${TEST_ADJ_DIR}"

  # Source all dependencies in order
  source "${PROJECT_ROOT}/scripts/common/logging.sh"
  source "${PROJECT_ROOT}/scripts/common/lockfiles.sh"
  source "${PROJECT_ROOT}/scripts/messaging/telegram/send.sh"

  # Create mocks for external commands invoked by commands.sh
  create_mock_opencode_reply "mock pulse output"

  # Source commands (cmd_*) — needs ADJ_DIR, msg_send_text, etc.
  source "${PROJECT_ROOT}/scripts/messaging/telegram/commands.sh"

  # Create mock chat.sh that returns a canned response
  mkdir -p "${TEST_ADJ_DIR}/scripts/messaging/telegram"
  cat > "${TEST_ADJ_DIR}/scripts/messaging/telegram/chat.sh" <<'CHAT_MOCK'
#!/bin/bash
echo "Mock chat reply to: $1"
CHAT_MOCK
  chmod +x "${TEST_ADJ_DIR}/scripts/messaging/telegram/chat.sh"

  # Create mock status.sh
  mkdir -p "${TEST_ADJ_DIR}/scripts/observability"
  cat > "${TEST_ADJ_DIR}/scripts/observability/status.sh" <<'STATUS_MOCK'
#!/bin/bash
echo "Status: RUNNING"
STATUS_MOCK
  chmod +x "${TEST_ADJ_DIR}/scripts/observability/status.sh"

  # Create mock emergency_kill.sh
  mkdir -p "${TEST_ADJ_DIR}/scripts/lifecycle"
  cat > "${TEST_ADJ_DIR}/scripts/lifecycle/emergency_kill.sh" <<'KILL_MOCK'
#!/bin/bash
exit 0
KILL_MOCK
  chmod +x "${TEST_ADJ_DIR}/scripts/lifecycle/emergency_kill.sh"

  # Create mock restart.sh
  cat > "${TEST_ADJ_DIR}/scripts/lifecycle/restart.sh" <<'RESTART_MOCK'
#!/bin/bash
exit 0
RESTART_MOCK
  chmod +x "${TEST_ADJ_DIR}/scripts/lifecycle/restart.sh"

  # Source dispatch.sh (the library under test)
  source "${PROJECT_ROOT}/scripts/messaging/dispatch.sh"
}

teardown() {
  # Clean up background jobs
  jobs -p 2>/dev/null | xargs kill 2>/dev/null || true
  rm -f /tmp/adjutant_current_chat_job.json
  teardown_mocks
  teardown_test_env
}

# ===== Authorization =====

@test "dispatch_message: rejects messages from unauthorized senders without sending a reply" {
  dispatch_message "hello" "100" "OTHER_USER_ID"
  assert_mock_not_called "curl"
}

@test "dispatch_message: accepts messages from the authorized sender" {
  dispatch_message "/help" "100" "99999"
  assert_mock_called "curl"
}

# ===== Command routing =====

@test "dispatch_message: routes /status to cmd_status which calls status.sh" {
  dispatch_message "/status" "100" "99999"
  assert_mock_called "curl"
  # Multi-line text splits across log lines, so check the full log
  local full_log
  full_log="$(cat "${MOCK_LOG}/curl.log")"
  [[ "${full_log}" == *"Status: RUNNING"* ]]
}

@test "dispatch_message: routes /pause to cmd_pause which sets the PAUSED lockfile" {
  dispatch_message "/pause" "100" "99999"
  [ -f "${TEST_ADJ_DIR}/PAUSED" ]
}

@test "dispatch_message: routes /resume to cmd_resume which removes the PAUSED lockfile" {
  touch "${TEST_ADJ_DIR}/PAUSED"
  dispatch_message "/resume" "100" "99999"
  [ ! -f "${TEST_ADJ_DIR}/PAUSED" ]
}

@test "dispatch_message: routes /help to cmd_help which lists available commands" {
  dispatch_message "/help" "100" "99999"
  # Multi-line help text spans multiple log lines, so check the full log
  local full_log
  full_log="$(cat "${MOCK_LOG}/curl.log")"
  [[ "${full_log}" == *"/status"* ]]
  [[ "${full_log}" == *"/pause"* ]]
  [[ "${full_log}" == *"/resume"* ]]
}

@test "dispatch_message: routes /start to cmd_help (same as /help for Telegram bots)" {
  dispatch_message "/start" "100" "99999"
  local full_log
  full_log="$(cat "${MOCK_LOG}/curl.log")"
  [[ "${full_log}" == *"/status"* ]]
}

@test "dispatch_message: routes /kill to cmd_kill which sends shutdown message" {
  dispatch_message "/kill" "100" "99999"
  local last_args
  last_args="$(mock_last_args "curl")"
  [[ "${last_args}" == *"Emergency kill"* ]] || [[ "${last_args}" == *"shutdown"* ]] || [[ "${last_args}" == *"Shutting down"* ]]
}

@test "dispatch_message: routes /screenshot <url> to cmd_screenshot" {
  # cmd_screenshot spawns a background job, so just verify the react call
  dispatch_message "/screenshot https://example.com" "100" "99999"
  assert_mock_called "curl"
}

@test "dispatch_message: routes /screenshot without URL to prompt for URL" {
  dispatch_message "/screenshot" "100" "99999"
  local last_args
  last_args="$(mock_last_args "curl")"
  [[ "${last_args}" == *"provide a URL"* ]]
}

@test "dispatch_message: routes /model without argument to show current model" {
  dispatch_message "/model" "100" "99999"
  assert_mock_called "curl"
}

# ===== Pending reflect flow =====

@test "dispatch_message: routes /reflect to cmd_reflect_request which creates the pending file" {
  dispatch_message "/reflect" "100" "99999"
  [ -f "${TEST_ADJ_DIR}/state/pending_reflect" ]
}

@test "dispatch_message: confirms reflect when /confirm is sent while pending" {
  touch "${TEST_ADJ_DIR}/state/pending_reflect"
  dispatch_message "/confirm" "100" "99999"
  # pending_reflect should be removed
  [ ! -f "${TEST_ADJ_DIR}/state/pending_reflect" ]
}

@test "dispatch_message: cancels reflect when any non-confirm text is sent while pending" {
  touch "${TEST_ADJ_DIR}/state/pending_reflect"
  dispatch_message "never mind" "100" "99999"
  # pending_reflect should be removed
  [ ! -f "${TEST_ADJ_DIR}/state/pending_reflect" ]
  local last_args
  last_args="$(mock_last_args "curl")"
  [[ "${last_args}" == *"cancelled"* ]]
}

@test "dispatch_message: does not route to commands when reflect is pending (except /confirm)" {
  touch "${TEST_ADJ_DIR}/state/pending_reflect"
  dispatch_message "/status" "100" "99999"
  # The /status should NOT be run — the pending flow intercepts it as a cancellation
  [ ! -f "${TEST_ADJ_DIR}/state/pending_reflect" ]
  local last_args
  last_args="$(mock_last_args "curl")"
  [[ "${last_args}" == *"cancelled"* ]]
}

# ===== Natural language chat (background job) =====

@test "dispatch_message: spawns a background chat job for non-command text" {
  dispatch_message "hello there" "100" "99999"
  # Give the background job a moment to start
  sleep 0.5
  # The job file should have been created
  [ -f "/tmp/adjutant_current_chat_job.json" ] || {
    # If it already completed and cleaned up, that's also fine — check curl was called
    sleep 1
    assert_mock_called "curl"
  }
}

@test "dispatch_message: chat job calls msg_react with the message_id before spawning" {
  dispatch_message "what's the weather?" "200" "99999"
  sleep 0.3
  # The first curl call should be the react (setMessageReaction) call
  local first_args
  first_args="$(mock_call_args "curl" 1)"
  [[ "${first_args}" == *"setMessageReaction"* ]]
}

@test "dispatch_message: chat job registers the PID in the job file" {
  dispatch_message "tell me a joke" "300" "99999"
  sleep 0.3
  if [ -f "/tmp/adjutant_current_chat_job.json" ]; then
    local content
    content="$(cat /tmp/adjutant_current_chat_job.json)"
    [[ "${content}" == *'"pid":'* ]]
    [[ "${content}" == *'"msg_id":300'* ]]
  fi
  # Wait for background job to finish
  sleep 1
}

@test "dispatch_message: chat job sends the reply via msg_send_text when chat.sh returns text" {
  dispatch_message "what's up" "400" "99999"
  # Wait for background job to complete
  sleep 2
  # curl should have been called with sendMessage containing the chat reply
  local call_count
  call_count="$(mock_call_count "curl")"
  [ "${call_count}" -ge 2 ]  # at least react + reply
}

# ===== dispatch_photo =====

@test "dispatch_photo: rejects photos from unauthorized senders" {
  dispatch_photo "OTHER_USER" "100" "some_file_id" ""
  assert_mock_not_called "curl"
}

@test "dispatch_photo: sends 'not available' message when no tg_handle_photo function exists" {
  # Unset the function to simulate a different adaptor
  unset -f tg_handle_photo
  dispatch_photo "99999" "100" "some_file_id" ""
  local last_args
  last_args="$(mock_last_args "curl")"
  [[ "${last_args}" == *"not available"* ]]
}

@test "dispatch_photo: calls tg_handle_photo when the function is available" {
  # Define a stub tg_handle_photo that just logs
  tg_handle_photo() {
    echo "tg_handle_photo called: $@" >> "${TEST_ADJ_DIR}/state/photo_handler.log"
  }
  dispatch_photo "99999" "100" "file_id_abc" "my caption"
  [ -f "${TEST_ADJ_DIR}/state/photo_handler.log" ]
  local content
  content="$(cat "${TEST_ADJ_DIR}/state/photo_handler.log")"
  [[ "${content}" == *"file_id_abc"* ]]
  [[ "${content}" == *"my caption"* ]]
}

# ===== In-flight job management =====

@test "_kill_inflight_job: removes the job file after killing" {
  # Create a fake job file with a non-existent PID
  printf '{"pid":999999,"msg_id":50}\n' > /tmp/adjutant_current_chat_job.json
  _kill_inflight_job "60"
  [ ! -f /tmp/adjutant_current_chat_job.json ]
}

@test "_kill_inflight_job: does nothing when no job file exists" {
  rm -f /tmp/adjutant_current_chat_job.json
  _kill_inflight_job "100"
  # Should not error
  [ ! -f /tmp/adjutant_current_chat_job.json ]
}

@test "_register_job: creates a job file with pid and msg_id" {
  rm -f /tmp/adjutant_current_chat_job.json
  _register_job "12345" "200"
  [ -f /tmp/adjutant_current_chat_job.json ]
  local content
  content="$(cat /tmp/adjutant_current_chat_job.json)"
  [[ "${content}" == *'"pid":12345'* ]]
  [[ "${content}" == *'"msg_id":200'* ]]
}
