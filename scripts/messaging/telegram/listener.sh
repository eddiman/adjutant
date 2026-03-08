#!/bin/bash
# scripts/messaging/telegram/listener.sh — Telegram polling loop (thin dispatcher)
#
# Phase 2 rewrite: 660 lines → ~120 lines.
# All logic is now in focused modules:
#   send.sh     — msg_send_text, msg_send_photo, msg_react, msg_typing
#   photos.sh   — tg_download_photo, tg_handle_photo
#   commands.sh — cmd_status, cmd_pause, cmd_pulse, etc.
#   dispatch.sh — dispatch_message, dispatch_photo (backend-agnostic)
#   adaptor.sh  — interface contract (default no-ops)
#
# This file is responsible ONLY for:
#   1. Loading common utilities and modules
#   2. Polling Telegram getUpdates API
#   3. Parsing updates (using jq — no Python)
#   4. Routing to dispatch_message / dispatch_photo
#
# Architecture: Standalone. No persistent server. Each command spawns an
# ephemeral process that exits when complete. Stopping the listener only
# orphans in-flight children, which complete or timeout on their own.

# Ensure Homebrew and common tool paths are available when run from Launch Agent
export PATH="/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"
export HOME="${HOME:-$(eval echo ~)}"
export TMPDIR="${TMPDIR:-/tmp}"

# --- Load common utilities ---
source "$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/common/paths.sh"
source "${ADJ_DIR}/scripts/common/env.sh"
source "${ADJ_DIR}/scripts/common/logging.sh"
source "${ADJ_DIR}/scripts/common/lockfiles.sh"
source "${ADJ_DIR}/scripts/common/platform.sh"
source "${ADJ_DIR}/scripts/common/opencode.sh"

# --- Load messaging modules ---
source "${ADJ_DIR}/scripts/messaging/adaptor.sh"           # Interface defaults
source "${ADJ_DIR}/scripts/messaging/telegram/send.sh"     # Overrides with Telegram impl
source "${ADJ_DIR}/scripts/messaging/telegram/photos.sh"   # Photo handling
source "${ADJ_DIR}/scripts/messaging/telegram/commands.sh" # /command handlers
source "${ADJ_DIR}/scripts/messaging/dispatch.sh"          # Backend-agnostic dispatcher

# --- Pre-flight checks ---
check_killed || exit 1

require_telegram_credentials || exit 1
# TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are now exported

# Verify jq is available (required for JSON parsing — replaces embedded Python)
if ! command -v jq &>/dev/null; then
  log_error telegram "jq is required but not found. Install with: brew install jq (macOS) or apt install jq (Linux)"
  exit 1
fi

# --- Single-instance guard ---
# Uses mkdir for atomic lock — prevents duplicate listeners from running
LISTENER_LOCK="${ADJ_DIR}/state/listener.lock"
if ! mkdir "${LISTENER_LOCK}" 2>/dev/null; then
  # Check if the lock holder is still alive (stale lock detection)
  local_lock_pid=""
  if [ -f "${LISTENER_LOCK}/pid" ]; then
    local_lock_pid="$(cat "${LISTENER_LOCK}/pid" 2>/dev/null)"
  fi
  if [ -n "${local_lock_pid}" ] && kill -0 "${local_lock_pid}" 2>/dev/null; then
    adj_log telegram "Another listener is already running (PID ${local_lock_pid}). Exiting."
    exit 1
  fi
  # Stale lock — previous listener crashed without cleanup
  adj_log telegram "Removing stale listener lock (PID ${local_lock_pid:-unknown} no longer running)"
  rm -rf "${LISTENER_LOCK}"
  mkdir "${LISTENER_LOCK}" 2>/dev/null || { adj_log telegram "Failed to acquire listener lock. Exiting."; exit 1; }
fi
echo $$ > "${LISTENER_LOCK}/pid"

# --- State ---
OFFSET_FILE="${ADJ_DIR}/state/telegram_offset"
mkdir -p "${ADJ_DIR}/state"

OFFSET=0
if [ -f "${OFFSET_FILE}" ]; then
  _raw_offset="$(cat "${OFFSET_FILE}" | tr -d '[:space:]')"
  # Reject anything that isn't a plain integer — corrupted file falls back to 0
  if [[ "${_raw_offset}" =~ ^[0-9]+$ ]]; then
    OFFSET="${_raw_offset}"
  else
    adj_log telegram "WARNING: corrupt offset file (value: '${_raw_offset}'), resetting to 0"
    echo "0" > "${OFFSET_FILE}"
  fi
fi

