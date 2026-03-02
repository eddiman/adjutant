#!/bin/bash
# scripts/setup/install.sh — Adjutant curl installer
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/eddiman/adjutant/main/scripts/setup/install.sh | bash
#
# What this script does:
#   1. Checks system prerequisites (bash 4+, curl, jq, opencode)
#   2. Asks where to install Adjutant (default: ~/.adjutant)
#   3. Downloads the latest release tarball from GitHub Releases
#   4. Runs the interactive setup wizard
#
# Environment variables (all optional):
#   ADJUTANT_INSTALL_DIR   Override install path (skips the prompt)
#   ADJUTANT_REPO          Override GitHub owner/repo (default: eddiman/adjutant)
#   ADJUTANT_VERSION       Pin a specific release tag (default: latest)
#   ADJUTANT_NO_WIZARD     Set to "true" to skip the wizard after install

set -euo pipefail

# ── Configuration ────────────────────────────────────────────────────────────

ADJUTANT_REPO="${ADJUTANT_REPO:-eddiman/adjutant}"
GITHUB_API="https://api.github.com/repos/${ADJUTANT_REPO}"

# ── Colour helpers ───────────────────────────────────────────────────────────

if [ -t 1 ] && command -v tput &>/dev/null; then
  _BOLD="$(tput bold)"
  _GREEN="$(tput setaf 2)"
  _YELLOW="$(tput setaf 3)"
  _RED="$(tput setaf 1)"
  _CYAN="$(tput setaf 6)"
  _RESET="$(tput sgr0)"
else
  _BOLD="" _GREEN="" _YELLOW="" _RED="" _CYAN="" _RESET=""
fi

info()    { printf "  ${_CYAN}→${_RESET} %s\n" "$*"; }
ok()      { printf "  ${_GREEN}✓${_RESET} %s\n" "$*"; }
warn()    { printf "  ${_YELLOW}!${_RESET} %s\n" "$*"; }
die()     { printf "\n  ${_RED}✗ Error:${_RESET} %s\n\n" "$*" >&2; exit 1; }

# ── Banner ───────────────────────────────────────────────────────────────────

print_banner() {
  printf "\n"
  printf "  ${_BOLD}Adjutant${_RESET} — persistent autonomous agent\n"
  printf "  ─────────────────────────────────────────\n"
  printf "\n"
}

# ── Prerequisite checks ──────────────────────────────────────────────────────

check_prerequisites() {
  info "Checking prerequisites..."
  local failed=0

  # Bash version (need 4.0+ for associative arrays)
  local bash_major
  bash_major="${BASH_VERSINFO[0]:-0}"
  if [ "$bash_major" -lt 4 ]; then
    warn "bash 4+ required (found bash ${BASH_VERSION:-unknown})"
    if [ "$(uname -s)" = "Darwin" ]; then
      warn "  macOS ships with bash 3. Install with: brew install bash"
    fi
    failed=1
  else
    ok "bash ${BASH_VERSION%%(*} (>= 4.0)"
  fi

  # curl
  if command -v curl &>/dev/null; then
    ok "curl $(curl --version | head -1 | awk '{print $2}')"
  else
    warn "curl not found — required for downloading releases"
    failed=1
  fi

  # jq
  if command -v jq &>/dev/null; then
    ok "jq $(jq --version)"
  else
    warn "jq not found — required for JSON parsing"
    if [ "$(uname -s)" = "Darwin" ]; then
      warn "  Install with: brew install jq"
    else
      warn "  Install with: sudo apt-get install jq  (or your distro's package manager)"
    fi
    failed=1
  fi

  # opencode
  if command -v opencode &>/dev/null; then
    ok "opencode $(opencode --version 2>/dev/null | head -1 || echo '(version unknown)')"
  else
    warn "opencode not found — required for LLM calls"
    warn "  Install from: https://opencode.ai"
    failed=1
  fi

  if [ "$failed" -ne 0 ]; then
    printf "\n"
    die "Prerequisites not met. Install the missing tools and run this installer again."
  fi

  printf "\n"
}

