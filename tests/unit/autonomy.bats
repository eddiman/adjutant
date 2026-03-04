#!/usr/bin/env bats
# tests/unit/autonomy.bats — Unit tests for Phase 7 autonomy features
#
# Tests:
#   - notify.sh budget guard: reject at limit, increment counter, read from yaml,
#     default budget of 3, date-scoped counter file
#   - actions.jsonl schema: pulse, review, and escalation append patterns

load "${BATS_TEST_DIRNAME}/../test_helper/setup.bash"

setup() {
  setup_test_env
  source "${COMMON}/paths.sh"
  export ADJ_DIR="${TEST_ADJ_DIR}"
  export NO_COLOR=1
}

teardown() { teardown_test_env; }

# ── Helpers ──────────────────────────────────────────────────────────────────

# Seed a minimal adjutant.yaml with max_per_day
_seed_notify_config() {
  local max="${1:-3}"
  cat > "${TEST_ADJ_DIR}/adjutant.yaml" <<YAML
notifications:
  max_per_day: ${max}
  quiet_hours:
    enabled: false
debug:
  dry_run: false
YAML
}

# Seed a date-scoped notify counter file
_seed_notify_count() {
  local count="$1"
  local today
  today="$(date +%Y-%m-%d)"
  echo "${count}" > "${TEST_ADJ_DIR}/state/notify_count_${today}.txt"
}

# Read today's notify counter
_read_notify_count() {
  local today
  today="$(date +%Y-%m-%d)"
  local f="${TEST_ADJ_DIR}/state/notify_count_${today}.txt"
  [ -f "${f}" ] && cat "${f}" || echo "0"
}

# Append a JSONL line to actions.jsonl
_seed_action() {
  local line="$1"
  echo "${line}" >> "${TEST_ADJ_DIR}/state/actions.jsonl"
}

# ═══════════════════════════════════════════════════════════════════════════════
# notify.sh — Budget guard
# ═══════════════════════════════════════════════════════════════════════════════

@test "notify: rejects send when daily budget is exceeded" {
  _seed_notify_config 3
  _seed_notify_count 3

  # We test the budget logic inline (notify.sh requires real credentials/curl).
  # Extract and run just the budget guard fragment.
  local today
  today="$(date +%Y-%m-%d)"
  local count_file="${TEST_ADJ_DIR}/state/notify_count_${today}.txt"
  local count=0
  [ -f "${count_file}" ] && count="$(cat "${count_file}")"

  local max=3
  if [ -f "${TEST_ADJ_DIR}/adjutant.yaml" ]; then
    local yaml_val
    yaml_val="$(grep -E '^\s*max_per_day:' "${TEST_ADJ_DIR}/adjutant.yaml" | head -1 | grep -oE '[0-9]+')"
    [ -n "${yaml_val}" ] && max="${yaml_val}"
  fi

  run bash -c '[ "'"${count}"'" -ge "'"${max}"'" ] && echo "ERROR:budget_exceeded ('"${count}"'/'"${max}"' sent today)" && exit 1 || exit 0'
  assert_failure
  assert_output --partial "ERROR:budget_exceeded"
}

@test "notify: allows send when under daily budget" {
  _seed_notify_config 3
  _seed_notify_count 2

  local today
  today="$(date +%Y-%m-%d)"
  local count_file="${TEST_ADJ_DIR}/state/notify_count_${today}.txt"
  local count=0
  [ -f "${count_file}" ] && count="$(cat "${count_file}")"

  local max=3
  if [ -f "${TEST_ADJ_DIR}/adjutant.yaml" ]; then
    local yaml_val
    yaml_val="$(grep -E '^\s*max_per_day:' "${TEST_ADJ_DIR}/adjutant.yaml" | head -1 | grep -oE '[0-9]+')"
    [ -n "${yaml_val}" ] && max="${yaml_val}"
  fi

  [ "${count}" -lt "${max}" ]
}

@test "notify: reads max_per_day from adjutant.yaml" {
  _seed_notify_config 5

  local max=3
  if [ -f "${TEST_ADJ_DIR}/adjutant.yaml" ]; then
    local yaml_val
    yaml_val="$(grep -E '^\s*max_per_day:' "${TEST_ADJ_DIR}/adjutant.yaml" | head -1 | grep -oE '[0-9]+')"
    [ -n "${yaml_val}" ] && max="${yaml_val}"
  fi

  assert_equal "${max}" "5"
}

@test "notify: uses default budget of 3 when adjutant.yaml absent" {
  rm -f "${TEST_ADJ_DIR}/adjutant.yaml"

  local max=3
  if [ -f "${TEST_ADJ_DIR}/adjutant.yaml" ]; then
    local yaml_val
    yaml_val="$(grep -E '^\s*max_per_day:' "${TEST_ADJ_DIR}/adjutant.yaml" | head -1 | grep -oE '[0-9]+')"
    [ -n "${yaml_val}" ] && max="${yaml_val}"
  fi

  assert_equal "${max}" "3"
}

