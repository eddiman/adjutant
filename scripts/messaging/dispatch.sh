#!/bin/bash
# scripts/messaging/dispatch.sh — Backend-agnostic command dispatcher
#
# Called by the listener (any adaptor) when a new message or photo arrives.
# Routes to command handlers or natural language chat.
#
# This file is adaptor-independent — it uses msg_send_text(), msg_react(),
# msg_typing() etc. from whatever adaptor is loaded.
#
# Requires: ADJ_DIR (from paths.sh)
# Requires: adaptor functions (msg_send_text, msg_authorize, msg_typing, msg_react)
# Requires: cmd_* functions (from commands.sh)
# Requires: adj_log (from logging.sh)
#
# Provides:
#   dispatch_message  "text" "message_id" "from_id"
#   dispatch_photo    "from_id" "message_id" "local_file_path" ["caption"]

# State files
PENDING_REFLECT_FILE="${ADJ_DIR}/state/pending_reflect"
CURRENT_CHAT_JOB_FILE="/tmp/adjutant_current_chat_job.json"

# Rate limiting state
# Keeps a log of message timestamps (one epoch per line) in a rolling window file.
# Threshold is read from adjutant.yaml if yq is available; hard default is 10/min.
_RATE_LIMIT_FILE="${ADJ_DIR}/state/rate_limit_window"
_RATE_LIMIT_MAX="${ADJUTANT_RATE_LIMIT_MAX:-10}"     # messages per minute
_RATE_LIMIT_WINDOW=60                                  # seconds

# --- Rate limit check ---
# Appends current epoch to the window file, prunes entries older than the window,
# then returns 1 if the count exceeds the threshold.
_check_rate_limit() {
  local now
  now="$(date +%s)"
  local cutoff=$(( now - _RATE_LIMIT_WINDOW ))

  mkdir -p "${ADJ_DIR}/state"

  # Append current timestamp
  echo "${now}" >> "${_RATE_LIMIT_FILE}"

  # Prune timestamps outside the window (rewrite file in place)
  local tmp_file="${_RATE_LIMIT_FILE}.tmp.$$"
  awk -v cutoff="${cutoff}" '$1 > cutoff' "${_RATE_LIMIT_FILE}" > "${tmp_file}" 2>/dev/null \
    && mv "${tmp_file}" "${_RATE_LIMIT_FILE}" 2>/dev/null \
    || rm -f "${tmp_file}"

  # Count remaining entries in window
  local count
  count="$(wc -l < "${_RATE_LIMIT_FILE}" 2>/dev/null | tr -d ' ')"
  count="${count:-0}"

  if [ "${count}" -gt "${_RATE_LIMIT_MAX}" ]; then
    adj_log messaging "Rate limit exceeded: ${count} messages in last ${_RATE_LIMIT_WINDOW}s (max ${_RATE_LIMIT_MAX}). Dropping message."
    return 1
  fi

  return 0
}

# --- Kill any in-flight chat job superseded by a new message ---
_kill_inflight_job() {
  local current_msg_id="$1"

  if [ -f "${CURRENT_CHAT_JOB_FILE}" ]; then
    local old_pid old_msg_id
    # Parse the simple key=value file — no Python
    old_pid="$(grep -o '"pid":[0-9]*' "${CURRENT_CHAT_JOB_FILE}" 2>/dev/null | head -1 | cut -d: -f2)"
    old_msg_id="$(grep -o '"msg_id":[0-9]*' "${CURRENT_CHAT_JOB_FILE}" 2>/dev/null | head -1 | cut -d: -f2)"

    if [ -n "${old_pid}" ] && [ -n "${old_msg_id}" ] && [ "${old_msg_id}" != "${current_msg_id}" ]; then
      pkill -9 -P "${old_pid}" 2>/dev/null || true
      kill -9 "${old_pid}" 2>/dev/null || true
      adj_log messaging "Killed job PID=${old_pid} for msg=${old_msg_id} (superseded by msg=${current_msg_id})"
    fi
    rm -f "${CURRENT_CHAT_JOB_FILE}"
  fi
}

# --- Register a background chat job ---
_register_job() {
  local pid="$1"
  local msg_id="$2"
  printf '{"pid":%d,"msg_id":%d}\n' "${pid}" "${msg_id}" > "${CURRENT_CHAT_JOB_FILE}"
}

