#!/bin/bash
# Check if Adjutant is running, paused, or killed, show registered scheduled jobs,
# and surface the last autonomous activity (heartbeat, notification count, recent actions).
# Usage: adjutant status  (or scripts/observability/status.sh)

# Load common utilities
COMMON="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/common"
source "${COMMON}/paths.sh"
source "${COMMON}/lockfiles.sh"

# ── Cron → human-readable ─────────────────────────────────────────────────────
# Converts a 5-field cron expression to a short English description.
# Handles the patterns actually used in adjutant.yaml; falls back to raw expr.
_cron_human() {
  local expr="$1"
  local minute hour dom month dow
  read -r minute hour dom month dow <<< "${expr}"

  # Day-of-week helper: "1-5" → "weekdays", "0,6" or "6,0" → "weekends", "*" → "every day"
  local day_phrase
  case "${dow}" in
    "1-5")      day_phrase="weekdays" ;;
    "0,6"|"6,0") day_phrase="weekends" ;;
    "0")        day_phrase="Sundays" ;;
    "1")        day_phrase="Mondays" ;;
    "2")        day_phrase="Tuesdays" ;;
    "3")        day_phrase="Wednesdays" ;;
    "4")        day_phrase="Thursdays" ;;
    "5")        day_phrase="Fridays" ;;
    "6")        day_phrase="Saturdays" ;;
    "*")        day_phrase="every day" ;;
    *)          day_phrase="on dow=${dow}" ;;
  esac

  # Time helper: single or comma-separated hours with a fixed minute
  local time_phrase=""
  if [[ "${minute}" =~ ^[0-9]+$ && "${hour}" != "*" ]]; then
    local min_fmt
    printf -v min_fmt "%02d" "${minute}"
    if [[ "${hour}" == *","* ]]; then
      # Multiple hours: "9,17" → "09:00 and 17:00"
      local times=""
      IFS=',' read -ra hours <<< "${hour}"
      for h in "${hours[@]}"; do
        local hfmt
        printf -v hfmt "%02d" "${h}"
        times="${times:+${times} and }${hfmt}:${min_fmt}"
      done
      time_phrase="${times}"
    else
      local hfmt
      printf -v hfmt "%02d" "${hour}"
      time_phrase="${hfmt}:${min_fmt}"
    fi
  fi

  # Handle */N minute intervals
  if [[ "${minute}" == "*/"* && "${hour}" == "*" ]]; then
    local interval="${minute#*/}"
    echo "every ${interval} minutes"
    return
  fi

  # Handle hourly (minute fixed, hour=*)
  if [[ "${minute}" =~ ^[0-9]+$ && "${hour}" == "*" ]]; then
    echo "every hour at :${minute}"
    return
  fi

  if [ -n "${time_phrase}" ]; then
    echo "at ${time_phrase}, ${day_phrase}"
  else
    echo "${expr}"
  fi
}

# ── State ────────────────────────────────────────────────────────────────────
if is_killed; then
  echo "Adjutant has been killed and is not running."
elif is_paused; then
  echo "Adjutant is paused. Send /resume to bring it back."
else
  echo "Adjutant is up and running."
fi

echo ""

# ── Scheduled jobs ───────────────────────────────────────────────────────────
SCHEDULE_MANAGE="${ADJ_DIR}/scripts/capabilities/schedule/manage.sh"
if source "${SCHEDULE_MANAGE}" 2>/dev/null; then
  JOB_COUNT="$(schedule_count 2>/dev/null || echo "0")"
  if [ "${JOB_COUNT}" -eq 0 ]; then
    # No registered jobs — still check crontab for legacy pulse/review entries
    CRON_JOBS="$(crontab -l 2>/dev/null | grep -v '^#' | grep -v '^$' | grep -E "pulse\.md|review\.md" || true)"
    if [ -z "${CRON_JOBS}" ]; then
      echo "No scheduled jobs configured."
    else
      echo "Scheduled jobs:"
      echo "${CRON_JOBS}" | while IFS= read -r line; do
        if echo "${line}" | grep -q "pulse\.md"; then
          echo "  Autonomous Pulse"
        elif echo "${line}" | grep -q "review\.md"; then
          echo "  Daily Review"
        else
          echo "  ${line}"
        fi
      done
    fi
  else
    LIVE_CRONTAB="$(crontab -l 2>/dev/null || true)"
    active_jobs=""
    inactive_jobs=""

    while IFS=$'\t' read -r name desc sched _script _log enabled notify; do
      [ -z "${name}" ] && continue

      local_sched="$(_cron_human "${sched}")"
      notify_note=""
      [ "${notify}" = "true" ] && notify_note=" (notifies)"

      if [ "${enabled}" = "true" ]; then
        if ! echo "${LIVE_CRONTAB}" | grep -qF "# adjutant:${name}"; then
          inactive_jobs="${inactive_jobs}  ${name} — ${desc}, ${local_sched}${notify_note} [not in crontab]
"
        else
          active_jobs="${active_jobs}  ${name} — ${desc}, ${local_sched}${notify_note}
"
        fi
      else
        inactive_jobs="${inactive_jobs}  ${name} — ${desc}, ${local_sched}${notify_note} [disabled]
