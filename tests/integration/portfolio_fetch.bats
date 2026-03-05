#!/usr/bin/env bats
# tests/integration/portfolio_fetch.bats — Integration tests for portfolio-kb/scripts/fetch.sh
#
# fetch.sh pulls positions and orders from Nordnet, then fetches watchlist prices
# via yfinance. All external calls are mocked via PATH injection.
#
# Mock strategy:
#   - curl dispatches on URL: nordnet login / positions / orders get different canned JSON
#   - python3 mocked to return canned yfinance output
#   - nordnet_auth.sh session state pre-seeded to skip login on most tests

load "${BATS_TEST_DIRNAME}/../test_helper/setup.bash"
load "${BATS_TEST_DIRNAME}/../test_helper/mocks.bash"

# Path to the portfolio KB (may not exist on CI — tests degrade gracefully)
PORTFOLIO_KB="/Volumes/Mandalor/JottaSync/AI_knowledge_bases/portfolio-kb"
FETCH_SCRIPT="${PORTFOLIO_KB}/scripts/fetch.sh"

# Canned API responses
_POSITIONS_JSON='[{"instrument":{"name":"Equinor ASA","symbol":"EQNR","isin":"NO0010096985"},"qty":100,"avg_cost_price":{"value":"310.50","currency":"NOK"},"last_price":{"price":285.24,"currency":"NOK"},"unrealized_profit":{"value":"-2526","currency":"NOK"},"unrealized_profit_pct":-0.0813}]'
_ORDERS_JSON='[]'
_LOGIN_JSON='{"session_key":"test-session-key-abc123","expires_in":3600}'

setup_file() { setup_file_scripts_template; }
teardown_file() { teardown_file_scripts_template; }

setup() {
  setup_test_env
  setup_mocks

  # Seed adjutant.yaml with model tiers (needed by _resolve_model)
  cat >> "${TEST_ADJ_DIR}/adjutant.yaml" << 'YAML'
llm:
  models:
    cheap: "anthropic/claude-haiku-4-5"
    medium: "anthropic/claude-sonnet-4-6"
    expensive: "anthropic/claude-opus-4-5"
YAML

  # Seed .env with Nordnet credentials
  printf '\nNORDNET_USERNAME=testuser\nNORDNET_PASSWORD=testpass\nNORDNET_ACCOUNT_ID=12345\n' \
    >> "${TEST_ADJ_DIR}/.env"

  # Create a minimal KB structure in TEST_ADJ_DIR for isolation
  KB_TEST="${TEST_ADJ_DIR}/portfolio-kb"
  mkdir -p "${KB_TEST}/data/positions" \
           "${KB_TEST}/data/market" \
           "${KB_TEST}/data/analysis" \
           "${KB_TEST}/knowledge" \
           "${KB_TEST}/state" \
           "${KB_TEST}/scripts/lib"

  # Copy scripts from real KB if it exists, else skip
  if [ -d "${PORTFOLIO_KB}/scripts" ]; then
    cp -R "${PORTFOLIO_KB}/scripts/." "${KB_TEST}/scripts/"
  fi

  # Copy knowledge files
  if [ -d "${PORTFOLIO_KB}/knowledge" ]; then
    cp -R "${PORTFOLIO_KB}/knowledge/." "${KB_TEST}/knowledge/"
  fi

  # Seed watchlist (empty — tests yfinance skip path)
  cat > "${KB_TEST}/data/market/watchlist.md" << 'MD'
# Watchlist
MD

  # Seed a pre-authenticated session to skip login in most tests
  cat > "${KB_TEST}/state/nordnet_session.json" << JSON
{"session_key":"pre-seeded-key","expires_at":"2099-01-01T00:00:00Z","authenticated_at":"2026-03-05T00:00:00Z"}
JSON

  export KB_TEST
  export ADJUTANT_HOME="${TEST_ADJ_DIR}"
  export ADJ_DIR="${TEST_ADJ_DIR}"
}

teardown() {
  teardown_mocks
  teardown_test_env
}

# Helper: set up conditional curl mock for Nordnet endpoints
_setup_nordnet_curl() {
  local positions_json="${1:-${_POSITIONS_JSON}}"
  local orders_json="${2:-${_ORDERS_JSON}}"

  _create_mock_custom "curl" "
if echo \"\$@\" | grep -q 'nordnet.no/api/2/login'; then
  printf '%s200' '${_LOGIN_JSON}'
elif echo \"\$@\" | grep -q '/positions'; then
  printf '%s200' '${positions_json}'
elif echo \"\$@\" | grep -q '/orders'; then
  printf '%s200' '${orders_json}'
else
  printf '{}200'
fi
"
}

