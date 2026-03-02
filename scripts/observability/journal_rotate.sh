#!/bin/bash
# scripts/observability/journal_rotate.sh — Archive and compress old journal entries
#
# Rotates three targets:
#   1. journal/*.md          — daily journal entries → journal/.archive/
#   2. journal/news/*.md     — news briefings       → journal/news/.archive/
#   3. state/adjutant.log    — operational log       → state/adjutant.log.1.gz (keeps 3 rotations)
#
# Configuration (from adjutant.yaml):
#   journal.retention_days     — days to keep uncompressed (default: 30)
#   journal.news_retention_days — days to keep news entries (default: 14)
#   journal.log_max_size_kb    — rotate adjutant.log when it exceeds this size (default: 5120 = 5MB)
#   journal.log_rotations      — number of compressed log backups to keep (default: 3)
#
# Usage:
#   bash scripts/observability/journal_rotate.sh           # rotate all
#   bash scripts/observability/journal_rotate.sh --dry-run # show what would happen
#   bash scripts/observability/journal_rotate.sh --quiet   # suppress output (for cron)
#
# Exit codes:
#   0 — success (or nothing to do)
#   1 — fatal error (ADJ_DIR not found, etc.)

set -euo pipefail

# --- Bootstrap ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../common/paths.sh"
source "${SCRIPT_DIR}/../common/logging.sh"

# --- Defaults ---
DEFAULT_RETENTION_DAYS=30
DEFAULT_NEWS_RETENTION_DAYS=14
DEFAULT_LOG_MAX_SIZE_KB=5120
DEFAULT_LOG_ROTATIONS=3

# --- Parse args ---
DRY_RUN=false
QUIET=false

for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=true ;;
    --quiet)   QUIET=true ;;
    --help|-h)
      cat <<'EOF'
Usage: journal_rotate.sh [--dry-run] [--quiet]

Options:
  --dry-run   Show what would be archived/deleted without doing it
  --quiet     Suppress output (for cron jobs)
  --help      Show this help

Rotates old journal entries, news briefings, and the operational log.
Configuration is read from adjutant.yaml under the 'journal' key.
EOF
      exit 0
      ;;
    *)
      echo "Unknown option: $arg" >&2
      echo "Run with --help for usage." >&2
      exit 1
      ;;
  esac
done

# --- Helpers ---
_msg() {
  if [ "$QUIET" = false ]; then
    echo "$@"
  fi
}

# Read a YAML value using the same yaml_get pattern from helpers.sh
# Simple grep-based — no external YAML parser needed
_yaml_get() {
  local key="$1"
  local default="$2"
  local yaml_file="${ADJ_DIR}/adjutant.yaml"

  if [ ! -f "$yaml_file" ]; then
    echo "$default"
    return
  fi

  local value
  value=$(grep -E "^[[:space:]]*${key}:" "$yaml_file" 2>/dev/null | head -1 | sed 's/^[^:]*:[[:space:]]*//' | sed 's/[[:space:]]*#.*//' | tr -d '"'"'" || true)

  if [ -n "$value" ]; then
    echo "$value"
  else
    echo "$default"
  fi
}

# --- Load config ---
RETENTION_DAYS=$(_yaml_get "retention_days" "$DEFAULT_RETENTION_DAYS")
NEWS_RETENTION_DAYS=$(_yaml_get "news_retention_days" "$DEFAULT_NEWS_RETENTION_DAYS")
LOG_MAX_SIZE_KB=$(_yaml_get "log_max_size_kb" "$DEFAULT_LOG_MAX_SIZE_KB")
LOG_ROTATIONS=$(_yaml_get "log_rotations" "$DEFAULT_LOG_ROTATIONS")

# --- Directories ---
JOURNAL_DIR="${ADJ_DIR}/journal"
JOURNAL_ARCHIVE="${JOURNAL_DIR}/.archive"
NEWS_DIR="${JOURNAL_DIR}/news"
NEWS_ARCHIVE="${NEWS_DIR}/.archive"
LOG_FILE="${ADJ_DIR}/state/adjutant.log"

# --- Counters ---
ARCHIVED_COUNT=0
NEWS_ARCHIVED_COUNT=0
LOG_ROTATED=false

# ============================================================
# 1. Rotate main journal entries
# ============================================================
rotate_journal() {
  if [ ! -d "$JOURNAL_DIR" ]; then
    _msg "No journal directory found, skipping."
    return
  fi

  # Find .md files older than retention threshold
  local old_files
  old_files=$(find "$JOURNAL_DIR" -maxdepth 1 -name "*.md" -type f -mtime +"${RETENTION_DAYS}" 2>/dev/null || true)

  if [ -z "$old_files" ]; then
    _msg "Journal: nothing to archive (retention: ${RETENTION_DAYS} days)"
    return
  fi

  if [ "$DRY_RUN" = false ]; then
    mkdir -p "$JOURNAL_ARCHIVE"
  fi

  while IFS= read -r file; do
    [ -z "$file" ] && continue
    local basename
    basename="$(basename "$file")"

    if [ "$DRY_RUN" = true ]; then
      _msg "  [dry-run] Would archive: ${basename}"
    else
      gzip -c "$file" > "${JOURNAL_ARCHIVE}/${basename}.gz"
      rm "$file"
      adj_log "journal" "Archived: ${basename}"
    fi
    ARCHIVED_COUNT=$((ARCHIVED_COUNT + 1))
  done <<< "$old_files"

  _msg "Journal: archived ${ARCHIVED_COUNT} entries → .archive/"
}

