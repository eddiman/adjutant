#!/usr/bin/env bats
# tests/unit/platform.bats — Tests for scripts/common/platform.sh

load "${BATS_TEST_DIRNAME}/../test_helper/setup.bash"

setup() {
  setup_test_env
  source "${COMMON}/paths.sh"
  source "${COMMON}/platform.sh"
}

teardown() { teardown_test_env; }

# --- OS detection ---

@test "platform: ADJUTANT_OS is detected as either 'macos' or 'linux' based on the current system" {
  [[ "$ADJUTANT_OS" == "macos" || "$ADJUTANT_OS" == "linux" ]]
}

@test "platform: ADJUTANT_OS is exported so child processes can read it" {
  run bash -c 'echo "$ADJUTANT_OS"'
  [[ "$output" == "macos" || "$output" == "linux" ]]
}

# --- date_subtract: portable date arithmetic returning ISO-8601 strings ---

@test "platform: date_subtract 1 hours returns a timestamp in YYYY-MM-DDTHH:MM:SSZ format" {
  run date_subtract 1 hours
  assert_success
  assert_output --regexp '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$'
}

@test "platform: date_subtract 7 days returns a timestamp in YYYY-MM-DDTHH:MM:SSZ format" {
  run date_subtract 7 days
  assert_success
  assert_output --regexp '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$'
}

@test "platform: date_subtract 30 minutes returns a timestamp in YYYY-MM-DDTHH:MM:SSZ format" {
  run date_subtract 30 minutes
  assert_success
  assert_output --regexp '^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$'
}

@test "platform: date_subtract fails with 'Unknown unit' when given an unsupported time unit like 'fortnights'" {
  run date_subtract 5 fortnights
  assert_failure
  assert_output --partial "Unknown unit"
}

@test "platform: date_subtract 1 hours produces a time that is approximately 3600 seconds before now" {
  local now
  now=$(date -u +%s)
  local result
  result=$(date_subtract 1 hours)

  # Parse the result back to epoch for comparison (must use -u since date_subtract outputs UTC)
  local result_epoch
  if [ "$ADJUTANT_OS" = "macos" ]; then
    result_epoch=$(date -u -jf "%Y-%m-%dT%H:%M:%SZ" "$result" +%s 2>/dev/null)
  else
    result_epoch=$(date -u -d "$result" +%s 2>/dev/null)
  fi

  # Result should be roughly 3600 seconds ago (allow 30s tolerance for CI/slow systems)
  local diff=$((now - result_epoch))
  [ "$diff" -ge 3570 ] && [ "$diff" -le 3630 ]
}

# --- date_subtract_epoch: same as date_subtract but returns epoch seconds ---

@test "platform: date_subtract_epoch 1 hours returns a numeric epoch timestamp" {
  run date_subtract_epoch 1 hours
  assert_success
  assert_output --regexp '^[0-9]+$'
}

@test "platform: date_subtract_epoch 1 hours returns a value less than the current time" {
  local now
  now=$(date -u +%s)
  local result
  result=$(date_subtract_epoch 1 hours)
  [ "$result" -lt "$now" ]
}

@test "platform: date_subtract_epoch fails when given an unsupported time unit" {
  run date_subtract_epoch 1 fortnights
  assert_failure
}

# --- file_mtime: file modification time in epoch seconds ---

@test "platform: file_mtime returns a recent epoch timestamp for a file that exists" {
  local testfile="${TEST_ADJ_DIR}/testfile"
  echo "hello" > "$testfile"
  run file_mtime "$testfile"
  assert_success
  assert_output --regexp '^[0-9]+$'
  # Should be a reasonable recent epoch (after 2020)
  [ "$output" -gt 1577836800 ]
}

@test "platform: file_mtime returns '0' and fails when the file does not exist" {
  run file_mtime "/nonexistent/file"
  assert_failure
  assert_output "0"
}

# --- file_size: file size in bytes ---

@test "platform: file_size returns '5' for a file containing exactly 5 bytes" {
  local testfile="${TEST_ADJ_DIR}/testfile"
  printf "hello" > "$testfile"  # 5 bytes, no trailing newline
  run file_size "$testfile"
  assert_success
  assert_output "5"
}

@test "platform: file_size returns '0' and fails when the file does not exist" {
  run file_size "/nonexistent/file"
  assert_failure
  assert_output "0"
}

@test "platform: file_size returns '0' for an empty file" {
  local testfile="${TEST_ADJ_DIR}/emptyfile"
  touch "$testfile"
  run file_size "$testfile"
  assert_success
  assert_output "0"
}

# --- ensure_path: add common tool directories to PATH without duplicating ---

@test "platform: ensure_path preserves all existing PATH entries" {
  local old_path="$PATH"
  ensure_path
  # All old entries should still be in PATH
  [[ ":${PATH}:" == *":${old_path%%:*}:"* ]]
}

@test "platform: calling ensure_path twice produces the exact same PATH (no duplicates)" {
  ensure_path
  local first_path="$PATH"
  ensure_path
  local second_path="$PATH"
  assert_equal "$first_path" "$second_path"
}

@test "platform: ensure_path adds /usr/local/bin to PATH when it was not already present" {
  local old_path="$PATH"
  PATH=$(echo "$PATH" | tr ':' '\n' | grep -v '/usr/local/bin' | tr '\n' ':' | sed 's/:$//')
  ensure_path
  [[ ":${PATH}:" == *":/usr/local/bin:"* ]]
  PATH="$old_path"
}
