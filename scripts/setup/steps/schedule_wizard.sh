#!/bin/bash
# scripts/setup/steps/schedule_wizard.sh — Interactive scheduled job creation wizard
#
# Walks the user through registering a new scheduled job in adjutant.yaml schedules:.
# Writes the entry, installs the crontab entry immediately, and suggests a test run.
#
# Called by: adjutant schedule add
#
# Usage:
#   bash schedule_wizard.sh
#
# Requires: ADJ_DIR set, helpers.sh available, manage.sh + install.sh available

set -euo pipefail

# Resolve ADJ_DIR if not already set
if [ -z "${ADJ_DIR:-}" ]; then
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  source "${SCRIPT_DIR}/../../common/paths.sh"
fi

SETUP_DIR="${ADJ_DIR}/scripts/setup"
source "${SETUP_DIR}/helpers.sh"
source "${ADJ_DIR}/scripts/capabilities/schedule/manage.sh"

# ── Common schedule examples ───────────────────────────────────────────────

_schedule_hint() {
  printf "  ${_DIM}Examples:${_RESET}\n" >/dev/tty
  printf "  ${_DIM}  0 8 * * 1-5      weekdays at 8:00am${_RESET}\n" >/dev/tty
  printf "  ${_DIM}  0 9,17 * * 1-5   weekdays at 9am and 5pm${_RESET}\n" >/dev/tty
  printf "  ${_DIM}  0 * * * *         every hour${_RESET}\n" >/dev/tty
  printf "  ${_DIM}  */30 * * * *      every 30 minutes${_RESET}\n" >/dev/tty
  printf "  ${_DIM}  0 20 * * 1-5      weekdays at 8pm${_RESET}\n" >/dev/tty
  printf "  ${_DIM}  0 6 * * *         every day at 6am${_RESET}\n" >/dev/tty
}

# ── Interactive wizard ─────────────────────────────────────────────────────

wiz_header "Add a Scheduled Job"
echo "" >/dev/tty
wiz_info "Register any script as a scheduled job in adjutant.yaml schedules:." >/dev/tty
wiz_info "The job will be installed in your crontab immediately." >/dev/tty
echo "" >/dev/tty

# ── Step 1: Name ──────────────────────────────────────────────────────────

printf "  ${_BOLD}Name${_RESET}\n" >/dev/tty
printf "  ${_DIM}Lowercase alphanumeric with hyphens or underscores (e.g. portfolio-fetch)${_RESET}\n" >/dev/tty
echo "" >/dev/tty

local_name=""
while true; do
  local_name="$(wiz_input "Job name" "")"
  if [ -z "${local_name}" ]; then
    wiz_warn "Name cannot be empty." >/dev/tty
    continue
  fi
  if ! echo "${local_name}" | grep -qE '^[a-z0-9][a-z0-9_-]*$' 2>/dev/null; then
    wiz_warn "Must be lowercase alphanumeric with hyphens/underscores." >/dev/tty
    continue
  fi
  if schedule_exists "${local_name}"; then
    wiz_warn "A job named '${local_name}' is already registered." >/dev/tty
    wiz_info "Use 'adjutant schedule remove ${local_name}' first if you want to replace it." >/dev/tty
    continue
  fi
  break
done
echo "" >/dev/tty

# ── Step 2: Description ───────────────────────────────────────────────────

printf "  ${_BOLD}Description${_RESET}\n" >/dev/tty
printf "  ${_DIM}Shown in 'adjutant schedule list' and /schedule list. Free text.${_RESET}\n" >/dev/tty
echo "" >/dev/tty

local_desc="$(wiz_input "Description" "")"
[ -z "${local_desc}" ] && local_desc="Scheduled job: ${local_name}"
echo "" >/dev/tty

# ── Step 3: Script path ───────────────────────────────────────────────────

printf "  ${_BOLD}Script path${_RESET}\n" >/dev/tty
printf "  ${_DIM}Absolute path, or relative to your Adjutant directory (${ADJ_DIR}).${_RESET}\n" >/dev/tty
printf "  ${_DIM}The script must exit 0 on success. Its stdout is captured by /schedule run.${_RESET}\n" >/dev/tty
echo "" >/dev/tty

