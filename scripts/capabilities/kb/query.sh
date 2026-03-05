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
#
# Resolution order:
#   1. "inherit"   → state/telegram_model.txt → adjutant.yaml cheap tier → hardcoded default
#   2. "cheap"     → adjutant.yaml llm.models.cheap    → "anthropic/claude-haiku-4-5"
#   3. "medium"    → adjutant.yaml llm.models.medium   → "anthropic/claude-sonnet-4-6"
#   4. "expensive" → adjutant.yaml llm.models.expensive → "anthropic/claude-opus-4-5"
#   5. explicit    → used as-is
#
# Using named tiers keeps Adjutant in control: changing a tier in adjutant.yaml
# propagates to all KBs that reference it — no per-KB edits required.
_resolve_model() {
  local kb_model="$1"
  local adj_yaml="${ADJ_DIR}/adjutant.yaml"

  # Read a named tier from adjutant.yaml llm.models.<tier>, with fallback
  _tier_model() {
    local tier="$1"
    local fallback="$2"
    if [ -f "${adj_yaml}" ]; then
      local val
      val="$(grep -E "^[[:space:]]+${tier}:" "${adj_yaml}" | head -1 \
            | sed 's/^[^:]*:[[:space:]]*//' | tr -d '"'"'")"
      [ -n "${val}" ] && echo "${val}" && return
    fi
    echo "${fallback}"
  }

  case "${kb_model}" in
    inherit|"")
      local model_file="${ADJ_DIR}/state/telegram_model.txt"
      if [ -f "${model_file}" ]; then
        tr -d '\n' < "${model_file}"
      else
        _tier_model "cheap" "anthropic/claude-haiku-4-5"
      fi
      ;;
    cheap)
      _tier_model "cheap" "anthropic/claude-haiku-4-5"
      ;;
    medium)
      _tier_model "medium" "anthropic/claude-sonnet-4-6"
      ;;
    expensive)
      _tier_model "expensive" "anthropic/claude-opus-4-5"
      ;;
    *)
      echo "${kb_model}"
      ;;
  esac
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

  # Run opencode with timeout via OPENCODE_TIMEOUT env var (opencode_run honours it)
  local raw_file err_file
  raw_file="$(mktemp)"
  err_file="$(mktemp)"

  OPENCODE_TIMEOUT="${KB_QUERY_TIMEOUT}" opencode_run "${args[@]}" > "${raw_file}" 2>"${err_file}" || true

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
