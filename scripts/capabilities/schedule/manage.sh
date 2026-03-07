#!/bin/bash
# scripts/capabilities/schedule/manage.sh — Scheduled job CRUD operations
#
# Provides functions for registering, unregistering, enabling, disabling,
# listing, and inspecting scheduled jobs declared in adjutant.yaml schedules:.
# Used by both the CLI (adjutant schedule) and Telegram commands (cmd_schedule).
#
# This file is a sourced library — do NOT add set -euo pipefail here.
#
# Usage:
#   source "${ADJ_DIR}/scripts/capabilities/schedule/manage.sh"
#   schedule_add "portfolio_fetch" "Fetch portfolio data" "0 9 * * 1-5" \
#                "/path/to/fetch.sh" "state/portfolio_fetch.log"
#   schedule_list
#   schedule_get_field "portfolio_fetch" "script"
#   schedule_set_enabled "portfolio_fetch" "false"
#   schedule_remove "portfolio_fetch"
#
# Requires: ADJ_DIR (from paths.sh)
# No yq dependency — pure awk/grep/sed parsing.

# ── Constants ──────────────────────────────────────────────────────────────

SCHEDULE_CONFIG="${ADJ_DIR}/adjutant.yaml"

# ── Internal helpers ───────────────────────────────────────────────────────

# Resolve a path: if absolute, return as-is; if relative, prepend ADJ_DIR.
# Args: $1 = path string
_schedule_resolve_path() {
  local p="$1"
  case "${p}" in
    /*) echo "${p}" ;;
    *)  echo "${ADJ_DIR}/${p}" ;;
  esac
}

# Resolve a schedule entry to an executable command.
# Supports either:
#   - script: <path>
#   - kb_name: <name> + kb_operation: <operation>
_schedule_resolve_command() {
  local name="$1"
  local script_raw kb_name kb_operation

  script_raw="$(schedule_get_field "${name}" script)"
  kb_name="$(schedule_get_field "${name}" kb_name)"
  kb_operation="$(schedule_get_field "${name}" kb_operation)"

  if [ -n "${kb_name}" ] && [ -n "${kb_operation}" ]; then
    echo "bash ${ADJ_DIR}/scripts/capabilities/kb/run.sh ${kb_name} ${kb_operation}"
    return 0
  fi

  if [ -n "${script_raw}" ]; then
    echo "$(_schedule_resolve_path "${script_raw}")"
    return 0
  fi

  echo ""
}

# ── Registry Queries ───────────────────────────────────────────────────────

# Count registered schedule entries.
# Output: integer
schedule_count() {
  [ -f "${SCHEDULE_CONFIG}" ] || { echo "0"; return; }
  # Count "- name:" lines inside the schedules: block
  awk '
    /^schedules:/ { in_block=1; next }
    in_block && /^[^ ]/ { in_block=0 }
    in_block && /^  - name:/ { count++ }
    END { print count+0 }
  ' "${SCHEDULE_CONFIG}"
}

# Check if a job name is already registered.
# Args: $1 = name
# Returns: 0 if exists, 1 if not
schedule_exists() {
  local name="$1"
  [ -f "${SCHEDULE_CONFIG}" ] || return 1
  awk -v target="${name}" '
    /^schedules:/ { in_block=1; next }
    in_block && /^[^ ]/ { in_block=0 }
    in_block && /^  - name:/ {
      gsub(/.*- name: *"?|"? *$/, "")
      if ($0 == target) { found=1; exit }
    }
    END { exit !found }
  ' "${SCHEDULE_CONFIG}"
}

# List all registered jobs.
# Output: one tab-separated line per job: name<TAB>description<TAB>schedule<TAB>script-or-<kb><TAB>log<TAB>enabled<TAB>notify<TAB>kb_name<TAB>kb_operation
schedule_list() {
  [ -f "${SCHEDULE_CONFIG}" ] || return 0

  awk '
    /^schedules:/ { in_block=1; next }
    in_block && /^[^ ]/ { in_block=0 }

    in_block && /^  - name:/ {
      # Emit previous entry
      if (name != "") {
        script_out = (script == "" ? "<kb>" : script)
        printf "%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n", name, desc, sched, script_out, logf, enabled, notify, kb_name, kb_operation
      }
      name=""; desc=""; sched=""; script=""; logf=""; enabled=""; notify="false"; kb_name=""; kb_operation=""
      val=$0; sub(/.*- name: *"?/, "", val); sub(/"? *$/, "", val); name=val
    }
    in_block && name != "" && /^    description:/ {
      val=$0; sub(/.*description: *"?/, "", val); sub(/"? *$/, "", val); desc=val
    }
    in_block && name != "" && /^    schedule:/ {
      val=$0; sub(/.*schedule: *"?/, "", val); sub(/"? *$/, "", val); sched=val
    }
    in_block && name != "" && /^    script:/ {
      val=$0; sub(/.*script: *"?/, "", val); sub(/"? *$/, "", val); script=val
    }
    in_block && name != "" && /^    log:/ {
      val=$0; sub(/.*log: *"?/, "", val); sub(/"? *$/, "", val); logf=val
    }
    in_block && name != "" && /^    enabled:/ {
      val=$0; sub(/.*enabled: */, "", val); sub(/ *$/, "", val); enabled=val
    }
    in_block && name != "" && /^    notify:/ {
      val=$0; sub(/.*notify: */, "", val); sub(/ *$/, "", val); notify=val
    }
    in_block && name != "" && /^    kb_name:/ {
      val=$0; sub(/.*kb_name: *"?/, "", val); sub(/"? *$/, "", val); kb_name=val
    }
    in_block && name != "" && /^    kb_operation:/ {
      val=$0; sub(/.*kb_operation: *"?/, "", val); sub(/"? *$/, "", val); kb_operation=val
    }
    END {
      if (name != "") {
        script_out = (script == "" ? "<kb>" : script)
        printf "%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n", name, desc, sched, script_out, logf, enabled, notify, kb_name, kb_operation
      }
    }
  ' "${SCHEDULE_CONFIG}"
}