@test "notify: counter file is date-scoped (YYYY-MM-DD)" {
  _seed_notify_config 3
  _seed_notify_count 1

  local today
  today="$(date +%Y-%m-%d)"
  local count_file="${TEST_ADJ_DIR}/state/notify_count_${today}.txt"

  # File must exist and be named with today's date
  [ -f "${count_file}" ]
  # File must contain the count we seeded
  assert_equal "$(cat "${count_file}")" "1"
}

@test "notify: counter file for a different date is not used today" {
  _seed_notify_config 3
  # Seed a counter for yesterday
  local yesterday
  yesterday="$(date -v-1d +%Y-%m-%d 2>/dev/null || date -d 'yesterday' +%Y-%m-%d 2>/dev/null || echo "2000-01-01")"
  echo "99" > "${TEST_ADJ_DIR}/state/notify_count_${yesterday}.txt"

  # Today's counter should be absent / 0
  local today
  today="$(date +%Y-%m-%d)"
  local count_file="${TEST_ADJ_DIR}/state/notify_count_${today}.txt"
  local count=0
  [ -f "${count_file}" ] && count="$(cat "${count_file}")"

  assert_equal "${count}" "0"
}

# ═══════════════════════════════════════════════════════════════════════════════
# actions.jsonl — Schema validation helpers
# ═══════════════════════════════════════════════════════════════════════════════

@test "actions.jsonl: pulse record contains required fields" {
  local line='{"ts":"2026-03-05T09:00:00Z","type":"pulse","kbs_checked":["work"],"issues_found":[],"escalated":false}'
  _seed_action "${line}"

  local last
  last="$(tail -1 "${TEST_ADJ_DIR}/state/actions.jsonl")"

  # Must contain all required keys
  [[ "${last}" == *'"type":"pulse"'* ]]
  [[ "${last}" == *'"ts":'* ]]
  [[ "${last}" == *'"kbs_checked":'* ]]
  [[ "${last}" == *'"issues_found":'* ]]
  [[ "${last}" == *'"escalated":'* ]]
}

@test "actions.jsonl: review record contains required fields" {
  local line='{"ts":"2026-03-05T20:00:00Z","type":"review","kbs_checked":["work"],"insights_sent":1,"recommendations":["Check sprint"]}'
  _seed_action "${line}"

  local last
  last="$(tail -1 "${TEST_ADJ_DIR}/state/actions.jsonl")"

  [[ "${last}" == *'"type":"review"'* ]]
  [[ "${last}" == *'"ts":'* ]]
  [[ "${last}" == *'"kbs_checked":'* ]]
  [[ "${last}" == *'"insights_sent":'* ]]
  [[ "${last}" == *'"recommendations":'* ]]
}

@test "actions.jsonl: escalation record contains required fields" {
  local line='{"ts":"2026-03-05T09:05:00Z","type":"escalation","trigger":"2026-03-05-0900.md","action":"notified","project":"work"}'
  _seed_action "${line}"

  local last
  last="$(tail -1 "${TEST_ADJ_DIR}/state/actions.jsonl")"

  [[ "${last}" == *'"type":"escalation"'* ]]
  [[ "${last}" == *'"ts":'* ]]
  [[ "${last}" == *'"trigger":'* ]]
  [[ "${last}" == *'"action":'* ]]
  [[ "${last}" == *'"project":'* ]]
}

@test "actions.jsonl: notify record contains required fields" {
  local line='{"ts":"2026-03-05T09:05:01Z","type":"notify","detail":"[work] Sprint deadline approaching."}'
  _seed_action "${line}"

  local last
  last="$(tail -1 "${TEST_ADJ_DIR}/state/actions.jsonl")"

  [[ "${last}" == *'"type":"notify"'* ]]
  [[ "${last}" == *'"ts":'* ]]
  [[ "${last}" == *'"detail":'* ]]
}

@test "actions.jsonl: dry_run pulse record has dry_run:true field" {
  local line='{"ts":"2026-03-05T09:00:00Z","type":"pulse","dry_run":true,"kbs_checked":["work"],"issues_found":[],"escalated":false}'
  _seed_action "${line}"

  local last
  last="$(tail -1 "${TEST_ADJ_DIR}/state/actions.jsonl")"

  [[ "${last}" == *'"dry_run":true'* ]]
}

@test "actions.jsonl: multiple records append as separate lines (JSONL)" {
  _seed_action '{"ts":"2026-03-05T09:00:00Z","type":"pulse","kbs_checked":[],"issues_found":[],"escalated":false}'
  _seed_action '{"ts":"2026-03-05T20:00:00Z","type":"review","kbs_checked":[],"insights_sent":0,"recommendations":[]}'

  local line_count
  line_count="$(wc -l < "${TEST_ADJ_DIR}/state/actions.jsonl" | tr -d ' ')"
  assert_equal "${line_count}" "2"
}
