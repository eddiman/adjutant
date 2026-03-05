#!/bin/bash
# scripts/setup/repair.sh — Re-runnable health check and repair
#
# Detects issues with an existing Adjutant installation and offers
# to fix each one with user confirmation (prompt-before-fix).
#
# Run via: adjutant setup (on existing install)
#     or:  adjutant setup --repair
#
# Checks:
#   - adjutant.yaml present
#   - .env present with valid credentials
#   - CLI executable and on PATH
#   - Script permissions
#   - Required directories exist
#   - Dependencies available
#   - Listener running
#   - Scheduled jobs synced to crontab
#
# Requires: helpers.sh sourced, ADJ_DIR set

# Requires: helpers.sh sourced (by wizard.sh before sourcing us)

run_repair() {
  echo ""
  printf "  ${_BOLD}Checking installation health...${_RESET}\n"
  echo ""

  local issues_found=0
  local issues_fixed=0

  # ── Config File ──────────────────────────────────────────────────────────
  if [ -f "${ADJ_DIR}/adjutant.yaml" ]; then
    wiz_ok "adjutant.yaml present"
  else
    wiz_fail "adjutant.yaml missing"
    issues_found=$((issues_found + 1))
    if wiz_confirm "Create default adjutant.yaml?" "Y"; then
      source "${SETUP_DIR}/wizard.sh" 2>/dev/null || true
      # Write minimal config inline to avoid circular source
      if [ "${DRY_RUN:-}" = "true" ]; then
        dry_run_would "write ${ADJ_DIR}/adjutant.yaml (minimal config)"
        wiz_ok "  -> would create adjutant.yaml"
      else
        cat > "${ADJ_DIR}/adjutant.yaml" <<'YAML'
instance:
  name: "adjutant"
identity:
  soul: "identity/soul.md"
  heart: "identity/heart.md"
  registry: "identity/registry.md"
messaging:
  backend: "telegram"
features:
  news:
    enabled: false
  screenshot:
    enabled: true
  vision:
    enabled: true
  usage_tracking:
    enabled: true
YAML
        wiz_ok "  -> fixed (created adjutant.yaml)"
      fi
      issues_fixed=$((issues_fixed + 1))
    fi
  fi

  # ── Credentials ──────────────────────────────────────────────────────────
  if [ -f "${ADJ_DIR}/.env" ]; then
    local token chatid
    token=$(grep -E '^TELEGRAM_BOT_TOKEN=' "${ADJ_DIR}/.env" | head -1 | cut -d'=' -f2- | tr -d "'\"")
    chatid=$(grep -E '^TELEGRAM_CHAT_ID=' "${ADJ_DIR}/.env" | head -1 | cut -d'=' -f2- | tr -d "'\"")

    if [ -n "$token" ] && [ "$token" != "your-bot-token-here" ] && \
       [ -n "$chatid" ] && [ "$chatid" != "your-chat-id-here" ]; then
      wiz_ok ".env present with valid credentials"
    else
      wiz_fail ".env present but credentials are placeholder values"
      issues_found=$((issues_found + 1))
      if wiz_confirm "Run Telegram credential setup?" "Y"; then
        source "${SETUP_DIR}/steps/messaging.sh"
        step_messaging && issues_fixed=$((issues_fixed + 1))
      fi
    fi
  else
    wiz_fail ".env missing"
    issues_found=$((issues_found + 1))
    if wiz_confirm "Create .env with Telegram credentials?" "Y"; then
      source "${SETUP_DIR}/steps/messaging.sh"
      step_messaging && issues_fixed=$((issues_fixed + 1))
    fi
  fi

  # ── CLI Executable ───────────────────────────────────────────────────────
  local adjutant_cli="${ADJ_DIR}/adjutant"
  if [ -f "$adjutant_cli" ]; then
    if [ -x "$adjutant_cli" ]; then
      wiz_ok "adjutant CLI executable"
    else
      wiz_fail "adjutant CLI not executable"
      issues_found=$((issues_found + 1))
      if wiz_confirm "Fix permissions (chmod +x)?" "Y"; then
        if [ "${DRY_RUN:-}" = "true" ]; then
          dry_run_would "chmod +x ${adjutant_cli}"
          wiz_ok "  -> would fix"
        else
          chmod +x "$adjutant_cli"
          wiz_ok "  -> fixed"
        fi
        issues_fixed=$((issues_fixed + 1))
      fi
    fi
  else
    wiz_warn "adjutant CLI not found at ${adjutant_cli}"
  fi

  # ── PATH Check ───────────────────────────────────────────────────────────
  if command -v adjutant >/dev/null 2>&1; then
    wiz_ok "adjutant on PATH"
  else
    wiz_warn "adjutant not on PATH"
    issues_found=$((issues_found + 1))

    local shell_name="${SHELL##*/}"
    local shell_rc=""
    case "$shell_name" in
      zsh)  shell_rc="${HOME}/.zshrc" ;;
      bash) shell_rc="${HOME}/.bashrc" ;;
      *)    shell_rc="${HOME}/.profile" ;;
    esac

    if [ -n "$shell_rc" ] && [ -f "$shell_rc" ]; then
      if ! grep -q "alias adjutant=" "$shell_rc" 2>/dev/null; then
        if wiz_confirm "Add alias to ${shell_rc}?" "Y"; then
          if [ "${DRY_RUN:-}" = "true" ]; then
            dry_run_would "append alias adjutant='${adjutant_cli}' to ${shell_rc}"
            wiz_ok "  -> would add alias to ${shell_rc}"
          else
            echo "" >> "$shell_rc"
            echo "# Adjutant CLI (added by setup wizard)" >> "$shell_rc"
            echo "alias adjutant='${adjutant_cli}'" >> "$shell_rc"
            wiz_ok "  -> added alias to ${shell_rc}"
          fi
          issues_fixed=$((issues_fixed + 1))
        fi
      else
        wiz_ok "  -> alias already in ${shell_rc}"
      fi
    fi
  fi

  # ── Script Permissions ───────────────────────────────────────────────────
  local non_exec_scripts
  non_exec_scripts=$(find "${ADJ_DIR}/scripts" -name '*.sh' -type f ! -perm -u+x 2>/dev/null | wc -l | tr -d ' ')
  if [ "$non_exec_scripts" -eq 0 ]; then
    wiz_ok "scripts/ permissions OK"
  else
    wiz_fail "${non_exec_scripts} scripts not executable"
    issues_found=$((issues_found + 1))
    if wiz_confirm "Fix script permissions?" "Y"; then
      if [ "${DRY_RUN:-}" = "true" ]; then
        dry_run_would "chmod +x all *.sh files under ${ADJ_DIR}/scripts/"
        wiz_ok "  -> would fix"
      else
        find "${ADJ_DIR}/scripts" -name '*.sh' -type f ! -perm -u+x -exec chmod +x {} +
        wiz_ok "  -> fixed"
      fi
      issues_fixed=$((issues_fixed + 1))
    fi
  fi

  # ── .env Permissions ─────────────────────────────────────────────────────
  if [ -f "${ADJ_DIR}/.env" ]; then
    local env_perms
    if [ "$ADJUTANT_OS" = "macos" ]; then
      env_perms=$(stat -f "%Lp" "${ADJ_DIR}/.env" 2>/dev/null)
    else
      env_perms=$(stat -c "%a" "${ADJ_DIR}/.env" 2>/dev/null)
    fi
    if [ "$env_perms" = "600" ]; then
      wiz_ok ".env permissions (600)"
    else
      wiz_warn ".env permissions are ${env_perms} (should be 600)"
      issues_found=$((issues_found + 1))
      if wiz_confirm "Restrict .env to owner-only (chmod 600)?" "Y"; then
        if [ "${DRY_RUN:-}" = "true" ]; then
          dry_run_would "chmod 600 ${ADJ_DIR}/.env"
          wiz_ok "  -> would fix"
        else
          chmod 600 "${ADJ_DIR}/.env"
          wiz_ok "  -> fixed"
        fi
        issues_fixed=$((issues_fixed + 1))
      fi
    fi
  fi

  # ── Required Directories ─────────────────────────────────────────────────
  local required_dirs=(state journal identity prompts photos screenshots)
  for d in "${required_dirs[@]}"; do
    if [ -d "${ADJ_DIR}/${d}" ]; then
      wiz_ok "${d}/ directory exists"
    else
      wiz_fail "${d}/ directory missing"
      issues_found=$((issues_found + 1))
      if wiz_confirm "Create ${d}/?" "Y"; then
        if [ "${DRY_RUN:-}" = "true" ]; then
          dry_run_would "mkdir -p ${ADJ_DIR}/${d}"
          wiz_ok "  -> would create"
        else
          mkdir -p "${ADJ_DIR}/${d}"
          wiz_ok "  -> created"
        fi
        issues_fixed=$((issues_fixed + 1))
      fi
    fi
  done

  # ── Dependencies ─────────────────────────────────────────────────────────
  wiz_ok "Dependencies:"
  local all_deps_ok=true
  for cmd in bash curl jq python3 opencode; do
    if has_command "$cmd"; then
      printf "    %-12s OK\n" "$cmd"
    else
      printf "    %-12s ${_RED}MISSING${_RESET}\n" "$cmd"
      all_deps_ok=false
    fi
  done
  if ! $all_deps_ok; then
    issues_found=$((issues_found + 1))
  fi

  # ── Listener Status ──────────────────────────────────────────────────────
  # Delegate to service.sh for authoritative listener detection (checks
  # listener.lock/pid, telegram.pid, and pgrep — in that order).
  local listener_status
  if [ -f "${ADJ_DIR}/scripts/messaging/telegram/service.sh" ]; then
    listener_status="$(bash "${ADJ_DIR}/scripts/messaging/telegram/service.sh" status 2>/dev/null)"
  else
    listener_status="Stopped"
  fi

  if echo "${listener_status}" | grep -q "^Running"; then
    wiz_ok "Listener: ${listener_status}"
  else
    wiz_warn "Listener not running"
    issues_found=$((issues_found + 1))
    if wiz_confirm "Start the listener now?" "Y"; then
      if [ "${DRY_RUN:-}" = "true" ]; then
        dry_run_would "bash ${ADJ_DIR}/scripts/messaging/telegram/service.sh start"
        wiz_ok "  -> would start listener"
        issues_fixed=$((issues_fixed + 1))
      elif [ -f "${ADJ_DIR}/scripts/messaging/telegram/service.sh" ]; then
        local start_output
        start_output="$(bash "${ADJ_DIR}/scripts/messaging/telegram/service.sh" start 2>&1)"
        if echo "${start_output}" | grep -q "^Started\|^Already running"; then
          wiz_ok "  -> ${start_output}"
          issues_fixed=$((issues_fixed + 1))
        else
          wiz_warn "  -> ${start_output}"
        fi
      else
        wiz_warn "  -> service.sh not found"
      fi
    fi
  fi

  # ── Scheduled Jobs ───────────────────────────────────────────────────────
  # Check that every enabled job in the registry has a crontab entry.
  # Uses the schedule registry — not hardcoded job names.
  if source "${ADJ_DIR}/scripts/capabilities/schedule/manage.sh" 2>/dev/null && \
     source "${ADJ_DIR}/scripts/capabilities/schedule/install.sh" 2>/dev/null; then
    local sched_count
    sched_count="$(schedule_count 2>/dev/null || echo 0)"
    if [ "${sched_count}" -gt 0 ]; then
      local missing_jobs=0
      while IFS=$'\t' read -r name desc sched script logf enabled; do
        [ -z "${name}" ] && continue
        [ "${enabled}" != "true" ] && continue
        local marker="# adjutant:${name}"
        if ! crontab -l 2>/dev/null | grep -qF "${marker}"; then
          missing_jobs=$((missing_jobs + 1))
        fi
      done < <(schedule_list 2>/dev/null)

      if [ "${missing_jobs}" -eq 0 ]; then
        wiz_ok "Scheduled jobs: all ${sched_count} job(s) synced to crontab"
      else
        wiz_warn "Scheduled jobs: ${missing_jobs} enabled job(s) missing from crontab"
        issues_found=$((issues_found + 1))
        if wiz_confirm "Sync schedule registry to crontab now?" "Y"; then
          if [ "${DRY_RUN:-}" = "true" ]; then
            dry_run_would "adjutant schedule sync (schedule_install_all)"
            wiz_ok "  -> would sync"
          else
            schedule_install_all 2>/dev/null && wiz_ok "  -> synced" || wiz_warn "  -> sync failed"
          fi
          issues_fixed=$((issues_fixed + 1))
        fi
      fi
    else
      wiz_info "Scheduled jobs: none registered"
    fi
  else
    wiz_warn "Scheduled jobs: could not load schedule registry (skipping check)"
  fi

  # ── Summary ──────────────────────────────────────────────────────────────
  echo ""
  if [ "$issues_found" -eq 0 ]; then
    wiz_ok "All checks passed. Adjutant is healthy."
  elif [ "$issues_fixed" -eq "$issues_found" ]; then
    wiz_ok "Found ${issues_found} issue(s), all fixed."
  else
    local remaining=$((issues_found - issues_fixed))
    wiz_warn "Found ${issues_found} issue(s), fixed ${issues_fixed}, ${remaining} remaining."
  fi
  echo ""
}
