#!/bin/bash
# scripts/capabilities/kb/manage.sh — Knowledge base CRUD operations
#
# Provides functions for creating, registering, unregistering, listing,
# and inspecting knowledge bases. Used by both the CLI (`adjutant kb`)
# and the interactive wizard (`kb_wizard.sh`).
#
# Usage:
#   source "${ADJ_DIR}/scripts/capabilities/kb/manage.sh"
#   kb_create "my-notes" "/path/to/kb" "My personal notes" "inherit" "read-only"
#   kb_list
#   kb_info "my-notes"
#   kb_remove "my-notes"
#
# Requires: ADJ_DIR (from paths.sh), jq

# ── Constants ──────────────────────────────────────────────────────────────

KB_REGISTRY="${ADJ_DIR}/knowledge_bases/registry.yaml"
KB_TEMPLATES="${ADJ_DIR}/templates/kb"

# ── Registry Helpers ───────────────────────────────────────────────────────

# Read the number of registered KBs
# Returns: integer count
kb_count() {
  if [ ! -f "${KB_REGISTRY}" ]; then
    echo "0"
    return
  fi
  local count
  count="$(grep -c '^  - name:' "${KB_REGISTRY}" 2>/dev/null)" || count="0"
  echo "${count}"
}

# Check if a KB name is already registered
# Args: $1 = name
# Returns: 0 if exists, 1 if not
kb_exists() {
  local name="$1"
  [ -f "${KB_REGISTRY}" ] || return 1
  grep -q "^  - name: \"${name}\"" "${KB_REGISTRY}" 2>/dev/null
}

# List all registered KBs (name + description, tab-separated)
# Output: one line per KB: name<TAB>description<TAB>path<TAB>access
kb_list() {
  if [ ! -f "${KB_REGISTRY}" ]; then
    return 0
  fi

  # Parse YAML manually — extract blocks between "- name:" entries
  local name="" description="" path="" access=""
  while IFS= read -r line; do
    case "${line}" in
      *"- name: "*)
        # Emit previous entry if we have one
        if [ -n "${name}" ]; then
          printf '%s\t%s\t%s\t%s\n' "${name}" "${description}" "${path}" "${access}"
        fi
        name="$(echo "${line}" | sed 's/.*- name: "//' | sed 's/"$//')"
        description="" path="" access=""
        ;;
      *"description: "*)
        description="$(echo "${line}" | sed 's/.*description: "//' | sed 's/"$//')"
        ;;
      *"path: "*)
        path="$(echo "${line}" | sed 's/.*path: "//' | sed 's/"$//')"
        ;;
      *"access: "*)
        access="$(echo "${line}" | sed 's/.*access: "//' | sed 's/"$//')"
        ;;
    esac
  done < "${KB_REGISTRY}"

  # Emit last entry
  if [ -n "${name}" ]; then
    printf '%s\t%s\t%s\t%s\n' "${name}" "${description}" "${path}" "${access}"
  fi
}

# Get info about a specific KB
# Args: $1 = name
# Output: key=value pairs, one per line
kb_info() {
  local target="$1"
  if ! kb_exists "${target}"; then
    echo "ERROR: Knowledge base '${target}' not found in registry." >&2
    return 1
  fi

  local name="" description="" path="" model="" access="" created=""
  local in_target=false
  while IFS= read -r line; do
    case "${line}" in
      *"- name: \"${target}\""*)
        in_target=true
        name="${target}"
        ;;
      *"- name: "*)
        # Another entry — stop if we were in the target
        if ${in_target}; then break; fi
        ;;
    esac
    if ${in_target}; then
      case "${line}" in
        *"description: "*) description="$(echo "${line}" | sed 's/.*description: "//' | sed 's/"$//')" ;;
        *"path: "*)        path="$(echo "${line}" | sed 's/.*path: "//' | sed 's/"$//')" ;;
        *"model: "*)       model="$(echo "${line}" | sed 's/.*model: "//' | sed 's/"$//')" ;;
        *"access: "*)      access="$(echo "${line}" | sed 's/.*access: "//' | sed 's/"$//')" ;;
        *"created: "*)     created="$(echo "${line}" | sed 's/.*created: "//' | sed 's/"$//')" ;;
      esac
    fi
  done < "${KB_REGISTRY}"

  echo "name=${name}"
  echo "description=${description}"
  echo "path=${path}"
  echo "model=${model}"
  echo "access=${access}"
  echo "created=${created}"
}

