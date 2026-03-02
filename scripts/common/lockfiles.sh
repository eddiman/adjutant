#!/bin/bash
# scripts/common/lockfiles.sh — Centralized KILLED/PAUSED state management
#
# Replaces the inconsistent lockfile checks scattered across all scripts:
#   - telegram_listener.sh: checks KILLED only (no PAUSED)
#   - telegram.sh: checks KILLED only
#   - news_briefing.sh: checks BOTH (only script that does)
#   - fetch_news.sh: checks KILLED only
#   - analyze_news.sh: checks KILLED only
#   - startup.sh: checks KILLED (recovery mode), warns about PAUSED
#   - status.sh: checks PAUSED only (no KILLED!)
#   - kill.sh: creates PAUSED
#   - resume.sh: removes PAUSED
#   - emergency_kill.sh: creates KILLED
#
# Usage:
#   source "${ADJ_DIR}/scripts/common/lockfiles.sh"
#   check_operational || exit 1  # Exits if KILLED or PAUSED

# Requires ADJ_DIR (from paths.sh)
if [ -z "${ADJ_DIR:-}" ]; then
  echo "Error: ADJ_DIR not set. Source paths.sh before lockfiles.sh." >&2
  return 1 2>/dev/null || exit 1
fi

# Check if KILLED lockfile exists (hard stop — system is shut down)
# Returns 1 if killed, 0 if not
check_killed() {
  if [ -f "${ADJ_DIR}/KILLED" ]; then
    echo "KILLED lockfile exists at ${ADJ_DIR}/KILLED" >&2
    echo "Run startup.sh to restore Adjutant." >&2
    return 1
  fi
  return 0
}

# Check if PAUSED lockfile exists (soft stop — system is paused)
# Returns 1 if paused, 0 if not
check_paused() {
  if [ -f "${ADJ_DIR}/PAUSED" ]; then
    echo "Adjutant is paused (${ADJ_DIR}/PAUSED exists)." >&2
    return 1
  fi
  return 0
}

# Combined check: fails if KILLED or PAUSED
# Usage: check_operational || exit 1
check_operational() {
  check_killed || return 1
  check_paused || return 1
  return 0
}

# Boolean queries (for conditionals, no stderr output)
is_killed()      { [ -f "${ADJ_DIR}/KILLED" ]; }
is_paused()      { [ -f "${ADJ_DIR}/PAUSED" ]; }
is_operational() { ! is_killed && ! is_paused; }

# State mutation
set_paused() {
  touch "${ADJ_DIR}/PAUSED"
}

set_killed() {
  touch "${ADJ_DIR}/KILLED"
}

clear_paused() {
  rm -f "${ADJ_DIR}/PAUSED"
}

clear_killed() {
  rm -f "${ADJ_DIR}/KILLED"
}
