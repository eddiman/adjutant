#!/bin/bash
# scripts/setup/wizard.sh — Main setup wizard orchestrator
#
# Runs the full 6-step setup for a fresh Adjutant installation.
# For existing installs, delegates to repair.sh instead.
#
# Usage:
#   bash scripts/setup/wizard.sh           # interactive setup
#   bash scripts/setup/wizard.sh --repair  # force repair mode
#
# Steps:
#   1. Prerequisites check
#   2. Installation path
#   3. Identity setup (LLM-driven soul.md/heart.md)
#   4. Messaging (Telegram credentials)
#   5. Feature selection
#   6. Service installation

set -euo pipefail

# Resolve our own location
SETUP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Load helpers first (no ADJ_DIR dependency)
source "${SETUP_DIR}/helpers.sh"

# Load platform detection (sets ADJUTANT_OS)
# We need to handle the case where paths.sh can't resolve ADJ_DIR yet
export ADJUTANT_OS="unknown"
case "$(uname -s)" in
  Darwin) ADJUTANT_OS="macos" ;;
  Linux)  ADJUTANT_OS="linux" ;;
esac

# ── Main Flow ───────────────────────────────────────────────────────────────

main() {
  local force_repair=false

  # Parse arguments
  for arg in "$@"; do
    case "$arg" in
      --dry-run) export DRY_RUN=true ;;
      --repair) force_repair=true ;;
      --help|-h)
        echo "Usage: adjutant setup [--repair] [--dry-run]"
        echo ""
        echo "  --repair      Force repair mode on existing installation"
        echo "  --dry-run     Walk through the full wizard interactively without"
        echo "                writing any files or running any commands."
        echo ""
        exit 0
        ;;
    esac
  done

  wiz_banner

  if [ "${DRY_RUN:-}" = "true" ]; then
    printf "  ${_YELLOW}[DRY RUN]${_RESET} Simulation mode — prompts are real, but no files will be written and no commands will be executed.\n"
    echo ""
  fi

  # Detect existing installation
  local existing_install=false
  if [ -n "${ADJ_DIR:-}" ] && [ -f "${ADJ_DIR}/adjutant.yaml" ]; then
    existing_install=true
  fi

  if $existing_install && ! $force_repair; then
    printf "  Existing installation detected at ${_BOLD}%s${_RESET}\n" "${ADJ_DIR}"
    echo ""
    local choice
    choice=$(wiz_choose "What would you like to do?" \
      "Repair / health check (recommended)" \
      "Run full setup from scratch")

    if [ "$choice" = "2" ]; then
      _run_fresh_setup "$@"
    else
      source "${SETUP_DIR}/repair.sh"
      run_repair
    fi
  elif $force_repair && $existing_install; then
    source "${SETUP_DIR}/repair.sh"
    run_repair
  else
    _run_fresh_setup "$@"
  fi
}

_run_fresh_setup() {
  # ── Step 1: Prerequisites ──────────────────────────────────────────────
  source "${SETUP_DIR}/steps/prerequisites.sh"
  step_prerequisites || {
    echo ""
    wiz_fail "Cannot continue without required dependencies."
    exit 1
  }

  # ── Step 2: Installation Path ──────────────────────────────────────────
  source "${SETUP_DIR}/steps/install_path.sh"
  step_install_path || {
    echo ""
    wiz_fail "Installation path setup failed."
    exit 1
  }

  # Now that we have ADJ_DIR, ensure adjutant.yaml exists
  _ensure_config

  # Source platform.sh now that ADJ_DIR is set
  if [ -f "${ADJ_DIR}/scripts/common/platform.sh" ]; then
    source "${ADJ_DIR}/scripts/common/platform.sh"
  fi

  # ── Step 3: Identity ───────────────────────────────────────────────────
  source "${SETUP_DIR}/steps/identity.sh"
  step_identity || {
    wiz_warn "Identity setup had issues — you can edit identity files later"
  }

  # ── Step 4: Messaging ──────────────────────────────────────────────────
  source "${SETUP_DIR}/steps/messaging.sh"
  step_messaging || {
    wiz_warn "Messaging setup incomplete — run 'adjutant setup' again to finish"
  }

  # ── Step 5: Features ───────────────────────────────────────────────────
  source "${SETUP_DIR}/steps/features.sh"
  step_features || {
    wiz_warn "Feature selection had issues"
  }

  # ── Step 6: Service Installation ───────────────────────────────────────
  source "${SETUP_DIR}/steps/service.sh"
  step_service || {
    wiz_warn "Service installation had issues — start manually with 'adjutant start'"
  }

  # ── Done ───────────────────────────────────────────────────────────────
  _show_completion
}

