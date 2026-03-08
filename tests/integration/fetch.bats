#!/usr/bin/env bats
# tests/integration/fetch.bats — Integration tests for scripts/news/fetch.sh
#
# fetch.sh is a standalone script that fetches news from multiple sources:
#   - Hacker News (via hn.algolia.com API)
#   - Reddit (via reddit search API)
#   - Company blogs (via HTML scraping)
#
# It reads news_config.json, calls curl for each enabled source, combines
# results into a JSON array, and writes to state/news_raw/<today>.json.
#
# All external calls (curl, jq) are real or mocked via PATH injection.
# The KILLED lockfile check is tested to verify operational gating.

load "${BATS_TEST_DIRNAME}/../test_helper/setup.bash"
load "${BATS_TEST_DIRNAME}/../test_helper/mocks.bash"

FETCH_SCRIPT="${PROJECT_ROOT}/scripts/news/fetch.sh"
TODAY="$(date +%Y-%m-%d)"

setup_file()    { setup_file_scripts_template; }
teardown_file() { teardown_file_scripts_template; }

setup() {
  setup_test_env
  setup_mocks

  export ADJUTANT_HOME="${TEST_ADJ_DIR}"

  # Seed default news config with only hackernews enabled
  seed_news_config
}

teardown() {
  teardown_mocks
  teardown_test_env
}

# Helper: create a curl mock that returns canned responses based on URL
_setup_fetch_curl_hn() {
  local hn_response="${1:-}"
  if [ -z "${hn_response}" ]; then
    hn_response='{"hits":[{"title":"AI Agent Framework Released","url":"https://example.com/agent","points":150,"objectID":"12345","created_at_i":1700000000}]}'
  fi
  _create_mock_custom "curl" '
if echo "$@" | grep -q "hn.algolia.com"; then
  cat <<'\''HN_RESP'\''
'"${hn_response}"'
HN_RESP
elif echo "$@" | grep -q "reddit.com"; then
  echo "{\"data\":{\"children\":[]}}"
else
  echo "{}"
fi
'
}

# ===== Precondition checks =====

@test "fetch.sh: exits with error when news_config.json is missing" {
  rm -f "${TEST_ADJ_DIR}/news_config.json"
  run bash "${FETCH_SCRIPT}"
  assert_failure
  [[ "${output}" == *"Configuration file not found"* ]]
}

@test "fetch.sh: exits when the KILLED lockfile is present" {
  _setup_fetch_curl_hn
  touch "${TEST_ADJ_DIR}/KILLED"
  run bash "${FETCH_SCRIPT}"
  assert_failure
}

# ===== Hacker News source =====

@test "fetch.sh: fetches HN items and writes a valid output file with correct fields" {
  _setup_fetch_curl_hn '{"hits":[{"title":"Test Agent Title","url":"https://test.com/article","points":42,"objectID":"999","created_at_i":1700000000}]}'
  run bash "${FETCH_SCRIPT}"
  assert_success

  # Called HN API with configured keywords
  assert_mock_called "curl"
  local full_log
  full_log="$(cat "${MOCK_LOG}/curl.log")"
  [[ "${full_log}" == *"hn.algolia.com"* ]]
  [[ "${full_log}" == *"AI agent"* ]] || [[ "${full_log}" == *"autonomous"* ]]

  # Output file written and valid
  local raw_file="${TEST_ADJ_DIR}/state/news_raw/${TODAY}.json"
  [ -f "${raw_file}" ]
  run jq 'type' "${raw_file}"
  assert_output '"array"'

  # Fields extracted correctly
  run jq -r '.[0].title' "${raw_file}"
  assert_output "Test Agent Title"
  run jq -r '.[0].url' "${raw_file}"
  assert_output "https://test.com/article"
  run jq '.[0].score' "${raw_file}"
  assert_output "42"
  run jq -r '.[0].source' "${raw_file}"
  assert_output "hackernews"
}

