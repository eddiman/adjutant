#!/bin/bash
# scripts/lifecycle/pulse_cron.sh — Cron wrapper for autonomous pulse
#
# Thin wrapper called by the crontab when the autonomous_pulse job fires.
# Runs the pulse prompt via opencode and writes output to the log.
#
# Registered in adjutant.yaml schedules: as the autonomous_pulse script.
# Managed via: adjutant schedule enable autonomous_pulse
#
# Requires: opencode on PATH, ADJ_DIR resolvable

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../common/paths.sh"

PULSE_PROMPT="${ADJ_DIR}/prompts/pulse.md"

if [ ! -f "${PULSE_PROMPT}" ]; then
  echo "ERROR: Pulse prompt not found at ${PULSE_PROMPT}" >&2
  exit 1
fi

if ! command -v opencode >/dev/null 2>&1; then
  echo "ERROR: opencode not found on PATH" >&2
  exit 1
fi

exec opencode run --print "${PULSE_PROMPT}" --cwd "${ADJ_DIR}"
