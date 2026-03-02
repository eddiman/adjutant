#!/bin/bash
# scripts/setup/uninstall.sh — Adjutant uninstaller
#
# Interactively removes Adjutant from the system:
#   1. Confirms intent (requires explicit "yes")
#   2. Stops all running processes
#   3. Removes service (launchd / systemd)
#   4. Offers to remove PATH alias from shell rc file
#   5. Offers to delete all Adjutant files
#
# If only the alias is removed (files kept), informs user of file location
# and how to run this script again for full removal.
#
# Usage:
#   adjutant uninstall
#   bash ~/.adjutant/scripts/setup/uninstall.sh

# ── Bootstrap ────────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../common/paths.sh"
source "${SCRIPT_DIR}/../common/platform.sh"
source "${SCRIPT_DIR}/helpers.sh"

# ── Banner ───────────────────────────────────────────────────────────────────

_uninstall_banner() {
  echo ""
  printf "${_BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${_RESET}\n"
  printf "${_BOLD}  Adjutant — Uninstall${_RESET}\n"
  printf "${_BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${_RESET}\n"
  echo ""
  printf "  Installation directory: ${_BOLD}%s${_RESET}\n" "$ADJ_DIR"
  echo ""
}

# ── Confirmation ─────────────────────────────────────────────────────────────

_uninstall_confirm() {
  printf "  ${_YELLOW}This will stop all Adjutant processes and optionally${_RESET}\n"
  printf "  ${_YELLOW}remove Adjutant from your PATH and/or delete all files.${_RESET}\n"
  echo ""
  printf "  Type ${_BOLD}yes${_RESET} to continue, or anything else to abort: " >/dev/tty
  local answer
  read -r answer </dev/tty
  echo ""

  if [ "$answer" != "yes" ]; then
    printf "  Aborted. Nothing was changed.\n"
    exit 0
  fi
}

# ── Stop processes ───────────────────────────────────────────────────────────

_uninstall_stop_processes() {
  printf "${_BOLD}Stopping processes...${_RESET}\n"
  echo ""

  # ── OpenCode web server ──
  printf "  Stopping OpenCode...\n"
  pkill -TERM -f "opencode web" 2>/dev/null || true
  sleep 1
  pkill -KILL -f "opencode web" 2>/dev/null || true
  rm -f "${ADJ_DIR}/state/opencode_web.pid"
  wiz_ok "OpenCode stopped"

  # ── Telegram listener (3-tier) ──
  printf "  Stopping Telegram listener...\n"

  # Tier 1: nohup launcher PID
  if [ -f "${ADJ_DIR}/state/telegram.pid" ]; then
    local pid
    pid="$(cat "${ADJ_DIR}/state/telegram.pid" 2>/dev/null || true)"
    if [ -n "$pid" ]; then
      kill -TERM "$pid" 2>/dev/null || true
      sleep 1
      kill -KILL "$pid" 2>/dev/null || true
    fi
    rm -f "${ADJ_DIR}/state/telegram.pid"
  fi

  # Tier 2: listener.lock PID (the actual listener process)
  if [ -f "${ADJ_DIR}/state/listener.lock/pid" ]; then
    local lpid
    lpid="$(cat "${ADJ_DIR}/state/listener.lock/pid" 2>/dev/null || true)"
    if [ -n "$lpid" ]; then
      kill -TERM "$lpid" 2>/dev/null || true
      sleep 1
      kill -KILL "$lpid" 2>/dev/null || true
    fi
  fi
  rm -rf "${ADJ_DIR}/state/listener.lock"

  # Tier 3: orphan sweep
  pkill -TERM -f "messaging/telegram/listener\.sh" 2>/dev/null || true
  pkill -TERM -f "telegram_listener\.sh" 2>/dev/null || true

  wiz_ok "Telegram listener stopped"

  # ── News briefing jobs ──
  printf "  Stopping news jobs...\n"
  pkill -TERM -f "news/briefing\.sh"  2>/dev/null || true
  pkill -TERM -f "news_briefing\.sh"  2>/dev/null || true
  pkill -TERM -f "news/fetch\.sh"     2>/dev/null || true
  pkill -TERM -f "news/analyze\.sh"   2>/dev/null || true
  wiz_ok "News jobs stopped"

  # Clear any KILLED lockfile so it doesn't matter for uninstall
  rm -f "${ADJ_DIR}/KILLED"

  echo ""
}