# --- Dispatch a text message ---
# Args: $1=text, $2=message_id, $3=from_id
dispatch_message() {
  local text="$1"
  local message_id="$2"
  local from_id="$3"

  # Check authorization
  if ! msg_authorize "${from_id}"; then
    adj_log messaging "Rejected unauthorized sender: ${from_id}"
    return
  fi

  # Rate limit check — drop message and log if over threshold
  if ! _check_rate_limit; then
    msg_send_text "I'm receiving messages too quickly. Please wait a moment before sending another." "${message_id}"
    return
  fi

  adj_log messaging "Received msg=${message_id}: ${text}"

  # Handle pending reflect confirmation flow
  if [ -f "${PENDING_REFLECT_FILE}" ]; then
    if [ "${text}" = "/confirm" ]; then
      cmd_reflect_confirm "${message_id}"
    else
      rm -f "${PENDING_REFLECT_FILE}"
      msg_send_text "No problem — I've cancelled the reflection." "${message_id}"
      adj_log messaging "Reflect cancelled."
    fi
    return
  fi

  # Command dispatch
  case "${text}" in
    /status)        cmd_status "${message_id}" ;;
    /pause)         cmd_pause "${message_id}" ;;
    /resume)        cmd_resume "${message_id}" ;;
    /kill)          cmd_kill "${message_id}" ;;
    /pulse)         cmd_pulse "${message_id}" ;;
    /restart)       cmd_restart "${message_id}" ;;
    /reflect)       cmd_reflect_request "${message_id}" ;;
    /help)          cmd_help "${message_id}" ;;
    /start)         cmd_help "${message_id}" ;;
    /model)         cmd_model "" "${message_id}" ;;
    /model\ *)      cmd_model "${text#/model }" "${message_id}" ;;
    /screenshot\ *) cmd_screenshot "${text#/screenshot }" "${message_id}" ;;
    /screenshot)    msg_send_text "Please provide a URL. Example: /screenshot https://example.com" "${message_id}" ;;
    /search\ *)     cmd_search "${text#/search }" "${message_id}" ;;
    /search)        msg_send_text "Please provide a search query. Example: /search latest AI news" "${message_id}" ;;
    /kb)            cmd_kb "list" "${message_id}" ;;
    /kb\ *)         cmd_kb ${text#/kb } "${message_id}" ;;
    /schedule)      cmd_schedule "list" "${message_id}" ;;
    /schedule\ *)   cmd_schedule "${text#/schedule }" "${message_id}" ;;
    *)
      # Natural language conversation
      adj_log messaging "Chat msg=${message_id}: ${text}"
      _kill_inflight_job "${message_id}"
      msg_react "${message_id}"
      (
        msg_typing start "chat_${message_id}"

        local chat_reply
        chat_reply="$(bash "${ADJ_DIR}/scripts/messaging/telegram/chat.sh" "${text}" 2>>"${ADJ_DIR}/state/adjutant.log")" || true

        msg_typing stop "chat_${message_id}"
        rm -f "${CURRENT_CHAT_JOB_FILE}"

        if [ -n "${chat_reply}" ]; then
          msg_send_text "${chat_reply}" "${message_id}"
          adj_log messaging "Reply sent for msg=${message_id}"
        else
          msg_send_text "I ran into a problem getting a response. Try again in a moment." "${message_id}"
          adj_log messaging "Fallback reply sent for msg=${message_id}"
        fi
      ) </dev/null >/dev/null 2>&1 &
      local new_job_pid=$!
      _register_job "${new_job_pid}" "${message_id}"
      disown "${new_job_pid}"
      ;;
  esac
}

# --- Dispatch a photo message ---
# This is a thin wrapper — the actual photo handling is adaptor-specific
# (Telegram needs to download via file_id, other backends may have URLs).
# The adaptor's photos.sh provides the concrete implementation.
# Args: $1=from_id, $2=message_id, $3=file_id_or_path, $4=caption
dispatch_photo() {
  local from_id="$1"
  local message_id="$2"
  local file_ref="$3"
  local caption="${4:-}"

  # Check authorization
  if ! msg_authorize "${from_id}"; then
    adj_log messaging "Rejected photo from unauthorized sender: ${from_id}"
    return
  fi

  # Delegate to the adaptor-specific photo handler
  # For Telegram: tg_handle_photo (from photos.sh)
  # Other adaptors would define their own handler
  if type tg_handle_photo &>/dev/null; then
    tg_handle_photo "${from_id}" "${message_id}" "${file_ref}" "${caption}"
  else
    adj_log messaging "No photo handler available for current adaptor"
    msg_send_text "Photo handling is not available." "${message_id}"
  fi
}