# Get a single field from a KB entry
# Args: $1 = name, $2 = field (path, model, access, description, created)
# Output: field value
kb_get_field() {
  local target="$1"
  local field="$2"
  kb_info "${target}" 2>/dev/null | grep "^${field}=" | cut -d'=' -f2-
}

# ── Registry Mutations ─────────────────────────────────────────────────────

# Register a KB in the registry
# Args: $1=name $2=path $3=description $4=model $5=access $6=created
kb_register() {
  local name="$1"
  local path="$2"
  local description="$3"
  local model="${4:-inherit}"
  local access="${5:-read-only}"
  local created="${6:-$(date '+%Y-%m-%d')}"

  if kb_exists "${name}"; then
    echo "ERROR: Knowledge base '${name}' already registered." >&2
    return 1
  fi

  # Ensure registry directory exists
  mkdir -p "$(dirname "${KB_REGISTRY}")"

  # If registry doesn't exist or has empty list, create it
  if [ ! -f "${KB_REGISTRY}" ] || ! grep -q '^knowledge_bases:' "${KB_REGISTRY}" 2>/dev/null; then
    cat > "${KB_REGISTRY}" <<EOF
knowledge_bases:
  - name: "${name}"
    description: "${description}"
    path: "${path}"
    model: "${model}"
    access: "${access}"
    created: "${created}"
EOF
    return 0
  fi

  # Check if registry has empty list
  if grep -q '^knowledge_bases: \[\]' "${KB_REGISTRY}" 2>/dev/null; then
    # Replace empty list with first entry
    cat > "${KB_REGISTRY}" <<EOF
knowledge_bases:
  - name: "${name}"
    description: "${description}"
    path: "${path}"
    model: "${model}"
    access: "${access}"
    created: "${created}"
EOF
    return 0
  fi

  # Append to existing entries
  cat >> "${KB_REGISTRY}" <<EOF
  - name: "${name}"
    description: "${description}"
    path: "${path}"
    model: "${model}"
    access: "${access}"
    created: "${created}"
EOF
}

# Unregister a KB from the registry (does NOT delete files)
# Args: $1 = name
kb_unregister() {
  local name="$1"

  if ! kb_exists "${name}"; then
    echo "ERROR: Knowledge base '${name}' not found in registry." >&2
    return 1
  fi

  # Build new registry without the target entry
  local tmpfile
  tmpfile="$(mktemp)"
  local skip=false

  # Write header with comment preservation
  local in_header=true
  while IFS= read -r line; do
    if ${in_header}; then
      if [[ "${line}" == "#"* ]] || [[ "${line}" == "" ]] || [[ "${line}" == "knowledge_bases:"* ]]; then
        echo "${line}" >> "${tmpfile}"
        if [[ "${line}" == "knowledge_bases:"* ]]; then
          in_header=false
        fi
        continue
      fi
      in_header=false
    fi

    # Check if this is the start of the target entry
    if [[ "${line}" == *"- name: \"${name}\""* ]]; then
      skip=true
      continue
    fi

    # Check if this is the start of a different entry (end of skip)
    if ${skip} && [[ "${line}" == *"- name: "* ]]; then
      skip=false
    fi

    if ! ${skip}; then
      echo "${line}" >> "${tmpfile}"
    fi
  done < "${KB_REGISTRY}"

  # Check if we have any entries left
  local remaining
  remaining="$(grep -c '^  - name:' "${tmpfile}" 2>/dev/null)" || remaining="0"
  if [ "${remaining}" -eq 0 ]; then
    # Restore empty list format — preserve header comments
    local header_lines
    header_lines="$(sed -n '1,/^knowledge_bases:/p' "${tmpfile}")"
    # Re-build with empty list
    local comment_lines
    comment_lines="$(grep '^#' "${KB_REGISTRY}" 2>/dev/null || true)"
    if [ -n "${comment_lines}" ]; then
      printf '%s\n\nknowledge_bases: []\n' "${comment_lines}" > "${tmpfile}"
    else
      echo "knowledge_bases: []" > "${tmpfile}"
    fi
  fi

  mv "${tmpfile}" "${KB_REGISTRY}"
}

