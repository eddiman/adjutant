#!/bin/bash
# scripts/lifecycle/update.sh — Adjutant self-update mechanism
#
# Checks GitHub releases for a newer version, downloads it, backs up the
# current install, extracts the new framework files, and runs adjutant doctor.
#
# Usage:
#   bash scripts/lifecycle/update.sh            # interactive
#   adjutant update                             # via CLI
#   adjutant update --check                     # check only, no install
#   adjutant update --yes                       # non-interactive (auto-confirm)
#
# Environment variables:
#   ADJUTANT_REPO     GitHub owner/repo (default: eddiman/adjutant)
#   ADJUTANT_VERSION  Force a specific version tag to install

set -euo pipefail

# Resolve ADJ_DIR
source "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/common/paths.sh"
source "${ADJ_DIR}/scripts/common/logging.sh"

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

info()  { printf "  ${_CYAN}→${_RESET} %s\n" "$*"; }
ok()    { printf "  ${_GREEN}✓${_RESET} %s\n" "$*"; }
warn()  { printf "  ${_YELLOW}!${_RESET} %s\n" "$*"; }
die()   { printf "\n  ${_RED}✗ Error:${_RESET} %s\n\n" "$*" >&2; exit 1; }

# ── Semver comparison ────────────────────────────────────────────────────────
# Returns 0 if $1 < $2 (i.e. an update is available)
# Returns 1 if $1 >= $2 (already up to date or ahead)
_semver_lt() {
  local current="$1" latest="$2"
  # Strip leading 'v'
  current="${current#v}"
  latest="${latest#v}"

  local IFS='.'
  local c=($current) l=($latest)

  # Pad arrays to same length
  while [ "${#c[@]}" -lt 3 ]; do c+=("0"); done
  while [ "${#l[@]}" -lt 3 ]; do l+=("0"); done

  for i in 0 1 2; do
    local cv="${c[$i]:-0}" lv="${l[$i]:-0}"
    if [ "$cv" -lt "$lv" ]; then return 0; fi
    if [ "$cv" -gt "$lv" ]; then return 1; fi
  done
  return 1  # Equal — not an update
}

# ── Get current version ──────────────────────────────────────────────────────
get_current_version() {
  local ver_file="${ADJ_DIR}/VERSION"
  if [ -f "$ver_file" ]; then
    cat "$ver_file" | tr -d '[:space:]'
  else
    echo "unknown"
  fi
}

# ── Get latest remote version ────────────────────────────────────────────────
get_latest_version() {
  local latest
  latest="$(curl -fsSL "${GITHUB_API}/releases/latest" 2>/dev/null \
    | jq -r '.tag_name // empty' 2>/dev/null)" \
    || die "Could not reach GitHub API at ${GITHUB_API}. Check your internet connection."

  if [ -z "$latest" ] || [ "$latest" = "null" ]; then
    die "No releases found at ${GITHUB_API}. Has a release been published?"
  fi

  echo "$latest"
}

# ── Backup current install ───────────────────────────────────────────────────
backup_current() {
  local backup_dir="${ADJ_DIR}/.backup"
  local timestamp
  timestamp="$(date '+%Y%m%d_%H%M%S')"
  local backup_path="${backup_dir}/pre-update_${timestamp}"

  mkdir -p "${backup_path}"

  info "Backing up current install to ${backup_path}..."
  # Back up framework dirs only (not user data)
  for dir in scripts templates tests; do
    if [ -d "${ADJ_DIR}/${dir}" ]; then
      cp -r "${ADJ_DIR}/${dir}" "${backup_path}/${dir}"
    fi
  done
  for f in adjutant VERSION .adjutant-root; do
    if [ -f "${ADJ_DIR}/${f}" ]; then
      cp "${ADJ_DIR}/${f}" "${backup_path}/${f}"
    fi
  done

  ok "Backup saved to ${backup_path}"
  echo "${backup_path}"
}

