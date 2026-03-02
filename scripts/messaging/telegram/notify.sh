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

RESPONSE=$(curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
  --data-urlencode "chat_id=${TELEGRAM_CHAT_ID}" \
  --data-urlencode "text=${MESSAGE}")

# Check if successful
if echo "$RESPONSE" | grep -q '"ok":true'; then
  echo "Sent."
else
  echo "Error sending message:"
  echo "$RESPONSE" | jq '.' 2>/dev/null || echo "$RESPONSE"
  exit 1
fi
