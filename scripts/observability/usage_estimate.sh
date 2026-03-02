#!/bin/bash
# Adjutant usage estimator for Claude Pro caps
# Session cap: 44k tokens / 5 hours
# Weekly cap: ~350k tokens heuristic
set -e

# Load common utilities
COMMON="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/common"
source "${COMMON}/paths.sh"
source "${COMMON}/platform.sh"

USAGE_LOG="${ADJ_DIR}/state/usage_log.jsonl"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Usage: ./usage_estimate.sh <operation> <input_tokens> <output_tokens>
# Example: ./usage_estimate.sh "pulse check" 3000 500

OPERATION="${1:-manual}"
INPUT_TOKENS="${2:-0}"
OUTPUT_TOKENS="${3:-0}"
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

if [ "$INPUT_TOKENS" -eq 0 ]; then
  echo "Usage: usage_estimate.sh <operation> <input_tokens> <output_tokens>"
  echo ""
  echo "Common estimates:"
  echo "  Pulse check:       3000 input,  500 output"
  echo "  Escalation:        5800 input,  600 output"
  echo "  Daily review:     10000 input, 1000 output"
  echo "  /reflect (Opus):  15000 input, 2000 output"
  echo "  Conversation (5m): 8000 input, 1500 output"
  exit 1
fi

TOTAL_TOKENS=$((INPUT_TOKENS + OUTPUT_TOKENS))

# API equivalent cost (for reference, not actual billing)
# Sonnet: $3/1M input, $15/1M output
# Opus: $5/1M input, $25/1M output
MODEL="${4:-sonnet}"
if [ "$MODEL" = "opus" ]; then
  COST_INPUT=$(echo "scale=4; $INPUT_TOKENS * 5 / 1000000" | bc)
  COST_OUTPUT=$(echo "scale=4; $OUTPUT_TOKENS * 25 / 1000000" | bc)
else
  COST_INPUT=$(echo "scale=4; $INPUT_TOKENS * 3 / 1000000" | bc)
  COST_OUTPUT=$(echo "scale=4; $OUTPUT_TOKENS * 15 / 1000000" | bc)
fi
COST_TOTAL=$(echo "scale=4; $COST_INPUT + $COST_OUTPUT" | bc)

# Log to JSONL
echo "{\"timestamp\":\"$TIMESTAMP\",\"operation\":\"$OPERATION\",\"model\":\"$MODEL\",\"input\":$INPUT_TOKENS,\"output\":$OUTPUT_TOKENS,\"total\":$TOTAL_TOKENS,\"cost_equiv\":$COST_TOTAL}" >> "$USAGE_LOG"

# Calculate session and weekly totals
SESSION_WINDOW_START=$(date_subtract 5 hours)
WEEK_START=$(date_subtract 7 days)

SESSION_TOTAL=$(grep -E "\"timestamp\":\"[^\"]+\"" "$USAGE_LOG" | \
  awk -F'"' -v start="$SESSION_WINDOW_START" '$4 >= start' | \
  grep -oE '"total":[0-9]+' | cut -d':' -f2 | \
  awk '{sum+=$1} END {print sum}')

WEEK_TOTAL=$(grep -E "\"timestamp\":\"[^\"]+\"" "$USAGE_LOG" | \
  awk -F'"' -v start="$WEEK_START" '$4 >= start' | \
  grep -oE '"total":[0-9]+' | cut -d':' -f2 | \
  awk '{sum+=$1} END {print sum}')

SESSION_TOTAL=${SESSION_TOTAL:-0}
WEEK_TOTAL=${WEEK_TOTAL:-0}

SESSION_CAP=44000
WEEK_CAP=350000

SESSION_PCT=$(echo "scale=1; $SESSION_TOTAL * 100 / $SESSION_CAP" | bc)
WEEK_PCT=$(echo "scale=1; $WEEK_TOTAL * 100 / $WEEK_CAP" | bc)

echo ""
echo -e "${GREEN}Logged:${NC} $OPERATION — $TOTAL_TOKENS tokens (\$${COST_TOTAL} equiv)"
echo ""
echo "Session usage (5h rolling): $SESSION_TOTAL / $SESSION_CAP tokens (${SESSION_PCT}%)"
echo "Weekly usage (7d rolling):  $WEEK_TOTAL / $WEEK_CAP tokens (${WEEK_PCT}%)"
echo ""

if (( $(echo "$SESSION_PCT > 80" | bc -l) )); then
  echo -e "${RED}⚠ Session cap approaching — slow down${NC}"
elif (( $(echo "$SESSION_PCT > 50" | bc -l) )); then
  echo -e "${YELLOW}Session usage moderate${NC}"
else
  echo -e "${GREEN}Session usage healthy${NC}"
fi
