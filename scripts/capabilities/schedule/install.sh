#!/bin/bash
# scripts/capabilities/schedule/install.sh — Crontab reconciler for scheduled jobs
#
# Single source of truth for how managed cron entries are formatted and managed.
# All functions read job metadata from adjutant.yaml schedules: via manage.sh.
#
# This file is a sourced library — do NOT add set -euo pipefail here.
#
# Crontab entry format:
#   <schedule> <resolved_script> >> <resolved_log> 2>&1  # adjutant:<name>
#
# The "# adjutant:<name>" marker is the identity key. All entries still contain
# ".adjutant" so existing startup.sh grep counts remain valid.
#
# Backwards compatibility: lines containing ".adjutant" but without
# "# adjutant:<name>" (old format, pre-phase-8) are left untouched.
#
# Usage:
#   source "${ADJ_DIR}/scripts/capabilities/schedule/install.sh"
#   schedule_install_all          # reconcile full crontab with registry
#   schedule_install_one "name"   # install/update one entry
#   schedule_uninstall_one "name" # remove one entry
#   schedule_run_now "name"       # exec job in foreground (for testing)
#
# Requires: ADJ_DIR, manage.sh (auto-sourced)

# ── Internal ───────────────────────────────────────────────────────────────

# Resolve a path: absolute stays as-is; relative is prepended with ADJ_DIR.
_install_resolve_path() {
  local p="$1"
  case "${p}" in
    /*) echo "${p}" ;;
    *)  echo "${ADJ_DIR}/${p}" ;;
  esac
}

# Return the crontab marker string for a job name.
_install_marker() {
  local name="$1"
  echo "# adjutant:${name}"
}

# ── Public API ─────────────────────────────────────────────────────────────

# Reconcile the full crontab with the current registry.
# For each enabled job: ensure its crontab line exists and is current.
# For each disabled job: ensure no crontab line exists.
# Existing lines without a "# adjutant:<name>" suffix are left untouched.
# This function is idempotent — safe to call repeatedly.
schedule_install_all() {
  # Ensure manage.sh is sourced
  if ! type schedule_list &>/dev/null; then
    source "${ADJ_DIR}/scripts/capabilities/schedule/manage.sh"
  fi

  while IFS=$'\t' read -r name desc sched script log enabled; do
    [ -z "${name}" ] && continue
    if [ "${enabled}" = "true" ]; then
      schedule_install_one "${name}"
    else
      schedule_uninstall_one "${name}"
    fi
  done < <(schedule_list)
}

# Install or update the crontab entry for a single job.
# Reads job metadata from the registry via manage.sh.
# Args: $1 = name
# Returns: 0 on success, 1 on error
schedule_install_one() {
  local name="$1"

  if ! type schedule_list &>/dev/null; then
    source "${ADJ_DIR}/scripts/capabilities/schedule/manage.sh"
  fi

  if ! schedule_exists "${name}"; then
    echo "ERROR: Job '${name}' not found in registry." >&2
    return 1
  fi

  local sched script_raw log_raw
  sched="$(schedule_get_field "${name}" schedule)"
  script_raw="$(schedule_get_field "${name}" script)"
  log_raw="$(schedule_get_field "${name}" log)"

  # Default log if empty
  [ -z "${log_raw}" ] && log_raw="state/${name}.log"

  local script_path log_path
  script_path="$(_install_resolve_path "${script_raw}")"
  log_path="$(_install_resolve_path "${log_raw}")"

  # Ensure log directory exists
  mkdir -p "$(dirname "${log_path}")" 2>/dev/null || true

  local marker
  marker="$(_install_marker "${name}")"
  local cron_line="${sched} ${script_path} >> ${log_path} 2>&1  ${marker}"

  # Remove any existing entry for this job, then append the new one
  # grep -v exits 1 when no lines match — use || true to prevent set -e abort
  { crontab -l 2>/dev/null | grep -v "${marker}" || true; echo "${cron_line}"; } | crontab - 2>/dev/null
}

# Remove the crontab entry for a single job.
# Args: $1 = name
# Returns: 0 (always — no error if entry was not present)
schedule_uninstall_one() {
  local name="$1"
  local marker
  marker="$(_install_marker "${name}")"

  # Remove line containing the marker
  local existing
  existing="$(crontab -l 2>/dev/null)" || existing=""

  if echo "${existing}" | grep -qF "${marker}"; then
    # grep -v exits 1 when nothing matches — use || true to prevent set -e abort
    { echo "${existing}" | grep -vF "${marker}" || true; } | crontab - 2>/dev/null
  fi
}

# Run a job immediately in the foreground.
# Used by "adjutant schedule run <name>" and "/schedule run <name>".
# Output from the job goes to stdout.
# Args: $1 = name
# Returns: exit code of the job script
schedule_run_now() {
  local name="$1"

  if ! type schedule_list &>/dev/null; then
    source "${ADJ_DIR}/scripts/capabilities/schedule/manage.sh"
  fi

  if ! schedule_exists "${name}"; then
    echo "ERROR: Job '${name}' not found in registry." >&2
    return 1
  fi

  local script_raw
  script_raw="$(schedule_get_field "${name}" script)"

  local script_path
  script_path="$(_install_resolve_path "${script_raw}")"

  if [ ! -f "${script_path}" ]; then
    echo "ERROR: Script not found: ${script_path}" >&2
    return 1
  fi

  if [ ! -x "${script_path}" ]; then
    echo "ERROR: Script is not executable: ${script_path}" >&2
    return 1
  fi

  exec bash "${script_path}"
}
