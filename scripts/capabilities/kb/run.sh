#!/bin/bash
# scripts/capabilities/kb/run.sh — Run a generic KB-local operation by KB name

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../../common/paths.sh"
source "${SCRIPT_DIR}/manage.sh"

kb_run() {
  local kb_name="$1"
  local operation="$2"
  shift 2 || true

  if [ -z "${kb_name}" ] || [ -z "${operation}" ]; then
    echo "ERROR: Usage: run.sh <kb-name> <operation> [args...]" >&2
    return 1
  fi

  local script_path
  script_path="$(kb_get_operation_script "${kb_name}" "${operation}")" || return 1

  local result
  if ! result="$(bash "${script_path}" "$@" 2>&1)"; then
    printf 'ERROR: %s\n' "${result}" >&2
    return 1
  fi

  printf '%s\n' "${result}"
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  if [ $# -lt 2 ]; then
    echo "Usage: run.sh <kb-name> <operation> [args...]" >&2
    exit 1
  fi
  kb_run "$@"
fi
