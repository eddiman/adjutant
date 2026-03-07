#!/bin/bash
# scripts/capabilities/schedule/notify_wrap.sh — Cron job notification wrapper
#
# Runs a scheduled script, captures its output and exit code, then sends a
# Telegram notification with the result. Used by schedule_install_one when
# a job has notify: true set in adjutant.yaml.
#
# Usage (by install.sh — not called directly):
#   bash notify_wrap.sh <job_name> <script_path>
#
# Notification format (success):
#   [job_name] OK: <first line of output>
#
# Notification format (failure):
#   [job_name] ERROR (rc=N): <first line of output>
#
# The wrapper always exits 0 so cron does not generate its own mail on failure.
# The real exit code is preserved in the notification message.

set -euo pipefail

JOB_NAME="${1:-unknown}"
SCRIPT_PATH="${2:-}"

if [ -z "${SCRIPT_PATH}" ]; then
  echo "Usage: notify_wrap.sh <job_name> <script_path>" >&2
  exit 1
fi

# Resolve ADJ_DIR and load common utilities
COMMON="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/common"
source "${COMMON}/paths.sh"
source "${COMMON}/logging.sh"

NOTIFY_SCRIPT="${ADJ_DIR}/scripts/messaging/telegram/notify.sh"

# Run the target script, writing output to a temp file to avoid pipe buffer
# deadlocks when the script produces large output (>64KB fills the pipe and
# causes both parent and child to block indefinitely).
TMP_OUT="$(mktemp)"
trap 'rm -f "${TMP_OUT}"' EXIT

SCRIPT_RC=0
bash "${SCRIPT_PATH}" >"${TMP_OUT}" 2>&1 || SCRIPT_RC=$?

# Extract first non-empty line for the notification summary
SUMMARY="$(grep -m1 '.' "${TMP_OUT}" || echo "(no output)")"

if [ "${SCRIPT_RC}" -eq 0 ]; then
  MESSAGE="[${JOB_NAME}] ${SUMMARY}"
else
  MESSAGE="[${JOB_NAME}] ERROR (rc=${SCRIPT_RC}): ${SUMMARY}"
fi

adj_log "schedule" "${MESSAGE}"

# Send Telegram notification — fire and forget, don't fail the wrapper
if [ -f "${NOTIFY_SCRIPT}" ]; then
  bash "${NOTIFY_SCRIPT}" "${MESSAGE}" >/dev/null 2>&1 || true
fi

# Always exit 0 — cron should not treat notification failures as errors
exit 0
