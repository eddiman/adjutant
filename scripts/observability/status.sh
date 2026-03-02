#!/bin/bash
# Check if Adjutant is running, paused, or killed, and show registered cron jobs.
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