"
      fi
    done < <(schedule_list 2>/dev/null)

    if [ -n "${active_jobs}" ]; then
      echo "Active jobs:"
      printf "%s" "${active_jobs}"
    fi
    if [ -n "${inactive_jobs}" ]; then
      echo "Inactive jobs:"
      printf "%s" "${inactive_jobs}"
    fi
  fi
else
  CRON_JOBS="$(crontab -l 2>/dev/null | grep -v '^#' | grep -v '^$' | grep ".adjutant" || true)"
  if [ -z "${CRON_JOBS}" ]; then
    echo "No scheduled jobs configured."
  else
    echo "Scheduled jobs:"
    echo "${CRON_JOBS}" | while IFS= read -r line; do
      if echo "${line}" | grep -q "pulse\.md"; then
        echo "  Autonomous Pulse"
      elif echo "${line}" | grep -q "review\.md"; then
        echo "  Daily Review"
      else
        echo "  ${line}"
      fi
    done
  fi
fi

echo ""

# ── Autonomous activity ───────────────────────────────────────────────────────
echo "Autonomous activity:"
echo ""

HEARTBEAT_FILE="${ADJ_DIR}/state/last_heartbeat.json"
if [ -f "${HEARTBEAT_FILE}" ]; then
  HB_TYPE="$(grep -oE '"type"[[:space:]]*:[[:space:]]*"[^"]*"' "${HEARTBEAT_FILE}" | head -1 | sed 's/.*"[[:space:]]*:[[:space:]]*"\([^"]*\)"/\1/')"
  HB_TS_RAW="$(grep -oE '"timestamp"[[:space:]]*:[[:space:]]*"[^"]*"' "${HEARTBEAT_FILE}" | head -1 | sed 's/.*"[[:space:]]*:[[:space:]]*"\([^"]*\)"/\1/')"
  HB_TRIGGER="$(grep -oE '"trigger"[[:space:]]*:[[:space:]]*"[^"]*"' "${HEARTBEAT_FILE}" | head -1 | sed 's/.*"[[:space:]]*:[[:space:]]*"\([^"]*\)"/\1/')"
  HB_ACTION="$(grep -oE '"action"[[:space:]]*:[[:space:]]*"[^"]*"' "${HEARTBEAT_FILE}" | head -1 | sed 's/.*"[[:space:]]*:[[:space:]]*"\([^"]*\)"/\1/')"
  HB_PROJECT="$(grep -oE '"project"[[:space:]]*:[[:space:]]*"[^"]*"' "${HEARTBEAT_FILE}" | head -1 | sed 's/.*"[[:space:]]*:[[:space:]]*"\([^"]*\)"/\1/')"

  last_cycle_line="Last cycle: ${HB_TYPE} at ${HB_TS_RAW}"
  [ -n "${HB_PROJECT}" ] && last_cycle_line="${last_cycle_line} on ${HB_PROJECT}"
  [ -n "${HB_TRIGGER}" ] && last_cycle_line="${last_cycle_line}, triggered by ${HB_TRIGGER}"
  [ -n "${HB_ACTION}" ]  && last_cycle_line="${last_cycle_line}. ${HB_ACTION}"
  echo "${last_cycle_line}"
else
  echo "No autonomous cycles recorded yet."
fi

echo ""

# ── Notifications ────────────────────────────────────────────────────────────
TODAY="$(date +%Y-%m-%d)"
NOTIFY_COUNT_FILE="${ADJ_DIR}/state/notify_count_${TODAY}.txt"
NOTIFY_COUNT=0
[ -f "${NOTIFY_COUNT_FILE}" ] && NOTIFY_COUNT="$(cat "${NOTIFY_COUNT_FILE}")"
NOTIFY_MAX="$(grep -E '^\s*max_per_day:' "${ADJ_DIR}/adjutant.yaml" 2>/dev/null | head -1 | grep -oE '[0-9]+' || echo 3)"

echo "Notifications today: ${NOTIFY_COUNT}/${NOTIFY_MAX}"

echo ""

# ── Recent actions ───────────────────────────────────────────────────────────
ACTIONS_FILE="${ADJ_DIR}/state/actions.jsonl"
if [ -f "${ACTIONS_FILE}" ] && [ -s "${ACTIONS_FILE}" ]; then
  echo "Recent actions:"
  tail -5 "${ACTIONS_FILE}" | while IFS= read -r line; do
    ACTION_TS_RAW="$(echo "${line}" | grep -o '"ts":"[^"]*"' | cut -d'"' -f4)"
    ACTION_TYPE="$(echo "${line}" | grep -o '"type":"[^"]*"' | cut -d'"' -f4)"
    ACTION_AGENT="$(echo "${line}" | grep -o '"agent":"[^"]*"' | cut -d'"' -f4)"
    if [ -n "${ACTION_AGENT}" ]; then
      echo "  ${ACTION_TS_RAW} — ${ACTION_TYPE} (${ACTION_AGENT})"
    else
      echo "  ${ACTION_TS_RAW} — ${ACTION_TYPE}"
    fi
  done
fi
