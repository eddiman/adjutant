#!/bin/bash
# scripts/setup/steps/autonomy.sh — Step 7: Autonomy Configuration
#
# Guides the user through enabling autonomous pulse checks and daily reviews:
#   - Enable/disable the autonomous cycle
#   - Set notification budget (max_per_day)
#   - Configure quiet hours
#   - Enable pulse/review scheduled jobs via the schedule registry
#
# Pulse and review schedules are managed in adjutant.yaml schedules: as the
# autonomous_pulse and autonomous_review entries. To change their schedule,
# edit adjutant.yaml schedules: directly or use:
#   adjutant schedule disable autonomous_pulse
#   adjutant schedule remove autonomous_pulse
#   adjutant schedule add
#
# Sets:
#   WIZARD_AUTONOMY_ENABLED=true/false
#   WIZARD_AUTONOMY_MAX_PER_DAY=<integer>
#
# Requires: helpers.sh sourced, ADJ_DIR set

WIZARD_AUTONOMY_ENABLED=false
WIZARD_AUTONOMY_MAX_PER_DAY=3

step_autonomy() {
  wiz_step 7 7 "Autonomy Configuration"
  echo ""

  printf "  Autonomy mode lets Adjutant query your knowledge bases on a schedule,\n"
  printf "  surface significant signals, and send you Telegram notifications.\n"
  printf "  You remain in full control via the PAUSED kill switch and a notification budget.\n"
  echo ""
  printf "  ${_DIM}Pulse schedule:  0 9,17 * * 1-5  (weekdays 9am and 5pm)${_RESET}\n"
  printf "  ${_DIM}Review schedule: 0 20 * * 1-5    (weekdays 8pm)${_RESET}\n"
  printf "  ${_DIM}Edit in adjutant.yaml schedules: or with: adjutant schedule disable autonomous_pulse${_RESET}\n"
  echo ""

  if ! wiz_confirm "Enable autonomous pulse checks?" "N"; then
    WIZARD_AUTONOMY_ENABLED=false
    wiz_info "Autonomy disabled — enable later by setting autonomy.enabled: true in adjutant.yaml"
    wiz_info "Then run: adjutant schedule enable autonomous_pulse"
    _autonomy_update_config
    echo ""
    return 0
  fi

  WIZARD_AUTONOMY_ENABLED=true
  wiz_ok "Autonomy enabled"
  echo ""

  # Notification budget
  printf "  ${_BOLD}Notification budget${_RESET} (hard limit: sends are blocked once this is reached)\n"
  local budget_input
  budget_input="$(wiz_input "Maximum notifications per day" "3")"
  WIZARD_AUTONOMY_MAX_PER_DAY="${budget_input:-3}"
  wiz_ok "Max notifications per day: ${WIZARD_AUTONOMY_MAX_PER_DAY}"
  echo ""

  # Quiet hours
  if wiz_confirm "Enable quiet hours? (suppress notifications during these hours)" "N"; then
    local quiet_start quiet_end
    quiet_start="$(wiz_input "Quiet hours start (HH:MM, 24h)" "22:00")"
    quiet_end="$(wiz_input "Quiet hours end (HH:MM, 24h)" "07:00")"
    quiet_start="${quiet_start:-22:00}"
    quiet_end="${quiet_end:-07:00}"
    wiz_ok "Quiet hours: ${quiet_start} – ${quiet_end}"
    _autonomy_update_config
    _autonomy_update_quiet_hours "true" "${quiet_start}" "${quiet_end}"
  else
    wiz_info "Quiet hours disabled"
    _autonomy_update_config
  fi

  # Enable scheduled jobs via registry
  echo ""
  _autonomy_enable_schedules
  echo ""

  return 0
}