# ── Remove platform service ──────────────────────────────────────────────────

_uninstall_remove_service() {
  case "$ADJUTANT_OS" in
    macos) _uninstall_remove_launchd ;;
    linux) _uninstall_remove_systemd ;;
  esac
}

_uninstall_remove_launchd() {
  local plist_file="${HOME}/Library/LaunchAgents/com.adjutant.telegram.plist"

  # Also handle alternate filename seen on some installs
  local plist_alt="${HOME}/Library/LaunchAgents/adjutant.telegram.plist"

  local found_plist=""
  [ -f "$plist_file" ] && found_plist="$plist_file"
  [ -z "$found_plist" ] && [ -f "$plist_alt" ] && found_plist="$plist_alt"

  if [ -z "$found_plist" ]; then
    wiz_info "No LaunchAgent plist found — skipping"
    return 0
  fi

  printf "${_BOLD}Removing LaunchAgent...${_RESET}\n"
  echo ""

  launchctl unload "$found_plist" 2>/dev/null || true
  rm -f "$found_plist"
  wiz_ok "LaunchAgent removed: $found_plist"
  echo ""
}

_uninstall_remove_systemd() {
  local service_file="${HOME}/.config/systemd/user/adjutant-telegram.service"

  if [ ! -f "$service_file" ]; then
    wiz_info "No systemd service file found — skipping"
    return 0
  fi

  printf "${_BOLD}Removing systemd service...${_RESET}\n"
  echo ""

  systemctl --user stop    adjutant-telegram.service 2>/dev/null || true
  systemctl --user disable adjutant-telegram.service 2>/dev/null || true
  rm -f "$service_file"
  systemctl --user daemon-reload 2>/dev/null || true
  wiz_ok "systemd service removed: $service_file"
  echo ""
}

# ── Remove PATH alias ────────────────────────────────────────────────────────

_uninstall_remove_path() {
  printf "${_BOLD}Shell alias / PATH${_RESET}\n"
  echo ""

  # Detect rc file
  local shell_name="${SHELL##*/}"
  local shell_rc=""
  case "$shell_name" in
    zsh)  shell_rc="${HOME}/.zshrc" ;;
    bash) shell_rc="${HOME}/.bashrc" ;;
    fish) shell_rc="${HOME}/.config/fish/config.fish" ;;
    *)    shell_rc="${HOME}/.profile" ;;
  esac

  # Check if the alias is present in the rc file
  local alias_found=false
  if [ -f "$shell_rc" ]; then
    if grep -q "alias adjutant" "$shell_rc" 2>/dev/null; then
      alias_found=true
    fi
  fi

  if ! $alias_found; then
    wiz_info "No adjutant alias found in ${shell_rc}"
    # Check if ADJ_DIR is on PATH directly
    case ":${PATH}:" in
      *":${ADJ_DIR}:"*)
        wiz_info "Note: ${ADJ_DIR} appears to be on PATH — remove it manually from your shell config if desired"
        ;;
    esac
    echo ""
    return 0
  fi

  wiz_info "Found alias in: ${shell_rc}"
  echo ""

  if ! wiz_confirm "Remove adjutant alias from ${shell_rc}?" "N"; then
    wiz_info "Alias left in place"
    echo ""
    return 0
  fi

  # Remove the alias line and the comment line immediately above it (if present)
  # Handles both bash/zsh style: alias adjutant='...'
  # And fish style:              alias adjutant '...'
  if [ "$shell_name" = "fish" ]; then
    # Fish: remove just the alias line
    sed -i.bak "/alias adjutant /d" "$shell_rc" && rm -f "${shell_rc}.bak"
  else
    # bash/zsh: remove the comment + alias pair written by the wizard
    # The wizard writes:
    #   (blank line)
    #   # Adjutant CLI (added by setup wizard)
    #   alias adjutant='...'
    #
    # Use a two-pass sed: first remove the comment, then the alias line.
    sed -i.bak "/# Adjutant CLI (added by setup wizard)/d" "$shell_rc" && rm -f "${shell_rc}.bak"
    sed -i.bak "/alias adjutant=/d" "$shell_rc" && rm -f "${shell_rc}.bak"
  fi

  wiz_ok "Alias removed from ${shell_rc}"
  wiz_info "Restart your terminal or run: source ${shell_rc}"
  echo ""
}

