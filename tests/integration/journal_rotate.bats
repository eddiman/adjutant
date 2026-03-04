#!/usr/bin/env bats
# tests/integration/journal_rotate.bats — Integration tests for journal rotation
#
# Tests the full rotation pipeline via the adjutant CLI and the rotate script
# directly, including multi-target rotation, config interaction, and idempotency.

load "${BATS_TEST_DIRNAME}/../test_helper/setup.bash"

setup_file()    { setup_file_scripts_template; }
teardown_file() { teardown_file_scripts_template; }

setup() {
  setup_test_env
  source "${COMMON}/paths.sh"

  ROTATE_SCRIPT="${ADJ_DIR}/scripts/observability/journal_rotate.sh"

  # Create journal directories
  mkdir -p "${ADJ_DIR}/journal/news"
}

teardown() { teardown_test_env; }

# --- Helper: create a journal file with an old mtime ---
create_old_file() {
  local path="$1"
  local days_ago="${2:-60}"
  echo "# Entry: $(basename "$path")" > "$path"
  local old_date
  if [ "$(uname -s)" = "Darwin" ]; then
    old_date=$(date -v-${days_ago}d "+%Y%m%d0000")
  else
    old_date=$(date -d "${days_ago} days ago" "+%Y%m%d0000")
  fi
  touch -t "$old_date" "$path"
}

# ============================================================
# CLI subcommand integration
# ============================================================

@test "CLI: adjutant rotate --help shows usage" {
  # Copy the adjutant CLI into the test env
  cp "${PROJECT_ROOT}/adjutant" "${ADJ_DIR}/adjutant"
  chmod +x "${ADJ_DIR}/adjutant"

  run bash "${ADJ_DIR}/adjutant" rotate --help
  assert_success
  assert_output --partial "Usage:"
}

@test "CLI: adjutant help mentions rotate command" {
  cp "${PROJECT_ROOT}/adjutant" "${ADJ_DIR}/adjutant"
  chmod +x "${ADJ_DIR}/adjutant"

  run bash "${ADJ_DIR}/adjutant" help
  assert_success
  assert_output --partial "rotate"
}

# ============================================================
# End-to-end: all three targets in one run
# ============================================================

@test "rotate: archives journal, news, and rotates log in a single run" {
  # Set up a custom low threshold for log rotation
  cat > "${ADJ_DIR}/adjutant.yaml" <<'YAML'
name: adjutant-test
retention_days: 5
news_retention_days: 3
log_max_size_kb: 1
YAML

  # Create old journal entries
  create_old_file "${ADJ_DIR}/journal/2025-01-15.md" 60
  create_old_file "${ADJ_DIR}/journal/2025-01-20.md" 55

  # Create old news entries
  create_old_file "${ADJ_DIR}/journal/news/2025-01-15.md" 60

  # Create a large log file
  dd if=/dev/zero bs=1024 count=2 2>/dev/null | tr '\0' 'X' > "${ADJ_DIR}/state/adjutant.log"

  run bash "$ROTATE_SCRIPT"
  assert_success

  # Journal entries archived
  [ -f "${ADJ_DIR}/journal/.archive/2025-01-15.md.gz" ]
  [ -f "${ADJ_DIR}/journal/.archive/2025-01-20.md.gz" ]
  [ ! -f "${ADJ_DIR}/journal/2025-01-15.md" ]
  [ ! -f "${ADJ_DIR}/journal/2025-01-20.md" ]

  # News entry archived
  [ -f "${ADJ_DIR}/journal/news/.archive/2025-01-15.md.gz" ]
  [ ! -f "${ADJ_DIR}/journal/news/2025-01-15.md" ]

  # Log rotated
  [ -f "${ADJ_DIR}/state/adjutant.log.1.gz" ]
}

# ============================================================
# Idempotency
# ============================================================

@test "rotate: running twice produces no errors and no duplicate archives" {
  create_old_file "${ADJ_DIR}/journal/2025-06-01.md" 90

  run bash "$ROTATE_SCRIPT"
  assert_success
  [ -f "${ADJ_DIR}/journal/.archive/2025-06-01.md.gz" ]

  # Run again — nothing to do
  run bash "$ROTATE_SCRIPT"
  assert_success
  assert_output --partial "nothing to archive"
  assert_output --partial "Nothing to rotate"
}

# ============================================================
# Selective rotation (only some targets have old data)
# ============================================================

