#!/bin/bash
# scripts/setup/steps/service.sh — Step 6: Service Installation
#
# Installs platform-appropriate service management:
#   - macOS: LaunchAgent plist for auto-start
#   - Linux: systemd user service
#   - Both: cron job for news briefing (if enabled)
#
# Also handles:
#   - PATH/alias setup for the 'adjutant' CLI
#   - File permissions
#
# Requires: helpers.sh sourced, ADJ_DIR set, ADJUTANT_OS set

step_service() {
  wiz_step 6 7 "Service Installation"
  echo ""

  local os="${ADJUTANT_OS:-unknown}"
  printf "  Platform detected: ${_BOLD}%s${_RESET}\n" "$os"
  echo ""

  # File permissions
  _service_fix_permissions

  # CLI accessibility
  _service_setup_cli

  # Service manager
  case "$os" in
    macos) _service_install_launchd ;;
    linux) _service_install_systemd ;;
    *)
      wiz_warn "Unknown platform — skipping service installation"
      wiz_info "Start manually with: adjutant start"
      ;;
  esac

  # Cron jobs — install all enabled schedules from adjutant.yaml
  echo ""
  _service_install_schedules

  echo ""
  return 0
}

# Fix file permissions
_service_fix_permissions() {
  local adjutant_cli="${ADJ_DIR}/adjutant"

  # Make CLI executable
  if [ -f "$adjutant_cli" ] && [ ! -x "$adjutant_cli" ]; then
    if [ "${DRY_RUN:-}" = "true" ]; then
      dry_run_would "chmod +x ${adjutant_cli}"
      wiz_ok "Would make adjutant CLI executable"
    else
      chmod +x "$adjutant_cli"
      wiz_ok "Made adjutant CLI executable"
    fi
  elif [ -f "$adjutant_cli" ]; then
    wiz_ok "adjutant CLI is executable"
  fi

  # Make all scripts executable
  if [ "${DRY_RUN:-}" = "true" ]; then
    dry_run_would "chmod +x all *.sh files under ${ADJ_DIR}/scripts/"
  else
    find "${ADJ_DIR}/scripts" -name '*.sh' -type f ! -perm -u+x -exec chmod +x {} + 2>/dev/null
  fi
  wiz_ok "Script permissions OK"

  # Restrict .env
  if [ -f "${ADJ_DIR}/.env" ]; then
    if [ "${DRY_RUN:-}" = "true" ]; then
      dry_run_would "chmod 600 ${ADJ_DIR}/.env"
    else
      chmod 600 "${ADJ_DIR}/.env"
    fi
    wiz_ok ".env permissions restricted (600)"
  fi
}

# Set up CLI accessibility (PATH or alias)
_service_setup_cli() {
  local adjutant_cli="${ADJ_DIR}/adjutant"

  # Check if adjutant is already on PATH
  if command -v adjutant >/dev/null 2>&1; then
    wiz_ok "adjutant is on PATH"
    return 0
  fi

  # Check if ADJ_DIR is on PATH
  case ":${PATH}:" in
    *":${ADJ_DIR}:"*)
      wiz_ok "adjutant directory is on PATH"
      return 0
      ;;
  esac

  echo ""
  if ! wiz_confirm "adjutant is not on PATH. Add a shell alias?" "Y"; then
    wiz_info "You can add it later: alias adjutant='${adjutant_cli}'"
    return 0
  fi

  # Detect shell config file
  local shell_rc=""
  local shell_name="${SHELL##*/}"
  case "$shell_name" in
    zsh)  shell_rc="${HOME}/.zshrc" ;;
    bash) shell_rc="${HOME}/.bashrc" ;;
    fish) shell_rc="${HOME}/.config/fish/config.fish" ;;
    *)    shell_rc="${HOME}/.profile" ;;
  esac

  if [ ! -f "$shell_rc" ]; then
    wiz_warn "Shell config not found: ${shell_rc}"
    wiz_info "Add manually: alias adjutant='${adjutant_cli}'"
    return 0
  fi

  # Check if alias already exists
  if grep -q "alias adjutant=" "$shell_rc" 2>/dev/null; then
    wiz_ok "Alias already exists in ${shell_rc}"
    return 0
  fi

  # Add the alias
  if [ "${DRY_RUN:-}" = "true" ]; then
    dry_run_would "append alias adjutant='${adjutant_cli}' to ${shell_rc}"
    wiz_ok "Would add alias to ${shell_rc}"
    wiz_info "Run 'source ${shell_rc}' or restart your terminal"
    return 0
  fi

  if [ "$shell_name" = "fish" ]; then
    echo "alias adjutant '${adjutant_cli}'" >> "$shell_rc"
  else
    echo "" >> "$shell_rc"
    echo "# Adjutant CLI (added by setup wizard)" >> "$shell_rc"
    echo "alias adjutant='${adjutant_cli}'" >> "$shell_rc"
  fi

  wiz_ok "Added alias to ${shell_rc}"
  wiz_info "Run 'source ${shell_rc}' or restart your terminal"
}

