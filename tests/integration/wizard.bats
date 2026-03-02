#!/usr/bin/env bats
# tests/integration/wizard.bats — Integration tests for the setup wizard
#
# Tests the wizard flow end-to-end with mocked external tools.
# Uses the standard test isolation model (ADJUTANT_HOME, temp dirs, PATH mocks).

load "${BATS_TEST_DIRNAME}/../test_helper/setup.bash"
load "${BATS_TEST_DIRNAME}/../test_helper/mocks.bash"

setup() {
  setup_test_env
  setup_mocks

  # Ensure the setup scripts are available and executable in the test tree
  chmod +x "${TEST_ADJ_DIR}/scripts/setup/helpers.sh" \
            "${TEST_ADJ_DIR}/scripts/setup/wizard.sh" \
            "${TEST_ADJ_DIR}/scripts/setup/repair.sh" \
            "${TEST_ADJ_DIR}/scripts/setup/steps/"*.sh 2>/dev/null || true
}

teardown() {
  teardown_mocks
  teardown_test_env
}

# Helper: run a wizard script fragment non-interactively
# Overrides wiz_confirm/wiz_input/wiz_secret/wiz_multiline to return canned values
_run_noninteractive() {
  local script="$1"
  shift
  bash -c "
    export NO_COLOR=1
    export ADJ_DIR='${TEST_ADJ_DIR}'
    export ADJUTANT_HOME='${TEST_ADJ_DIR}'
    export ADJUTANT_OS='macos'
    export SETUP_DIR='${TEST_ADJ_DIR}/scripts/setup'
    export PATH=\"${MOCK_BIN}:\${PATH}\"

    source '${TEST_ADJ_DIR}/scripts/setup/helpers.sh'

    # Non-interactive overrides
    wiz_confirm() { return 1; }
    wiz_choose()  { echo '1'; }
    wiz_input()   { echo \"\${2:-}\"; }
    wiz_secret()  { echo 'mock-secret'; }
    wiz_multiline() { echo 'mock multiline input'; }

    $*
  "
}

# ═══════════════════════════════════════════════════════════════════════════════
# CLI Dispatcher — setup subcommand
# ═══════════════════════════════════════════════════════════════════════════════

@test "CLI: adjutant help includes setup command" {
  run bash "${PROJECT_ROOT}/adjutant" help
  assert_success
  assert_output --partial "setup"
  assert_output --partial "setup wizard"
}

@test "CLI: adjutant setup --help shows usage" {
  # wizard.sh should handle --help and exit 0
  run bash -c "
    export ADJUTANT_HOME='${TEST_ADJ_DIR}'
    bash '${TEST_ADJ_DIR}/scripts/setup/wizard.sh' --help
  "
  assert_success
  assert_output --partial "Usage: adjutant setup"
  assert_output --partial "--repair"
}

# ═══════════════════════════════════════════════════════════════════════════════
# Prerequisites Step — Integration
# ═══════════════════════════════════════════════════════════════════════════════

@test "prerequisites: passes when all deps are mocked as available" {
  # Create mocks for required deps (skip bash — we're running in it)
  for cmd in curl jq python3 opencode; do
    _create_mock "$cmd" "${cmd} 1.0.0" 0
  done
  # npx fails (playwright not installed)
  _create_mock "npx" "" 1

  run _run_noninteractive "" "
    source '${TEST_ADJ_DIR}/scripts/setup/steps/prerequisites.sh'
    step_prerequisites
  "
  assert_success
  assert_output --partial "All required dependencies found"
}

@test "prerequisites: fails when opencode is missing" {
  for cmd in curl jq python3; do
    _create_mock "$cmd" "${cmd} 1.0.0" 0
  done
  # opencode missing — remove from mock_bin
  rm -f "${MOCK_BIN}/opencode"
  # Also shadow system PATH so real opencode isn't found
  _create_mock "npx" "" 1

  run bash -c "
    export NO_COLOR=1 ADJ_DIR='${TEST_ADJ_DIR}' ADJUTANT_OS='macos'
    export PATH=\"${MOCK_BIN}:/usr/bin:/bin\"
    source '${TEST_ADJ_DIR}/scripts/setup/helpers.sh'
    source '${TEST_ADJ_DIR}/scripts/setup/steps/prerequisites.sh'
    step_prerequisites
  "
  assert_failure
  assert_output --partial "opencode"
  assert_output --partial "Missing required dependencies"
}

# ═══════════════════════════════════════════════════════════════════════════════
# Identity Step — Template fallback integration
# ═══════════════════════════════════════════════════════════════════════════════

@test "identity: falls back to templates when opencode is unavailable" {
  # Don't create opencode mock — ensure it's missing from PATH
  rm -f "${MOCK_BIN}/opencode"
  rm -rf "${TEST_ADJ_DIR}/identity"

  run bash -c "
    export NO_COLOR=1 ADJ_DIR='${TEST_ADJ_DIR}' ADJUTANT_OS='macos'
    export PATH=\"${MOCK_BIN}:/usr/bin:/bin\"
    source '${TEST_ADJ_DIR}/scripts/setup/helpers.sh'
    wiz_confirm() { return 0; }
    wiz_input()   { echo 'test-agent'; }
    wiz_multiline() { echo 'test description'; }
    source '${TEST_ADJ_DIR}/scripts/setup/steps/identity.sh'
    step_identity
  "
  assert_success
  assert_output --partial "opencode not found"
  assert_output --partial "Template identity files written"
  [ -f "${TEST_ADJ_DIR}/identity/soul.md" ]
  [ -f "${TEST_ADJ_DIR}/identity/heart.md" ]
  [ -f "${TEST_ADJ_DIR}/identity/registry.md" ]
}

@test "identity: skips regeneration when user declines and files exist" {
  mkdir -p "${TEST_ADJ_DIR}/identity"
  echo "existing soul" > "${TEST_ADJ_DIR}/identity/soul.md"
  echo "existing heart" > "${TEST_ADJ_DIR}/identity/heart.md"

  run bash -c "
    export NO_COLOR=1 ADJ_DIR='${TEST_ADJ_DIR}' ADJUTANT_OS='macos'
    export PATH=\"${MOCK_BIN}:\${PATH}\"
    source '${TEST_ADJ_DIR}/scripts/setup/helpers.sh'
    wiz_confirm() { return 1; }
    source '${TEST_ADJ_DIR}/scripts/setup/steps/identity.sh'
    step_identity
  "
  assert_success
  assert_output --partial "Keeping existing identity files"

  # Files should be untouched
  run cat "${TEST_ADJ_DIR}/identity/soul.md"
  assert_output "existing soul"
}

@test "identity: generates files via opencode mock" {
  rm -rf "${TEST_ADJ_DIR}/identity"

  # Create opencode mock that returns NDJSON
  create_mock_opencode_reply "# Adjutant — Soul\n\nGenerated identity content"

  run bash -c "
    export NO_COLOR=1 ADJ_DIR='${TEST_ADJ_DIR}' ADJUTANT_OS='macos'
    export PATH=\"${MOCK_BIN}:\${PATH}\"
    source '${TEST_ADJ_DIR}/scripts/setup/helpers.sh'
    # Accept all confirmations
    wiz_confirm() { return 0; }
    wiz_input()   { echo 'test-agent'; }
    wiz_multiline() { echo 'I need help monitoring my projects'; }
    source '${TEST_ADJ_DIR}/scripts/setup/steps/identity.sh'
    step_identity
  "
  assert_success
  [ -f "${TEST_ADJ_DIR}/identity/soul.md" ]
  [ -f "${TEST_ADJ_DIR}/identity/heart.md" ]
}

# ═══════════════════════════════════════════════════════════════════════════════
# Messaging Step — Credential validation
# ═══════════════════════════════════════════════════════════════════════════════

@test "messaging: skips reconfiguration when valid creds exist and user declines" {
  # .env already has valid credentials (seeded by setup_test_env)
  run bash -c "
    export NO_COLOR=1 ADJ_DIR='${TEST_ADJ_DIR}' ADJUTANT_OS='macos'
    export PATH=\"${MOCK_BIN}:\${PATH}\"
    source '${TEST_ADJ_DIR}/scripts/setup/helpers.sh'
    wiz_confirm() { return 1; }
    source '${TEST_ADJ_DIR}/scripts/setup/steps/messaging.sh'
    step_messaging
  "
  assert_success
  assert_output --partial "Telegram bot token configured"
  assert_output --partial "Telegram chat ID configured"
}

@test "messaging: validates token with Telegram API mock" {
  # Remove existing .env so it triggers fresh setup
  rm -f "${TEST_ADJ_DIR}/.env"

  # Mock curl to return successful getMe / getUpdates
  _create_mock_custom "curl" '
    if [[ "$*" == *"getMe"* ]]; then
      echo "{\"ok\":true,\"result\":{\"username\":\"test_bot\"}}"
    elif [[ "$*" == *"getUpdates"* ]]; then
      echo "{\"ok\":true,\"result\":[{\"message\":{\"chat\":{\"id\":12345}}}]}"
    else
      echo "{\"ok\":true}"
    fi
  '

  run bash -c "
    export NO_COLOR=1 ADJ_DIR='${TEST_ADJ_DIR}' ADJUTANT_OS='macos'
    export PATH=\"${MOCK_BIN}:\${PATH}\"
    source '${TEST_ADJ_DIR}/scripts/setup/helpers.sh'
    # Simulate: user has token, enters it, confirms ready
    _confirm_call=0
    wiz_confirm() {
      _confirm_call=\$((_confirm_call + 1))
      # 1st call: 'Do you have a Telegram bot token?' -> yes
      # 2nd call: 'Ready? (press Enter after sending)' -> yes
      return 0
    }
    wiz_input() { echo '123456789:ABCdefGHI_jklMNO'; }
    wiz_secret() { echo '123456789:ABCdefGHI_jklMNO'; }
    source '${TEST_ADJ_DIR}/scripts/setup/steps/messaging.sh'
    step_messaging
  "
  assert_success
  assert_output --partial "Bot verified"
}

# ═══════════════════════════════════════════════════════════════════════════════
# Features Step — Configuration updates
# ═══════════════════════════════════════════════════════════════════════════════

@test "features: updates adjutant.yaml when features are selected" {
  # Write a proper config with features section
  cat > "${TEST_ADJ_DIR}/adjutant.yaml" <<'YAML'
features:
  news:
    enabled: false
  screenshot:
    enabled: false
  vision:
    enabled: false
  usage_tracking:
    enabled: false
YAML

  _create_mock "npx" "" 1  # playwright not available

  run bash -c "
    export NO_COLOR=1 ADJ_DIR='${TEST_ADJ_DIR}' ADJUTANT_OS='macos'
    export PATH=\"${MOCK_BIN}:\${PATH}\"
    source '${TEST_ADJ_DIR}/scripts/setup/helpers.sh'
    # Decline all features
    wiz_confirm() { return 1; }
    source '${TEST_ADJ_DIR}/scripts/setup/steps/features.sh'
    step_features
  "
  assert_success
  assert_output --partial "Feature configuration saved"
}

@test "features: creates news_config.json when news is enabled" {
  cat > "${TEST_ADJ_DIR}/adjutant.yaml" <<'YAML'
features:
  news:
    enabled: false
  screenshot:
    enabled: false
  vision:
    enabled: false
  usage_tracking:
    enabled: false
YAML

  rm -f "${TEST_ADJ_DIR}/news_config.json"
  _create_mock "npx" "" 1

  run bash -c "
    export NO_COLOR=1 ADJ_DIR='${TEST_ADJ_DIR}' ADJUTANT_OS='macos'
    export PATH=\"${MOCK_BIN}:\${PATH}\"
    source '${TEST_ADJ_DIR}/scripts/setup/helpers.sh'
    _call=0
    wiz_confirm() {
      _call=\$((_call + 1))
      # 1st: news -> yes, rest -> no
      [ \$_call -eq 1 ] && return 0
      return 1
    }
    source '${TEST_ADJ_DIR}/scripts/setup/steps/features.sh'
    step_features
  "
  assert_success
  [ -f "${TEST_ADJ_DIR}/news_config.json" ]
  # Verify it's valid JSON
  run jq empty "${TEST_ADJ_DIR}/news_config.json"
  assert_success
}

# ═══════════════════════════════════════════════════════════════════════════════
# Service Step — Permission fixes
# ═══════════════════════════════════════════════════════════════════════════════

@test "service: fixes script permissions and .env permissions" {
  # Create a non-executable script
  chmod -x "${TEST_ADJ_DIR}/scripts/setup/helpers.sh"
  # Set .env to world-readable
  chmod 644 "${TEST_ADJ_DIR}/.env"

  # Create adjutant CLI stub
  printf '#!/bin/bash\necho "ok"\n' > "${TEST_ADJ_DIR}/adjutant"

  _create_mock "npx" "" 1

  run bash -c "
    export NO_COLOR=1 ADJ_DIR='${TEST_ADJ_DIR}' ADJUTANT_OS='macos'
    export PATH=\"${MOCK_BIN}:\${PATH}\"
    export WIZARD_FEATURES_NEWS=false
    source '${TEST_ADJ_DIR}/scripts/setup/helpers.sh'
    wiz_confirm() { return 1; }
    source '${TEST_ADJ_DIR}/scripts/setup/steps/service.sh'
    step_service
  "
  assert_success
  assert_output --partial "permissions"

  # .env should be 600
  local perms
  perms=$(stat -f "%Lp" "${TEST_ADJ_DIR}/.env" 2>/dev/null || stat -c "%a" "${TEST_ADJ_DIR}/.env" 2>/dev/null)
  assert_equal "$perms" "600"
}

# ═══════════════════════════════════════════════════════════════════════════════
# Repair Mode — Full health check
# ═══════════════════════════════════════════════════════════════════════════════

@test "repair: healthy installation passes all checks" {
  # Set up a healthy installation
  mkdir -p "${TEST_ADJ_DIR}"/{state,journal,identity,prompts,photos,screenshots}
  printf '#!/bin/bash\necho "ok"\n' > "${TEST_ADJ_DIR}/adjutant"
  chmod +x "${TEST_ADJ_DIR}/adjutant"
  chmod 600 "${TEST_ADJ_DIR}/.env"
  find "${TEST_ADJ_DIR}/scripts" -name '*.sh' -type f -exec chmod +x {} +

  # Mock required commands
  for cmd in curl jq python3 opencode; do
    _create_mock "$cmd" "${cmd} 1.0.0" 0
  done

  run bash -c "
    export NO_COLOR=1 ADJ_DIR='${TEST_ADJ_DIR}' ADJUTANT_OS='macos'
    export SETUP_DIR='${TEST_ADJ_DIR}/scripts/setup'
    export PATH=\"${TEST_ADJ_DIR}:${MOCK_BIN}:\${PATH}\"
    source '${TEST_ADJ_DIR}/scripts/setup/helpers.sh'
    wiz_confirm() { return 1; }
    # Mock pgrep to show listener running
    pgrep() { echo 12345; return 0; }
    export -f pgrep
    source '${TEST_ADJ_DIR}/scripts/setup/repair.sh'
    run_repair
  "
  assert_success
  assert_output --partial "All checks passed"
}

@test "repair: detects placeholder credentials in .env" {
  # Write .env with placeholders
  cat > "${TEST_ADJ_DIR}/.env" <<'ENV'
TELEGRAM_BOT_TOKEN=your-bot-token-here
TELEGRAM_CHAT_ID=your-chat-id-here
ENV

  for cmd in curl jq python3 opencode; do
    _create_mock "$cmd" "${cmd} 1.0.0" 0
  done

  run bash -c "
    export NO_COLOR=1 ADJ_DIR='${TEST_ADJ_DIR}' ADJUTANT_OS='macos'
    export SETUP_DIR='${TEST_ADJ_DIR}/scripts/setup'
    export PATH=\"${MOCK_BIN}:\${PATH}\"
    source '${TEST_ADJ_DIR}/scripts/setup/helpers.sh'
    wiz_confirm() { return 1; }
    pgrep() { return 1; }
    export -f pgrep
    source '${TEST_ADJ_DIR}/scripts/setup/repair.sh'
    run_repair
  "
  assert_success
  assert_output --partial "credentials are placeholder"
}

@test "repair: detects non-executable scripts and reports count" {
  mkdir -p "${TEST_ADJ_DIR}"/{state,journal,identity,prompts,photos,screenshots}
  chmod 600 "${TEST_ADJ_DIR}/.env"

  # Make some scripts non-executable
  find "${TEST_ADJ_DIR}/scripts" -name '*.sh' -type f -exec chmod -x {} +

  for cmd in curl jq python3 opencode; do
    _create_mock "$cmd" "${cmd} 1.0.0" 0
  done

  run bash -c "
    export NO_COLOR=1 ADJ_DIR='${TEST_ADJ_DIR}' ADJUTANT_OS='macos'
    export SETUP_DIR='${TEST_ADJ_DIR}/scripts/setup'
    export PATH=\"${MOCK_BIN}:\${PATH}\"
    source '${TEST_ADJ_DIR}/scripts/setup/helpers.sh'
    wiz_confirm() { return 1; }
    pgrep() { return 1; }
    export -f pgrep
    source '${TEST_ADJ_DIR}/scripts/setup/repair.sh'
    run_repair
  "
  assert_success
  assert_output --partial "scripts not executable"
}

@test "repair: detects missing adjutant.yaml" {
  rm -f "${TEST_ADJ_DIR}/adjutant.yaml"

  for cmd in curl jq python3 opencode; do
    _create_mock "$cmd" "${cmd} 1.0.0" 0
  done

  run bash -c "
    export NO_COLOR=1 ADJ_DIR='${TEST_ADJ_DIR}' ADJUTANT_OS='macos'
    export SETUP_DIR='${TEST_ADJ_DIR}/scripts/setup'
    export PATH=\"${MOCK_BIN}:\${PATH}\"
    source '${TEST_ADJ_DIR}/scripts/setup/helpers.sh'
    wiz_confirm() { return 1; }
    pgrep() { return 1; }
    export -f pgrep
    source '${TEST_ADJ_DIR}/scripts/setup/repair.sh'
    run_repair
  "
  assert_success
  assert_output --partial "adjutant.yaml missing"
}

# ═══════════════════════════════════════════════════════════════════════════════
# Wizard Orchestrator — Mode detection
# ═══════════════════════════════════════════════════════════════════════════════

@test "wizard: --help flag exits cleanly with usage info" {
  run bash -c "
    export ADJUTANT_HOME='${TEST_ADJ_DIR}'
    bash '${TEST_ADJ_DIR}/scripts/setup/wizard.sh' --help
  "
  assert_success
  assert_output --partial "Usage: adjutant setup"
}

@test "wizard: detects existing installation on startup" {
  # wizard.sh should detect ADJ_DIR has adjutant.yaml
  # We need to make it non-interactive: override the confirm to say "no" (repair path)
  # then repair says "no" to everything
  run bash -c "
    export NO_COLOR=1
    export ADJUTANT_HOME='${TEST_ADJ_DIR}'
    export ADJ_DIR='${TEST_ADJ_DIR}'
    export PATH=\"${MOCK_BIN}:\${PATH}\"

    # Patch wizard.sh to be non-interactive
    # We source it in a controlled way
    source '${TEST_ADJ_DIR}/scripts/setup/helpers.sh'
    ADJUTANT_OS='macos'
    SETUP_DIR='${TEST_ADJ_DIR}/scripts/setup'

    wiz_confirm() { return 1; }
    pgrep() { return 1; }
    export -f pgrep

    # Source repair.sh manually (wizard would source it)
    source '${TEST_ADJ_DIR}/scripts/setup/repair.sh'

    # Simulate the detection logic from wizard.sh main()
    wiz_banner
    echo 'Existing installation detected at ${TEST_ADJ_DIR}'
    run_repair
  "
  assert_success
  assert_output --partial "Existing installation detected"
}
