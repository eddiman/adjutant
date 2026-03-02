#!/usr/bin/env bats
# tests/unit/journal_rotate.bats — Tests for scripts/observability/journal_rotate.sh

load "${BATS_TEST_DIRNAME}/../test_helper/setup.bash"

setup() {
  setup_test_env
  source "${COMMON}/paths.sh"
  source "${COMMON}/logging.sh"

  ROTATE_SCRIPT="${ADJ_DIR}/scripts/observability/journal_rotate.sh"

  # Create journal directories
  mkdir -p "${ADJ_DIR}/journal"
  mkdir -p "${ADJ_DIR}/journal/news"
}

teardown() { teardown_test_env; }

# --- Helper: create a journal file with an old mtime ---
create_old_journal() {
  local name="$1"
  local days_ago="${2:-60}"
  local dir="${3:-${ADJ_DIR}/journal}"
  echo "# Journal entry for ${name}" > "${dir}/${name}"
  # Use touch -t to set mtime to N days ago
  local old_date
  if [ "$(uname -s)" = "Darwin" ]; then
    old_date=$(date -v-${days_ago}d "+%Y%m%d0000")
  else
    old_date=$(date -d "${days_ago} days ago" "+%Y%m%d0000")
  fi
  touch -t "$old_date" "${dir}/${name}"
}

create_recent_journal() {
  local name="$1"
  local dir="${2:-${ADJ_DIR}/journal}"
  echo "# Recent entry for ${name}" > "${dir}/${name}"
  # Default mtime = now, which is recent
}

# ============================================================
# --help flag
# ============================================================

@test "journal_rotate: --help exits successfully and shows usage" {
  run bash "$ROTATE_SCRIPT" --help
  assert_success
  assert_output --partial "Usage:"
  assert_output --partial "--dry-run"
  assert_output --partial "--quiet"
}

@test "journal_rotate: unknown flag exits with error" {
  run bash "$ROTATE_SCRIPT" --bogus
  assert_failure
  assert_output --partial "Unknown option"
}

# ============================================================
# Main journal rotation
# ============================================================

@test "journal_rotate: archives .md files older than retention threshold" {
  create_old_journal "2025-12-01.md" 60
  create_old_journal "2025-12-15.md" 45

  run bash "$ROTATE_SCRIPT"
  assert_success

  # Originals should be gone
  [ ! -f "${ADJ_DIR}/journal/2025-12-01.md" ]
  [ ! -f "${ADJ_DIR}/journal/2025-12-15.md" ]

  # Archives should exist
  [ -f "${ADJ_DIR}/journal/.archive/2025-12-01.md.gz" ]
  [ -f "${ADJ_DIR}/journal/.archive/2025-12-15.md.gz" ]
}

@test "journal_rotate: keeps recent journal files untouched" {
  create_recent_journal "2026-02-27.md"
  create_old_journal "2025-12-01.md" 60

  run bash "$ROTATE_SCRIPT"
  assert_success

  # Recent file should still exist
  [ -f "${ADJ_DIR}/journal/2026-02-27.md" ]
  # Old file should be archived
  [ ! -f "${ADJ_DIR}/journal/2025-12-01.md" ]
  [ -f "${ADJ_DIR}/journal/.archive/2025-12-01.md.gz" ]
}

@test "journal_rotate: reports nothing to archive when all files are recent" {
  create_recent_journal "2026-02-27.md"

  run bash "$ROTATE_SCRIPT"
  assert_success
  assert_output --partial "nothing to archive"
}

@test "journal_rotate: archived .gz file decompresses to original content" {
  create_old_journal "2025-11-01.md" 90

  run bash "$ROTATE_SCRIPT"
  assert_success

  # Decompress and verify content
  local content
  content=$(gzip -dc "${ADJ_DIR}/journal/.archive/2025-11-01.md.gz")
  [ "$content" = "# Journal entry for 2025-11-01.md" ]
}

@test "journal_rotate: logs archival to adjutant.log" {
  create_old_journal "2025-10-01.md" 120

  run bash "$ROTATE_SCRIPT"
  assert_success

  run cat "${ADJ_DIR}/state/adjutant.log"
  assert_output --partial "[journal] Archived: 2025-10-01.md"
}

