#!/usr/bin/env bats
# tests/integration/portfolio_trade.bats — Integration tests for portfolio-kb/scripts/trade.sh
#
# Three sub-suites:
#   1. Dry-run mode    (--dry-run flag): curl never called, nothing written to history/
#   2. Mock mode       (NORDNET_MOCK_WRITES=true): curl never called, mock_requests.jsonl written
#   3. Risk limits     : ERROR:risk-limit returned, curl never called in any mode

load "${BATS_TEST_DIRNAME}/../test_helper/setup.bash"
load "${BATS_TEST_DIRNAME}/../test_helper/mocks.bash"

PORTFOLIO_KB="/Volumes/Mandalor/JottaSync/AI_knowledge_bases/portfolio-kb"
TRADE_SCRIPT="${PORTFOLIO_KB}/scripts/trade.sh"

setup_file() { setup_file_scripts_template; }
teardown_file() { teardown_file_scripts_template; }

setup() {
  setup_test_env
  setup_mocks

  # Seed adjutant.yaml
  cat >> "${TEST_ADJ_DIR}/adjutant.yaml" << 'YAML'
llm:
  models:
    cheap: "anthropic/claude-haiku-4-5"
    medium: "anthropic/claude-sonnet-4-6"
    expensive: "anthropic/claude-opus-4-5"
YAML

  # Seed credentials
  printf '\nNORDNET_USERNAME=testuser\nNORDNET_PASSWORD=testpass\nNORDNET_ACCOUNT_ID=12345\n' \
    >> "${TEST_ADJ_DIR}/.env"

  # Create isolated KB structure
  KB_TEST="${TEST_ADJ_DIR}/portfolio-kb"
  mkdir -p "${KB_TEST}/scripts/lib" \
           "${KB_TEST}/knowledge" \
           "${KB_TEST}/state" \
           "${KB_TEST}/data/analysis"

  # Copy scripts from real KB if present
  if [ -d "${PORTFOLIO_KB}/scripts" ]; then
    cp -R "${PORTFOLIO_KB}/scripts/." "${KB_TEST}/scripts/"
  fi
  if [ -d "${PORTFOLIO_KB}/knowledge" ]; then
    cp -R "${PORTFOLIO_KB}/knowledge/." "${KB_TEST}/knowledge/"
  fi

  # Pre-seed session (skip auth for most tests)
  cat > "${KB_TEST}/state/nordnet_session.json" << JSON
{"session_key":"pre-seeded-key","expires_at":"2099-01-01T00:00:00Z","authenticated_at":"2026-03-05T00:00:00Z"}
JSON

  # Write a minimal risk-limits.md so risk checks pass by default
  cat > "${KB_TEST}/knowledge/risk-limits.md" << 'MD'
max_single_trade_value_nok: 10000
max_trades_per_day: 3
stop_loss_pct: 8
autonomous_allowed_actions: ["sell"]
MD

  export KB_TEST
  export ADJUTANT_HOME="${TEST_ADJ_DIR}"
  export ADJ_DIR="${TEST_ADJ_DIR}"
}

teardown() {
  teardown_mocks
  teardown_test_env
}

# ===== Dry-run mode =====

@test "trade.sh --dry-run: outputs OK:DRY_RUN" {
  [ -d "${PORTFOLIO_KB}" ] || skip "portfolio KB not present"
  KB_DIR="${KB_TEST}" run bash "${KB_TEST}/scripts/trade.sh" \
    --action sell --instrument EQNR.OL --quantity 10 --limit-price 285.00 --dry-run
  assert_success
  [[ "${output}" == "OK:DRY_RUN"* ]]
}

@test "trade.sh --dry-run: curl is never called" {
  [ -d "${PORTFOLIO_KB}" ] || skip "portfolio KB not present"
  create_mock_curl_telegram_ok
  KB_DIR="${KB_TEST}" run bash "${KB_TEST}/scripts/trade.sh" \
    --action sell --instrument EQNR.OL --quantity 10 --limit-price 285.00 --dry-run
  assert_success
  assert_mock_not_called "curl"
}

