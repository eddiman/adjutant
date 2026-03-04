#!/usr/bin/env bats
# tests/integration/autonomy.bats — Integration tests for Phase 7 autonomy features
#
# Tests:
#   - notify.sh budget guard (script-layer enforcement)
#   - status.sh autonomous activity display (heartbeat, notification count, actions ledger)

load "${BATS_TEST_DIRNAME}/../test_helper/setup.bash"
load "${BATS_TEST_DIRNAME}/../test_helper/mocks.bash"

NOTIFY_SCRIPT="${PROJECT_ROOT}/scripts/messaging/telegram/notify.sh"
STATUS_SCRIPT="${PROJECT_ROOT}/scripts/observability/status.sh"

setup_file()    { setup_file_scripts_template; }
teardown_file() { teardown_file_scripts_template; }

setup() {
  setup_test_env
  setup_mocks
  create_mock_curl_telegram_ok
  create_mock_crontab ""

  # Seed adjutant.yaml with notifications.max_per_day
  cat > "${TEST_ADJ_DIR}/adjutant.yaml" <<'YAML'
notifications:
  max_per_day: 3
  quiet_hours:
    enabled: false
debug:
  dry_run: false
YAML
}

teardown() {
  teardown_mocks
  teardown_test_env
}

# ── Helper: seed today's notify count ────────────────────────────────────────

_seed_notify_count() {
  local count="$1"
  local today
  today="$(date +%Y-%m-%d)"
  echo "${count}" > "${TEST_ADJ_DIR}/state/notify_count_${today}.txt"
}

_read_notify_count() {
  local today
  today="$(date +%Y-%m-%d)"
  local f="${TEST_ADJ_DIR}/state/notify_count_${today}.txt"
  [ -f "${f}" ] && cat "${f}" || echo "0"
}

# ── Helper: seed heartbeat / actions ledger ───────────────────────────────────

_seed_heartbeat() {
  local type="${1:-pulse}"
  local ts="${2:-2026-03-05T09:00:00Z}"
  cat > "${TEST_ADJ_DIR}/state/last_heartbeat.json" <<JSON
{"type":"${type}","timestamp":"${ts}","kbs_checked":["work"],"issues_found":[],"escalated":false}
JSON
}

_seed_actions_jsonl() {
  local lines=("$@")
  for line in "${lines[@]}"; do
    echo "${line}" >> "${TEST_ADJ_DIR}/state/actions.jsonl"
  done
}

# ═══════════════════════════════════════════════════════════════════════════════
# notify.sh — Budget guard integration
# ═══════════════════════════════════════════════════════════════════════════════

@test "notify integration: budget guard blocks send when daily limit reached" {
  _seed_notify_count 3  # already at max

  run bash "${NOTIFY_SCRIPT}" "This should be blocked"
  assert_failure
  assert_output --partial "ERROR:budget_exceeded"
  assert_output --partial "3/3"
}

@test "notify integration: send succeeds and increments counter when under budget" {
  _seed_notify_count 1  # 1 of 3 used

  run bash "${NOTIFY_SCRIPT}" "Hello from adjutant"
  assert_success
  assert_output --partial "Sent."
  assert_output --partial "2/3"
}

@test "notify integration: counter file increments from 0 on first send of the day" {
  # No counter file exists yet
  run bash "${NOTIFY_SCRIPT}" "First message today"
  assert_success
  assert_output --partial "1/3"

  local count
  count="$(_read_notify_count)"
  assert_equal "${count}" "1"
}

@test "notify integration: respects max_per_day from adjutant.yaml" {
  # Override with a custom budget
  cat > "${TEST_ADJ_DIR}/adjutant.yaml" <<'YAML'
notifications:
  max_per_day: 1
  quiet_hours:
    enabled: false
YAML
  _seed_notify_count 1  # at the custom limit

  run bash "${NOTIFY_SCRIPT}" "Over budget"
  assert_failure
  assert_output --partial "ERROR:budget_exceeded"
  assert_output --partial "1/1"
}

@test "notify integration: uses default budget of 3 when adjutant.yaml absent" {
  rm -f "${TEST_ADJ_DIR}/adjutant.yaml"
  _seed_notify_count 2  # under default of 3

  run bash "${NOTIFY_SCRIPT}" "Under default budget"
  assert_success
  assert_output --partial "3/3"
}

@test "notify integration: budget does NOT block curl when under limit" {
  _seed_notify_count 0

  run bash "${NOTIFY_SCRIPT}" "Message"
  assert_success
  assert_mock_called "curl"
}

