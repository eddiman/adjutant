#!/bin/bash
# Daily agentic AI news briefing orchestrator

set -euo pipefail

# Resolve ADJUTANT_DIR and load common utilities
COMMON="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/common"
source "${COMMON}/paths.sh"
source "${COMMON}/lockfiles.sh"
source "${COMMON}/logging.sh"
source "${COMMON}/platform.sh"

CONFIG_FILE="${ADJUTANT_DIR}/news_config.json"
STATE_DIR="${ADJUTANT_DIR}/state"
ANALYZED_DIR="${STATE_DIR}/news_analyzed"
DEDUP_FILE="${STATE_DIR}/news_seen_urls.json"
JOURNAL_DIR="${ADJUTANT_DIR}/journal/news"
TODAY=$(date +%d.%m.%Y)
TODAY_FILE=$(date +%Y-%m-%d)  # Keep filename format for consistency
ANALYZED_FILE="${ANALYZED_DIR}/${TODAY_FILE}.json"
JOURNAL_FILE="${JOURNAL_DIR}/${TODAY_FILE}.md"

# Helper: log to stderr and adjutant.log
nlog() { adj_log "news" "$*"; echo "[$(date +%H:%M:%S)] $*" >&2; }

nlog "===== Agentic AI News Briefing: ${TODAY} ====="

# === Step 1: Check operational state ===
check_operational || exit 1

# === Step 2: Fetch news ===
nlog "Fetching news..."
"${ADJUTANT_DIR}/scripts/news/fetch.sh"

# === Step 3: Analyze news ===
nlog "Analyzing news..."
"${ADJUTANT_DIR}/scripts/news/analyze.sh"

# Check if analysis produced results
if [[ ! -f "$ANALYZED_FILE" ]]; then
  nlog "No analysis results found"
  exit 0
fi

ITEMS=$(cat "$ANALYZED_FILE")
ITEM_COUNT=$(echo "$ITEMS" | jq 'length')

if [[ "$ITEM_COUNT" -eq 0 ]]; then
  nlog "No interesting news today"
  exit 0
fi

nlog "Found ${ITEM_COUNT} items to deliver"

# === Step 4: Format markdown briefing ===
nlog "Formatting briefing..."

BRIEFING="🤖 Agentic AI News — ${TODAY}

$(echo "$ITEMS" | jq -r '.[] | "\(.rank). \(.title)\n   → \(.url)\n   \(.summary)\n"')"

# === Step 5: Write to journal ===
if jq -e '.delivery.journal == true' "$CONFIG_FILE" > /dev/null 2>&1; then
  nlog "Writing to journal..."
  echo "$BRIEFING" > "$JOURNAL_FILE"
fi

# === Step 6: Send Telegram notification ===
if jq -e '.delivery.telegram == true' "$CONFIG_FILE" > /dev/null 2>&1; then
  nlog "Sending Telegram notification..."
  "${ADJUTANT_DIR}/scripts/messaging/telegram/notify.sh" "$BRIEFING"
fi

# === Step 7: Update dedup cache ===
nlog "Updating dedup cache..."

# Load current cache
CACHE=$(cat "$DEDUP_FILE")

# Extract URLs from analyzed items (by looking them up in the raw file)
RAW_FILE="${STATE_DIR}/news_raw/${TODAY_FILE}.json"
NEW_URLS=$(cat "$RAW_FILE" | jq -c --argjson items "$ITEMS" '[
  .[] | select(.title as $t | $items | map(.title) | index($t) != null) | {
    url: .url,
    first_seen: (now | todate)
  }
]')

# Add new URLs to cache
UPDATED_CACHE=$(echo "$CACHE" | jq --argjson new "$NEW_URLS" '.urls += $new')

# Prune entries older than window_days
WINDOW_DAYS=$(jq -r '.deduplication.window_days // 30' "$CONFIG_FILE")
CUTOFF_TIMESTAMP=$(date_subtract_epoch "$WINDOW_DAYS" days)

PRUNED_CACHE=$(echo "$UPDATED_CACHE" | jq --argjson cutoff "$CUTOFF_TIMESTAMP" '{
  urls: [.urls[] | select(.first_seen | fromdateiso8601 > $cutoff)]
}')

echo "$PRUNED_CACHE" > "$DEDUP_FILE"

CACHE_SIZE=$(echo "$PRUNED_CACHE" | jq '.urls | length')
nlog "Dedup cache updated: ${CACHE_SIZE} URLs tracked"

# === Step 8: Cleanup old files ===
nlog "Cleaning up old files..."

RAW_RETENTION=$(jq -r '.cleanup.raw_retention_days // 7' "$CONFIG_FILE")
ANALYZED_RETENTION=$(jq -r '.cleanup.analyzed_retention_days // 7' "$CONFIG_FILE")

# Delete raw files older than retention period (find -mtime works the same on both platforms)
find "${STATE_DIR}/news_raw" -name "*.json" -mtime +${RAW_RETENTION} -delete 2>/dev/null || true
find "${STATE_DIR}/news_analyzed" -name "*.json" -mtime +${ANALYZED_RETENTION} -delete 2>/dev/null || true

nlog "Briefing complete!"