# Get a single field from a job entry.
# Args: $1 = name, $2 = field (description|schedule|script|log|enabled|notify|kb_name|kb_operation)
# Output: field value (empty string if not found)
schedule_get_field() {
  local target="$1"
  local field="$2"
  awk -v target="${target}" -v field="${field}" '
    /^schedules:/ { in_block=1; next }
    in_block && /^[^ ]/ { in_block=0 }

    in_block && /^  - name:/ {
      current=$0; sub(/.*- name: *"?/, "", current); sub(/"? *$/, "", current)
      in_entry=(current == target)
      next
    }

    in_entry {
      if (field == "name") { print target; exit }
      if (field == "description" && /^    description:/) { val=$0; sub(/.*description: *"?/, "", val); sub(/"? *$/, "", val); print val; exit }
      if (field == "schedule" && /^    schedule:/) { val=$0; sub(/.*schedule: *"?/, "", val); sub(/"? *$/, "", val); print val; exit }
      if (field == "script" && /^    script:/) { val=$0; sub(/.*script: *"?/, "", val); sub(/"? *$/, "", val); print val; exit }
      if (field == "log" && /^    log:/) { val=$0; sub(/.*log: *"?/, "", val); sub(/"? *$/, "", val); print val; exit }
      if (field == "enabled" && /^    enabled:/) { val=$0; sub(/.*enabled: */, "", val); sub(/ *$/, "", val); print val; exit }
      if (field == "notify" && /^    notify:/) { val=$0; sub(/.*notify: */, "", val); sub(/ *$/, "", val); print val; exit }
      if (field == "kb_name" && /^    kb_name:/) { val=$0; sub(/.*kb_name: *"?/, "", val); sub(/"? *$/, "", val); print val; exit }
      if (field == "kb_operation" && /^    kb_operation:/) { val=$0; sub(/.*kb_operation: *"?/, "", val); sub(/"? *$/, "", val); print val; exit }
    }
  ' "${SCHEDULE_CONFIG}"
}

# ── Registry Mutations ─────────────────────────────────────────────────────

# Append a new job entry to adjutant.yaml schedules:.
# Args: $1=name $2=description $3=schedule $4=script $5=log (optional)
# Does NOT install crontab — call schedule_install_all separately.
# Returns: 0 on success, 1 on error
_schedule_append() {
  local name="$1"
  local description="$2"
  local schedule="$3"
  local script="$4"
  local logpath="${5:-state/${name}.log}"
  local enabled="${6:-true}"
  local notify="${7:-false}"

  if ! grep -q '^schedules:' "${SCHEDULE_CONFIG}" 2>/dev/null; then
    # Append a new schedules: block
    cat >> "${SCHEDULE_CONFIG}" <<YAML

schedules:
  - name: "${name}"
    description: "${description}"
    schedule: "${schedule}"
    script: "${script}"
    log: "${logpath}"
    enabled: ${enabled}
    notify: ${notify}
YAML
    return 0
  fi

  # schedules: block exists — check if it has entries already
  if awk '/^schedules:/{in_block=1;next} in_block&&/^[^ ]/{in_block=0} in_block&&/^  - name:/{found=1;exit} END{exit !found}' "${SCHEDULE_CONFIG}" 2>/dev/null; then
    # Append after the last entry in the block — find end of schedules: block
    local tmpfile
    tmpfile="$(mktemp)"

    awk -v name="${name}" \
        -v desc="${description}" \
        -v sched="${schedule}" \
        -v script="${script}" \
        -v logpath="${logpath}" \
        -v enabled="${enabled}" \
        -v notify="${notify}" '
      /^schedules:/ { in_block=1; print; next }
      in_block && /^[^ ]/ {
        # End of schedules block — inject new entry before this line
        printf "  - name: \"%s\"\n    description: \"%s\"\n    schedule: \"%s\"\n    script: \"%s\"\n    log: \"%s\"\n    enabled: %s\n    notify: %s\n", name, desc, sched, script, logpath, enabled, notify
        in_block=0
        print
        next
      }
      { print }
      END {
        # schedules: was the last block — append at end
        if (in_block) {
          printf "  - name: \"%s\"\n    description: \"%s\"\n    schedule: \"%s\"\n    script: \"%s\"\n    log: \"%s\"\n    enabled: %s\n    notify: %s\n", name, desc, sched, script, logpath, enabled, notify
        }
      }
    ' "${SCHEDULE_CONFIG}" > "${tmpfile}" && mv "${tmpfile}" "${SCHEDULE_CONFIG}"
  else
    # schedules: block exists but is empty — append first entry
    local tmpfile
    tmpfile="$(mktemp)"
    awk -v name="${name}" \
        -v desc="${description}" \
        -v sched="${schedule}" \
        -v script="${script}" \
        -v logpath="${logpath}" \
        -v enabled="${enabled}" \
        -v notify="${notify}" '
      /^schedules:/ {
        print
        printf "  - name: \"%s\"\n    description: \"%s\"\n    schedule: \"%s\"\n    script: \"%s\"\n    log: \"%s\"\n    enabled: %s\n    notify: %s\n", name, desc, sched, script, logpath, enabled, notify
        next
      }
      { print }
    ' "${SCHEDULE_CONFIG}" > "${tmpfile}" && mv "${tmpfile}" "${SCHEDULE_CONFIG}"
  fi
}

