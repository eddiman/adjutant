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

@test "briefing.sh: succeeds when no lockfiles are present" {
  run bash "${BRIEFING_SCRIPT}"
  assert_success
}

# ===== Subprocess invocation =====

@test "briefing.sh: calls fetch.sh as a subprocess" {
  # Replace fetch.sh with a stub that creates a marker file
  cat > "${TEST_ADJ_DIR}/scripts/news/fetch.sh" <<STUB
#!/bin/bash
touch "${TEST_ADJ_DIR}/fetch_was_called"
exit 0
STUB
  chmod +x "${TEST_ADJ_DIR}/scripts/news/fetch.sh"

  run bash "${BRIEFING_SCRIPT}"
  assert_success
  [ -f "${TEST_ADJ_DIR}/fetch_was_called" ]
}

@test "briefing.sh: calls analyze.sh as a subprocess after fetch" {
  cat > "${TEST_ADJ_DIR}/scripts/news/analyze.sh" <<STUB
#!/bin/bash
touch "${TEST_ADJ_DIR}/analyze_was_called"
exit 0
STUB
  chmod +x "${TEST_ADJ_DIR}/scripts/news/analyze.sh"

  run bash "${BRIEFING_SCRIPT}"
  assert_success
  [ -f "${TEST_ADJ_DIR}/analyze_was_called" ]
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

@test "briefing.sh: exits gracefully when analyzed file contains an empty array" {
  seed_analyzed_news '[]'
  run bash "${BRIEFING_SCRIPT}"
  assert_success
  [[ "${output}" == *"No interesting news today"* ]]
}

@test "briefing.sh: does not write journal when there are no analyzed items" {
  seed_analyzed_news '[]'
  run bash "${BRIEFING_SCRIPT}"
  assert_success
  [ ! -f "${TEST_ADJ_DIR}/journal/news/${TODAY}.md" ]
}

@test "briefing.sh: does not call notify.sh when there are no analyzed items" {
  seed_analyzed_news '[]'
  run bash "${BRIEFING_SCRIPT}"
  assert_success
  [ ! -f "${MOCK_LOG}/notify.log" ]
}

# ===== Briefing formatting =====

@test "briefing.sh: logs the count of items found for delivery" {
  run bash "${BRIEFING_SCRIPT}"
  assert_success
  [[ "${output}" == *"Found 2 items to deliver"* ]]
}

@test "briefing.sh: includes today's date in the briefing header" {
  run bash "${BRIEFING_SCRIPT}"
  assert_success
  # The briefing is written to journal; check the file content
  local journal_file="${TEST_ADJ_DIR}/journal/news/${TODAY}.md"
  [ -f "${journal_file}" ]
  run cat "${journal_file}"
  [[ "${output}" == *"${TODAY_DISPLAY}"* ]]
}

@test "briefing.sh: includes ranked item titles in the briefing" {
  run bash "${BRIEFING_SCRIPT}"
  assert_success
  local journal_file="${TEST_ADJ_DIR}/journal/news/${TODAY}.md"
  run cat "${journal_file}"
  [[ "${output}" == *"AI Agent Framework Released"* ]]
  [[ "${output}" == *"Autonomous Agent Benchmark"* ]]
}

@test "briefing.sh: includes item URLs in the briefing" {
  run bash "${BRIEFING_SCRIPT}"
  assert_success
  local journal_file="${TEST_ADJ_DIR}/journal/news/${TODAY}.md"
  run cat "${journal_file}"
  [[ "${output}" == *"https://example.com/agent-1"* ]]
  [[ "${output}" == *"https://example.com/agent-2"* ]]
}

@test "briefing.sh: includes item summaries in the briefing" {
  run bash "${BRIEFING_SCRIPT}"
  assert_success
  local journal_file="${TEST_ADJ_DIR}/journal/news/${TODAY}.md"
  run cat "${journal_file}"
  [[ "${output}" == *"Major new framework"* ]]
}

# ===== Journal delivery =====

@test "briefing.sh: writes the briefing to the journal file when delivery.journal is true" {
  run bash "${BRIEFING_SCRIPT}"
  assert_success
  [ -f "${TEST_ADJ_DIR}/journal/news/${TODAY}.md" ]
}

@test "briefing.sh: does not write journal when delivery.journal is false" {
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

# ===== Telegram delivery =====

@test "briefing.sh: calls notify.sh when delivery.telegram is true" {
  run bash "${BRIEFING_SCRIPT}"
  assert_success
  [ -f "${MOCK_LOG}/notify.log" ]
}

@test "briefing.sh: passes the briefing text to notify.sh" {
  run bash "${BRIEFING_SCRIPT}"
  assert_success
  local notify_args
  notify_args="$(cat "${MOCK_LOG}/notify.log")"
  [[ "${notify_args}" == *"AI Agent Framework Released"* ]]
}

@test "briefing.sh: does not call notify.sh when delivery.telegram is false" {
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

@test "briefing.sh: adds delivered URLs to the dedup cache" {
  run bash "${BRIEFING_SCRIPT}"
  assert_success
  local dedup_file="${TEST_ADJ_DIR}/state/news_seen_urls.json"
  local url_count
  url_count="$(jq '.urls | length' "${dedup_file}")"
  [ "${url_count}" -ge 1 ]
}

@test "briefing.sh: dedup cache contains URLs from the analyzed items" {
  run bash "${BRIEFING_SCRIPT}"
  assert_success
  local dedup_file="${TEST_ADJ_DIR}/state/news_seen_urls.json"
  run jq -r '.urls[].url' "${dedup_file}"
  [[ "${output}" == *"https://example.com/agent-1"* ]]
}

@test "briefing.sh: dedup cache entries have a first_seen timestamp" {
  run bash "${BRIEFING_SCRIPT}"
  assert_success
  local dedup_file="${TEST_ADJ_DIR}/state/news_seen_urls.json"
  local has_timestamp
  has_timestamp="$(jq '.urls[0] | has("first_seen")' "${dedup_file}")"
  [ "${has_timestamp}" = "true" ]
}

@test "briefing.sh: preserves existing dedup entries when adding new ones" {
  seed_news_dedup '{"urls":[{"url":"https://old.example.com/article","first_seen":"2026-02-26T10:00:00Z"}]}'
  run bash "${BRIEFING_SCRIPT}"
  assert_success
  local dedup_file="${TEST_ADJ_DIR}/state/news_seen_urls.json"
  local url_count
  url_count="$(jq '.urls | length' "${dedup_file}")"
  # Should have at least old + new URLs
  [ "${url_count}" -ge 2 ]
  run jq -r '.urls[].url' "${dedup_file}"
  [[ "${output}" == *"https://old.example.com/article"* ]]
}

# ===== Dedup cache pruning =====

@test "briefing.sh: prunes dedup entries older than the configured window_days" {
  # Seed a dedup entry with a very old first_seen date
  seed_news_dedup '{"urls":[{"url":"https://ancient.example.com/old","first_seen":"2020-01-01T00:00:00Z"}]}'
  run bash "${BRIEFING_SCRIPT}"
  assert_success
  local dedup_file="${TEST_ADJ_DIR}/state/news_seen_urls.json"
  run jq -r '.urls[].url' "${dedup_file}"
  # The ancient entry should be pruned (older than 30 days)
  [[ "${output}" != *"https://ancient.example.com/old"* ]]
}

@test "briefing.sh: keeps recent dedup entries during pruning" {
  # Seed a dedup entry from yesterday — should survive 30-day window
  local yesterday
  yesterday="$(date -u -v-1d +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -d '1 day ago' +%Y-%m-%dT%H:%M:%SZ)"
  seed_news_dedup "{\"urls\":[{\"url\":\"https://recent.example.com/new\",\"first_seen\":\"${yesterday}\"}]}"
  run bash "${BRIEFING_SCRIPT}"
  assert_success
  local dedup_file="${TEST_ADJ_DIR}/state/news_seen_urls.json"
  run jq -r '.urls[].url' "${dedup_file}"
  [[ "${output}" == *"https://recent.example.com/new"* ]]
}

@test "briefing.sh: logs the dedup cache size after update" {
  run bash "${BRIEFING_SCRIPT}"
  assert_success
  [[ "${output}" == *"Dedup cache updated:"*"URLs tracked"* ]]
}

# ===== File cleanup =====

@test "briefing.sh: does not delete today's raw news file during cleanup" {
  run bash "${BRIEFING_SCRIPT}"
  assert_success
  [ -f "${TEST_ADJ_DIR}/state/news_raw/${TODAY}.json" ]
}

@test "briefing.sh: does not delete today's analyzed news file during cleanup" {
  run bash "${BRIEFING_SCRIPT}"
  assert_success
  [ -f "${TEST_ADJ_DIR}/state/news_analyzed/${TODAY}.json" ]
}

@test "briefing.sh: logs the cleanup step" {
  run bash "${BRIEFING_SCRIPT}"
  assert_success
  [[ "${output}" == *"Cleaning up old files"* ]]
}

# ===== Logging =====

@test "briefing.sh: logs the start banner with today's date" {
  run bash "${BRIEFING_SCRIPT}"
  assert_success
  [[ "${output}" == *"Agentic AI News Briefing"* ]]
  [[ "${output}" == *"${TODAY_DISPLAY}"* ]]
}

@test "briefing.sh: logs 'Briefing complete!' on successful run" {
  run bash "${BRIEFING_SCRIPT}"
  assert_success
  [[ "${output}" == *"Briefing complete!"* ]]
}

@test "briefing.sh: logs the fetching step" {
  run bash "${BRIEFING_SCRIPT}"
  assert_success
  [[ "${output}" == *"Fetching news"* ]]
}

@test "briefing.sh: logs the analyzing step" {
  run bash "${BRIEFING_SCRIPT}"
  assert_success
  [[ "${output}" == *"Analyzing news"* ]]
}

@test "briefing.sh: logs the formatting step" {
  run bash "${BRIEFING_SCRIPT}"
  assert_success
  [[ "${output}" == *"Formatting briefing"* ]]
}