@test "notify integration: budget blocks curl entirely — curl is never called" {
  _seed_notify_count 3

  run bash "${NOTIFY_SCRIPT}" "Blocked message"
  assert_failure
  assert_mock_not_called "curl"
}

# ═══════════════════════════════════════════════════════════════════════════════
# status.sh — Autonomous activity display
# ═══════════════════════════════════════════════════════════════════════════════

@test "status integration: shows 'Autonomous activity:' section" {
  run bash "${STATUS_SCRIPT}"
  assert_success
  assert_output --partial "Autonomous activity:"
}

@test "status integration: shows 'No autonomous cycles recorded yet' when heartbeat absent" {
  run bash "${STATUS_SCRIPT}"
  assert_success
  assert_output --partial "No autonomous cycles recorded yet."
}

@test "status integration: shows last cycle type and timestamp from last_heartbeat.json" {
  _seed_heartbeat "pulse" "2026-03-05T09:00:00Z"

  run bash "${STATUS_SCRIPT}"
  assert_success
  assert_output --partial "Last cycle: pulse at 2026-03-05T09:00:00Z"
}

@test "status integration: shows last cycle type as 'review' when heartbeat type is review" {
  _seed_heartbeat "review" "2026-03-05T20:00:00Z"

  run bash "${STATUS_SCRIPT}"
  assert_success
  assert_output --partial "Last cycle: review at 2026-03-05T20:00:00Z"
}

@test "status integration: shows notification count as 0/3 when no sends today" {
  run bash "${STATUS_SCRIPT}"
  assert_success
  assert_output --partial "Notifications today: 0/3"
}

@test "status integration: shows correct N/M notification count after sends" {
  _seed_notify_count 2

  run bash "${STATUS_SCRIPT}"
  assert_success
  assert_output --partial "Notifications today: 2/3"
}

@test "status integration: notification count reflects max_per_day from adjutant.yaml" {
  cat > "${TEST_ADJ_DIR}/adjutant.yaml" <<'YAML'
notifications:
  max_per_day: 5
  quiet_hours:
    enabled: false
YAML
  _seed_notify_count 2

  run bash "${STATUS_SCRIPT}"
  assert_success
  assert_output --partial "Notifications today: 2/5"
}

@test "status integration: does not show 'Recent actions:' when actions.jsonl is absent" {
  run bash "${STATUS_SCRIPT}"
  assert_success
  # Should not show the recent actions header when file is absent
  [[ "${output}" != *"Recent actions:"* ]]
}

@test "status integration: shows 'Recent actions:' when actions.jsonl has entries" {
  _seed_actions_jsonl \
    '{"ts":"2026-03-05T09:00:00Z","type":"pulse","kbs_checked":[],"issues_found":[],"escalated":false}'

  run bash "${STATUS_SCRIPT}"
  assert_success
  assert_output --partial "Recent actions:"
}

@test "status integration: shows action timestamp and type in recent actions" {
  _seed_actions_jsonl \
    '{"ts":"2026-03-05T09:00:00Z","type":"pulse","kbs_checked":[],"issues_found":[],"escalated":false}'

  run bash "${STATUS_SCRIPT}"
  assert_success
  assert_output --partial "2026-03-05T09:00:00Z"
  assert_output --partial "pulse"
}

@test "status integration: shows at most 5 recent actions" {
  for i in 1 2 3 4 5 6 7; do
    _seed_actions_jsonl "{\"ts\":\"2026-03-05T0${i}:00:00Z\",\"type\":\"pulse\",\"kbs_checked\":[],\"issues_found\":[],\"escalated\":false}"
  done

  run bash "${STATUS_SCRIPT}"
  assert_success
  # The 5-line tail means we see entries 3-7 (last 5) not entry 1
  assert_output --partial "Recent actions:"
}

@test "status integration: detects pulse cron job correctly" {
  create_mock_crontab "0 9,17 * * 1-5 opencode run --print \"/home/user/.adjutant/prompts/pulse.md\""

  run bash "${STATUS_SCRIPT}"
  assert_success
  assert_output --partial "Autonomous Pulse"
}

@test "status integration: detects review cron job correctly" {
  create_mock_crontab "0 20 * * 1-5 opencode run --print \"/home/user/.adjutant/prompts/review.md\""

  run bash "${STATUS_SCRIPT}"
  assert_success
  assert_output --partial "Daily Review"
}
