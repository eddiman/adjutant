#!/bin/bash
# scripts/messaging/telegram/send.sh — Telegram send/react/typing primitives
#
# Implements the messaging adaptor interface (scripts/messaging/adaptor.sh)
# for Telegram. Extracted from the monolithic telegram_listener.sh.
#
# Requires: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID (set before sourcing)
# Requires: ADJ_DIR (from paths.sh)
#
# Provides:
#   msg_send_text  "message" [reply_to_message_id]
#   msg_send_photo "file_path" ["caption"]
#   msg_react      "message_id" ["emoji"]
#   msg_typing     start|stop  [pidfile_suffix]

# --- Send a text message ---
# Args: $1 = message text, $2 = optional reply-to message ID
msg_send_text() {
  local msg="$1"
  local reply_to="${2:-}"

  # Sanitize: strip control characters, limit to 4000 chars (Telegram limit)
  msg="$(printf '%s' "${msg}" | tr -d '\000-\010\013-\037\177' | cut -c1-4000)"

  local args=(
    -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage"
    --data-urlencode "chat_id=${TELEGRAM_CHAT_ID}"
    --data-urlencode "text=${msg}"
    --data-urlencode "parse_mode=Markdown"
  )

  if [ -n "${reply_to}" ]; then
    args+=(--data-urlencode "reply_to_message_id=${reply_to}")
  fi

  curl "${args[@]}" > /dev/null 2>&1
}

# --- Send a photo ---
# Args: $1 = file path to image, $2 = optional caption
msg_send_photo() {
  local filepath="$1"
  local caption="${2:-}"

  if [ ! -f "${filepath}" ]; then
    adj_log telegram "msg_send_photo: file not found: ${filepath}"
    return 1
  fi

  local args=(
    -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendPhoto"
    -F "chat_id=${TELEGRAM_CHAT_ID}"
    -F "photo=@${filepath}"
  )

  if [ -n "${caption}" ]; then
    args+=(-F "caption=${caption}")
  fi

  curl "${args[@]}" > /dev/null 2>&1
}

# --- Add a reaction emoji to a message ---
# Args: $1 = message ID, $2 = emoji (default: eyes)
msg_react() {
  local message_id="$1"
  local emoji="${2:-👀}"

  [ -z "${message_id}" ] && return 0

  # Fire in background — don't block the listener loop waiting for API response
  curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setMessageReaction" \
    -H "Content-Type: application/json" \
    -d "{\"chat_id\":${TELEGRAM_CHAT_ID},\"message_id\":${message_id},\"reaction\":[{\"type\":\"emoji\",\"emoji\":\"${emoji}\"}]}" \
    > /dev/null 2>&1 &
}

# --- Typing indicator management ---
# Uses a background loop that sends "typing" action every 4 seconds.
# Args: $1 = start|stop, $2 = pidfile suffix (for concurrent operations)
#
# Usage:
#   msg_typing start "photo_123"
#   ... do work ...
#   msg_typing stop "photo_123"

_typing_pidfile() {
  echo "/tmp/adjutant_typing_${1:-default}.pid"
}

msg_typing() {
  local action="$1"
  local suffix="${2:-default}"
  local pidfile
  pidfile="$(_typing_pidfile "${suffix}")"

  case "${action}" in
    start)
      # Kill any existing typing indicator for this suffix
      _typing_kill "${pidfile}"

      bash -c "
        while true; do
          curl -s -X POST \"https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendChatAction\" \
            --data-urlencode \"chat_id=${TELEGRAM_CHAT_ID}\" \
            --data-urlencode \"action=typing\" \
            > /dev/null 2>&1
          sleep 4
        done
      " </dev/null >/dev/null 2>&1 &
      echo $! > "${pidfile}"
      ;;
    stop)
      _typing_kill "${pidfile}"
      ;;
    *)
      return 1
      ;;
  esac
}

_typing_kill() {
  local pidfile="$1"
  [ -f "${pidfile}" ] || return 0
  local pid
  pid="$(cat "${pidfile}" 2>/dev/null)"
  rm -f "${pidfile}"
  if [ -n "${pid}" ]; then
    kill "${pid}" 2>/dev/null || true
    pkill -P "${pid}" 2>/dev/null || true
  fi
}

# --- Authorize a sender ---
# Telegram uses TELEGRAM_CHAT_ID for authorization
# Args: $1 = sender chat ID
msg_authorize() {
  local from_id="$1"
  [ "${from_id}" = "${TELEGRAM_CHAT_ID}" ]
}

# --- Get the authenticated user ID ---
msg_get_user_id() {
  echo "${TELEGRAM_CHAT_ID}"
}
