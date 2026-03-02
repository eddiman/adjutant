#!/bin/bash
# Resume Adjutant after a pause.
# Usage: adjutant resume  (or scripts/lifecycle/resume.sh)
set -e

COMMON="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/common"
source "${COMMON}/paths.sh"
source "${COMMON}/lockfiles.sh"

clear_paused
echo "Adjutant resumed. Heartbeats will run on next schedule."
