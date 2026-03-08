#!/bin/bash
# Adjutant — Website screenshot tool.
# Takes a screenshot of a URL and sends it to Telegram.
#
# Strategy:
#   1. Take a viewport screenshot (1280x900) — fits Telegram's sendPhoto limits
#   2. If sendPhoto fails (e.g. dimension/size issue), fall back to sendDocument
#      which has no dimension restrictions (max 50MB)
#
# Usage:
#   screenshot.sh <url> [caption]
#
# Called by:
#   - telegram commands.sh cmd_screenshot() for /screenshot <url> commands
#   - Claude (adjutant agent) via bash tool to proactively send screenshots
#
# Output: Sends photo/document to Telegram. Prints "OK:<filepath>" or "ERROR:<reason>" on stdout.

# Load common utilities
COMMON="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/common"
source "${COMMON}/paths.sh"
source "${COMMON}/env.sh"
source "${COMMON}/logging.sh"
source "${COMMON}/platform.sh"

ensure_path

LOG_FILE="${ADJ_DIR}/state/adjutant.log"
SCREENSHOTS_DIR="${ADJ_DIR}/screenshots"

# --- Args ---
URL="${1:-}"
CAPTION="${2:-}"

if [ -z "${URL}" ]; then
  echo "ERROR: No URL provided. Usage: screenshot.sh <url> [caption]"
  exit 1
fi

# Normalise URL — add https:// if missing
if [[ "${URL}" != http://* && "${URL}" != https://* ]]; then
  URL="https://${URL}"
fi

# --- Load credentials ---
require_telegram_credentials || { echo "ERROR: Missing bot credentials in .env"; exit 1; }

# --- Build output filename ---
mkdir -p "${SCREENSHOTS_DIR}"
DOMAIN="$(python3 -c "
from urllib.parse import urlparse
import sys
try:
    u = urlparse('${URL}')
    d = u.netloc.replace('www.', '').replace(':', '-')
    print(d[:40] if d else 'page')
except:
    print('page')
" 2>/dev/null || echo "page")"
TIMESTAMP="$(date '+%Y-%m-%d_%H-%M-%S')"
OUTFILE="${SCREENSHOTS_DIR}/${TIMESTAMP}_${DOMAIN}.png"

adj_log "screenshot" "Screenshot requested: ${URL}"

# --- Take screenshot via Playwright + auto cookie-banner dismissal ---
# Uses a custom Node script (playwright_screenshot.mjs) that:
#   1. Navigates to the URL
#   2. Scans all frames (incl. CMP iframes) for cookie accept buttons
#   3. Clicks the first match from a broad list of NO/EN accept labels
#   4. Takes a 1280x900 viewport screenshot
PW_SCRIPT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/playwright_screenshot.mjs"
PW_RESULT="$(node "${PW_SCRIPT}" "${URL}" "${OUTFILE}" 2>/tmp/adj_pw_err.txt)"
PW_EXIT=$?

if [ ${PW_EXIT} -ne 0 ] || [ ! -f "${OUTFILE}" ]; then
  PW_ERR="$(cat /tmp/adj_pw_err.txt 2>/dev/null | tail -3)"
  adj_log "screenshot" "Screenshot FAILED for ${URL}: ${PW_ERR}"
  echo "ERROR: Screenshot failed — ${PW_ERR:-${PW_RESULT}}"
  exit 1
fi

FILE_SIZE="$(file_size "${OUTFILE}")"
adj_log "screenshot" "Screenshot saved: ${OUTFILE} (${FILE_SIZE} bytes)"

# --- Vision analysis (when no manual caption provided) ---
# Runs before sending so the caption reflects actual visual content.
# The prompt instructs the model to look past cookie banners / overlays
# and describe what the page is actually about.
if [ -z "${CAPTION}" ]; then
  VISION_SCRIPT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/vision/vision.sh"
  VISION_PROMPT="Analyze this webpage screenshot. There may be a cookie consent banner, GDPR prompt, or other overlay in the foreground — ignore it and focus on the underlying page content behind it. Describe what the page is about in 1-3 concise sentences: the site name, main topic or purpose, and any key visible content (headlines, products, data, etc.). Be specific and factual."

  if [ -f "${VISION_SCRIPT}" ]; then
    adj_log "screenshot" "Running vision analysis on ${OUTFILE}"
    VISION_RESULT="$(bash "${VISION_SCRIPT}" "${OUTFILE}" "${VISION_PROMPT}" 2>/dev/null)"
    if [ -n "${VISION_RESULT}" ]; then
      CAPTION="${VISION_RESULT}"
      adj_log "screenshot" "Vision caption generated for ${URL}"
    else
      adj_log "screenshot" "Vision returned empty — falling back to URL caption"
      CAPTION="${URL}"
    fi
  else
    CAPTION="${URL}"
  fi
fi

# Telegram captions: max 1024 chars
CAPTION="$(printf '%s' "${CAPTION}" | cut -c1-1024)"

# --- Try sendPhoto first ---
SEND_RESPONSE="$(curl -s -X POST \
  "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendPhoto" \
  -F "chat_id=${TELEGRAM_CHAT_ID}" \
  -F "photo=@${OUTFILE};type=image/png" \
  -F "caption=${CAPTION}" 2>/dev/null)"

OK="$(echo "${SEND_RESPONSE}" | jq -r 'if .ok then "yes" else "no" end' 2>/dev/null || echo 'no')"

if [ "${OK}" = "yes" ]; then
  adj_log "screenshot" "Screenshot sent via sendPhoto for ${URL}"
  echo "OK:${OUTFILE}:::${CAPTION}"
  exit 0
fi

TG_ERR="$(echo "${SEND_RESPONSE}" | jq -r '.description // "unknown"' 2>/dev/null || echo 'unknown')"
adj_log "screenshot" "sendPhoto failed (${TG_ERR}), falling back to sendDocument"

# --- Fallback: sendDocument (no dimension limits, max 50MB) ---
SEND_RESPONSE2="$(curl -s -X POST \
  "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendDocument" \
  -F "chat_id=${TELEGRAM_CHAT_ID}" \
  -F "document=@${OUTFILE};type=image/png" \
  -F "caption=${CAPTION}" 2>/dev/null)"

OK2="$(echo "${SEND_RESPONSE2}" | jq -r 'if .ok then "yes" else "no" end' 2>/dev/null || echo 'no')"

if [ "${OK2}" = "yes" ]; then
  adj_log "screenshot" "Screenshot sent via sendDocument for ${URL}"
  echo "OK:${OUTFILE}:::${CAPTION}"
  exit 0
fi

TG_ERR2="$(echo "${SEND_RESPONSE2}" | jq -r '.description // "unknown"' 2>/dev/null || echo 'unknown')"
adj_log "screenshot" "sendDocument also failed for ${URL}: ${TG_ERR2}"
echo "ERROR: Could not send screenshot — sendPhoto: ${TG_ERR}, sendDocument: ${TG_ERR2}"
exit 1
