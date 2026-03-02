#!/bin/bash
# Analyze and rank news items using local pre-filter + Haiku

set -euo pipefail

# Resolve ADJUTANT_DIR and load common utilities
COMMON="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/common"
source "${COMMON}/paths.sh"
source "${COMMON}/lockfiles.sh"
source "${COMMON}/logging.sh"
source "${COMMON}/platform.sh"
ensure_path
source "${COMMON}/opencode.sh"

CONFIG_FILE="${ADJUTANT_DIR}/news_config.json"
STATE_DIR="${ADJUTANT_DIR}/state"
RAW_DIR="${STATE_DIR}/news_raw"
ANALYZED_DIR="${STATE_DIR}/news_analyzed"
DEDUP_FILE="${STATE_DIR}/news_seen_urls.json"
TODAY=$(date +%Y-%m-%d)
RAW_FILE="${RAW_DIR}/${TODAY}.json"
OUTPUT_FILE="${ANALYZED_DIR}/${TODAY}.json"

# Helper: log to stderr and adjutant.log
nlog() { adj_log "news-analyze" "$*"; echo "[$(date +%H:%M:%S)] $*" >&2; }

# Check if killed
check_killed || exit 1

# Check if raw data exists
if [[ ! -f "$RAW_FILE" ]]; then
  echo "Error: Raw news file not found: $RAW_FILE" >&2
  exit 1
fi

# Initialize dedup file if it doesn't exist
if [[ ! -f "$DEDUP_FILE" ]]; then
  echo '{"urls":[]}' > "$DEDUP_FILE"
fi

nlog "Starting news analysis for ${TODAY}"

# Load raw items
RAW_ITEMS=$(cat "$RAW_FILE")
TOTAL_COUNT=$(echo "$RAW_ITEMS" | jq 'length')
nlog "Loaded ${TOTAL_COUNT} raw items"

# === Step 1: Deduplication ===
nlog "Deduplicating..."

# Load seen URLs
SEEN_URLS=$(jq -r '.urls[].url' "$DEDUP_FILE")

# Filter out seen URLs
UNSEEN_ITEMS=$(echo "$RAW_ITEMS" | jq --arg seen_urls "$SEEN_URLS" '[
  .[] | select(.url as $u | ($seen_urls | split("\n") | index($u) == null))
]')

UNSEEN_COUNT=$(echo "$UNSEEN_ITEMS" | jq 'length')
nlog "After dedup: ${UNSEEN_COUNT} unseen items"

if [[ "$UNSEEN_COUNT" -eq 0 ]]; then
  nlog "No new items to analyze"
  echo '[]' > "$OUTPUT_FILE"
  exit 0
fi

# === Step 2: Bash Pre-filter ===
nlog "Pre-filtering with keywords..."

# Load keywords from config
KEYWORDS=$(jq -r '.keywords | map(ascii_downcase) | join("|")' "$CONFIG_FILE")

# Filter items by keyword match in title (case-insensitive)
FILTERED_ITEMS=$(echo "$UNSEEN_ITEMS" | jq --arg keywords "$KEYWORDS" '[
  .[] | select(.title | ascii_downcase | test($keywords))
]')

FILTERED_COUNT=$(echo "$FILTERED_ITEMS" | jq 'length')
nlog "After keyword filter: ${FILTERED_COUNT} items"

if [[ "$FILTERED_COUNT" -eq 0 ]]; then
  nlog "No items match keywords — falling back to top scored items"
  FILTERED_ITEMS=$(echo "$UNSEEN_ITEMS" | jq 'sort_by(-.score)')
fi

# Sort by score and take top N
PREFILTER_LIMIT=$(jq -r '.analysis.prefilter_limit // 10' "$CONFIG_FILE")
TOP_ITEMS=$(echo "$FILTERED_ITEMS" | jq --argjson limit "$PREFILTER_LIMIT" '
  sort_by(-.score) | .[:$limit]
')

TOP_COUNT=$(echo "$TOP_ITEMS" | jq 'length')
nlog "Sending top ${TOP_COUNT} items to Haiku..."

# === Step 3: Haiku Analysis ===

# Prepare input for Haiku
ITEMS_TEXT=$(echo "$TOP_ITEMS" | jq -r 'to_entries | map(
  "\(.key + 1). \(.value.title) — \(.value.url) — [score: \(.value.score), source: \(.value.source)]"
) | join("\n")')

TOP_N=$(jq -r '.analysis.top_n // 5' "$CONFIG_FILE")
MODEL=$(jq -r '.analysis.model // "anthropic/claude-haiku-4-5"' "$CONFIG_FILE")

# Create Haiku prompt
PROMPT="You are analyzing agentic AI news. Here are ${TOP_COUNT} candidate items:

${ITEMS_TEXT}

Pick the top ${TOP_N} most interesting/novel items. Prioritize: new models, frameworks, research papers, implementations, significant benchmarks.

Return ONLY a JSON array (no other text):
[
  {\"rank\": 1, \"title\": \"...\", \"url\": \"...\", \"summary\": \"One sentence why it matters\"}
]"

# Health-check the opencode server before making the API call.
# If degraded (e.g. post-sleep), this attempts a restart before we proceed.
nlog "Checking opencode server health..."
if ! opencode_health_check; then
  nlog "opencode server unrecoverable — aborting analysis"
  exit 1
fi

# Call Haiku via opencode with JSON format (90s timeout)
nlog "Calling ${MODEL}..."

HAIKU_RESPONSE=$(OPENCODE_TIMEOUT=90 opencode_run run "$PROMPT" --model "$MODEL" --format json 2>&1)
HAIKU_RC=$?

if [[ $HAIKU_RC -eq 124 ]]; then
  nlog "Haiku call timed out after 90s — aborting"
  exit 1
elif [[ $HAIKU_RC -ne 0 ]]; then
  nlog "Haiku call failed (rc=${HAIKU_RC}) — aborting"
  exit 1
fi

# Extract text from JSON events and concatenate
HAIKU_TEXT=$(echo "$HAIKU_RESPONSE" | jq -r 'select(.type == "text") | .part.text' | tr -d '\n')

# Extract JSON array from the text
HAIKU_JSON=$(echo "$HAIKU_TEXT" | grep -o '\[.*\]' | head -1 || true)

if [[ -z "$HAIKU_JSON" || "$HAIKU_JSON" == "null" ]]; then
  echo "Error: Haiku did not return valid JSON" >&2
  echo "Response was: $HAIKU_RESPONSE" >&2
  exit 1
fi

# Save analysis result
echo "$HAIKU_JSON" | jq '.' > "$OUTPUT_FILE"

SELECTED_COUNT=$(echo "$HAIKU_JSON" | jq 'length')
nlog "Analysis complete: ${SELECTED_COUNT} items selected → ${OUTPUT_FILE}"
