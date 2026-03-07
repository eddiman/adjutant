#!/bin/bash
# scripts/lifecycle/review_cron.sh — Cron wrapper for autonomous daily review
#
# Thin wrapper called by the crontab when the autonomous_review job fires.
# Runs the review prompt via opencode and writes output to the log.
#
# Registered in adjutant.yaml schedules: as the autonomous_review script.
# Managed via: adjutant schedule enable autonomous_review
#
# Requires: opencode on PATH, ADJ_DIR resolvable

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../common/paths.sh"

REVIEW_PROMPT="${ADJ_DIR}/prompts/review.md"

if [ ! -f "${REVIEW_PROMPT}" ]; then
  echo "ERROR: Review prompt not found at ${REVIEW_PROMPT}" >&2
  exit 1
fi

if ! command -v opencode >/dev/null 2>&1; then
  echo "ERROR: opencode not found on PATH" >&2
  exit 1
fi

exec opencode run --dir "${ADJ_DIR}" "$(cat "${REVIEW_PROMPT}")"