@test "fetch.sh: uses objectID as fallback URL when article URL is missing" {
  _setup_fetch_curl_hn '{"hits":[{"title":"HN Discussion","objectID":"55555","points":10,"created_at_i":1700000000}]}'
  run bash "${FETCH_SCRIPT}"
  assert_success
  local raw_file="${TEST_ADJ_DIR}/state/news_raw/${TODAY}.json"
  run jq -r '.[0].url' "${raw_file}"
  [[ "${output}" == *"news.ycombinator.com/item?id=55555"* ]]
}

# ===== Disabled sources =====

@test "fetch.sh: does not call reddit or blog APIs when those sources are disabled" {
  _setup_fetch_curl_hn
  run bash "${FETCH_SCRIPT}"
  assert_success
  local full_log
  full_log="$(cat "${MOCK_LOG}/curl.log")"
  [[ "${full_log}" != *"reddit.com"* ]]
  # Only one curl call — the HN one
  local call_count
  call_count="$(mock_call_count "curl")"
  [ "${call_count}" -eq 1 ]
}

# ===== Reddit source =====

@test "fetch.sh: calls reddit API with User-Agent header when reddit source is enabled" {
  seed_news_config '{
  "keywords": ["AI agent"],
  "sources": {
    "hackernews": {"enabled": false},
    "reddit": {"enabled": true, "subreddits": ["MachineLearning"], "max_items": 5},
    "blogs": {"enabled": false}
  },
  "analysis": {"prefilter_limit": 5, "top_n": 3}
}'
  _create_mock_custom "curl" '
echo "{\"data\":{\"children\":[{\"data\":{\"title\":\"Reddit AI Post\",\"url\":\"https://reddit.com/r/ml/1\",\"ups\":50,\"created_utc\":1700000000}}]}}"
'
  run bash "${FETCH_SCRIPT}"
  assert_success
  local full_log
  full_log="$(cat "${MOCK_LOG}/curl.log")"
  [[ "${full_log}" == *"reddit.com"* ]]
  [[ "${full_log}" == *"User-Agent"* ]]
}

# ===== Multiple sources =====

@test "fetch.sh: combines items from all enabled sources into a single array" {
  seed_news_config '{
  "keywords": ["AI agent"],
  "sources": {
    "hackernews": {"enabled": true, "max_items": 5, "lookback_hours": 24},
    "reddit": {"enabled": true, "subreddits": ["MachineLearning"], "max_items": 5},
    "blogs": {"enabled": false}
  },
  "analysis": {"prefilter_limit": 5, "top_n": 3}
}'
  _create_mock_custom "curl" '
if echo "$@" | grep -q "hn.algolia.com"; then
  echo "{\"hits\":[{\"title\":\"HN Item\",\"url\":\"https://hn.com/1\",\"points\":100,\"objectID\":\"1\",\"created_at_i\":1700000000}]}"
elif echo "$@" | grep -q "reddit.com"; then
  echo "{\"data\":{\"children\":[{\"data\":{\"title\":\"Reddit Item\",\"url\":\"https://reddit.com/1\",\"ups\":50,\"created_utc\":1700000000}}]}}"
else
  echo "{}"
fi
'
  run bash "${FETCH_SCRIPT}"
  assert_success
  local raw_file="${TEST_ADJ_DIR}/state/news_raw/${TODAY}.json"
  local count
  count="$(jq 'length' "${raw_file}")"
  [ "${count}" -eq 2 ]
}

# ===== Empty results =====

@test "fetch.sh: writes empty array when API returns no results" {
  _create_mock_custom "curl" '
echo "{\"hits\":[]}"
'
  run bash "${FETCH_SCRIPT}"
  assert_success
  local raw_file="${TEST_ADJ_DIR}/state/news_raw/${TODAY}.json"
  run jq 'length' "${raw_file}"
  assert_output "0"
}