@test "rotate: only rotates targets that have old data" {
  # Only journal has old files — news and log are fine
  create_old_file "${ADJ_DIR}/journal/2025-03-01.md" 45
  echo "recent news" > "${ADJ_DIR}/journal/news/2026-02-27.md"
  echo "small log" > "${ADJ_DIR}/state/adjutant.log"

  run bash "$ROTATE_SCRIPT"
  assert_success

  # Journal archived
  [ -f "${ADJ_DIR}/journal/.archive/2025-03-01.md.gz" ]

  # News untouched
  [ -f "${ADJ_DIR}/journal/news/2026-02-27.md" ]

  # Log untouched
  [ ! -f "${ADJ_DIR}/state/adjutant.log.1.gz" ]
}

# ============================================================
# Verify archive contents are valid
# ============================================================

@test "rotate: archived files can be fully round-tripped (compress → decompress)" {
  # Create journal with multi-line content
  cat > "${ADJ_DIR}/journal/2025-04-01.md" <<'MD'
## 14:30 — Pulse (Haiku)
- [Project Alpha]: Monitoring code review pipeline
- [Project Beta]: Tests passing

## 15:00 — Escalation (Sonnet)
- Found security vulnerability in auth module
- **Notified via Telegram.**
MD

  if [ "$(uname -s)" = "Darwin" ]; then
    touch -t "$(date -v-60d '+%Y%m%d0000')" "${ADJ_DIR}/journal/2025-04-01.md"
  else
    touch -t "$(date -d '60 days ago' '+%Y%m%d0000')" "${ADJ_DIR}/journal/2025-04-01.md"
  fi

  # Save original content
  local original
  original=$(cat "${ADJ_DIR}/journal/2025-04-01.md")

  run bash "$ROTATE_SCRIPT"
  assert_success

  # Round-trip check
  local restored
  restored=$(gzip -dc "${ADJ_DIR}/journal/.archive/2025-04-01.md.gz")
  [ "$original" = "$restored" ]
}

# ============================================================
# Log rotation: multiple cycles
# ============================================================

@test "rotate: log rotation over 3 cycles keeps exactly 3 backups" {
  cat > "${ADJ_DIR}/adjutant.yaml" <<'YAML'
name: adjutant-test
log_max_size_kb: 1
log_rotations: 3
YAML

  # Cycle 1
  dd if=/dev/zero bs=1024 count=2 2>/dev/null | tr '\0' '1' > "${ADJ_DIR}/state/adjutant.log"
  run bash "$ROTATE_SCRIPT" --quiet
  assert_success
  [ -f "${ADJ_DIR}/state/adjutant.log.1.gz" ]

  # Cycle 2
  dd if=/dev/zero bs=1024 count=2 2>/dev/null | tr '\0' '2' > "${ADJ_DIR}/state/adjutant.log"
  run bash "$ROTATE_SCRIPT" --quiet
  assert_success
  [ -f "${ADJ_DIR}/state/adjutant.log.1.gz" ]
  [ -f "${ADJ_DIR}/state/adjutant.log.2.gz" ]

  # Cycle 3
  dd if=/dev/zero bs=1024 count=2 2>/dev/null | tr '\0' '3' > "${ADJ_DIR}/state/adjutant.log"
  run bash "$ROTATE_SCRIPT" --quiet
  assert_success
  [ -f "${ADJ_DIR}/state/adjutant.log.1.gz" ]
  [ -f "${ADJ_DIR}/state/adjutant.log.2.gz" ]
  [ -f "${ADJ_DIR}/state/adjutant.log.3.gz" ]

  # Cycle 4 — oldest backup (.3.gz) should now contain cycle-1 data
  # and no .4.gz should be created
  dd if=/dev/zero bs=1024 count=2 2>/dev/null | tr '\0' '4' > "${ADJ_DIR}/state/adjutant.log"
  run bash "$ROTATE_SCRIPT" --quiet
  assert_success
  [ -f "${ADJ_DIR}/state/adjutant.log.1.gz" ]
  [ -f "${ADJ_DIR}/state/adjutant.log.2.gz" ]
  [ -f "${ADJ_DIR}/state/adjutant.log.3.gz" ]
  [ ! -f "${ADJ_DIR}/state/adjutant.log.4.gz" ]
}

# ============================================================
# Missing directories
# ============================================================

@test "rotate: handles missing journal/ directory gracefully" {
  rm -rf "${ADJ_DIR}/journal"

  run bash "$ROTATE_SCRIPT"
  assert_success
  assert_output --partial "No journal directory"
}

@test "rotate: handles missing journal/news/ directory gracefully" {
  rm -rf "${ADJ_DIR}/journal/news"

  run bash "$ROTATE_SCRIPT"
  assert_success
  assert_output --partial "No news journal directory"
}