@test "trade.sh --dry-run: no trade log written" {
  [ -d "${PORTFOLIO_KB}" ] || skip "portfolio KB not present"
  TODAY="$(date +%Y-%m-%d)"
  YEAR="${TODAY:0:4}"
  KB_DIR="${KB_TEST}" run bash "${KB_TEST}/scripts/trade.sh" \
    --action sell --instrument EQNR.OL --quantity 10 --dry-run
  assert_success
  [ ! -f "${KB_TEST}/history/${YEAR}/${TODAY}-trades.md" ]
}

@test "trade.sh --dry-run: includes instrument in output" {
  [ -d "${PORTFOLIO_KB}" ] || skip "portfolio KB not present"
  KB_DIR="${KB_TEST}" run bash "${KB_TEST}/scripts/trade.sh" \
    --action sell --instrument EQNR.OL --quantity 10 --dry-run
  assert_success
  [[ "${output}" == *"EQNR.OL"* ]]
}

# ===== Mock mode (NORDNET_MOCK_WRITES=true) =====

@test "trade.sh mock mode: outputs OK:MOCK:" {
  [ -d "${PORTFOLIO_KB}" ] || skip "portfolio KB not present"
  NORDNET_MOCK_WRITES=true KB_DIR="${KB_TEST}" run bash "${KB_TEST}/scripts/trade.sh" \
    --action sell --instrument EQNR.OL --quantity 10 --limit-price 285.00
  assert_success
  [[ "${output}" == "OK:MOCK:"* ]]
}

@test "trade.sh mock mode: curl is never called" {
  [ -d "${PORTFOLIO_KB}" ] || skip "portfolio KB not present"
  create_mock_curl_telegram_ok
  NORDNET_MOCK_WRITES=true KB_DIR="${KB_TEST}" run bash "${KB_TEST}/scripts/trade.sh" \
    --action sell --instrument EQNR.OL --quantity 10 --limit-price 285.00
  assert_success
  assert_mock_not_called "curl"
}

@test "trade.sh mock mode: writes to mock_requests.jsonl" {
  [ -d "${PORTFOLIO_KB}" ] || skip "portfolio KB not present"
  NORDNET_MOCK_WRITES=true KB_DIR="${KB_TEST}" run bash "${KB_TEST}/scripts/trade.sh" \
    --action sell --instrument EQNR.OL --quantity 10 --limit-price 285.00
  assert_success
  [ -f "${KB_TEST}/state/mock_requests.jsonl" ]
}

@test "trade.sh mock mode: mock_requests.jsonl contains POST entry" {
  [ -d "${PORTFOLIO_KB}" ] || skip "portfolio KB not present"
  NORDNET_MOCK_WRITES=true KB_DIR="${KB_TEST}" run bash "${KB_TEST}/scripts/trade.sh" \
    --action sell --instrument EQNR.OL --quantity 10 --limit-price 285.00
  assert_success
  grep -q '"method":"POST"' "${KB_TEST}/state/mock_requests.jsonl"
}

@test "trade.sh mock mode: writes trade log entry" {
  [ -d "${PORTFOLIO_KB}" ] || skip "portfolio KB not present"
  TODAY="$(date +%Y-%m-%d)"
  YEAR="${TODAY:0:4}"
  NORDNET_MOCK_WRITES=true KB_DIR="${KB_TEST}" run bash "${KB_TEST}/scripts/trade.sh" \
    --action sell --instrument EQNR.OL --quantity 10 --limit-price 285.00
  assert_success
  [ -f "${KB_TEST}/history/${YEAR}/${TODAY}-trades.md" ]
}

