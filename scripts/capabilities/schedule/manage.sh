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
# Output: one tab-separated line per job: name<TAB>description<TAB>schedule<TAB>script<TAB>log<TAB>enabled
schedule_list() {
  [ -f "${SCHEDULE_CONFIG}" ] || return 0

  awk '
    /^schedules:/ { in_block=1; next }
    in_block && /^[^ ]/ { in_block=0 }

    in_block && /^  - name:/ {
      # Emit previous entry
      if (name != "") {
        printf "%s\t%s\t%s\t%s\t%s\t%s\n", name, desc, sched, script, log, enabled
      }
      name=desc=sched=script=log=enabled=""
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
      val=$0; sub(/.*log: *"?/, "", val); sub(/"? *$/, "", val); log=val
    }
    in_block && name != "" && /^    enabled:/ {
      val=$0; sub(/.*enabled: */, "", val); sub(/ *$/, "", val); enabled=val
    }
    END {
      if (name != "") {
        printf "%s\t%s\t%s\t%s\t%s\t%s\n", name, desc, sched, script, log, enabled
      }
    }
  ' "${SCHEDULE_CONFIG}"
}

# Get a single field from a job entry.
# Args: $1 = name, $2 = field (description|schedule|script|log|enabled)
# Output: field value (empty string if not found)
schedule_get_field() {
  local target="$1"
  local field="$2"
  schedule_list | while IFS=$'\t' read -r name desc sched script log enabled; do
    if [ "${name}" = "${target}" ]; then
      case "${field}" in
        description) echo "${desc}" ;;
        schedule)    echo "${sched}" ;;
        script)      echo "${script}" ;;
        log)         echo "${log}" ;;
        enabled)     echo "${enabled}" ;;
        name)        echo "${name}" ;;
      esac
      return 0
    fi
  done
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
  local log="${5:-state/${name}.log}"
  local enabled="${6:-true}"

  if ! grep -q '^schedules:' "${SCHEDULE_CONFIG}" 2>/dev/null; then
    # Append a new schedules: block
    cat >> "${SCHEDULE_CONFIG}" <<YAML

schedules:
  - name: "${name}"
    description: "${description}"
    schedule: "${schedule}"
    script: "${script}"
    log: "${log}"
    enabled: ${enabled}
YAML
    return 0
  fi

  # schedules: block exists — check if it has entries already
  if awk '/^schedules:/{in_block=1;next} in_block&&/^[^ ]/{in_block=0} in_block&&/^  - name:/{found=1;exit} END{exit !found}' "${SCHEDULE_CONFIG}" 2>/dev/null; then
    # Append after the last entry in the block — find end of schedules: block
    local tmpfile
    tmpfile="$(mktemp)"
    trap 'rm -f "${tmpfile}"' RETURN

    awk -v name="${name}" \
        -v desc="${description}" \
        -v sched="${schedule}" \
        -v script="${script}" \
        -v log="${log}" \
        -v enabled="${enabled}" '
      /^schedules:/ { in_block=1; print; next }
      in_block && /^[^ ]/ {
        # End of schedules block — inject new entry before this line
        printf "  - name: \"%s\"\n    description: \"%s\"\n    schedule: \"%s\"\n    script: \"%s\"\n    log: \"%s\"\n    enabled: %s\n", name, desc, sched, script, log, enabled
        in_block=0
        print
        next
      }
      { print }
      END {
        # schedules: was the last block — append at end
        if (in_block) {
          printf "  - name: \"%s\"\n    description: \"%s\"\n    schedule: \"%s\"\n    script: \"%s\"\n    log: \"%s\"\n    enabled: %s\n", name, desc, sched, script, log, enabled
        }
      }
    ' "${SCHEDULE_CONFIG}" > "${tmpfile}" && mv "${tmpfile}" "${SCHEDULE_CONFIG}"
  else
    # schedules: block exists but is empty — append first entry
    local tmpfile
    tmpfile="$(mktemp)"
    trap 'rm -f "${tmpfile}"' RETURN
    awk -v name="${name}" \
        -v desc="${description}" \
        -v sched="${schedule}" \
        -v script="${script}" \
        -v log="${log}" \
        -v enabled="${enabled}" '
      /^schedules:/ {
        print
        printf "  - name: \"%s\"\n    description: \"%s\"\n    schedule: \"%s\"\n    script: \"%s\"\n    log: \"%s\"\n    enabled: %s\n", name, desc, sched, script, log, enabled
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
  local log="${5:-state/${name}.log}"

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
  _schedule_append "${name}" "${description}" "${schedule}" "${script}" "${log}" "true"

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
  trap 'rm -f "${tmpfile}"' RETURN

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
  trap 'rm -f "${tmpfile}"' RETURN

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