# ── Scaffold Operations ────────────────────────────────────────────────────

# Create the scaffold files for a new KB at the given path.
#
# Creates the standard KB directory structure:
#   kb.yaml                  — Adjutant metadata
#   README.md                — KB orientation doc (what it answers, structure)
#   opencode.json            — workspace permissions
#   .opencode/agents/kb.md  — sub-agent definition
#   data/current.md          — live status snapshot (fill this in)
#   data/.gitkeep
#   knowledge/.gitkeep       — stable reference docs
#   history/.gitkeep         — archived records
#   templates/.gitkeep       — reusable document formats
#
# Args: $1=name $2=path $3=description $4=model $5=access
kb_scaffold() {
  local name="$1"
  local kb_path="$2"
  local description="$3"
  local model="${4:-inherit}"
  local access="${5:-read-only}"
  local created
  created="$(date '+%Y-%m-%d')"

  local write_enabled="false"
  if [ "${access}" = "read-write" ]; then
    write_enabled="true"
  fi

  # Create standard directory structure
  mkdir -p "${kb_path}/.opencode/agents"
  mkdir -p "${kb_path}/data"
  mkdir -p "${kb_path}/knowledge"
  mkdir -p "${kb_path}/history"
  mkdir -p "${kb_path}/templates"

  # Render kb.yaml from template
  if [ -f "${KB_TEMPLATES}/kb.yaml" ]; then
    sed \
      -e "s|{{KB_NAME}}|${name}|g" \
      -e "s|{{KB_DESCRIPTION}}|${description}|g" \
      -e "s|{{KB_MODEL}}|${model}|g" \
      -e "s|{{KB_ACCESS}}|${access}|g" \
      -e "s|{{KB_CREATED}}|${created}|g" \
      "${KB_TEMPLATES}/kb.yaml" > "${kb_path}/kb.yaml"
  fi

  # Render opencode.json from template
  if [ -f "${KB_TEMPLATES}/opencode.json" ]; then
    cp "${KB_TEMPLATES}/opencode.json" "${kb_path}/opencode.json"
  fi

  # Render agent definition from template
  if [ -f "${KB_TEMPLATES}/agents/kb.md" ]; then
    sed \
      -e "s|{{KB_NAME}}|${name}|g" \
      -e "s|{{KB_DESCRIPTION}}|${description}|g" \
      -e "s|{{KB_WRITE_ENABLED}}|${write_enabled}|g" \
      "${KB_TEMPLATES}/agents/kb.md" > "${kb_path}/.opencode/agents/kb.md"
  fi

  # Render README.md from template (only if root is empty-ish)
  if [ -f "${KB_TEMPLATES}/docs/README.md" ] && [ ! -f "${kb_path}/README.md" ]; then
    sed \
      -e "s|{{KB_NAME}}|${name}|g" \
      -e "s|{{KB_DESCRIPTION}}|${description}|g" \
      "${KB_TEMPLATES}/docs/README.md" > "${kb_path}/README.md"
  fi

  # Create data/current.md stub — the most important file to fill in
  if [ ! -f "${kb_path}/data/current.md" ]; then
    cat > "${kb_path}/data/current.md" <<CURRENT_EOF
# Current Status — ${name}
Last updated: ${created}

---

## Active priorities

- (fill in)

## Open items / blockers

- (fill in)

## What's coming up

- (fill in)

## Key references

- (add links to key files as the KB grows)
CURRENT_EOF
  fi

  # Placeholder .gitkeep files so directories are tracked by git
  touch "${kb_path}/knowledge/.gitkeep"
  touch "${kb_path}/history/.gitkeep"
  touch "${kb_path}/templates/.gitkeep"
}

