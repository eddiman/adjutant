#!/bin/bash
# scripts/messaging/telegram/chat.sh — Natural conversation handler
#
# Routes a free-form message through OpenCode (adjutant agent) and returns
# the reply on stdout.
#
# Usage: ./chat.sh "your message here"
#
# Session continuity:
#   - Session ID stored in state/telegram_session.json
#   - Sessions reused within a configurable timeout window
#   - After timeout, a fresh session is started
#
# Phase 2: Rewrites Python session management and output parsing with jq.

# No strict mode — opencode may return non-zero on warnings
# set -euo pipefail  # intentionally disabled

# --- Load common utilities ---
source "$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/common/paths.sh"
source "${ADJ_DIR}/scripts/common/env.sh"
source "${ADJ_DIR}/scripts/common/platform.sh"
source "${ADJ_DIR}/scripts/common/opencode.sh"

ensure_path

# --- Configuration ---
SESSION_FILE="${ADJ_DIR}/state/telegram_session.json"
MODEL_FILE="${ADJ_DIR}/state/telegram_model.txt"
SESSION_TIMEOUT_SECONDS=7200  # 2 hours (TODO: read from adjutant.yaml)

# --- Verify jq is available ---
if ! command -v jq &>/dev/null; then
  echo "Error: jq is required but not found." >&2
  exit 1
fi

# --- Get current model ---
get_model() {
  if [ -f "${MODEL_FILE}" ]; then
    cat "${MODEL_FILE}" | tr -d '\n'
  else
    echo "anthropic/claude-haiku-4-5"
  fi
}

MESSAGE="${1:-}"
if [ -z "${MESSAGE}" ]; then
  echo "Usage: chat.sh \"message\""
  exit 1
fi

# --- Session management (pure bash + jq, no Python) ---

get_session_id() {
  [ ! -f "${SESSION_FILE}" ] && echo "" && return

  local session_id last_epoch now age
  session_id="$(jq -r '.session_id // empty' "${SESSION_FILE}" 2>/dev/null)"
  last_epoch="$(jq -r '.last_message_epoch // 0' "${SESSION_FILE}" 2>/dev/null)"
  now="$(date +%s)"
  age=$((now - ${last_epoch%.*}))  # truncate decimals from Python-era files

  if [ ${age} -lt ${SESSION_TIMEOUT_SECONDS} ] && [ -n "${session_id}" ]; then
    echo "${session_id}"
  else
    echo ""
  fi
}

save_session() {
  local sid="$1"
  local now_epoch now_human
  now_epoch="$(date +%s)"
  now_human="$(date '+%H:%M %d.%m.%Y')"

  jq -n \
    --arg sid "${sid}" \
    --argjson epoch "${now_epoch}" \
    --arg human "${now_human}" \
    '{session_id: $sid, last_message_epoch: $epoch, last_message_at: $human}' \
    > "${SESSION_FILE}"
}

touch_session() {
  [ ! -f "${SESSION_FILE}" ] && return

  local now_epoch now_human
  now_epoch="$(date +%s)"
  now_human="$(date '+%H:%M %d.%m.%Y')"

  local tmp
  tmp="$(mktemp)"
  jq \
    --argjson epoch "${now_epoch}" \
    --arg human "${now_human}" \
    '.last_message_epoch = $epoch | .last_message_at = $human' \
    "${SESSION_FILE}" > "${tmp}" 2>/dev/null && mv "${tmp}" "${SESSION_FILE}" || rm -f "${tmp}"
}

# --- Run opencode, return plain-text reply ---

run_opencode() {
  local session_id="$1"
  local raw_file="$2"
  local err_file="$3"
  local model
  model="$(get_model)"
  local args=(run --agent adjutant --dir "${ADJ_DIR}" --format json --model "${model}")

  [ -n "${session_id}" ] && args+=(--session "${session_id}")
  args+=("${MESSAGE}")

  OPENCODE_TIMEOUT=120 opencode_run "${args[@]}" > "${raw_file}" 2>"${err_file}"
  return $?
}

