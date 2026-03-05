#!/bin/bash
# Check if Adjutant is running, paused, or killed, show registered scheduled jobs,
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

# Show registered scheduled jobs from adjutant.yaml schedules:
echo "Scheduled jobs:"
SCHEDULE_MANAGE="${ADJ_DIR}/scripts/capabilities/schedule/manage.sh"
if source "${SCHEDULE_MANAGE}" 2>/dev/null; then
  JOB_COUNT="$(schedule_count 2>/dev/null || echo "0")"
  if [ "${JOB_COUNT}" -eq 0 ]; then
    echo "  (none — add with: adjutant schedule add)"
  else
    # Get live crontab for cross-reference
    LIVE_CRONTAB="$(crontab -l 2>/dev/null || true)"
    while IFS=$'\t' read -r name desc sched script log enabled; do
      [ -z "${name}" ] && continue
      status_flag=""
      if [ "${enabled}" = "true" ]; then
        if ! echo "${LIVE_CRONTAB}" | grep -qF "# adjutant:${name}"; then
          status_flag=" [not in crontab — run: adjutant schedule sync]"
        fi
      else
        status_flag=" [DISABLED]"
      fi
      echo "  - ${name}${status_flag}: ${sched}"
      echo "    ${desc}"
      echo "    → ${script}"
    done < <(schedule_list 2>/dev/null)
  fi
else
  # Fallback: parse crontab directly if manage.sh unavailable
  CRON_JOBS="$(crontab -l 2>/dev/null | grep -v '^#' | grep -v '^$' | grep ".adjutant" || true)"
  if [ -z "${CRON_JOBS}" ]; then
    echo "  (none)"
  else
    echo "${CRON_JOBS}" | while IFS= read -r line; do
      echo "  - ${line}"
    done
  fi
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