# ── Remove files ─────────────────────────────────────────────────────────────

_uninstall_remove_files() {
  printf "${_BOLD}Remove all Adjutant files${_RESET}\n"
  echo ""
  wiz_info "This will permanently delete: ${ADJ_DIR}"
  echo ""

  # Warn if running from inside ADJ_DIR
  case "$(pwd)/" in
    "${ADJ_DIR}"/*)
      wiz_warn "Your current directory is inside ${ADJ_DIR}"
      wiz_warn "Your shell's working directory will be gone after removal."
      echo ""
      ;;
  esac

  # Warn if ADJ_DIR is a symlink
  if [ -L "$ADJ_DIR" ]; then
    wiz_warn "${ADJ_DIR} is a symlink — only the symlink will be removed, not the target"
    echo ""
  fi

  if ! wiz_confirm "Permanently delete all files at ${ADJ_DIR}?" "N"; then
    return 1  # caller checks return value
  fi

  # Remove the news crontab entry before deleting files
  if crontab -l 2>/dev/null | grep -q "adjutant\|news/briefing\.sh\|news_briefing\.sh"; then
    printf "  Removing crontab entries...\n"
    # Backup first
    crontab -l 2>/dev/null > "/tmp/adjutant_crontab_backup_$(date +%s).txt" || true
    # Strip adjutant-related lines
    ( crontab -l 2>/dev/null | grep -v "adjutant\|news/briefing\.sh\|news_briefing\.sh" ) | crontab - 2>/dev/null || true
    wiz_ok "Crontab entries removed"
  fi

  # Delete the installation directory
  rm -rf "$ADJ_DIR"
  wiz_ok "Deleted: ${ADJ_DIR}"
  echo ""
  return 0
}

# ── Files-intact notice ───────────────────────────────────────────────────────

_uninstall_files_intact_notice() {
  echo ""
  printf "${_BOLD}${_YELLOW}  Your Adjutant files are intact.${_RESET}\n"
  printf "  Location: ${_BOLD}%s${_RESET}\n" "$ADJ_DIR"
  echo ""
  printf "  To fully remove Adjutant, run:\n"
  printf "    ${_BOLD}%s/scripts/setup/uninstall.sh${_RESET}\n" "$ADJ_DIR"
  echo ""
}

# ── Summary ──────────────────────────────────────────────────────────────────

_uninstall_summary() {
  local files_removed="$1"

  printf "${_BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${_RESET}\n"
  if $files_removed; then
    printf "${_BOLD}${_GREEN}  Adjutant has been uninstalled.${_RESET}\n"
  else
    printf "${_BOLD}  Adjutant processes stopped.${_RESET}\n"
  fi
  printf "${_BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${_RESET}\n"
  echo ""
}

# ── Main ─────────────────────────────────────────────────────────────────────

main() {
  _uninstall_banner
  _uninstall_confirm
  _uninstall_stop_processes
  _uninstall_remove_service
  _uninstall_remove_path

  local files_removed=false
  if _uninstall_remove_files; then
    files_removed=true
  else
    _uninstall_files_intact_notice
  fi

  _uninstall_summary "$files_removed"
}

main "$@"