# ── Install directory ────────────────────────────────────────────────────────

prompt_install_dir() {
  local default_dir="${HOME}/.adjutant"
  local install_dir="${ADJUTANT_INSTALL_DIR:-}"

  if [ -z "$install_dir" ]; then
    printf "  ${_BOLD}Install directory${_RESET} [${default_dir}]: "
    read -r install_dir
    install_dir="${install_dir:-$default_dir}"
  fi

  # Expand ~ manually (read doesn't expand tilde)
  install_dir="${install_dir/#\~/$HOME}"

  if [ -e "$install_dir" ] && [ ! -d "$install_dir" ]; then
    die "'${install_dir}' exists and is not a directory."
  fi

  if [ -d "$install_dir" ] && [ -f "${install_dir}/.adjutant-root" ]; then
    printf "\n"
    warn "Adjutant is already installed at '${install_dir}'."
    printf "  Run ${_BOLD}adjutant setup --repair${_RESET} to check the existing installation.\n\n"
    exit 0
  fi

  echo "$install_dir"
}

# ── Resolve version ──────────────────────────────────────────────────────────

resolve_version() {
  local version="${ADJUTANT_VERSION:-}"

  if [ -n "$version" ]; then
    echo "$version"
    return 0
  fi

  info "Fetching latest release..."
  local latest
  latest="$(curl -fsSL "${GITHUB_API}/releases/latest" | jq -r '.tag_name')" \
    || die "Could not fetch latest release from ${GITHUB_API}. Check your internet connection."

  if [ -z "$latest" ] || [ "$latest" = "null" ]; then
    die "No releases found at ${GITHUB_API}. Has a release been published?"
  fi

  echo "$latest"
}

# ── Download and extract ─────────────────────────────────────────────────────

download_and_extract() {
  local version="$1"
  local install_dir="$2"

  local tarball_url="${GITHUB_API}/releases/download/${version}/adjutant-${version}.tar.gz"
  local tmp_dir
  tmp_dir="$(mktemp -d)"
  local tmp_tarball="${tmp_dir}/adjutant.tar.gz"

  # Trap to clean up temp dir on exit
  trap 'rm -rf "${tmp_dir}"' EXIT

  info "Downloading adjutant ${version}..."
  curl -fsSL --progress-bar "$tarball_url" -o "$tmp_tarball" \
    || die "Download failed from ${tarball_url}"
  ok "Downloaded adjutant ${version}"

  info "Extracting to ${install_dir}..."
  mkdir -p "$install_dir"
  tar -xzf "$tmp_tarball" -C "$install_dir" --strip-components=1 \
    || die "Extraction failed. The tarball may be corrupt — try again."
  ok "Extracted to ${install_dir}"
}

# ── Post-install setup ───────────────────────────────────────────────────────

run_wizard() {
  local install_dir="$1"
  local wizard="${install_dir}/scripts/setup/wizard.sh"

  if [ ! -f "$wizard" ]; then
    die "Wizard not found at '${wizard}'. The extraction may have failed."
  fi

  printf "\n"
  printf "  ${_BOLD}Starting setup wizard...${_RESET}\n"
  printf "\n"

  export ADJ_DIR="$install_dir"
  export ADJUTANT_HOME="$install_dir"
  bash "$wizard"
}

# ── Main ─────────────────────────────────────────────────────────────────────

main() {
  print_banner
  check_prerequisites

  local install_dir
  install_dir="$(prompt_install_dir)"
  printf "\n"

  local version
  version="$(resolve_version)"
  ok "Version: ${version}"
  printf "\n"

  download_and_extract "$version" "$install_dir"
  printf "\n"

  if [ "${ADJUTANT_NO_WIZARD:-}" = "true" ]; then
    ok "Adjutant ${version} installed to ${install_dir}"
    info "Run ${_BOLD}bash ${install_dir}/scripts/setup/wizard.sh${_RESET} to complete setup."
  else
    run_wizard "$install_dir"
  fi
}

main "$@"
