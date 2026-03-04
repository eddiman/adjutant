#!/bin/bash
# scripts/messaging/telegram/notify.sh — Send a Telegram notification
#
# Usage: ./notify.sh "Your message here"
#
# Phase 2: Uses common utilities instead of duplicated credential loading.

set -e

# --- Load common utilities ---
source "$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/common/paths.sh"
source "${ADJ_DIR}/scripts/common/env.sh"

require_telegram_credentials || exit 1

MESSAGE="${1}"
if [ -z "${MESSAGE}" ]; then
  echo "Usage: notify.sh \"message\""
  exit 1
fi

# Sanitise: strip control characters, limit to 4096 chars (Telegram limit)
MESSAGE="$(printf '%s' "${MESSAGE}" | tr -d '\000-\010\013-\037\177' | cut -c1-4096)"

# --- Notification budget guard ---
NOTIFY_TODAY="$(date +%Y-%m-%d)"
NOTIFY_COUNT_FILE="${ADJ_DIR}/state/notify_count_${NOTIFY_TODAY}.txt"
NOTIFY_COUNT=0
[ -f "${NOTIFY_COUNT_FILE}" ] && NOTIFY_COUNT="$(cat "${NOTIFY_COUNT_FILE}")"

# Read max_per_day from adjutant.yaml (default: 3)
NOTIFY_MAX=3
if [ -f "${ADJ_DIR}/adjutant.yaml" ]; then
  NOTIFY_YAML_VAL="$(grep -E '^\s*max_per_day:' "${ADJ_DIR}/adjutant.yaml" | head -1 | grep -oE '[0-9]+' || true)"
  [ -n "${NOTIFY_YAML_VAL}" ] && NOTIFY_MAX="${NOTIFY_YAML_VAL}"
fi

if [ "${NOTIFY_COUNT}" -ge "${NOTIFY_MAX}" ]; then
  echo "ERROR:budget_exceeded (${NOTIFY_COUNT}/${NOTIFY_MAX} sent today)"
  exit 1
fi

RESPONSE=$(curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
  --data-urlencode "chat_id=${TELEGRAM_CHAT_ID}" \
  --data-urlencode "text=${MESSAGE}")

# Check if successful
if echo "$RESPONSE" | grep -q '"ok":true'; then
  echo $(( NOTIFY_COUNT + 1 )) > "${NOTIFY_COUNT_FILE}"
  echo "Sent. ($(( NOTIFY_COUNT + 1 ))/${NOTIFY_MAX} today)"
else
  echo "Error sending message:"
  echo "$RESPONSE" | jq '.' 2>/dev/null || echo "$RESPONSE"
  exit 1
fi