# Register a job and install its crontab entry.
# Args: $1=name $2=description $3=schedule $4=script $5=log (optional)
# Returns: 0 on success, 1 on error (message to stderr)
schedule_add() {
  local name="$1"
  local description="$2"
  local schedule="$3"
  local script="$4"
  local logpath="${5:-state/${name}.log}"

  # Validate name
  if ! echo "${name}" | grep -qE '^[a-z0-9][a-z0-9_-]*$' 2>/dev/null; then
    echo "ERROR: Job name must be lowercase alphanumeric with hyphens/underscores (e.g. 'portfolio-fetch')." >&2
    return 1
  fi

  # Check uniqueness
  if schedule_exists "${name}"; then
    echo "ERROR: Job '${name}' already registered. Use schedule_set_enabled or schedule_remove first." >&2
    return 1
  fi

  # Append to config
  _schedule_append "${name}" "${description}" "${schedule}" "${script}" "${logpath}" "true"

  # Install crontab entry
  source "${ADJ_DIR}/scripts/capabilities/schedule/install.sh"
  schedule_install_one "${name}"
}

# Remove a job from the registry and uninstall its crontab entry.
# Args: $1 = name
# Returns: 0 on success, 1 if not found
schedule_remove() {
  local name="$1"

  if ! schedule_exists "${name}"; then
    echo "ERROR: Job '${name}' not found in registry." >&2
    return 1
  fi

  # Uninstall from crontab first
  source "${ADJ_DIR}/scripts/capabilities/schedule/install.sh"
  schedule_uninstall_one "${name}"

  # Remove from adjutant.yaml
  local tmpfile
  tmpfile="$(mktemp)"

  awk -v target="${name}" '
    /^schedules:/ { in_block=1; print; next }
    in_block && /^[^ ]/ { in_block=0 }

    in_block && /^  - name:/ {
      val=$0; sub(/.*- name: *"?/, "", val); sub(/"? *$/, "", val)
      if (val == target) { skip=1; next }
      skip=0
    }
    in_block && skip && /^  - name:/ { skip=0 }
    !skip { print }
  ' "${SCHEDULE_CONFIG}" > "${tmpfile}" && mv "${tmpfile}" "${SCHEDULE_CONFIG}"
}

# Enable or disable a job.
# Args: $1 = name, $2 = "true" or "false"
# Returns: 0 on success, 1 if not found
schedule_set_enabled() {
  local name="$1"
  local value="$2"

  if ! schedule_exists "${name}"; then
    echo "ERROR: Job '${name}' not found in registry." >&2
    return 1
  fi

  # Update enabled: field in the job's block
  local tmpfile
  tmpfile="$(mktemp)"

  awk -v target="${name}" -v val="${value}" '
    /^schedules:/ { in_block=1; print; next }
    in_block && /^[^ ]/ { in_block=0 }

    in_block && /^  - name:/ {
      n=$0; sub(/.*- name: *"?/, "", n); sub(/"? *$/, "", n)
      in_entry=(n == target)
    }
    in_entry && /^    enabled:/ {
      sub(/enabled:.*/, "enabled: " val)
    }
    { print }
  ' "${SCHEDULE_CONFIG}" > "${tmpfile}" && mv "${tmpfile}" "${SCHEDULE_CONFIG}"

  # Sync crontab
  source "${ADJ_DIR}/scripts/capabilities/schedule/install.sh"
  if [ "${value}" = "true" ]; then
    schedule_install_one "${name}"
  else
    schedule_uninstall_one "${name}"
  fi
}