# Track last processed update_id to prevent duplicates
LAST_PROCESSED_ID=0

# --- Cleanup ---
RESP_FILE="/tmp/adjutant_tg_resp.$$"
trap 'rm -f "${RESP_FILE}"; rm -rf "${LISTENER_LOCK}"; adj_log telegram "Listener stopped."' EXIT
trap '' SIGCHLD

# --- Startup ---
adj_log telegram "Listener started (offset=${OFFSET})"
# Startup notification is sent by startup.sh — not here.
# Notifying here would spam on every crash-restart.

# Reaper counter: run opencode_reap every ~6 poll cycles (~1 minute)
# Interval reduced from 50 (~8 min) — runaway language-servers can consume
# several GB RSS within a minute, so 8 minutes was far too slow to catch them.
_REAP_COUNTER=0
_REAP_INTERVAL=6

# --- Main poll loop ---
while true; do
  # Check for kill signal each iteration
  if is_killed; then
    adj_log telegram "KILLED lockfile detected. Stopping listener."
    break
  fi

  # Periodic reaper: clean up orphaned bash-language-server processes
  _REAP_COUNTER=$((_REAP_COUNTER + 1))
  if [ "${_REAP_COUNTER}" -ge "${_REAP_INTERVAL}" ]; then
    _REAP_COUNTER=0
    opencode_reap
  fi

  # Poll Telegram — long-poll for up to 10s so the loop idles in the API
  # rather than spinning with sleep(1) between empty polls
  curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getUpdates?offset=${OFFSET}&timeout=10&allowed_updates=%5B%22message%22%5D" \
    -o "${RESP_FILE}" 2>/dev/null || true

  if [ ! -s "${RESP_FILE}" ]; then
    sleep 1
    continue
  fi

  # Verify response is valid JSON with ok=true
  if ! jq -e '.ok' "${RESP_FILE}" > /dev/null 2>&1; then
    sleep 1
    continue
  fi

  # Count updates
  local_count="$(jq '.result | length' "${RESP_FILE}" 2>/dev/null)"
  if [ -z "${local_count}" ] || [ "${local_count}" = "0" ]; then
    sleep 1
    continue
  fi

  # Process only the LAST update (matching original behavior — skip if behind)
  # Original listener processed only the last update to avoid replay storms
  last_idx=$((local_count - 1))

  update_id=""
  chat_id=""
  message_id=""
  update_id="$(jq -r ".result[${last_idx}].update_id" "${RESP_FILE}" 2>/dev/null)"

  # Always advance offset past all updates
  if [ -n "${update_id}" ] && [ "${update_id}" != "null" ]; then
    OFFSET=$((update_id + 1))
    echo "${OFFSET}" > "${OFFSET_FILE}"

    # Deduplication: skip if we've already processed this update_id
    if [ "${update_id}" -le "${LAST_PROCESSED_ID}" ] 2>/dev/null; then
      adj_log telegram "Skipping duplicate update_id=${update_id} (already processed)"
      sleep 1
      continue
    fi
    LAST_PROCESSED_ID="${update_id}"
  fi

  # Extract message fields
  chat_id="$(jq -r ".result[${last_idx}].message.chat.id // empty" "${RESP_FILE}" 2>/dev/null)"
  message_id="$(jq -r ".result[${last_idx}].message.message_id // empty" "${RESP_FILE}" 2>/dev/null)"

  [ -z "${chat_id}" ] || [ -z "${message_id}" ] && { sleep 1; continue; }

  # Check for photo
  has_photo="$(jq -r ".result[${last_idx}].message.photo // empty" "${RESP_FILE}" 2>/dev/null)"

  if [ -n "${has_photo}" ] && [ "${has_photo}" != "null" ]; then
    # Photo message — get highest resolution file_id (last in array)
    file_id=""
    caption=""
    file_id="$(jq -r ".result[${last_idx}].message.photo[-1].file_id // empty" "${RESP_FILE}" 2>/dev/null)"
    caption="$(jq -r ".result[${last_idx}].message.caption // empty" "${RESP_FILE}" 2>/dev/null)"

    if [ -n "${file_id}" ]; then
      dispatch_photo "${chat_id}" "${message_id}" "${file_id}" "${caption}"
    fi
  else
    # Text message
    text=""
    text="$(jq -r ".result[${last_idx}].message.text // empty" "${RESP_FILE}" 2>/dev/null)"

    if [ -n "${text}" ]; then
      dispatch_message "${text}" "${message_id}" "${chat_id}"
    fi
  fi
done

adj_log telegram "Listener exited."