local_script=""
while true; do
  local_script="$(wiz_input "Script path" "")"
  if [ -z "${local_script}" ]; then
    wiz_warn "Script path cannot be empty." >/dev/tty
    continue
  fi
  # Expand ~
  local_script="$(expand_path "${local_script}")"

  # Resolve to absolute for validation
  local resolved_script
  case "${local_script}" in
    /*) resolved_script="${local_script}" ;;
    *)  resolved_script="${ADJ_DIR}/${local_script}" ;;
  esac

  if [ ! -f "${resolved_script}" ]; then
    wiz_warn "File not found: ${resolved_script}" >/dev/tty
    if wiz_confirm "Use this path anyway? (you can create the script later)" "N"; then
      break
    fi
    continue
  fi
  if [ ! -x "${resolved_script}" ]; then
    wiz_warn "Script is not executable: ${resolved_script}" >/dev/tty
    if wiz_confirm "Make it executable now?" "Y"; then
      chmod +x "${resolved_script}"
      wiz_ok "Made executable." >/dev/tty
    fi
  fi
  break
done
echo "" >/dev/tty

# ── Step 4: Schedule ──────────────────────────────────────────────────────

printf "  ${_BOLD}Schedule (cron syntax)${_RESET}\n" >/dev/tty
_schedule_hint
echo "" >/dev/tty

local_schedule=""
while true; do
  local_schedule="$(wiz_input "Schedule" "")"
  if [ -z "${local_schedule}" ]; then
    wiz_warn "Schedule cannot be empty." >/dev/tty
    continue
  fi
  # Basic validation: must have exactly 5 fields
  local field_count
  field_count="$(echo "${local_schedule}" | awk '{print NF}')"
  if [ "${field_count}" -ne 5 ]; then
    wiz_warn "A cron schedule must have exactly 5 fields (got ${field_count})." >/dev/tty
    wiz_info "Example: 0 8 * * 1-5" >/dev/tty
    continue
  fi
  break
done
echo "" >/dev/tty

# ── Step 5: Log file ──────────────────────────────────────────────────────

printf "  ${_BOLD}Log file${_RESET}\n" >/dev/tty
printf "  ${_DIM}Where stdout/stderr from the job is written.${_RESET}\n" >/dev/tty
printf "  ${_DIM}Relative paths are relative to ${ADJ_DIR}.${_RESET}\n" >/dev/tty
echo "" >/dev/tty

local_log="$(wiz_input "Log file" "state/${local_name}.log")"
[ -z "${local_log}" ] && local_log="state/${local_name}.log"
echo "" >/dev/tty

# ── Summary + confirm ─────────────────────────────────────────────────────

wiz_header "Summary" >/dev/tty
wiz_info "Name:        ${local_name}" >/dev/tty
wiz_info "Description: ${local_desc}" >/dev/tty
wiz_info "Script:      ${local_script}" >/dev/tty
wiz_info "Schedule:    ${local_schedule}" >/dev/tty
wiz_info "Log:         ${local_log}" >/dev/tty
echo "" >/dev/tty

if ! wiz_confirm "Register and install this job?" "Y"; then
  echo "Cancelled." >/dev/tty
  exit 0
fi

echo "" >/dev/tty

# ── Write + install ───────────────────────────────────────────────────────

printf "  Adding to adjutant.yaml..." >/dev/tty
if schedule_add "${local_name}" "${local_desc}" "${local_schedule}" "${local_script}" "${local_log}"; then
  printf " ${_GREEN}done${_RESET}\n" >/dev/tty
else
  printf " ${_RED}failed${_RESET}\n" >/dev/tty
  exit 1
fi

echo "" >/dev/tty
wiz_ok "Job '${local_name}' registered and crontab entry installed." >/dev/tty
echo "" >/dev/tty
wiz_info "Verify with:  adjutant schedule list" >/dev/tty
wiz_info "Test now:     adjutant schedule run ${local_name}" >/dev/tty
wiz_info "Disable:      adjutant schedule disable ${local_name}" >/dev/tty
wiz_info "Remove:       adjutant schedule remove ${local_name}" >/dev/tty
echo "" >/dev/tty