@test "journal_rotate: does not archive non-.md files in journal/" {
  echo "some data" > "${ADJ_DIR}/journal/notes.txt"
  if [ "$(uname -s)" = "Darwin" ]; then
    touch -t "$(date -v-90d '+%Y%m%d0000')" "${ADJ_DIR}/journal/notes.txt"
  else
    touch -t "$(date -d '90 days ago' '+%Y%m%d0000')" "${ADJ_DIR}/journal/notes.txt"
  fi

  run bash "$ROTATE_SCRIPT"
  assert_success

  # .txt file should be untouched
  [ -f "${ADJ_DIR}/journal/notes.txt" ]
}

@test "journal_rotate: handles empty journal directory gracefully" {
  # journal/ exists but is empty
  run bash "$ROTATE_SCRIPT"
  assert_success
  assert_output --partial "nothing to archive"
}

# ============================================================
# News journal rotation
# ============================================================

@test "journal_rotate: archives old news briefing files" {
  create_old_journal "2025-11-01.md" 30 "${ADJ_DIR}/journal/news"

  run bash "$ROTATE_SCRIPT"
  assert_success

  [ ! -f "${ADJ_DIR}/journal/news/2025-11-01.md" ]
  [ -f "${ADJ_DIR}/journal/news/.archive/2025-11-01.md.gz" ]
}

@test "journal_rotate: keeps recent news files untouched" {
  create_recent_journal "2026-02-27.md" "${ADJ_DIR}/journal/news"

  run bash "$ROTATE_SCRIPT"
  assert_success

  [ -f "${ADJ_DIR}/journal/news/2026-02-27.md" ]
}

@test "journal_rotate: news uses shorter retention (14 days default) than main journal (30 days)" {
  # 20 days old — should be archived by news (14d) but kept by main journal (30d)
  create_old_journal "2026-02-07.md" 20 "${ADJ_DIR}/journal"
  create_old_journal "2026-02-07.md" 20 "${ADJ_DIR}/journal/news"

  run bash "$ROTATE_SCRIPT"
  assert_success

  # Main journal: 20 days < 30 day retention → kept
  [ -f "${ADJ_DIR}/journal/2026-02-07.md" ]
  # News: 20 days > 14 day retention → archived
  [ ! -f "${ADJ_DIR}/journal/news/2026-02-07.md" ]
  [ -f "${ADJ_DIR}/journal/news/.archive/2026-02-07.md.gz" ]
}

# ============================================================
# Log rotation (state/adjutant.log)
# ============================================================

@test "journal_rotate: skips log rotation when adjutant.log is below threshold" {
  echo "small log" > "${ADJ_DIR}/state/adjutant.log"

  run bash "$ROTATE_SCRIPT"
  assert_success
  assert_output --partial "skipping"

  # Log file should still be there, uncompressed
  [ -f "${ADJ_DIR}/state/adjutant.log" ]
  [ ! -f "${ADJ_DIR}/state/adjutant.log.1.gz" ]
}

@test "journal_rotate: rotates adjutant.log when it exceeds size threshold" {
  # Create a log file that exceeds 5MB default threshold
  # We'll use a custom tiny threshold via adjutant.yaml
  cat > "${ADJ_DIR}/adjutant.yaml" <<'YAML'
name: adjutant-test
log_max_size_kb: 1
YAML

  # Create a log larger than 1KB
  dd if=/dev/zero bs=1024 count=2 2>/dev/null | tr '\0' 'A' > "${ADJ_DIR}/state/adjutant.log"

  run bash "$ROTATE_SCRIPT"
  assert_success

  # Compressed backup should exist
  [ -f "${ADJ_DIR}/state/adjutant.log.1.gz" ]
  # Original should be truncated (empty or near-empty due to post-rotate log entry)
  local size
  size=$(wc -c < "${ADJ_DIR}/state/adjutant.log" | tr -d ' ')
  [ "$size" -lt 500 ]
}

