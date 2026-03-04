#!/bin/bash
# scripts/setup/steps/autonomy.sh — Step 7: Autonomy Configuration
#
# Guides the user through enabling autonomous pulse checks and daily reviews:
#   - Enable/disable the autonomous cycle
#   - Configure pulse and review cron schedules
#   - Set notification budget (max_per_day)
#   - Configure quiet hours
#   - Install cron jobs if autonomy is enabled
#
# Sets:
#   WIZARD_AUTONOMY_ENABLED=true/false
#   WIZARD_AUTONOMY_PULSE_SCHEDULE=<cron expression>
#   WIZARD_AUTONOMY_REVIEW_SCHEDULE=<cron expression>
#   WIZARD_AUTONOMY_MAX_PER_DAY=<integer>
#
# Requires: helpers.sh sourced, ADJ_DIR set

WIZARD_AUTONOMY_ENABLED=false
WIZARD_AUTONOMY_PULSE_SCHEDULE="0 9,17 * * 1-5"
WIZARD_AUTONOMY_REVIEW_SCHEDULE="0 20 * * 1-5"
WIZARD_AUTONOMY_MAX_PER_DAY=3

step_autonomy() {
  wiz_step 7 7 "Autonomy Configuration"
  echo ""

  printf "  Autonomy mode lets Adjutant query your knowledge bases on a schedule,\n"
  printf "  surface significant signals, and send you Telegram notifications.\n"
  printf "  You remain in full control via the PAUSED kill switch and a notification budget.\n"
  echo ""

  if ! wiz_confirm "Enable autonomous pulse checks?" "N"; then
    WIZARD_AUTONOMY_ENABLED=false
    wiz_info "Autonomy disabled — enable later by setting autonomy.enabled: true in adjutant.yaml"
    _autonomy_update_config
    echo ""
    return 0
  fi

  WIZARD_AUTONOMY_ENABLED=true
  wiz_ok "Autonomy enabled"
  echo ""

  # Pulse schedule
  printf "  ${_BOLD}Pulse schedule${_RESET} (cron syntax — how often to check all KBs)\n"
  printf "  Default: ${_DIM}0 9,17 * * 1-5${_RESET}  (weekdays at 9am and 5pm)\n"
  echo ""
  if wiz_confirm "Use the default pulse schedule?" "Y"; then
    WIZARD_AUTONOMY_PULSE_SCHEDULE="0 9,17 * * 1-5"
    wiz_ok "Pulse: weekdays at 9am and 5pm"
  else
    local custom_pulse
    custom_pulse="$(wiz_input "Pulse cron schedule" "0 9,17 * * 1-5")"
    WIZARD_AUTONOMY_PULSE_SCHEDULE="${custom_pulse:-0 9,17 * * 1-5}"
    wiz_ok "Pulse: ${WIZARD_AUTONOMY_PULSE_SCHEDULE}"
  fi
  echo ""

  # Daily review
  printf "  ${_BOLD}Daily review${_RESET} (deep synthesis, may trigger Telegram notifications)\n"
  printf "  Default: ${_DIM}0 20 * * 1-5${_RESET}  (weekdays at 8pm)\n"
  echo ""
  if wiz_confirm "Enable daily review?" "Y"; then
    if wiz_confirm "Use the default review schedule?" "Y"; then
      WIZARD_AUTONOMY_REVIEW_SCHEDULE="0 20 * * 1-5"
      wiz_ok "Review: weekdays at 8pm"
    else
      local custom_review
      custom_review="$(wiz_input "Review cron schedule" "0 20 * * 1-5")"
      WIZARD_AUTONOMY_REVIEW_SCHEDULE="${custom_review:-0 20 * * 1-5}"
      wiz_ok "Review: ${WIZARD_AUTONOMY_REVIEW_SCHEDULE}"
    fi
  else
    WIZARD_AUTONOMY_REVIEW_SCHEDULE=""
    wiz_info "Daily review disabled"
  fi
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

  # Install cron jobs
  echo ""
  _autonomy_install_crons
  echo ""

  return 0
}

