#!/bin/bash
# scripts/setup/steps/prerequisites.sh — Step 1: Dependency Check
#
# Checks for required and optional dependencies.
# Returns 0 if all required deps are present (optional may be missing).
# Returns 1 if any required dep is missing.
#
# Sets global arrays:
#   WIZARD_DEPS_OK=()       — required deps found
#   WIZARD_DEPS_MISSING=()  — required deps missing
#   WIZARD_OPTDEPS_OK=()    — optional deps found
#   WIZARD_OPTDEPS_MISSING=() — optional deps missing

# Requires: helpers.sh sourced

WIZARD_DEPS_OK=()
WIZARD_DEPS_MISSING=()
WIZARD_OPTDEPS_OK=()
WIZARD_OPTDEPS_MISSING=()

step_prerequisites() {
  wiz_step 1 6 "Prerequisites Check"
  echo ""

  local required_deps=(bash curl jq python3 opencode)
  local all_required_ok=true

  for cmd in "${required_deps[@]}"; do
    if has_command "$cmd"; then
      local version
      version=$(get_version "$cmd" 2>/dev/null || echo "found")
      wiz_ok "${cmd} (${version})"
      WIZARD_DEPS_OK+=("$cmd")
    else
      wiz_fail "${cmd} not found"
      WIZARD_DEPS_MISSING+=("$cmd")
      all_required_ok=false
    fi
  done

  # Optional dependencies
  echo ""
  printf "  ${_DIM}Optional:${_RESET}\n"

  # Playwright — npx may do a network lookup, warn the user it may take a moment
  printf "  Checking playwright... " >/dev/tty 2>/dev/null || true
  if has_command npx && npx playwright --version >/dev/null 2>&1; then
    local pw_ver
    pw_ver=$(npx playwright --version 2>/dev/null || echo "found")
    printf "\r" >/dev/tty 2>/dev/null || true
    wiz_ok "playwright (${pw_ver})"
    WIZARD_OPTDEPS_OK+=("playwright")
  else
    printf "\r" >/dev/tty 2>/dev/null || true
    wiz_warn "playwright not found"
    wiz_info "Needed for /screenshot. Install with: npx playwright install chromium"
    WIZARD_OPTDEPS_MISSING+=("playwright")
  fi

  # bc (used for cost estimation)
  if has_command bc; then
    wiz_ok "bc (math for cost estimates)"
    WIZARD_OPTDEPS_OK+=("bc")
  else
    wiz_warn "bc not found — cost estimates will be approximate"
    WIZARD_OPTDEPS_MISSING+=("bc")
  fi

  # bats (for development/testing)
  if has_command bats; then
    wiz_ok "bats (testing framework)"
    WIZARD_OPTDEPS_OK+=("bats")
  else
    wiz_info "bats not found — install with: brew install bats-core"
    WIZARD_OPTDEPS_MISSING+=("bats")
  fi

  # Summary
  echo ""
  if $all_required_ok; then
    wiz_ok "All required dependencies found"
    return 0
  else
    wiz_fail "Missing required dependencies: ${WIZARD_DEPS_MISSING[*]}"
    echo ""
    wiz_info "Install missing dependencies and re-run 'adjutant setup'"
    return 1
  fi
}