parse_output() {
  local raw_file="$1"
  local sid_file="$2"
  local err_file="$3"

  local reply="" session_id="" error_type=""

  # Parse NDJSON output line by line using jq
  while IFS= read -r line; do
    [ -z "${line}" ] && continue

    # Try to parse as JSON
    local line_type line_sid
    line_type="$(printf '%s' "${line}" | jq -r '.type // empty' 2>/dev/null)" || continue

    # Capture session ID from first message that has one
    if [ -z "${session_id}" ]; then
      line_sid="$(printf '%s' "${line}" | jq -r '.sessionID // empty' 2>/dev/null)"
      [ -n "${line_sid}" ] && session_id="${line_sid}"
    fi

    # Check for errors
    if [ "${line_type}" = "error" ]; then
      local err_name err_msg
      err_name="$(printf '%s' "${line}" | jq -r '.error.name // empty' 2>/dev/null)"
      err_msg="$(printf '%s' "${line}" | jq -r '.error.data.message // empty' 2>/dev/null)"
      if [[ "${err_msg}" == *"Model not found"* ]] || [[ "${err_name}" == *"ModelNotFound"* ]]; then
        error_type="model_not_found"
      fi
    fi

    # Accumulate text parts
    if [ "${line_type}" = "text" ]; then
      local part
      part="$(printf '%s' "${line}" | jq -r '.part.text // empty' 2>/dev/null)"
      reply="${reply}${part}"
    fi
  done < "${raw_file}"

  # Also check stderr for model errors
  if [ -z "${error_type}" ] && [ -f "${err_file}" ]; then
    local err_content
    err_content="$(cat "${err_file}" 2>/dev/null)"
    if [[ "${err_content}" == *"Model not found"* ]] || [[ "${err_content}" == *"ProviderModelNotFoundError"* ]]; then
      error_type="model_not_found"
    fi
  fi

  # Write session ID
  printf '%s' "${session_id}" > "${sid_file}"

  # Output result
  if [ "${error_type}" = "model_not_found" ]; then
    printf '%s' "MODEL_ERROR:model_not_found"
  else
    printf '%s' "${reply}"
  fi
}

# --- Main ---

EXISTING_SESSION="$(get_session_id)"
RAW_FILE="$(mktemp)"
SID_FILE="$(mktemp)"
ERR_FILE="$(mktemp)"
REPLY_FILE="$(mktemp)"

OPENCODE_RC=0
run_opencode "${EXISTING_SESSION}" "${RAW_FILE}" "${ERR_FILE}" || OPENCODE_RC=$?

if [[ "${OPENCODE_RC}" -eq 124 ]]; then
  rm -f "${RAW_FILE}" "${SID_FILE}" "${ERR_FILE}" "${REPLY_FILE}"
  echo "Request timed out after 120s — the AI server may be slow. Try again in a moment."
  exit 0
fi

parse_output "${RAW_FILE}" "${SID_FILE}" "${ERR_FILE}" > "${REPLY_FILE}"

NEW_SID="$(cat "${SID_FILE}")"
REPLY="$(cat "${REPLY_FILE}")"

rm -f "${RAW_FILE}" "${SID_FILE}" "${ERR_FILE}" "${REPLY_FILE}"

# Check for model error
if [ "${REPLY}" = "MODEL_ERROR:model_not_found" ]; then
  CURRENT_MODEL="$(get_model)"
  echo "The model \`$CURRENT_MODEL\` is no longer available. Use /model to switch to a valid one."
  exit 0
fi

# Persist session
if [ -n "${NEW_SID}" ]; then
  if [ -z "${EXISTING_SESSION}" ]; then
    save_session "${NEW_SID}"
  else
    touch_session
  fi
fi

# Output reply
if [ -n "${REPLY}" ]; then
  printf '%s' "${REPLY}"
else
  echo "I didn't get a response — something may have gone wrong. Try again."
fi
