#!/usr/bin/env bats
# tests/integration/analyze.bats — Integration tests for scripts/news/analyze.sh
#
# analyze.sh is a standalone script that processes raw news items through three stages:
#   1. Deduplication — filters out URLs already seen (from news_seen_urls.json)
#   2. Keyword pre-filter — keeps only items whose titles match config keywords
#   3. Haiku ranking — sends top candidates to opencode (LLM) for selection
#
# It reads from state/news_raw/<today>.json and writes to state/news_analyzed/<today>.json.
# External calls: jq (real), opencode (mocked via PATH injection).

load "${BATS_TEST_DIRNAME}/../test_helper/setup.bash"
load "${BATS_TEST_DIRNAME}/../test_helper/mocks.bash"

ANALYZE_SCRIPT="${PROJECT_ROOT}/scripts/news/analyze.sh"
TODAY="$(date +%Y-%m-%d)"

setup() {
  setup_test_env
  setup_mocks

  export ADJUTANT_HOME="${TEST_ADJ_DIR}"

  # Default news config
  seed_news_config

  # Default dedup file (empty — no seen URLs)
  seed_news_dedup '{"urls":[]}'

  # Default raw news with items that match the keywords
  seed_raw_news '[
    {"title":"New AI Agent Framework Released","url":"https://example.com/agent-1","score":150,"source":"hackernews","timestamp":"2026-02-27T10:00:00Z"},
    {"title":"Autonomous Agent Benchmark Results","url":"https://example.com/agent-2","score":100,"source":"hackernews","timestamp":"2026-02-27T09:00:00Z"},
    {"title":"Cooking Recipe Blog Post","url":"https://example.com/cooking","score":50,"source":"hackernews","timestamp":"2026-02-27T08:00:00Z"}
  ]'

  # Default opencode mock that returns a valid ranked JSON array
  _create_mock_custom "opencode" '
cat <<'\''NDJSON'\''
{"type":"text","part":{"text":"[{\"rank\":1,\"title\":\"New AI Agent Framework Released\",\"url\":\"https://example.com/agent-1\",\"summary\":\"Major new framework for building AI agents.\"}]"}}
{"type":"text.done"}
NDJSON
'
}

teardown() {
  teardown_mocks
  teardown_test_env
}

# ===== Precondition checks =====

@test "analyze.sh: exits with error when the KILLED lockfile is present" {
  touch "${TEST_ADJ_DIR}/KILLED"
  run bash "${ANALYZE_SCRIPT}"
  assert_failure
}

@test "analyze.sh: exits with error when the raw news file for today does not exist" {
  rm -f "${TEST_ADJ_DIR}/state/news_raw/${TODAY}.json"
  run bash "${ANALYZE_SCRIPT}"
  assert_failure
  [[ "${output}" == *"Raw news file not found"* ]]
}

@test "analyze.sh: creates the dedup file automatically when it does not exist" {
  rm -f "${TEST_ADJ_DIR}/state/news_seen_urls.json"
  run bash "${ANALYZE_SCRIPT}"
  assert_success
  [ -f "${TEST_ADJ_DIR}/state/news_seen_urls.json" ]
}

# ===== Deduplication =====

@test "analyze.sh: filters out URLs that already appear in the dedup cache" {
  seed_news_dedup '{"urls":[{"url":"https://example.com/agent-1","first_seen":"2026-02-26T10:00:00Z"}]}'
  run bash "${ANALYZE_SCRIPT}"
  assert_success
  # Only agent-2 should be sent to opencode (agent-1 is deduped, cooking doesn't match keywords)
  local opencode_args
  opencode_args="$(cat "${MOCK_LOG}/opencode.log")"
  [[ "${opencode_args}" != *"agent-1"* ]]
  [[ "${opencode_args}" == *"agent-2"* ]] || [[ "${opencode_args}" == *"Autonomous Agent"* ]]
}

@test "analyze.sh: writes empty array and exits early when all items are already seen" {
  seed_news_dedup '{"urls":[{"url":"https://example.com/agent-1","first_seen":"2026-02-26T10:00:00Z"},{"url":"https://example.com/agent-2","first_seen":"2026-02-26T10:00:00Z"},{"url":"https://example.com/cooking","first_seen":"2026-02-26T10:00:00Z"}]}'
  run bash "${ANALYZE_SCRIPT}"
  assert_success
  local output_file="${TEST_ADJ_DIR}/state/news_analyzed/${TODAY}.json"
  run jq 'length' "${output_file}"
  assert_output "0"
}

