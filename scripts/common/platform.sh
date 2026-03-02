#!/bin/bash
# scripts/common/platform.sh — OS detection and portable wrappers
#
# Replaces macOS-specific patterns found in:
#   usage_estimate.sh:  date -u -v-5H / date -u -v-7d (with fallback)
#   news_briefing.sh:   date -u -v-"${WINDOW_DAYS}d" (with fallback)
#   fetch_news.sh:      date -u -v-"${lookback_hours}H" (OSTYPE check)
#   fetch_agentic_news.sh: date -u -v-1d (NO fallback — broken on Linux)
#   telegram_listener.sh:  stat -f (implicitly via macOS assumption)
#
# Usage:
#   source "${ADJ_DIR}/scripts/common/platform.sh"
#   cutoff=$(date_subtract_epoch 24 hours)
#   modified=$(file_mtime "$filepath")

# Detect OS
ADJUTANT_OS="unknown"
case "$(uname -s)" in
  Darwin) ADJUTANT_OS="macos" ;;
  Linux)  ADJUTANT_OS="linux" ;;
esac
export ADJUTANT_OS

# Portable date subtraction → ISO-8601 string
# Usage: date_subtract 5 hours → "2026-02-26T05:30:00Z"
# Usage: date_subtract 7 days  → "2026-02-19T10:30:00Z"
date_subtract() {
  local amount="$1"
  local unit="$2"

  if [ "$ADJUTANT_OS" = "macos" ]; then
    local date_flag
    case "$unit" in
      hours|hour)     date_flag="-v-${amount}H" ;;
      days|day)       date_flag="-v-${amount}d" ;;
      minutes|minute) date_flag="-v-${amount}M" ;;
      seconds|second) date_flag="-v-${amount}S" ;;
      *) echo "Unknown unit: $unit" >&2; return 1 ;;
    esac
    date -u "$date_flag" +"%Y-%m-%dT%H:%M:%SZ"
  elif [ "$ADJUTANT_OS" = "linux" ]; then
    date -u -d "${amount} ${unit} ago" +"%Y-%m-%dT%H:%M:%SZ"
  else
    echo "Unsupported OS for date_subtract: $ADJUTANT_OS" >&2
    return 1
  fi
}

# Portable date subtraction → epoch seconds
# Usage: cutoff=$(date_subtract_epoch 24 hours)
# Replaces the OSTYPE-conditional pattern in fetch_news.sh
date_subtract_epoch() {
  local amount="$1"
  local unit="$2"

  if [ "$ADJUTANT_OS" = "macos" ]; then
    local date_flag
    case "$unit" in
      hours|hour)     date_flag="-v-${amount}H" ;;
      days|day)       date_flag="-v-${amount}d" ;;
      minutes|minute) date_flag="-v-${amount}M" ;;
      seconds|second) date_flag="-v-${amount}S" ;;
      *) echo "Unknown unit: $unit" >&2; return 1 ;;
    esac
    date -u "$date_flag" +%s
  elif [ "$ADJUTANT_OS" = "linux" ]; then
    date -u -d "${amount} ${unit} ago" +%s
  else
    echo "Unsupported OS for date_subtract_epoch: $ADJUTANT_OS" >&2
    return 1
  fi
}

# File modification time in epoch seconds
# Replaces: stat -f "%m" (macOS) vs stat -c "%Y" (Linux)
file_mtime() {
  local filepath="$1"
  if [ ! -e "$filepath" ]; then
    echo "0"
    return 1
  fi

  if [ "$ADJUTANT_OS" = "macos" ]; then
    stat -f "%m" "$filepath"
  elif [ "$ADJUTANT_OS" = "linux" ]; then
    stat -c "%Y" "$filepath"
  else
    echo "0"
    return 1
  fi
}

# File size in bytes
file_size() {
  local filepath="$1"
  if [ ! -e "$filepath" ]; then
    echo "0"
    return 1
  fi

  if [ "$ADJUTANT_OS" = "macos" ]; then
    stat -f "%z" "$filepath"
  elif [ "$ADJUTANT_OS" = "linux" ]; then
    stat -c "%s" "$filepath"
  else
    wc -c < "$filepath" | tr -d ' '
  fi
}

# Ensure PATH includes common tool locations
# Replaces the hardcoded PATH exports in telegram_listener.sh, screenshot.sh, etc.
ensure_path() {
  local dirs="/opt/homebrew/bin /opt/homebrew/sbin /usr/local/bin /usr/bin /bin /usr/sbin /sbin"
  for d in $dirs; do
    case ":${PATH}:" in
      *":${d}:"*) ;; # already present
      *) [ -d "$d" ] && PATH="${d}:${PATH}" ;;
    esac
  done
  export PATH
}
