#!/bin/bash
# scripts/common/paths.sh — Consistent ADJ_DIR resolution
#
# Source this FIRST before other common utilities.
# Replaces both the hardcoded "$HOME/.adjutant" pattern (8 scripts)
# and the relative BASH_SOURCE pattern (10 scripts) with one approach.
#
# Resolution order:
#   1. $ADJUTANT_HOME if set (explicit override)
#   2. Walk up from calling script to find .adjutant-root (tracked root marker)
#   3. Walk up from calling script to find adjutant.yaml (legacy fallback)
#   4. Fall back to $HOME/.adjutant (legacy)
#
# Usage:
#   source "$(dirname "${BASH_SOURCE[0]}")/../common/paths.sh"
#   # or from scripts/ level:
#   source "$(dirname "${BASH_SOURCE[0]}")/common/paths.sh"

resolve_adj_dir() {
  # 1. Explicit environment override
  if [ -n "${ADJUTANT_HOME:-}" ]; then
    echo "${ADJUTANT_HOME}"
    return 0
  fi

  # 2. Walk up from the calling script's directory
  local script_dir
  # BASH_SOURCE[1] is the script that sourced us
  if [ -n "${BASH_SOURCE[1]:-}" ]; then
    script_dir="$(cd "$(dirname "${BASH_SOURCE[1]}")" && pwd)"
  else
    script_dir="$(pwd)"
  fi

  local dir="$script_dir"
  while [ "$dir" != "/" ]; do
    if [ -f "$dir/.adjutant-root" ]; then
      echo "$dir"
      return 0
    fi
    dir="$(dirname "$dir")"
  done

  # 3. Walk up looking for adjutant.yaml (legacy — adjutant.yaml is now gitignored
  #    but may still be present in developer installs)
  dir="$script_dir"
  while [ "$dir" != "/" ]; do
    if [ -f "$dir/adjutant.yaml" ]; then
      echo "$dir"
      return 0
    fi
    dir="$(dirname "$dir")"
  done

  # 4. Legacy fallback
  echo "${HOME}/.adjutant"
}

ADJ_DIR="$(resolve_adj_dir)"
export ADJ_DIR

# Also export as ADJUTANT_DIR for scripts that use that name
# (news_briefing.sh, fetch_news.sh, analyze_news.sh, fetch_agentic_news.sh)
ADJUTANT_DIR="$ADJ_DIR"
export ADJUTANT_DIR

# Ensure the directory exists
if [ ! -d "$ADJ_DIR" ]; then
  echo "Error: Adjutant directory not found: $ADJ_DIR" >&2
  echo "Set ADJUTANT_HOME, or ensure .adjutant-root exists in the project root." >&2
  return 1 2>/dev/null || exit 1
fi