# Install macOS LaunchAgent
_service_install_launchd() {
  if ! wiz_confirm "Install Launch Agent for auto-start?" "Y"; then
    wiz_info "Start manually with: adjutant start"
    return 0
  fi

  local plist_dir="${HOME}/Library/LaunchAgents"
  local plist_file="${plist_dir}/com.adjutant.telegram.plist"

  if [ "${DRY_RUN:-}" = "true" ]; then
    dry_run_would "mkdir -p ${plist_dir}"
    dry_run_would "write ${plist_file} (LaunchAgent plist)"
    dry_run_would "launchctl unload ${plist_file}"
    dry_run_would "launchctl load ${plist_file}"
    wiz_ok "Would install and load Launch Agent"
    return 0
  fi

  mkdir -p "$plist_dir"

  cat > "$plist_file" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.adjutant.telegram</string>
  <key>ProgramArguments</key>
  <array>
    <string>${ADJ_DIR}/scripts/messaging/telegram/listener.sh</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <dict>
    <key>SuccessfulExit</key>
    <false/>
  </dict>
  <key>StandardOutPath</key>
  <string>${ADJ_DIR}/state/launchd_stdout.log</string>
  <key>StandardErrorPath</key>
  <string>${ADJ_DIR}/state/launchd_stderr.log</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    <key>ADJUTANT_HOME</key>
    <string>${ADJ_DIR}</string>
  </dict>
</dict>
</plist>
PLIST

  wiz_ok "Created ${plist_file}"

  # Load the agent
  if wiz_confirm "Load launch agent now? (starts the listener)" "Y"; then
    launchctl unload "$plist_file" 2>/dev/null
    launchctl load "$plist_file" 2>/dev/null && {
      wiz_ok "Launch agent loaded"
    } || {
      wiz_warn "Failed to load launch agent"
      wiz_info "Load manually: launchctl load ${plist_file}"
    }
  fi
}

# Install Linux systemd user service
_service_install_systemd() {
  if ! wiz_confirm "Install systemd user service for auto-start?" "Y"; then
    wiz_info "Start manually with: adjutant start"
    return 0
  fi

  local service_dir="${HOME}/.config/systemd/user"
  local service_file="${service_dir}/adjutant-telegram.service"

  if [ "${DRY_RUN:-}" = "true" ]; then
    dry_run_would "mkdir -p ${service_dir}"
    dry_run_would "write ${service_file} (systemd unit file)"
    dry_run_would "systemctl --user daemon-reload"
    dry_run_would "systemctl --user enable adjutant-telegram.service"
    dry_run_would "systemctl --user start adjutant-telegram.service"
    wiz_ok "Would install and start systemd service"
    return 0
  fi

  mkdir -p "$service_dir"

  cat > "$service_file" <<SERVICE
[Unit]
Description=Adjutant Telegram Listener
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=${ADJ_DIR}/scripts/messaging/telegram/listener.sh
Restart=on-failure
RestartSec=10
Environment=ADJUTANT_HOME=${ADJ_DIR}
Environment=PATH=/usr/local/bin:/usr/bin:/bin

[Install]
WantedBy=default.target
SERVICE

  wiz_ok "Created ${service_file}"

  # Enable and start
  if wiz_confirm "Enable and start the service now?" "Y"; then
    systemctl --user daemon-reload 2>/dev/null
    systemctl --user enable adjutant-telegram.service 2>/dev/null && {
      wiz_ok "Service enabled"
    } || wiz_warn "Failed to enable service"

    systemctl --user start adjutant-telegram.service 2>/dev/null && {
      wiz_ok "Service started"
    } || wiz_warn "Failed to start service — check: systemctl --user status adjutant-telegram"
  fi
}

# Install all enabled scheduled jobs from adjutant.yaml schedules:
_service_install_schedules() {
  local count
  count="$(bash -c "source \"${ADJ_DIR}/scripts/capabilities/schedule/manage.sh\" 2>/dev/null && schedule_count" 2>/dev/null || echo "0")"

  if [ "${count}" -eq 0 ]; then
    wiz_info "No scheduled jobs configured in adjutant.yaml schedules:"
    wiz_info "Add one later with: adjutant schedule add"
    return 0
  fi

  if ! wiz_confirm "Install cron entries for enabled scheduled jobs?" "Y"; then
    wiz_info "Run manually with: adjutant schedule sync"
    return 0
  fi

  if [ "${DRY_RUN:-}" = "true" ]; then
    dry_run_would "adjutant schedule sync (install all enabled cron entries)"
    wiz_ok "Would install scheduled job cron entries"
    return 0
  fi

  source "${ADJ_DIR}/scripts/capabilities/schedule/manage.sh"
  source "${ADJ_DIR}/scripts/capabilities/schedule/install.sh"
  schedule_install_all

  local enabled_count=0
  while IFS=$'\t' read -r name desc sched script log enabled notify kb_name kb_operation; do
    [ "${enabled}" = "true" ] && enabled_count=$(( enabled_count + 1 ))
  done < <(schedule_list)

  if [ "${enabled_count}" -gt 0 ]; then
    wiz_ok "Installed ${enabled_count} cron job(s) from schedules:"
  else
    wiz_info "No enabled jobs in schedules: — nothing installed."
    wiz_info "Enable a job with: adjutant schedule enable <name>"
  fi
}
