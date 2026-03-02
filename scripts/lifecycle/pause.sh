#!/bin/bash
# Pause Adjutant — all heartbeat jobs will skip until resumed.
# (Formerly kill.sh — renamed because it creates PAUSED, not KILLED)
# Usage: adjutant pause  (or scripts/lifecycle/pause.sh)
set -e

COMMON="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/common"
source "${COMMON}/paths.sh"
source "${COMMON}/lockfiles.sh"

set_paused
echo "Adjutant paused. All heartbeats will skip until resumed."
echo "Resume with: adjutant resume"