@test "journal_rotate: log rotation shifts existing backups (.1→.2, .2→.3)" {
  cat > "${ADJ_DIR}/adjutant.yaml" <<'YAML'
name: adjutant-test
log_max_size_kb: 1
log_rotations: 3
YAML

  # Create a fake .1.gz backup
  echo "old backup 1" | gzip > "${ADJ_DIR}/state/adjutant.log.1.gz"

  # Create log larger than threshold
  dd if=/dev/zero bs=1024 count=2 2>/dev/null | tr '\0' 'B' > "${ADJ_DIR}/state/adjutant.log"

  run bash "$ROTATE_SCRIPT"
  assert_success

  # Old .1.gz should now be .2.gz
  [ -f "${ADJ_DIR}/state/adjutant.log.2.gz" ]
  # New .1.gz should contain current log
  [ -f "${ADJ_DIR}/state/adjutant.log.1.gz" ]

  # Verify the shifted backup has the old content
  local old_content
  old_content=$(gzip -dc "${ADJ_DIR}/state/adjutant.log.2.gz")
  [ "$old_content" = "old backup 1" ]
}

@test "journal_rotate: does not create log file when it doesn't exist" {
  rm -f "${ADJ_DIR}/state/adjutant.log"

  run bash "$ROTATE_SCRIPT"
  assert_success
  assert_output --partial "no adjutant.log found"
}

# ============================================================
# --dry-run mode
# ============================================================

@test "journal_rotate: --dry-run shows what would happen but makes no changes" {
  create_old_journal "2025-10-15.md" 90

  run bash "$ROTATE_SCRIPT" --dry-run
  assert_success
  assert_output --partial "dry-run"
  assert_output --partial "Would archive: 2025-10-15.md"

  # File should still exist — not actually archived
  [ -f "${ADJ_DIR}/journal/2025-10-15.md" ]
  [ ! -d "${ADJ_DIR}/journal/.archive" ]
}

@test "journal_rotate: --dry-run does not create archive directories" {
  create_old_journal "2025-10-15.md" 90
  create_old_journal "2025-10-15.md" 90 "${ADJ_DIR}/journal/news"

  run bash "$ROTATE_SCRIPT" --dry-run
  assert_success

  [ ! -d "${ADJ_DIR}/journal/.archive" ]
  [ ! -d "${ADJ_DIR}/journal/news/.archive" ]
}

# ============================================================
# --quiet mode
# ============================================================

@test "journal_rotate: --quiet suppresses all output" {
  create_old_journal "2025-10-15.md" 90

  run bash "$ROTATE_SCRIPT" --quiet
  assert_success
  assert_output ""
}

# ============================================================
# Combined flags
# ============================================================

@test "journal_rotate: --dry-run and --quiet can be combined" {
  create_old_journal "2025-10-15.md" 90

  # --quiet wins — no output even in dry-run
  run bash "$ROTATE_SCRIPT" --dry-run --quiet
  assert_success
  assert_output ""

  # File untouched
  [ -f "${ADJ_DIR}/journal/2025-10-15.md" ]
}

# ============================================================
# Config reading from adjutant.yaml
# ============================================================

@test "journal_rotate: uses custom retention_days from adjutant.yaml" {
  cat > "${ADJ_DIR}/adjutant.yaml" <<'YAML'
name: adjutant-test
retention_days: 10
YAML

  # Create a file 15 days old — should be archived with 10-day retention
  create_old_journal "2026-02-12.md" 15

  run bash "$ROTATE_SCRIPT"
  assert_success

  [ ! -f "${ADJ_DIR}/journal/2026-02-12.md" ]
  [ -f "${ADJ_DIR}/journal/.archive/2026-02-12.md.gz" ]
}

@test "journal_rotate: uses default retention when adjutant.yaml has no journal config" {
  # Default adjutant.yaml from setup_test_env has no journal config
  # 25-day-old file should be kept (default 30-day retention)
  create_old_journal "2026-02-02.md" 25

  run bash "$ROTATE_SCRIPT"
  assert_success

  [ -f "${ADJ_DIR}/journal/2026-02-02.md" ]
}