# ── Download and extract update ──────────────────────────────────────────────
download_and_apply() {
  local version="$1"

  local tarball_url="https://github.com/${ADJUTANT_REPO}/releases/download/${version}/adjutant-${version}.tar.gz"
  local tmp_dir
  tmp_dir="$(mktemp -d)"
  local tmp_tarball="${tmp_dir}/adjutant.tar.gz"

  trap 'rm -rf "${tmp_dir}"' EXIT

  info "Downloading adjutant ${version}..."
  curl -fsSL --progress-bar "$tarball_url" -o "$tmp_tarball" \
    || die "Download failed from ${tarball_url}"
  ok "Downloaded adjutant ${version}"

  info "Extracting update..."
  local extract_dir="${tmp_dir}/extracted"
  mkdir -p "$extract_dir"
  tar -xzf "$tmp_tarball" -C "$extract_dir" --strip-components=1 \
    || die "Extraction failed. The tarball may be corrupt — try again."

  # Copy framework files from extracted tarball to ADJ_DIR
  # Exclude user data directories that may exist in ADJ_DIR
  info "Applying update to ${ADJ_DIR}..."
  rsync -a \
    --exclude='adjutant.yaml' \
    --exclude='identity/soul.md' \
    --exclude='identity/heart.md' \
    --exclude='identity/registry.md' \
    --exclude='news_config.json' \
    --exclude='.env' \
    --exclude='journal/' \
    --exclude='knowledge_bases/' \
    --exclude='state/' \
    --exclude='insights/' \
    --exclude='photos/' \
    --exclude='screenshots/' \
    "${extract_dir}/" "${ADJ_DIR}/"

  ok "Applied adjutant ${version}"
}

# ── Main ─────────────────────────────────────────────────────────────────────

main() {
  local check_only=false
  local auto_yes=false
  local force_version="${ADJUTANT_VERSION:-}"

  for arg in "$@"; do
    case "$arg" in
      --check)  check_only=true ;;
      --yes|-y) auto_yes=true ;;
      --help|-h)
        printf "Usage: adjutant update [--check] [--yes]\n\n"
        printf "  --check   Check for updates without installing\n"
        printf "  --yes     Non-interactive (auto-confirm install)\n"
        exit 0
        ;;
    esac
  done

  printf "\n  ${_BOLD}Adjutant Update${_RESET}\n\n"

  local current_version
  current_version="$(get_current_version)"
  info "Current version: ${current_version}"

  local target_version
  if [ -n "$force_version" ]; then
    target_version="$force_version"
    info "Target version: ${target_version} (forced)"
  else
    info "Checking for updates..."
    target_version="$(get_latest_version)"
    info "Latest version:  ${target_version}"
  fi

  printf "\n"

  # Strip leading 'v' for comparison
  local current_clean="${current_version#v}"
  local target_clean="${target_version#v}"

  if [ "$current_clean" = "unknown" ]; then
    warn "Cannot determine current version — VERSION file missing."
    warn "Proceeding with update anyway."
  elif ! _semver_lt "${current_clean}" "${target_clean}"; then
    ok "Already up to date (${current_version})."
    printf "\n"
    exit 0
  fi

  if $check_only; then
    printf "  Update available: ${current_version} → ${target_version}\n"
    printf "  Run ${_BOLD}adjutant update${_RESET} to install.\n\n"
    exit 0
  fi

  printf "  Update available: ${_BOLD}${current_version} → ${target_version}${_RESET}\n\n"

  # Confirm
  if ! $auto_yes; then
    printf "  Continue? [y/N] "
    local answer
    read -r answer
    case "$answer" in
      [Yy]*) ;;
      *) printf "\n  Cancelled.\n\n"; exit 0 ;;
    esac
    printf "\n"
  fi

  # Check if listener is running — warn but don't block
  if bash "${ADJ_DIR}/scripts/messaging/telegram/service.sh" status 2>/dev/null | grep -qi "running"; then
    warn "Listener is currently running."
    warn "It will continue using the old scripts until restarted."
    warn "Run ${_BOLD}adjutant restart${_RESET} after the update completes."
    printf "\n"
  fi

  backup_current

  printf "\n"

  download_and_apply "$target_version"

  printf "\n"
  ok "Update complete: ${current_version} → ${target_version}"
  printf "\n"

  # Run doctor to verify the updated install
  info "Running health check..."
  printf "\n"
  bash "${ADJ_DIR}/adjutant" doctor

  printf "\n"
  info "If the listener was running, restart it with: ${_BOLD}adjutant restart${_RESET}"
  printf "\n"

  adj_log lifecycle "Updated from ${current_version} to ${target_version}"
}

main "$@"