# Write autonomy config values to adjutant.yaml
_autonomy_update_config() {
  local config_file="${ADJ_DIR}/adjutant.yaml"
  [ ! -f "${config_file}" ] && return 0

  if [ "${DRY_RUN:-}" = "true" ]; then
    dry_run_would "write autonomy config to ${config_file}"
    return 0
  fi

  local enabled_val="false"
  [ "${WIZARD_AUTONOMY_ENABLED}" = "true" ] && enabled_val="true"

  # Update autonomy.enabled
  if grep -qE '^autonomy:' "${config_file}" 2>/dev/null; then
    local tmpfile="${config_file}.tmp.$$"
    awk -v enabled="${enabled_val}" \
        -v pulse="${WIZARD_AUTONOMY_PULSE_SCHEDULE}" \
        -v review="${WIZARD_AUTONOMY_REVIEW_SCHEDULE}" \
        -v maxday="${WIZARD_AUTONOMY_MAX_PER_DAY}" '
      /^autonomy:/ { in_autonomy=1; print; next }
      in_autonomy && /^[^ ]/ { in_autonomy=0 }
      in_autonomy && /enabled:/ {
        sub(/enabled:.*/, "enabled: " enabled)
      }
      in_autonomy && /pulse_schedule:/ {
        sub(/pulse_schedule:.*/, "pulse_schedule: \"" pulse "\"")
      }
      in_autonomy && /review_schedule:/ && review != "" {
        sub(/review_schedule:.*/, "review_schedule: \"" review "\"")
      }
      /max_per_day:/ {
        sub(/max_per_day:.*/, "max_per_day: " maxday)
      }
      { print }
    ' "${config_file}" > "${tmpfile}" && mv "${tmpfile}" "${config_file}"
  else
    # Append autonomy block if missing (shouldn't happen after Step 9, but be safe)
    cat >> "${config_file}" <<YAML

autonomy:
  enabled: ${enabled_val}
  pulse_schedule: "${WIZARD_AUTONOMY_PULSE_SCHEDULE}"
  review_schedule: "${WIZARD_AUTONOMY_REVIEW_SCHEDULE}"
YAML
  fi
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

# Install cron jobs for pulse and review
_autonomy_install_crons() {
  if ! wiz_confirm "Install cron jobs for pulse and review now?" "Y"; then
    wiz_info "Add manually to crontab:"
    printf "  ${_DIM}${WIZARD_AUTONOMY_PULSE_SCHEDULE} ${ADJ_DIR}/scripts/lifecycle/startup.sh --pulse${_RESET}\n"
    if [ -n "${WIZARD_AUTONOMY_REVIEW_SCHEDULE}" ]; then
      printf "  ${_DIM}${WIZARD_AUTONOMY_REVIEW_SCHEDULE} ${ADJ_DIR}/scripts/lifecycle/startup.sh --review${_RESET}\n"
    fi
    return 0
  fi

  local pulse_cron="${WIZARD_AUTONOMY_PULSE_SCHEDULE} opencode run --print \"${ADJ_DIR}/prompts/pulse.md\" --cwd \"${ADJ_DIR}\" >> \"${ADJ_DIR}/state/adjutant.log\" 2>&1"
  local review_cron="${WIZARD_AUTONOMY_REVIEW_SCHEDULE} opencode run --print \"${ADJ_DIR}/prompts/review.md\" --cwd \"${ADJ_DIR}\" >> \"${ADJ_DIR}/state/adjutant.log\" 2>&1"

  if [ "${DRY_RUN:-}" = "true" ]; then
    dry_run_would "crontab: add pulse job '${pulse_cron}'"
    wiz_ok "Would install pulse cron: ${WIZARD_AUTONOMY_PULSE_SCHEDULE}"
    if [ -n "${WIZARD_AUTONOMY_REVIEW_SCHEDULE}" ]; then
      dry_run_would "crontab: add review job '${review_cron}'"
      wiz_ok "Would install review cron: ${WIZARD_AUTONOMY_REVIEW_SCHEDULE}"
    fi
    return 0
  fi

  # Install pulse cron (skip if already present)
  if crontab -l 2>/dev/null | grep -qF "prompts/pulse.md"; then
    wiz_ok "Pulse cron job already installed"
  else
    (crontab -l 2>/dev/null; echo "${pulse_cron}") | crontab - 2>/dev/null && {
      wiz_ok "Pulse cron installed: ${WIZARD_AUTONOMY_PULSE_SCHEDULE}"
    } || {
      wiz_warn "Failed to install pulse cron — add manually:"
      wiz_info "${pulse_cron}"
    }
  fi

  # Install review cron (only if review schedule is set)
  if [ -n "${WIZARD_AUTONOMY_REVIEW_SCHEDULE}" ]; then
    if crontab -l 2>/dev/null | grep -qF "prompts/review.md"; then
      wiz_ok "Review cron job already installed"
    else
      (crontab -l 2>/dev/null; echo "${review_cron}") | crontab - 2>/dev/null && {
        wiz_ok "Review cron installed: ${WIZARD_AUTONOMY_REVIEW_SCHEDULE}"
      } || {
        wiz_warn "Failed to install review cron — add manually:"
        wiz_info "${review_cron}"
      }
    fi
  fi
}
