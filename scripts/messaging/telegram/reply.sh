#!/bin/bash
# scripts/messaging/telegram/reply.sh — Send a Telegram reply (with Markdown)
#
# Usage: ./reply.sh "Your message here"
#
# Phase 2: Uses common utilities instead of duplicated credential loading.

set -e

# --- Load common utilities ---
source "$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/common/paths.sh"
source "${ADJ_DIR}/scripts/common/env.sh"

require_telegram_credentials || exit 1

MESSAGE="${1}"
if [ -z "${MESSAGE}" ]; then
  echo "Usage: reply.sh \"message\""
  exit 1
fi

# Sanitise: strip control characters, limit to 4000 chars (Telegram message limit)
MESSAGE="$(printf '%s' "${MESSAGE}" | tr -d '\000-\010\013-\037\177' | cut -c1-4000)"

curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
  --data-urlencode "chat_id=${TELEGRAM_CHAT_ID}" \
  --data-urlencode "text=${MESSAGE}" \
  --data-urlencode "parse_mode=Markdown" \
  > /dev/null

echo "Replied."