# Auto-detect content types in an existing directory
# Args: $1 = path
# Output: comma-separated list of detected types (e.g., "markdown,code,json")
kb_detect_content() {
  local dir="$1"
  [ -d "${dir}" ] || return 1

  local types=()

  # Check for markdown files
  if find "${dir}" -maxdepth 3 -name '*.md' -print -quit 2>/dev/null | grep -q .; then
    types+=("markdown")
  fi

  # Check for code files
  if find "${dir}" -maxdepth 3 \( -name '*.py' -o -name '*.js' -o -name '*.ts' -o -name '*.sh' -o -name '*.go' -o -name '*.rs' -o -name '*.rb' -o -name '*.java' \) -print -quit 2>/dev/null | grep -q .; then
    types+=("code")
  fi

  # Check for JSON/YAML data
  if find "${dir}" -maxdepth 3 \( -name '*.json' -o -name '*.yaml' -o -name '*.yml' \) -print -quit 2>/dev/null | grep -q .; then
    types+=("data")
  fi

  # Check for text/docs
  if find "${dir}" -maxdepth 3 \( -name '*.txt' -o -name '*.rst' -o -name '*.org' \) -print -quit 2>/dev/null | grep -q .; then
    types+=("text")
  fi

  # Check for PDF
  if find "${dir}" -maxdepth 3 -name '*.pdf' -print -quit 2>/dev/null | grep -q .; then
    types+=("pdf")
  fi

  if [ ${#types[@]} -eq 0 ]; then
    echo "empty"
  else
    local IFS=","
    echo "${types[*]}"
  fi
}

# ── Combined Create Operation ──────────────────────────────────────────────

# Create a KB: scaffold + register
# Args: $1=name $2=path $3=description $4=model $5=access
# Returns: 0 on success, 1 on error (with message to stderr)
kb_create() {
  local name="$1"
  local kb_path="$2"
  local description="$3"
  local model="${4:-inherit}"
  local access="${5:-read-only}"

  # Validate name (lowercase alphanumeric + hyphens)
  if ! echo "${name}" | grep -qE '^[a-z0-9][a-z0-9-]*[a-z0-9]$' 2>/dev/null; then
    # Allow single-char names too
    if ! echo "${name}" | grep -qE '^[a-z0-9]$' 2>/dev/null; then
      echo "ERROR: KB name must be lowercase alphanumeric with hyphens (e.g., 'ml-papers')." >&2
      return 1
    fi
  fi

  # Validate path is absolute
  case "${kb_path}" in
    /*) ;; # absolute — OK
    *)
      echo "ERROR: KB path must be absolute (got '${kb_path}')." >&2
      return 1
      ;;
  esac

  # Check for duplicate name
  if kb_exists "${name}"; then
    echo "ERROR: Knowledge base '${name}' already registered." >&2
    return 1
  fi

  # Scaffold the KB directory
  kb_scaffold "${name}" "${kb_path}" "${description}" "${model}" "${access}"

  # Register in the registry
  kb_register "${name}" "${kb_path}" "${description}" "${model}" "${access}"
}

# ── Remove Operation ───────────────────────────────────────────────────────

# Remove a KB: unregister only (does NOT delete files)
# Args: $1 = name
kb_remove() {
  local name="$1"
  kb_unregister "${name}"
}