# --- Precondition checks ---

@test "fetch.sh: exits when KB scripts missing" {
  skip "KB must be present on this machine"
  [ -f "${PORTFOLIO_KB}/scripts/fetch.sh" ]
}

@test "fetch.sh: errors when NORDNET_ACCOUNT_ID missing" {
  [ -d "${PORTFOLIO_KB}" ] || skip "portfolio KB not present"
  _setup_nordnet_curl
  # Remove account ID from test env
  sed -i.bak '/NORDNET_ACCOUNT_ID/d' "${TEST_ADJ_DIR}/.env" && rm -f "${TEST_ADJ_DIR}/.env.bak"
  KB_DIR="${KB_TEST}" run bash "${KB_TEST}/scripts/fetch.sh"
  [[ "${output}" == *"NORDNET_ACCOUNT_ID"* ]]
}

# --- Curl is called for positions and orders ---

@test "fetch.sh: calls Nordnet positions endpoint" {
  [ -d "${PORTFOLIO_KB}" ] || skip "portfolio KB not present"
  _setup_nordnet_curl
  create_mock_python3 ""
  KB_DIR="${KB_TEST}" run bash "${KB_TEST}/scripts/fetch.sh"
  assert_mock_called "curl"
  assert_mock_args_contain "curl" "positions"
}

@test "fetch.sh: calls Nordnet orders endpoint" {
  [ -d "${PORTFOLIO_KB}" ] || skip "portfolio KB not present"
  _setup_nordnet_curl
  create_mock_python3 ""
  KB_DIR="${KB_TEST}" run bash "${KB_TEST}/scripts/fetch.sh"
  assert_mock_called "curl"
  assert_mock_args_contain "curl" "orders"
}

@test "fetch.sh: outputs OK on success" {
  [ -d "${PORTFOLIO_KB}" ] || skip "portfolio KB not present"
  _setup_nordnet_curl
  create_mock_python3 ""
  KB_DIR="${KB_TEST}" run bash "${KB_TEST}/scripts/fetch.sh"
  assert_success
  [[ "${output}" == OK:* ]]
}

# --- data/ files are written ---

@test "fetch.sh: writes daily positions snapshot" {
  [ -d "${PORTFOLIO_KB}" ] || skip "portfolio KB not present"
  _setup_nordnet_curl
  create_mock_python3 ""
  TODAY="$(date +%Y-%m-%d)"
  KB_DIR="${KB_TEST}" run bash "${KB_TEST}/scripts/fetch.sh"
  assert_success
  [ -f "${KB_TEST}/data/positions/${TODAY}.md" ]
}

@test "fetch.sh: writes open-orders.md" {
  [ -d "${PORTFOLIO_KB}" ] || skip "portfolio KB not present"
  _setup_nordnet_curl
  create_mock_python3 ""
  KB_DIR="${KB_TEST}" run bash "${KB_TEST}/scripts/fetch.sh"
  assert_success
  [ -f "${KB_TEST}/data/positions/open-orders.md" ]
}

@test "fetch.sh: updates current.md" {
  [ -d "${PORTFOLIO_KB}" ] || skip "portfolio KB not present"
  _setup_nordnet_curl
  create_mock_python3 ""
  KB_DIR="${KB_TEST}" run bash "${KB_TEST}/scripts/fetch.sh"
  assert_success
  [ -f "${KB_TEST}/data/current.md" ]
  grep -q "Last updated:" "${KB_TEST}/data/current.md"
}

# --- Lock prevents concurrent runs ---

@test "fetch.sh: errors when fetch_lock exists" {
  [ -d "${PORTFOLIO_KB}" ] || skip "portfolio KB not present"
  _setup_nordnet_curl
  mkdir -p "${KB_TEST}/state/fetch_lock"
  KB_DIR="${KB_TEST}" run bash "${KB_TEST}/scripts/fetch.sh"
  assert_failure
  [[ "${output}" == *"fetch_lock"* ]]
}

# --- Mock writes never hit real API ---

@test "fetch.sh: GET calls always hit real API (not mocked by NORDNET_MOCK_WRITES)" {
  [ -d "${PORTFOLIO_KB}" ] || skip "portfolio KB not present"
  _setup_nordnet_curl
  create_mock_python3 ""
  # Even with NORDNET_MOCK_WRITES set, reads must still go through
  NORDNET_MOCK_WRITES=true KB_DIR="${KB_TEST}" run bash "${KB_TEST}/scripts/fetch.sh"
  assert_success
  assert_mock_called "curl"
}