# ============================================================
# 2. Rotate news journal entries
# ============================================================
rotate_news() {
  if [ ! -d "$NEWS_DIR" ]; then
    _msg "No news journal directory found, skipping."
    return
  fi

  local old_files
  old_files=$(find "$NEWS_DIR" -maxdepth 1 -name "*.md" -type f -mtime +"${NEWS_RETENTION_DAYS}" 2>/dev/null || true)

  if [ -z "$old_files" ]; then
    _msg "News:    nothing to archive (retention: ${NEWS_RETENTION_DAYS} days)"
    return
  fi

  if [ "$DRY_RUN" = false ]; then
    mkdir -p "$NEWS_ARCHIVE"
  fi

  while IFS= read -r file; do
    [ -z "$file" ] && continue
    local basename
    basename="$(basename "$file")"

    if [ "$DRY_RUN" = true ]; then
      _msg "  [dry-run] Would archive news: ${basename}"
    else
      gzip -c "$file" > "${NEWS_ARCHIVE}/${basename}.gz"
      rm "$file"
      adj_log "journal" "Archived news: ${basename}"
    fi
    NEWS_ARCHIVED_COUNT=$((NEWS_ARCHIVED_COUNT + 1))
  done <<< "$old_files"

  _msg "News:    archived ${NEWS_ARCHIVED_COUNT} entries → news/.archive/"
}

# ============================================================
# 3. Rotate operational log (state/adjutant.log)
# ============================================================
rotate_log() {
  if [ ! -f "$LOG_FILE" ]; then
    _msg "Log:     no adjutant.log found, skipping."
    return
  fi

  # Get file size in KB (portable across macOS/Linux)
  local size_kb
  if [ "$(uname -s)" = "Darwin" ]; then
    size_kb=$(( $(stat -f%z "$LOG_FILE") / 1024 ))
  else
    size_kb=$(( $(stat -c%s "$LOG_FILE") / 1024 ))
  fi

  if [ "$size_kb" -lt "$LOG_MAX_SIZE_KB" ]; then
    _msg "Log:     adjutant.log is ${size_kb}KB (threshold: ${LOG_MAX_SIZE_KB}KB), skipping."
    return
  fi

  if [ "$DRY_RUN" = true ]; then
    _msg "  [dry-run] Would rotate adjutant.log (${size_kb}KB > ${LOG_MAX_SIZE_KB}KB threshold)"
    return
  fi

  # Shift existing rotations: .3.gz → delete, .2.gz → .3.gz, .1.gz → .2.gz
  local i=$LOG_ROTATIONS
  while [ "$i" -gt 1 ]; do
    local prev=$((i - 1))
    if [ -f "${LOG_FILE}.${prev}.gz" ]; then
      mv "${LOG_FILE}.${prev}.gz" "${LOG_FILE}.${i}.gz"
    fi
    i=$((i - 1))
  done

  # Compress current log → .1.gz
  gzip -c "$LOG_FILE" > "${LOG_FILE}.1.gz"

  # Truncate (don't delete — avoids race with concurrent writers)
  : > "$LOG_FILE"

  # Clean up any rotations beyond the limit
  i=$((LOG_ROTATIONS + 1))
  while [ -f "${LOG_FILE}.${i}.gz" ]; do
    rm "${LOG_FILE}.${i}.gz"
    i=$((i + 1))
  done

  LOG_ROTATED=true
  adj_log "journal" "Rotated adjutant.log (was ${size_kb}KB)"
  _msg "Log:     rotated adjutant.log (${size_kb}KB → .1.gz, kept ${LOG_ROTATIONS} backups)"
}

# ============================================================
# Main
# ============================================================
main() {
  if [ "$DRY_RUN" = true ]; then
    _msg "=== Journal Rotation (dry run) ==="
  else
    _msg "=== Journal Rotation ==="
  fi

  rotate_journal
  rotate_news
  rotate_log

  if [ "$DRY_RUN" = false ]; then
    local total=$((ARCHIVED_COUNT + NEWS_ARCHIVED_COUNT))
    if [ "$total" -gt 0 ] || [ "$LOG_ROTATED" = true ]; then
      _msg "Done. Archived ${total} journal entries."
    else
      _msg "Nothing to rotate."
    fi
  fi
}

main
