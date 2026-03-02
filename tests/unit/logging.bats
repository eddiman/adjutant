#!/usr/bin/env bats
# tests/unit/logging.bats — Tests for scripts/common/logging.sh

load "${BATS_TEST_DIRNAME}/../test_helper/setup.bash"

setup() {
  setup_test_env
  source "${COMMON}/paths.sh"
  source "${COMMON}/logging.sh"
}

teardown() { teardown_test_env; }

# --- adj_log: primary log function that writes to state/adjutant.log ---

@test "logging: adj_log creates the log file and writes the message with its context tag" {
  adj_log "test" "Hello world"
  [ -f "${ADJ_DIR}/state/adjutant.log" ]
  run cat "${ADJ_DIR}/state/adjutant.log"
  assert_output --partial "[test] Hello world"
}

@test "logging: adj_log entries are formatted as [HH:MM DD.MM.YYYY] [context] message" {
  adj_log "ctx" "msg"
  run cat "${ADJ_DIR}/state/adjutant.log"
  # Match timestamp pattern: [HH:MM DD.MM.YYYY]
  assert_output --regexp '^\[[0-9]{2}:[0-9]{2} [0-9]{2}\.[0-9]{2}\.[0-9]{4}\] \[ctx\] msg$'
}

@test "logging: adj_log appends to the log file — calling it twice produces two lines" {
  adj_log "a" "first"
  adj_log "b" "second"
  local count
  count=$(wc -l < "${ADJ_DIR}/state/adjutant.log" | tr -d ' ')
  [ "$count" -eq 2 ]
}

@test "logging: adj_log uses 'general' as the default context when an empty string is passed" {
  adj_log "" "no context"
  run cat "${ADJ_DIR}/state/adjutant.log"
  assert_output --partial "[general] no context"
}

@test "logging: adj_log strips control characters like tabs and carriage returns to prevent log injection" {
  # Embed a tab and carriage return in the message
  adj_log "sec" "$(printf 'bad\ttab\rreturn')"
  run cat "${ADJ_DIR}/state/adjutant.log"
  # Tab and CR should be stripped
  assert_output --partial "badtabreturn"
}

# --- fmt_ts: converts ISO-8601 timestamps to Adjutant's display format ---

@test "logging: fmt_ts converts '2026-02-26T14:30:00Z' to '14:30 26.02.2026'" {
  run fmt_ts "2026-02-26T14:30:00Z"
  assert_success
  assert_output "14:30 26.02.2026"
}

@test "logging: fmt_ts converts an ISO-8601 timestamp without the trailing Z suffix" {
  run fmt_ts "2026-02-26T14:30:00"
  assert_success
  assert_output "14:30 26.02.2026"
}

@test "logging: fmt_ts converts a date-only input like '2026-02-26' to '00:00 26.02.2026'" {
  run fmt_ts "2026-02-26"
  assert_success
  assert_output "00:00 26.02.2026"
}

@test "logging: fmt_ts returns an empty string when given empty input" {
  run fmt_ts ""
  assert_success
  assert_output ""
}

@test "logging: fmt_ts returns the original string unchanged when it cannot be parsed as a date" {
  run fmt_ts "not-a-date"
  assert_success
  assert_output "not-a-date"
}

# --- log_error: writes to both the log file and stderr ---

@test "logging: log_error writes an ERROR entry to the log file" {
  log_error "comp" "something broke" 2>/dev/null
  run cat "${ADJ_DIR}/state/adjutant.log"
  assert_output --partial "ERROR: something broke"
  assert_output --partial "[comp]"
}

@test "logging: log_error also prints the error message to stderr so the caller sees it immediately" {
  run log_error "comp" "failure msg"
  # bats 'run' captures stderr in $output too
  assert_output --partial "ERROR [comp]: failure msg"
}

# --- log_warn: writes to the log file only, no stderr output ---

@test "logging: log_warn writes a WARNING entry to the log file but produces no terminal output" {
  run log_warn "comp" "caution"
  # log_warn does NOT output to stderr/stdout
  assert_output ""
  run cat "${ADJ_DIR}/state/adjutant.log"
  assert_output --partial "WARNING: caution"
}

# --- log_debug: conditional — only writes when ADJUTANT_DEBUG or DEBUG is set ---

@test "logging: log_debug writes nothing when neither ADJUTANT_DEBUG nor DEBUG is set" {
  unset ADJUTANT_DEBUG
  unset DEBUG
  log_debug "comp" "debug msg"
  if [ -f "${ADJ_DIR}/state/adjutant.log" ]; then
    run cat "${ADJ_DIR}/state/adjutant.log"
    refute_output --partial "DEBUG: debug msg"
  fi
}

@test "logging: log_debug writes a DEBUG entry to the log file when ADJUTANT_DEBUG is set" {
  export ADJUTANT_DEBUG=1
  log_debug "comp" "debug msg"
  run cat "${ADJ_DIR}/state/adjutant.log"
  assert_output --partial "DEBUG: debug msg"
}

@test "logging: log_debug writes a DEBUG entry to the log file when DEBUG is set (fallback variable)" {
  unset ADJUTANT_DEBUG
  export DEBUG=1
  log_debug "comp" "debug via DEBUG"
  run cat "${ADJ_DIR}/state/adjutant.log"
  assert_output --partial "DEBUG: debug via DEBUG"
}

# --- Guard clause: ADJ_DIR must be set before sourcing logging.sh ---

@test "logging: sourcing logging.sh without ADJ_DIR set exits with an error telling you to source paths.sh first" {
  unset ADJ_DIR
  run bash -c "source '${COMMON}/logging.sh'"
  assert_failure
  assert_output --partial "ADJ_DIR not set"
}