@test "analyze.sh: does not call opencode when all items are deduped" {
  seed_news_dedup '{"urls":[{"url":"https://example.com/agent-1","first_seen":"2026-02-26T10:00:00Z"},{"url":"https://example.com/agent-2","first_seen":"2026-02-26T10:00:00Z"},{"url":"https://example.com/cooking","first_seen":"2026-02-26T10:00:00Z"}]}'
  run bash "${ANALYZE_SCRIPT}"
  assert_success
  assert_mock_not_called "opencode"
}

@test "analyze.sh: logs the count of unseen items after deduplication" {
  run bash "${ANALYZE_SCRIPT}"
  assert_success
  [[ "${output}" == *"After dedup:"*"unseen items"* ]]
}

# ===== Keyword pre-filter =====

@test "analyze.sh: keeps items whose titles match the configured keywords (case-insensitive)" {
  run bash "${ANALYZE_SCRIPT}"
  assert_success
  # "AI Agent" and "Autonomous Agent" match keywords, "Cooking Recipe" does not
  local opencode_args
  opencode_args="$(cat "${MOCK_LOG}/opencode.log")"
  [[ "${opencode_args}" == *"AI Agent Framework"* ]]
  [[ "${opencode_args}" != *"Cooking Recipe"* ]]
}

@test "analyze.sh: writes empty array and exits early when no items match keywords" {
  seed_raw_news '[
    {"title":"Cooking Recipe Blog Post","url":"https://example.com/cooking","score":50,"source":"hackernews","timestamp":"2026-02-27T08:00:00Z"},
    {"title":"Sports Update Today","url":"https://example.com/sports","score":30,"source":"reddit","timestamp":"2026-02-27T07:00:00Z"}
  ]'
  run bash "${ANALYZE_SCRIPT}"
  assert_success
  local output_file="${TEST_ADJ_DIR}/state/news_analyzed/${TODAY}.json"
  run jq 'length' "${output_file}"
  assert_output "0"
}

@test "analyze.sh: does not call opencode when no items match keywords" {
  seed_raw_news '[
    {"title":"Cooking Recipe Blog Post","url":"https://example.com/cooking","score":50,"source":"hackernews","timestamp":"2026-02-27T08:00:00Z"}
  ]'
  run bash "${ANALYZE_SCRIPT}"
  assert_success
  assert_mock_not_called "opencode"
}

@test "analyze.sh: logs the count of items after keyword filtering" {
  run bash "${ANALYZE_SCRIPT}"
  assert_success
  [[ "${output}" == *"After keyword filter:"*"items"* ]]
}

# ===== Score sorting and prefilter limit =====

@test "analyze.sh: sorts items by score descending before sending to Haiku" {
  seed_raw_news '[
    {"title":"Low Score AI Agent Post","url":"https://example.com/low","score":10,"source":"hackernews","timestamp":"2026-02-27T10:00:00Z"},
    {"title":"High Score AI Agent Post","url":"https://example.com/high","score":999,"source":"hackernews","timestamp":"2026-02-27T09:00:00Z"},
    {"title":"Mid Score Autonomous Agent Post","url":"https://example.com/mid","score":50,"source":"hackernews","timestamp":"2026-02-27T08:00:00Z"}
  ]'
  run bash "${ANALYZE_SCRIPT}"
  assert_success
  local opencode_args
  opencode_args="$(cat "${MOCK_LOG}/opencode.log")"
  # "High Score" should appear as item 1 (first in the list)
  [[ "${opencode_args}" == *"1. High Score"* ]]
}

