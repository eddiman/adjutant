#!/bin/bash
# scripts/common/env.sh — Credential loading (replaces 5x copy-paste)
#
# Replaces the repeated pattern found in:
#   telegram_listener.sh, notify_telegram.sh, screenshot.sh,
#   telegram_reply.sh, and telegram_chat.sh (implicitly)
#
# Original pattern (duplicated 5 times):
#   TELEGRAM_BOT_TOKEN="$(grep -E '^TELEGRAM_BOT_TOKEN=' "${ENV_FILE}" | head -1 | cut -d '=' -f2- | tr -d "'\"")"
#
# Now:
#   source "${ADJ_DIR}/scripts/common/env.sh"
#   TELEGRAM_BOT_TOKEN="$(get_credential TELEGRAM_BOT_TOKEN)"
#
# Security: Uses grep-based extraction — never sources .env directly.

# Requires ADJ_DIR (from paths.sh)
if [ -z "${ADJ_DIR:-}" ]; then
  echo "Error: ADJ_DIR not set. Source paths.sh before env.sh." >&2
  return 1 2>/dev/null || exit 1
fi

_adj_env_file="${ADJ_DIR}/.env"

# Verify .env file exists
load_env() {
  if [ ! -f "${_adj_env_file}" ]; then
    echo "Error: ${_adj_env_file} not found." >&2
    echo "Create it from .env.example with your credentials." >&2
    return 1
  fi
  return 0
}

# Extract a single credential value by key name
# Uses the exact same grep/cut/tr chain from the original scripts
get_credential() {
  local key="$1"

  if [ ! -f "${_adj_env_file}" ]; then
    echo "Error: ${_adj_env_file} not found." >&2
    return 1
  fi

  grep -E "^${key}=" "${_adj_env_file}" | head -1 | cut -d '=' -f2- | tr -d "'\""
}

# Check if a credential is set (non-empty)
has_credential() {
  local key="$1"
  local value
  value="$(get_credential "$key")"
  [ -n "$value" ]
}

# Load and validate Telegram credentials (most common use case)
# Sets TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID
require_telegram_credentials() {
  load_env || return 1

  TELEGRAM_BOT_TOKEN="$(get_credential TELEGRAM_BOT_TOKEN)"
  TELEGRAM_CHAT_ID="$(get_credential TELEGRAM_CHAT_ID)"

  if [ -z "${TELEGRAM_BOT_TOKEN}" ] || [ -z "${TELEGRAM_CHAT_ID}" ]; then
    echo "Error: TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set in ${_adj_env_file}" >&2
    return 1
  fi

  export TELEGRAM_BOT_TOKEN TELEGRAM_CHAT_ID
}
