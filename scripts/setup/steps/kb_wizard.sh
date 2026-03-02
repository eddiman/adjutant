#!/bin/bash
# scripts/setup/steps/kb_wizard.sh — Interactive KB creation wizard
#
# Walks the user through creating a new knowledge base with prompts
# for name, path, description, model, and access level.
#
# Supports:
#   - Interactive mode (default): full wizard with prompts
#   - Quick mode (--quick): one-liner scaffold from arguments
#
# Usage:
#   Interactive:  bash kb_wizard.sh
#   Quick:        bash kb_wizard.sh --quick --name my-kb --path /path --desc "My KB"
#
# Requires: ADJ_DIR set, helpers.sh available, manage.sh available

set -euo pipefail

# Resolve ADJ_DIR if not already set
if [ -z "${ADJ_DIR:-}" ]; then
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  source "${SCRIPT_DIR}/../../common/paths.sh"
fi

SETUP_DIR="${ADJ_DIR}/scripts/setup"
KB_MANAGE="${ADJ_DIR}/scripts/capabilities/kb/manage.sh"

# Source helpers
source "${SETUP_DIR}/helpers.sh"
source "${KB_MANAGE}"

# ── Quick Mode ─────────────────────────────────────────────────────────────

_kb_quick_create() {
  local name="" kb_path="" description="" model="inherit" access="read-only"

  while [ $# -gt 0 ]; do
    case "$1" in
      --name)  name="$2"; shift 2 ;;
      --path)  kb_path="$2"; shift 2 ;;
      --desc)  description="$2"; shift 2 ;;
      --model) model="$2"; shift 2 ;;
      --access) access="$2"; shift 2 ;;
      *)       shift ;;
    esac
  done

  if [ -z "${name}" ] || [ -z "${kb_path}" ]; then
    echo "Usage: kb_wizard.sh --quick --name <name> --path <path> [--desc \"...\"] [--model inherit] [--access read-only]" >&2
    return 1
  fi

  [ -z "${description}" ] && description="Knowledge base: ${name}"

  # Expand ~ in path
  kb_path="$(expand_path "${kb_path}")"

  kb_create "${name}" "${kb_path}" "${description}" "${model}" "${access}"
  echo "OK: Created knowledge base '${name}' at ${kb_path}"
}

# ── Interactive Mode ───────────────────────────────────────────────────────

_kb_wizard_interactive() {
  wiz_header "Create a Knowledge Base"
  echo "" >/dev/tty
  wiz_info "A KB is a scoped directory that Adjutant can query as a sub-agent." >/dev/tty
  wiz_info "Place docs, notes, or references in it and ask Adjutant questions." >/dev/tty
  echo "" >/dev/tty

  # Step 1: Name
  local name
  while true; do
    name="$(wiz_input "KB name (lowercase, hyphens ok)" "")"
    if [ -z "${name}" ]; then
      wiz_warn "Name cannot be empty." >/dev/tty
      continue
    fi
    # Validate format
    if ! echo "${name}" | grep -qE '^[a-z0-9]([a-z0-9-]*[a-z0-9])?$' 2>/dev/null; then
      wiz_warn "Must be lowercase alphanumeric with hyphens (e.g., 'ml-papers')." >/dev/tty
      continue
    fi
    # Check for duplicate
    if kb_exists "${name}"; then
      wiz_warn "A KB named '${name}' already exists." >/dev/tty
      continue
    fi
    break
  done

  # Step 2: Path
  local kb_path
  local default_path="${HOME}/knowledge-bases/${name}"
  while true; do
    kb_path="$(wiz_input "Directory path" "${default_path}")"
    kb_path="$(expand_path "${kb_path}")"

    # Must be absolute
    case "${kb_path}" in
      /*) ;; # OK
      *)
        wiz_warn "Path must be absolute." >/dev/tty
        continue
        ;;
    esac

    # Warn if directory exists with content
    if [ -d "${kb_path}" ] && [ -n "$(ls -A "${kb_path}" 2>/dev/null)" ]; then
      local content_types
      content_types="$(kb_detect_content "${kb_path}")"
      wiz_info "Directory exists with content: ${content_types}" >/dev/tty
      if ! wiz_confirm "Use this existing directory?" "Y"; then
        continue
      fi
    fi
    break
  done

  # Step 3: Description
  local description
  description="$(wiz_input "Description (drives auto-detection)" "")"
  if [ -z "${description}" ]; then
    description="Knowledge base: ${name}"
  fi

  # Step 4: Access level
  local access_choice
  access_choice="$(wiz_choose "Access level for the sub-agent?" "Read-only (recommended — agent can read but not modify)" "Read-write (agent can also create and edit files)")"
  local access="read-only"
  if [ "${access_choice}" = "2" ]; then
    access="read-write"
  fi

  # Step 5: Model
  local model="inherit"
  if wiz_confirm "Use Adjutant's current model? (or specify a different one)" "Y"; then
    model="inherit"
  else
    model="$(wiz_input "Model name (e.g., anthropic/claude-haiku-4-5)" "inherit")"
  fi

  # Summary
  echo "" >/dev/tty
  wiz_header "Summary" >/dev/tty
  wiz_info "Name:        ${name}" >/dev/tty
  wiz_info "Path:        ${kb_path}" >/dev/tty
  wiz_info "Description: ${description}" >/dev/tty
  wiz_info "Access:      ${access}" >/dev/tty
  wiz_info "Model:       ${model}" >/dev/tty
  echo "" >/dev/tty

  if ! wiz_confirm "Create this knowledge base?" "Y"; then
    echo "Cancelled." >/dev/tty
    return 1
  fi

  # Create it
  kb_create "${name}" "${kb_path}" "${description}" "${model}" "${access}"

  echo "" >/dev/tty
  wiz_ok "Knowledge base '${name}' created!" >/dev/tty
  wiz_info "Path:     ${kb_path}" >/dev/tty
  wiz_info "Registry: ${KB_REGISTRY}" >/dev/tty
  echo "" >/dev/tty
  wiz_info "Next steps:" >/dev/tty
  wiz_info "  1. Fill in ${kb_path}/data/current.md — live status snapshot" >/dev/tty
  wiz_info "  2. Add reference docs to ${kb_path}/knowledge/" >/dev/tty
  wiz_info "  3. Update README.md with what questions this KB can answer" >/dev/tty
  wiz_info "  4. Ask Adjutant a question — it will auto-detect this KB by description." >/dev/tty
}

# ── Main ───────────────────────────────────────────────────────────────────

if [[ "${1:-}" == "--quick" ]]; then
  shift
  _kb_quick_create "$@"
else
  _kb_wizard_interactive "$@"
fi
