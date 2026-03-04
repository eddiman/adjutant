#!/bin/bash
# Check if Adjutant is running, paused, or killed, show registered cron jobs,
# and surface the last autonomous activity (heartbeat, notification count, recent actions).
# Usage: adjutant status  (or scripts/observability/status.sh)

# Load common utilities
COMMON="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/common"
source "${COMMON}/paths.sh"
source "${COMMON}/lockfiles.sh"

# Check state using lockfiles.sh boolean queries
if is_killed; then
  echo "Status: KILLED"
elif is_paused; then
  echo "Status: PAUSED"
else
  echo "Status: RUNNING"
fi

echo ""

# Show registered cron jobs
echo "Registered cron jobs:"
CRON_JOBS=$(crontab -l 2>/dev/null | grep -v '^#' | grep -v '^$' | grep ".adjutant")

if [ -z "$CRON_JOBS" ]; then
  echo "  (none)"
else
  echo "$CRON_JOBS" | while IFS= read -r line; do
    # Parse cron schedule
    SCHEDULE=$(echo "$line" | awk '{print $1, $2, $3, $4, $5}')
    COMMAND=$(echo "$line" | awk '{$1=$2=$3=$4=$5=""; print $0}' | sed 's/^[[:space:]]*//')
    
    # Identify the job type
    if echo "$COMMAND" | grep -q "news_briefing.sh\|news/briefing.sh"; then
      JOB_NAME="News Briefing"
    elif echo "$COMMAND" | grep -q "prompts/pulse.md"; then
      JOB_NAME="Autonomous Pulse"
    elif echo "$COMMAND" | grep -q "prompts/review.md"; then
      JOB_NAME="Daily Review"
    else
      JOB_NAME="Unknown Job"
    fi
    
    # Format schedule description
    case "$SCHEDULE" in
      "0 8 * * 1-5")
        SCHEDULE_DESC="Every weekday at 08:00"
        ;;
      *)
        SCHEDULE_DESC="Schedule: $SCHEDULE"
        ;;
    esac
    
    echo "  - $JOB_NAME: $SCHEDULE_DESC"
    echo "    → $COMMAND"
  done
fi

echo ""
echo "Autonomous activity:"

# Last heartbeat
HEARTBEAT_FILE="${ADJ_DIR}/state/last_heartbeat.json"
if [ -f "${HEARTBEAT_FILE}" ]; then
  HB_TYPE="$(grep -o '"type":"[^"]*"' "${HEARTBEAT_FILE}" | head -1 | cut -d'"' -f4)"
  HB_TS="$(grep -o '"timestamp":"[^"]*"' "${HEARTBEAT_FILE}" | head -1 | cut -d'"' -f4)"
  echo "  Last cycle: ${HB_TYPE} at ${HB_TS}"
else
  echo "  No autonomous cycles recorded yet."
fi

# Today's notification count vs. budget
TODAY="$(date +%Y-%m-%d)"
NOTIFY_COUNT_FILE="${ADJ_DIR}/state/notify_count_${TODAY}.txt"
NOTIFY_COUNT=0
[ -f "${NOTIFY_COUNT_FILE}" ] && NOTIFY_COUNT="$(cat "${NOTIFY_COUNT_FILE}")"
NOTIFY_MAX="$(grep -E '^\s*max_per_day:' "${ADJ_DIR}/adjutant.yaml" 2>/dev/null | head -1 | grep -oE '[0-9]+' || echo 3)"
echo "  Notifications today: ${NOTIFY_COUNT}/${NOTIFY_MAX}"

# Last 5 actions from the ledger
ACTIONS_FILE="${ADJ_DIR}/state/actions.jsonl"
if [ -f "${ACTIONS_FILE}" ] && [ -s "${ACTIONS_FILE}" ]; then
  echo "  Recent actions:"
  tail -5 "${ACTIONS_FILE}" | while IFS= read -r line; do
    ACTION_TS="$(echo "${line}" | grep -o '"ts":"[^"]*"' | cut -d'"' -f4)"
    ACTION_TYPE="$(echo "${line}" | grep -o '"type":"[^"]*"' | cut -d'"' -f4)"
    echo "    ${ACTION_TS}  ${ACTION_TYPE}"
  done
fi
