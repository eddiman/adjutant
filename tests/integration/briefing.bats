#!/usr/bin/env bats
# tests/integration/briefing.bats — Integration tests for scripts/news/briefing.sh
#
# briefing.sh is the top-level orchestrator for the daily news briefing pipeline:
#   1. Checks operational state (KILLED/PAUSED lockfiles)
#   2. Calls fetch.sh and analyze.sh as subprocess scripts
#   3. Reads analyzed results and formats a markdown briefing
#   4. Optionally writes the briefing to a journal file
#   5. Optionally sends the briefing via Telegram (notify.sh)
#   6. Updates the dedup cache with newly delivered URLs
#   7. Prunes old dedup entries beyond the configured window
#   8. Cleans up old raw/analyzed files via find -mtime
#
# Since briefing.sh calls fetch.sh, analyze.sh, and notify.sh as subprocesses
# (via full path under ${ADJUTANT_DIR}/scripts/), we replace those copied scripts
# with stub versions that succeed silently or produce canned output. The real jq
# is used so dedup/pruning logic is exercised authentically.

load "${BATS_TEST_DIRNAME}/../test_helper/setup.bash"
load "${BATS_TEST_DIRNAME}/../test_helper/mocks.bash"

BRIEFING_SCRIPT="${PROJECT_ROOT}/scripts/news/briefing.sh"
TODAY="$(date +%Y-%m-%d)"
TODAY_DISPLAY="$(date +%d.%m.%Y)"

setup_file()    { setup_file_scripts_template; }
teardown_file() { teardown_file_scripts_template; }

setup() {
  setup_test_env
  setup_mocks

  export ADJUTANT_HOME="${TEST_ADJ_DIR}"

  # Seed default news config (journal + telegram enabled)
  seed_news_config

  # Seed the dedup file (empty)
  seed_news_dedup '{"urls":[]}'

  # Seed raw news that matches what analyzed items reference
  seed_raw_news '[
    {"title":"AI Agent Framework Released","url":"https://example.com/agent-1","score":150,"source":"hackernews","timestamp":"2026-02-27T10:00:00Z"},
    {"title":"Autonomous Agent Benchmark","url":"https://example.com/agent-2","score":100,"source":"hackernews","timestamp":"2026-02-27T09:00:00Z"}
  ]'

  # Seed analyzed news with ranked items
  seed_analyzed_news '[
    {"rank":1,"title":"AI Agent Framework Released","url":"https://example.com/agent-1","summary":"Major new framework for building AI agents."},
    {"rank":2,"title":"Autonomous Agent Benchmark","url":"https://example.com/agent-2","summary":"New benchmark results for autonomous agents."}
  ]'

  # Replace fetch.sh with a no-op stub (the real fetch would call curl)
  cat > "${TEST_ADJ_DIR}/scripts/news/fetch.sh" <<'STUB'
#!/bin/bash
# Stub fetch.sh — does nothing, raw news is pre-seeded
exit 0
STUB
  chmod +x "${TEST_ADJ_DIR}/scripts/news/fetch.sh"

  # Replace analyze.sh with a no-op stub (analyzed news is pre-seeded)
  cat > "${TEST_ADJ_DIR}/scripts/news/analyze.sh" <<'STUB'
#!/bin/bash
# Stub analyze.sh — does nothing, analyzed news is pre-seeded
exit 0
STUB
  chmod +x "${TEST_ADJ_DIR}/scripts/news/analyze.sh"

  # Replace notify.sh with a stub that logs its arguments
  cat > "${TEST_ADJ_DIR}/scripts/messaging/telegram/notify.sh" <<STUB
#!/bin/bash
# Stub notify.sh — logs the message it receives
echo "\$@" >> "${MOCK_LOG}/notify.log"
exit 0
STUB
  chmod +x "${TEST_ADJ_DIR}/scripts/messaging/telegram/notify.sh"
}

teardown() {
  teardown_mocks
  teardown_test_env
}

# ===== Precondition checks =====

@test "briefing.sh: exits with error when the KILLED lockfile is present" {
  touch "${TEST_ADJ_DIR}/KILLED"
  run bash "${BRIEFING_SCRIPT}"
  assert_failure
}

@test "briefing.sh: exits with error when the PAUSED lockfile is present" {
  touch "${TEST_ADJ_DIR}/PAUSED"
  run bash "${BRIEFING_SCRIPT}"
  assert_failure
}

# ===== Full pipeline =====

@test "briefing.sh: runs the full pipeline: calls fetch and analyze, writes journal, sends Telegram notification" {
  # Replace fetch.sh with a marker-creating stub
  cat > "${TEST_ADJ_DIR}/scripts/news/fetch.sh" <<STUB
#!/bin/bash
touch "${TEST_ADJ_DIR}/fetch_was_called"
exit 0
STUB
  chmod +x "${TEST_ADJ_DIR}/scripts/news/fetch.sh"

  cat > "${TEST_ADJ_DIR}/scripts/news/analyze.sh" <<STUB
#!/bin/bash
touch "${TEST_ADJ_DIR}/analyze_was_called"
exit 0
STUB
  chmod +x "${TEST_ADJ_DIR}/scripts/news/analyze.sh"

  run bash "${BRIEFING_SCRIPT}"
  assert_success

  # Subprocesses were called
  [ -f "${TEST_ADJ_DIR}/fetch_was_called" ]
  [ -f "${TEST_ADJ_DIR}/analyze_was_called" ]

  # Journal written with correct content
  local journal_file="${TEST_ADJ_DIR}/journal/news/${TODAY}.md"
  [ -f "${journal_file}" ]
  run cat "${journal_file}"
  [[ "${output}" == *"${TODAY_DISPLAY}"* ]]
  [[ "${output}" == *"AI Agent Framework Released"* ]]
  [[ "${output}" == *"Autonomous Agent Benchmark"* ]]
  [[ "${output}" == *"https://example.com/agent-1"* ]]
  [[ "${output}" == *"Major new framework"* ]]

  # Telegram notification sent with briefing content
  [ -f "${MOCK_LOG}/notify.log" ]
  local notify_args
  notify_args="$(cat "${MOCK_LOG}/notify.log")"
  [[ "${notify_args}" == *"AI Agent Framework Released"* ]]
}