@test "analyze.sh: respects the prefilter_limit from config to cap items sent to Haiku" {
  seed_news_config '{
  "keywords": ["AI agent", "autonomous agent"],
  "sources": {"hackernews": {"enabled": true, "max_items": 5, "lookback_hours": 24}, "reddit": {"enabled": false}, "blogs": {"enabled": false}},
  "analysis": {"prefilter_limit": 1, "top_n": 1, "model": "anthropic/claude-haiku-4-5"},
  "delivery": {"telegram": true, "journal": true},
  "deduplication": {"window_days": 30},
  "cleanup": {"raw_retention_days": 7, "analyzed_retention_days": 7}
}'
  seed_raw_news '[
    {"title":"First AI Agent Post","url":"https://example.com/1","score":100,"source":"hackernews","timestamp":"2026-02-27T10:00:00Z"},
    {"title":"Second AI Agent Post","url":"https://example.com/2","score":50,"source":"hackernews","timestamp":"2026-02-27T09:00:00Z"}
  ]'
  run bash "${ANALYZE_SCRIPT}"
  assert_success
  # With prefilter_limit=1, only the highest scoring item should be sent
  local opencode_args
  opencode_args="$(cat "${MOCK_LOG}/opencode.log")"
  [[ "${opencode_args}" == *"First AI Agent"* ]]
  [[ "${opencode_args}" != *"Second AI Agent"* ]]
}

# ===== Opencode / Haiku call =====

@test "analyze.sh: calls opencode with the model specified in the config" {
  run bash "${ANALYZE_SCRIPT}"
  assert_success
  assert_mock_called "opencode"
  local opencode_args
  opencode_args="$(cat "${MOCK_LOG}/opencode.log")"
  [[ "${opencode_args}" == *"--model"* ]]
  [[ "${opencode_args}" == *"anthropic/claude-haiku-4-5"* ]]
}

@test "analyze.sh: calls opencode with the --format json flag" {
  run bash "${ANALYZE_SCRIPT}"
  assert_success
  local opencode_args
  opencode_args="$(cat "${MOCK_LOG}/opencode.log")"
  [[ "${opencode_args}" == *"--format json"* ]] || [[ "${opencode_args}" == *"--format"*"json"* ]]
}

@test "analyze.sh: includes item titles and URLs in the prompt sent to opencode" {
  run bash "${ANALYZE_SCRIPT}"
  assert_success
  local opencode_args
  opencode_args="$(cat "${MOCK_LOG}/opencode.log")"
  [[ "${opencode_args}" == *"AI Agent Framework"* ]]
  [[ "${opencode_args}" == *"example.com"* ]]
}

@test "analyze.sh: exits with error when opencode returns no valid JSON array" {
  _create_mock_custom "opencode" '
echo "{\"type\":\"text\",\"part\":{\"text\":\"I cannot process this request.\"}}"
echo "{\"type\":\"text.done\"}"
'
  run bash "${ANALYZE_SCRIPT}"
  assert_failure
  [[ "${output}" == *"Haiku did not return valid JSON"* ]]
}

# ===== Output =====

@test "analyze.sh: writes the analyzed results to the output file for today" {
  run bash "${ANALYZE_SCRIPT}"
  assert_success
  [ -f "${TEST_ADJ_DIR}/state/news_analyzed/${TODAY}.json" ]
}

@test "analyze.sh: output file contains valid JSON array" {
  run bash "${ANALYZE_SCRIPT}"
  assert_success
  local output_file="${TEST_ADJ_DIR}/state/news_analyzed/${TODAY}.json"
  run jq 'type' "${output_file}"
  assert_success
  assert_output '"array"'
}

@test "analyze.sh: output file contains the ranked items from Haiku" {
  run bash "${ANALYZE_SCRIPT}"
  assert_success
  local output_file="${TEST_ADJ_DIR}/state/news_analyzed/${TODAY}.json"
  run jq -r '.[0].title' "${output_file}"
  assert_output "New AI Agent Framework Released"
}

# ===== Logging =====

@test "analyze.sh: logs the start message with today's date" {
  run bash "${ANALYZE_SCRIPT}"
  assert_success
  [[ "${output}" == *"Starting news analysis for ${TODAY}"* ]]
}

@test "analyze.sh: logs the final count of selected items" {
  run bash "${ANALYZE_SCRIPT}"
  assert_success
  [[ "${output}" == *"Analysis complete:"*"items selected"* ]]
}

@test "analyze.sh: logs the total count of raw items loaded" {
  run bash "${ANALYZE_SCRIPT}"
  assert_success
  [[ "${output}" == *"Loaded 3 raw items"* ]]
}
