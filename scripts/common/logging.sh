#!/bin/bash
# scripts/common/logging.sh — Safe logging (fixes Python injection vulnerability)
#
# Replaces:
#   - fmt_ts() in telegram_listener.sh (lines 56-76) — Python heredoc with
#     triple-quote injection vulnerability (SECURITY_ASSESSMENT.md HIGH severity)
#   - Various inline log() functions scattered across scripts
#
# The original fmt_ts() passes $1 directly into a Python triple-quoted string:
#     raw = '''$1'''.strip()
# An attacker controlling $1 could inject ''' followed by arbitrary Python.
# This version uses pure bash/date — no Python, no injection.
#
# Usage:
#   source "${ADJ_DIR}/scripts/common/logging.sh"
#   adj_log "telegram" "Received message from user"
#   readable=$(fmt_ts "2026-02-26T14:30:00Z")

# Requires ADJ_DIR (from paths.sh)
if [ -z "${ADJ_DIR:-}" ]; then
  echo "Error: ADJ_DIR not set. Source paths.sh before logging.sh." >&2
  return 1 2>/dev/null || exit 1
fi

# Ensure state directory exists for log files
mkdir -p "${ADJ_DIR}/state"

# Primary log function — writes to adjutant.log
# Usage: adj_log "context" "message content"
adj_log() {
  local context="${1:-general}"
  shift
  local msg="$*"

  # Sanitize: strip control characters (except newline→space) to prevent log injection
  msg="$(printf '%s' "$msg" | tr -d '\000-\011\013-\037\177' | tr '\n' ' ')"

  echo "[$(date '+%H:%M %d.%m.%Y')] [${context}] ${msg}" >> "${ADJ_DIR}/state/adjutant.log"
}

# Portable timestamp formatting — pure bash/date, no Python
# Input:  ISO-8601 timestamps in various formats
# Output: "HH:MM DD.MM.YYYY" (matching Adjutant's existing format)
# Falls back to returning the original string if parsing fails
#
# Replaces the vulnerable fmt_ts() from telegram_listener.sh
fmt_ts() {
  local raw="$1"

  # Short-circuit: if empty, return empty
  [ -z "$raw" ] && return 0

  # Ensure ADJUTANT_OS is available
  if [ -z "${ADJUTANT_OS:-}" ]; then
    case "$(uname -s)" in
      Darwin) ADJUTANT_OS="macos" ;;
      Linux)  ADJUTANT_OS="linux" ;;
      *)      ADJUTANT_OS="unknown" ;;
    esac
  fi

  if [ "$ADJUTANT_OS" = "macos" ]; then
    # macOS date -jf: try common ISO-8601 variants
    date -jf "%Y-%m-%dT%H:%M:%SZ" "$raw" "+%H:%M %d.%m.%Y" 2>/dev/null && return 0
    date -jf "%Y-%m-%dT%H:%M:%S" "$raw" "+%H:%M %d.%m.%Y" 2>/dev/null && return 0
    date -jf "%Y-%m-%d %H:%M:%S" "$raw" "+%H:%M %d.%m.%Y" 2>/dev/null && return 0
    date -jf "%Y-%m-%d" "$raw" "+00:00 %d.%m.%Y" 2>/dev/null && return 0
  elif [ "$ADJUTANT_OS" = "linux" ]; then
    # GNU date -d: handles most ISO-8601 variants natively
    date -d "$raw" "+%H:%M %d.%m.%Y" 2>/dev/null && return 0
  fi

  # Fallback: return original string
  echo "$raw"
}

# Log an error — writes to log file AND stderr
log_error() {
  local context="${1:-general}"
  shift
  adj_log "$context" "ERROR: $*"
  echo "ERROR [${context}]: $*" >&2
}

# Log a warning — writes to log file only
log_warn() {
  local context="${1:-general}"
  shift
  adj_log "$context" "WARNING: $*"
}

# Log debug info — only if ADJUTANT_DEBUG or DEBUG is set
log_debug() {
  if [ -n "${ADJUTANT_DEBUG:-${DEBUG:-}}" ]; then
    local context="${1:-general}"
    shift
    adj_log "$context" "DEBUG: $*"
  fi
}