# Write autonomy config values to adjutant.yaml (enabled flag only)
_autonomy_update_config() {
  local config_file="${ADJ_DIR}/adjutant.yaml"
  [ ! -f "${config_file}" ] && return 0

  if [ "${DRY_RUN:-}" = "true" ]; then
    dry_run_would "write autonomy config to ${config_file}"
    return 0
  fi

  local enabled_val="false"
  [ "${WIZARD_AUTONOMY_ENABLED}" = "true" ] && enabled_val="true"

  # Update notifications.max_per_day
  local tmpfile="${config_file}.tmp.$$"
  awk -v enabled="${enabled_val}" \
      -v maxday="${WIZARD_AUTONOMY_MAX_PER_DAY}" '
    /^autonomy:/ { in_autonomy=1; print; next }
    in_autonomy && /^[^ ]/ { in_autonomy=0 }
    in_autonomy && /enabled:/ {
      sub(/enabled:.*/, "enabled: " enabled)
    }
    /max_per_day:/ {
      sub(/max_per_day:.*/, "max_per_day: " maxday)
    }
    { print }
  ' "${config_file}" > "${tmpfile}" && mv "${tmpfile}" "${config_file}"
}

# Update quiet_hours settings in adjutant.yaml
_autonomy_update_quiet_hours() {
  local enabled="$1"
  local start="$2"
  local end="$3"
  local config_file="${ADJ_DIR}/adjutant.yaml"

  [ ! -f "${config_file}" ] && return 0
  [ "${DRY_RUN:-}" = "true" ] && { dry_run_would "update quiet_hours in ${config_file}"; return 0; }

  local tmpfile="${config_file}.tmp.$$"
  awk -v qenabled="${enabled}" -v qstart="${start}" -v qend="${end}" '
    /quiet_hours:/ { in_qh=1; print; next }
    in_qh && /^[[:space:]]*enabled:/ {
      sub(/enabled:.*/, "enabled: " qenabled); in_qh=2
    }
    in_qh==2 && /^[[:space:]]*start:/ {
      sub(/start:.*/, "start: \"" qstart "\"")
    }
    in_qh==2 && /^[[:space:]]*end:/ {
      sub(/end:.*/, "end: \"" qend "\""); in_qh=0
    }
    { print }
  ' "${config_file}" > "${tmpfile}" && mv "${tmpfile}" "${config_file}"
}

# Enable autonomous_pulse and autonomous_review in the schedule registry
_autonomy_enable_schedules() {
  if [ "${DRY_RUN:-}" = "true" ]; then
    dry_run_would "schedule_set_enabled autonomous_pulse true"
    dry_run_would "schedule_set_enabled autonomous_review true"
    wiz_ok "Would enable autonomous_pulse and autonomous_review in schedules:"
    return 0
  fi

  if ! source "${ADJ_DIR}/scripts/capabilities/schedule/manage.sh" 2>/dev/null; then
    wiz_warn "Could not load schedule manager — enable manually with: adjutant schedule enable autonomous_pulse"
    return 0
  fi

  local installed=0

  if schedule_exists "autonomous_pulse" 2>/dev/null; then
    if schedule_set_enabled "autonomous_pulse" "true" 2>/dev/null; then
      wiz_ok "autonomous_pulse enabled (weekdays 9am and 5pm)"
      installed=$(( installed + 1 ))
    else
      wiz_warn "Failed to enable autonomous_pulse — run: adjutant schedule enable autonomous_pulse"
    fi
  else
    wiz_warn "autonomous_pulse not found in schedules: — add it with: adjutant schedule add"
  fi

  if schedule_exists "autonomous_review" 2>/dev/null; then
    if schedule_set_enabled "autonomous_review" "true" 2>/dev/null; then
      wiz_ok "autonomous_review enabled (weekdays 8pm)"
      installed=$(( installed + 1 ))
    else
      wiz_warn "Failed to enable autonomous_review — run: adjutant schedule enable autonomous_review"
    fi
  else
    wiz_warn "autonomous_review not found in schedules: — add it with: adjutant schedule add"
  fi

  if [ "${installed}" -gt 0 ]; then
    wiz_info "Cron entries installed. Adjust schedules in adjutant.yaml schedules: if needed."
  fi
}