# Ensure adjutant.yaml exists at the install path
_ensure_config() {
  local config_file="${ADJ_DIR}/adjutant.yaml"

  if [ -f "$config_file" ]; then
    return 0
  fi

  if [ "${DRY_RUN:-}" = "true" ]; then
    dry_run_would "write ${config_file} (adjutant.yaml defaults)"
    wiz_ok "Would create adjutant.yaml"
    return 0
  fi

  # Write default adjutant.yaml
  cat > "$config_file" <<'YAML'
# adjutant.yaml — Single source of truth for this Adjutant instance
#
# This file serves two purposes:
#   1. Root marker for path resolution (scripts/common/paths.sh looks for this)
#   2. Unified configuration replacing scattered hardcoded values
#
# Secrets (tokens, chat IDs) stay in .env — this file is safe to commit.

instance:
  name: "adjutant"

identity:
  soul: "identity/soul.md"
  heart: "identity/heart.md"
  registry: "identity/registry.md"

messaging:
  backend: "telegram"
  telegram:
    session_timeout_seconds: 7200
    default_model: "anthropic/claude-haiku-4-5"
    rate_limit:
      messages_per_minute: 10
      backoff_exponential: true

llm:
  backend: "opencode"
  models:
    cheap: "anthropic/claude-haiku-4-5"
    medium: "anthropic/claude-sonnet-4-5"
    expensive: "anthropic/claude-opus-4-5"
  caps:
    session_tokens: 44000
    session_window_hours: 5
    weekly_tokens: 350000

features:
  news:
    enabled: false
    config_path: "news_config.json"
    schedule: "0 8 * * 1-5"
  screenshot:
    enabled: false
  vision:
    enabled: true
  usage_tracking:
    enabled: true

platform:
  service_manager: "launchd"
  process_manager: "pidfile"

notifications:
  max_per_day: 3
  quiet_hours:
    enabled: false
    start: "22:00"
    end: "07:00"

security:
  prompt_injection_guard: true
  env_file: ".env"
  log_unknown_senders: true
  rate_limiting: true

debug:
  dry_run: false
  verbose_logging: false
  mock_llm: false
YAML

  wiz_ok "Created adjutant.yaml"
}

# Show the completion summary
_show_completion() {
  if [ "${DRY_RUN:-}" = "true" ]; then
    echo ""
    printf "  ${_YELLOW}[DRY RUN]${_RESET} Simulation complete. No changes were made.\n"
    echo ""
    return 0
  fi

  wiz_complete_banner

  printf "  Send /help to your Telegram bot to get started.\n"
  echo ""

  # Cost estimate table
  printf "  ${_BOLD}Estimated monthly cost at typical usage:${_RESET}\n"
  echo ""
  printf "  %-26s %-11s %s\n" "Operation" "Frequency" "Cost/mo"
  printf "  %-26s %-11s %s\n" "--------------------------" "-----------" "--------"
  printf "  %-26s %-11s %s\n" "Casual chat (Haiku)" "5/day" "~\$3.00"
  printf "  %-26s %-11s %s\n" "Pulse checks" "2/day" "~\$0.60"

  if [ "${WIZARD_FEATURES_NEWS:-false}" = "true" ]; then
    printf "  %-26s %-11s %s\n" "News briefing (Haiku)" "1/day" "~\$1.50"
  fi

  printf "  %-26s %-11s %s\n" "Deep reflect (Opus)" "1/week" "~\$1.20"
  printf "  %-26s %-11s %s\n" "--------------------------" "-----------" "--------"

  local total="~\$4.80"
  if [ "${WIZARD_FEATURES_NEWS:-false}" = "true" ]; then
    total="~\$6.30"
  fi
  printf "  %-26s %-11s %s\n" "Total estimate" "" "$total"
  echo ""

  printf "  Config:  ${ADJ_DIR}/adjutant.yaml\n"
  printf "  Logs:    ${ADJ_DIR}/state/adjutant.log\n"
  printf "  Identity: ${ADJ_DIR}/identity/\n"
  echo ""
}

# Run
main "$@"