@test "briefing.sh: aborts with error when fetch.sh fails" {
  cat > "${TEST_ADJ_DIR}/scripts/news/fetch.sh" <<'STUB'
#!/bin/bash
echo "Fetch failed" >&2
exit 1
STUB
  chmod +x "${TEST_ADJ_DIR}/scripts/news/fetch.sh"

  run bash "${BRIEFING_SCRIPT}"
  assert_failure
}

@test "briefing.sh: aborts with error when analyze.sh fails" {
  cat > "${TEST_ADJ_DIR}/scripts/news/analyze.sh" <<'STUB'
#!/bin/bash
echo "Analyze failed" >&2
exit 1
STUB
  chmod +x "${TEST_ADJ_DIR}/scripts/news/analyze.sh"

  run bash "${BRIEFING_SCRIPT}"
  assert_failure
}

# ===== No results handling =====

@test "briefing.sh: exits gracefully when no analyzed file exists after analyze" {
  rm -f "${TEST_ADJ_DIR}/state/news_analyzed/${TODAY}.json"
  run bash "${BRIEFING_SCRIPT}"
  assert_success
  [[ "${output}" == *"No analysis results found"* ]]
}

@test "briefing.sh: exits gracefully and skips journal and notify when analyzed array is empty" {
  seed_analyzed_news '[]'
  run bash "${BRIEFING_SCRIPT}"
  assert_success
  [[ "${output}" == *"No interesting news today"* ]]
  [ ! -f "${TEST_ADJ_DIR}/journal/news/${TODAY}.md" ]
  [ ! -f "${MOCK_LOG}/notify.log" ]
}

# ===== Delivery toggles =====

@test "briefing.sh: skips journal when delivery.journal is false" {
  seed_news_config '{
    "keywords": ["AI agent"],
    "sources": {"hackernews": {"enabled": true, "max_items": 5, "lookback_hours": 24}, "reddit": {"enabled": false}, "blogs": {"enabled": false}},
    "analysis": {"prefilter_limit": 5, "top_n": 3, "model": "anthropic/claude-haiku-4-5"},
    "delivery": {"telegram": false, "journal": false},
    "deduplication": {"window_days": 30},
    "cleanup": {"raw_retention_days": 7, "analyzed_retention_days": 7}
  }'
  run bash "${BRIEFING_SCRIPT}"
  assert_success
  [ ! -f "${TEST_ADJ_DIR}/journal/news/${TODAY}.md" ]
}

@test "briefing.sh: skips notify.sh when delivery.telegram is false" {
  seed_news_config '{
    "keywords": ["AI agent"],
    "sources": {"hackernews": {"enabled": true, "max_items": 5, "lookback_hours": 24}, "reddit": {"enabled": false}, "blogs": {"enabled": false}},
    "analysis": {"prefilter_limit": 5, "top_n": 3, "model": "anthropic/claude-haiku-4-5"},
    "delivery": {"telegram": false, "journal": true},
    "deduplication": {"window_days": 30},
    "cleanup": {"raw_retention_days": 7, "analyzed_retention_days": 7}
  }'
  run bash "${BRIEFING_SCRIPT}"
  assert_success
  [ ! -f "${MOCK_LOG}/notify.log" ]
}

# ===== Dedup cache update =====

@test "briefing.sh: adds delivered URLs to dedup cache and prunes old entries" {
  # Pre-seed an ancient entry (should be pruned) and a recent one (should survive)
  local yesterday
  yesterday="$(date -u -v-1d +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -d '1 day ago' +%Y-%m-%dT%H:%M:%SZ)"
  seed_news_dedup "{\"urls\":[
    {\"url\":\"https://ancient.example.com/old\",\"first_seen\":\"2020-01-01T00:00:00Z\"},
    {\"url\":\"https://recent.example.com/new\",\"first_seen\":\"${yesterday}\"}
  ]}"

  run bash "${BRIEFING_SCRIPT}"
  assert_success

  local dedup_file="${TEST_ADJ_DIR}/state/news_seen_urls.json"

  # New URLs from analyzed items were added
  run jq -r '.urls[].url' "${dedup_file}"
  [[ "${output}" == *"https://example.com/agent-1"* ]]

  # Recent entry preserved; ancient entry pruned
  [[ "${output}" == *"https://recent.example.com/new"* ]]
  [[ "${output}" != *"https://ancient.example.com/old"* ]]
}

# ===== File cleanup =====

@test "briefing.sh: does not delete today's raw or analyzed news files during cleanup" {
  run bash "${BRIEFING_SCRIPT}"
  assert_success
  [ -f "${TEST_ADJ_DIR}/state/news_raw/${TODAY}.json" ]
  [ -f "${TEST_ADJ_DIR}/state/news_analyzed/${TODAY}.json" ]
}