@test "trade.sh mock mode: trade log contains MOCK marker" {
  [ -d "${PORTFOLIO_KB}" ] || skip "portfolio KB not present"
  TODAY="$(date +%Y-%m-%d)"
  YEAR="${TODAY:0:4}"
  NORDNET_MOCK_WRITES=true KB_DIR="${KB_TEST}" run bash "${KB_TEST}/scripts/trade.sh" \
    --action sell --instrument EQNR.OL --quantity 10 --limit-price 285.00
  assert_success
  grep -qi "mock" "${KB_TEST}/history/${YEAR}/${TODAY}-trades.md"
}

# ===== Risk limit enforcement =====

@test "trade.sh risk: rejects trade exceeding max_single_trade_value_nok" {
  [ -d "${PORTFOLIO_KB}" ] || skip "portfolio KB not present"
  # 100 shares at 200 NOK = 20000 NOK > 10000 limit
  KB_DIR="${KB_TEST}" run bash "${KB_TEST}/scripts/trade.sh" \
    --action sell --instrument EQNR.OL --quantity 100 --limit-price 200.00
  assert_failure
  [[ "${output}" == "ERROR:risk-limit:"* ]]
}

@test "trade.sh risk: curl never called when risk limit exceeded" {
  [ -d "${PORTFOLIO_KB}" ] || skip "portfolio KB not present"
  create_mock_curl_telegram_ok
  KB_DIR="${KB_TEST}" run bash "${KB_TEST}/scripts/trade.sh" \
    --action sell --instrument EQNR.OL --quantity 100 --limit-price 200.00
  assert_failure
  assert_mock_not_called "curl"
}

@test "trade.sh risk: rejects daily cap when 3 trades already logged" {
  [ -d "${PORTFOLIO_KB}" ] || skip "portfolio KB not present"
  TODAY="$(date +%Y-%m-%d)"
  YEAR="${TODAY:0:4}"
  mkdir -p "${KB_TEST}/history/${YEAR}"
  # Seed trade log with 3 entries to hit cap
  printf '# Trades -- %s\n\n## 09:00 -- SELL\n## 10:00 -- SELL\n## 11:00 -- SELL\n' \
    "${TODAY}" > "${KB_TEST}/history/${YEAR}/${TODAY}-trades.md"
  KB_DIR="${KB_TEST}" run bash "${KB_TEST}/scripts/trade.sh" \
    --action sell --instrument EQNR.OL --quantity 5 --limit-price 285.00
  assert_failure
  [[ "${output}" == *"daily cap"* ]]
}

@test "trade.sh risk: rejects buy action when autonomous_allowed_actions is sell-only (signal path)" {
  [ -d "${PORTFOLIO_KB}" ] || skip "portfolio KB not present"
  KB_DIR="${KB_TEST}" run bash "${KB_TEST}/scripts/trade.sh" \
    --action buy --instrument EQNR.OL --quantity 5 --limit-price 285.00 \
    --signal SIGNAL-20260305-001
  assert_failure
  [[ "${output}" == *"autonomous_allowed_actions"* ]]
}

# ===== Argument validation =====

@test "trade.sh: errors on missing required args" {
  [ -d "${PORTFOLIO_KB}" ] || skip "portfolio KB not present"
  KB_DIR="${KB_TEST}" run bash "${KB_TEST}/scripts/trade.sh" --action sell
  assert_failure
  [[ "${output}" == "ERROR:usage:"* ]]
}

@test "trade.sh: errors on invalid action" {
  [ -d "${PORTFOLIO_KB}" ] || skip "portfolio KB not present"
  KB_DIR="${KB_TEST}" run bash "${KB_TEST}/scripts/trade.sh" \
    --action hold --instrument EQNR.OL --quantity 5
  assert_failure
  [[ "${output}" == "ERROR:invalid action"* ]]
}

@test "trade.sh: errors on non-integer quantity" {
  [ -d "${PORTFOLIO_KB}" ] || skip "portfolio KB not present"
  KB_DIR="${KB_TEST}" run bash "${KB_TEST}/scripts/trade.sh" \
    --action sell --instrument EQNR.OL --quantity 5.5 --limit-price 285.00
  assert_failure
  [[ "${output}" == "ERROR:quantity"* ]]
}
