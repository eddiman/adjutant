#!/bin/bash
# Adjutant — Web search via Brave Search API.
#
# Uses the Brave Search API to return structured web results without
# browser automation or bot-detection issues. Token-efficient: only
# title, URL, and description are extracted from the top N results.
#
# Usage:
#   search.sh <query> [count]
#
#   query  — the search query string (required)
#   count  — number of results to return (default: 5, max: 10)
#
# Called by:
#   - telegram commands.sh cmd_search() for /search <query> commands
#   - Claude (adjutant agent) via bash tool for inline web lookups
#
# Output: Prints "OK:<formatted results>" or "ERROR:<reason>" on stdout.
#
# Requires: BRAVE_API_KEY in .env

# Load common utilities
COMMON="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/common"
source "${COMMON}/paths.sh"
source "${COMMON}/env.sh"
source "${COMMON}/logging.sh"

# --- Args ---
QUERY="${1:-}"
COUNT="${2:-5}"

if [ -z "${QUERY}" ]; then
  echo "ERROR: No query provided. Usage: search.sh <query> [count]"
  exit 1
fi

# Clamp count to 1–10
if [ "${COUNT}" -lt 1 ] 2>/dev/null; then COUNT=1; fi
if [ "${COUNT}" -gt 10 ] 2>/dev/null; then COUNT=10; fi

# --- Load credentials ---
BRAVE_API_KEY="$(get_credential BRAVE_API_KEY)"
if [ -z "${BRAVE_API_KEY}" ]; then
  echo "ERROR: BRAVE_API_KEY not set in .env — get a free key at https://api.search.brave.com"
  exit 1
fi

adj_log "search" "Search requested: ${QUERY} (count=${COUNT})"

# --- URL-encode the query ---
# python3 handles UTF-8 characters (ø, ä, etc.) correctly
if command -v python3 &>/dev/null; then
  ENCODED_QUERY="$(python3 -c "import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1]))" "${QUERY}")"
else
  # Pure-bash fallback via curl's --data-urlencode (strips leading 'data=')
  ENCODED_QUERY="$(curl -s -G --data-urlencode "q=${QUERY}" --url "" 2>/dev/null | sed 's/^?q=//' || printf '%s' "${QUERY}" | tr ' ' '+')"
fi

# --- Call Brave Search API ---
TMP_RESPONSE="$(mktemp)"
trap 'rm -f "${TMP_RESPONSE}"' EXIT

HTTP_CODE="$(curl -s -w "%{http_code}" -o "${TMP_RESPONSE}" \
  --max-time 15 \
  "https://api.search.brave.com/res/v1/web/search?q=${ENCODED_QUERY}&count=${COUNT}&safesearch=moderate" \
  -H "Accept: application/json" \
  -H "X-Subscription-Token: ${BRAVE_API_KEY}" \
  2>/dev/null)"

if [ "${HTTP_CODE}" != "200" ]; then
  ERROR_MSG="$(jq -r '.message // .error // "unknown error"' "${TMP_RESPONSE}" 2>/dev/null || echo "HTTP ${HTTP_CODE}")"
  adj_log "search" "Brave API error (${HTTP_CODE}): ${ERROR_MSG}"
  echo "ERROR: Brave Search API returned ${HTTP_CODE} — ${ERROR_MSG}"
  exit 1
fi

# --- Extract and format results ---
# Pulls title, url, description from web.results[]
# Output is compact plain text — low token cost for the LLM
RESULT="$(jq -r '
  .web.results // [] |
  to_entries[] |
  "[\(.key + 1)] \(.value.title)\n    \(.value.url)\n    \(.value.description // "No description")\n"
' "${TMP_RESPONSE}" 2>/dev/null)"

if [ -z "${RESULT}" ]; then
  adj_log "search" "No results for: ${QUERY}"
  echo "OK:No results found for: ${QUERY}"
  exit 0
fi

RESULT_COUNT="$(jq -r '.web.results | length' "${TMP_RESPONSE}" 2>/dev/null || echo "?")"

adj_log "search" "Search returned ${RESULT_COUNT} results for: ${QUERY}"
echo "OK:Search results for \"${QUERY}\" (${RESULT_COUNT} results):

${RESULT}"
