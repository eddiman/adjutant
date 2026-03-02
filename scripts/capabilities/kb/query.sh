#!/bin/bash
# scripts/capabilities/kb/query.sh — Query a knowledge base sub-agent
#
# Spawns `opencode run --agent kb --dir <kb-path>` with the given query,
# parses NDJSON output, and returns the plain-text answer.
#
# Usage:
#   bash query.sh <kb-name> "your question here"
#   bash query.sh --path /path/to/kb "your question here"
#
# Output: plain text answer on stdout
# Exit codes: 0 = success, 1 = error
#
# Requires: ADJ_DIR (from paths.sh), opencode, jq

set -euo pipefail

# --- Load common utilities ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/../../common/paths.sh"
source "${SCRIPT_DIR}/../../common/opencode.sh"
source "${SCRIPT_DIR}/manage.sh"

# --- Configuration ---
KB_QUERY_TIMEOUT=120  # seconds

# --- Model Resolution ---
# Resolves the model for a KB query.
# If KB model is "inherit", uses the current Telegram model or Adjutant default.
_resolve_model() {
  local kb_model="$1"

  if [ "${kb_model}" = "inherit" ] || [ -z "${kb_model}" ]; then
    # Check for Telegram model override first
    local model_file="${ADJ_DIR}/state/telegram_model.txt"
    if [ -f "${model_file}" ]; then
      cat "${model_file}" | tr -d '\n'
    else
      echo "anthropic/claude-haiku-4-5"
    fi
  else
    echo "${kb_model}"
  fi
}

# --- NDJSON Parser ---
# Parses NDJSON output from opencode, extracting text parts.
# Reuses the proven pattern from chat.sh (lines 116-173).
# Args: $1 = raw NDJSON file path
# Output: accumulated text on stdout
_parse_ndjson() {
  local raw_file="$1"
  local reply=""

  while IFS= read -r line; do
    [ -z "${line}" ] && continue

    local line_type
    line_type="$(printf '%s' "${line}" | jq -r '.type // empty' 2>/dev/null)" || continue

    # Check for errors
    if [ "${line_type}" = "error" ]; then
      local err_msg
      err_msg="$(printf '%s' "${line}" | jq -r '.error.data.message // .error.name // "Unknown error"' 2>/dev/null)"
      echo "ERROR: ${err_msg}" >&2
      # Continue parsing — there may be partial text
    fi

    # Accumulate text parts
    if [ "${line_type}" = "text" ]; then
      local part
      part="$(printf '%s' "${line}" | jq -r '.part.text // empty' 2>/dev/null)"
      reply="${reply}${part}"
    fi
  done < "${raw_file}"

  printf '%s' "${reply}"
}

# --- Query Function ---
# Exported for use by other scripts (adjutant agent, telegram commands).
#
# Args: $1 = kb name or --path, $2 = query (or path if $1=--path, then $3=query)
# Output: answer text on stdout
# Returns: 0 on success, 1 on error
kb_query() {
  local kb_path="" kb_model="inherit" query=""

  if [ "$1" = "--path" ]; then
    kb_path="$2"
    query="$3"
    # Try to read model from kb.yaml at that path
    if [ -f "${kb_path}/kb.yaml" ]; then
      kb_model="$(grep '^model:' "${kb_path}/kb.yaml" 2>/dev/null | sed 's/^model:[[:space:]]*//' | tr -d '"' || echo "inherit")"
    fi
  else
    local kb_name="$1"
    query="$2"

    # Look up in registry
    if ! kb_exists "${kb_name}"; then
      echo "ERROR: Knowledge base '${kb_name}' not found." >&2
      return 1
    fi

    kb_path="$(kb_get_field "${kb_name}" "path")"
    kb_model="$(kb_get_field "${kb_name}" "model")"
  fi

  # Validate
  if [ -z "${kb_path}" ]; then
    echo "ERROR: KB path is empty." >&2
    return 1
  fi
  if [ ! -d "${kb_path}" ]; then
    echo "ERROR: KB directory does not exist: ${kb_path}" >&2
    return 1
  fi
  if [ -z "${query}" ]; then
    echo "ERROR: Query is empty." >&2
    return 1
  fi

  # Check for opencode
  local opencode_bin
  opencode_bin="$(command -v opencode 2>/dev/null || echo "")"
  if [ -z "${opencode_bin}" ]; then
    echo "ERROR: opencode CLI not found. Install it first." >&2
    return 1
  fi

  # Resolve model
  local model
  model="$(_resolve_model "${kb_model}")"

  # Build opencode args
  local args=(run --agent kb --dir "${kb_path}" --format json --model "${model}")
  args+=("${query}")

  # Run opencode (with timeout if available)
  local raw_file err_file
  raw_file="$(mktemp)"
  err_file="$(mktemp)"

  if command -v timeout >/dev/null 2>&1; then
    timeout "${KB_QUERY_TIMEOUT}" opencode_run "${args[@]}" > "${raw_file}" 2>"${err_file}" || true
  else
    opencode_run "${args[@]}" > "${raw_file}" 2>"${err_file}" || true
  fi

  # Parse output
  local reply
  reply="$(_parse_ndjson "${raw_file}")"

  # Clean up
  rm -f "${raw_file}" "${err_file}"

  if [ -z "${reply}" ]; then
    echo "The knowledge base did not return an answer. It may not contain relevant information for this query."
    return 0
  fi

  printf '%s' "${reply}"
}

# --- Main (when run directly) ---
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  if [ $# -lt 2 ]; then
    echo "Usage: query.sh <kb-name> \"your question\"" >&2
    echo "       query.sh --path /path/to/kb \"your question\"" >&2
    exit 1
  fi

  kb_query "$@"
fi
