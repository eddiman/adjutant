#!/bin/bash
# scripts/setup/helpers.sh — Shared UI helpers for the setup wizard
#
# Provides:
#   - Terminal color/formatting utilities
#   - Prompt helpers (yes/no, text input, multiline input)
#   - Step banner/progress display
#   - Token estimation and cost calculation
#   - YAML reading (for adjutant.yaml parsing)
#
# Usage:
#   source "${SETUP_DIR}/helpers.sh"

# ── Colors & Formatting ────────────────────────────────────────────────────

# Detect color support — disable if not a terminal or NO_COLOR is set
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
  _BOLD="\033[1m"
  _DIM="\033[2m"
  _RESET="\033[0m"
  _GREEN="\033[32m"
  _RED="\033[31m"
  _YELLOW="\033[33m"
  _CYAN="\033[36m"
  _WHITE="\033[37m"
else
  _BOLD="" _DIM="" _RESET="" _GREEN="" _RED="" _YELLOW="" _CYAN="" _WHITE=""
fi

# Print a styled check mark
wiz_ok() {
  printf "  ${_GREEN}✓${_RESET} %s\n" "$*"
}

# Print a styled X mark
wiz_fail() {
  printf "  ${_RED}✗${_RESET} %s\n" "$*"
}

# Print a styled warning
wiz_warn() {
  printf "  ${_YELLOW}!${_RESET} %s\n" "$*"
}

# Print a styled info line
wiz_info() {
  printf "  ${_DIM}→${_RESET} %s\n" "$*"
}

# Print styled header text
wiz_header() {
  printf "\n${_BOLD}${_CYAN}%s${_RESET}\n" "$*"
}

# Print the wizard title banner
wiz_banner() {
  echo ""
  printf "${_BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${_RESET}\n"
  printf "${_BOLD}  Adjutant — Setup Wizard${_RESET}\n"
  printf "${_BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${_RESET}\n"
  echo ""
}

# Print a completion banner
wiz_complete_banner() {
  echo ""
  printf "${_BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${_RESET}\n"
  printf "${_BOLD}${_GREEN}  Adjutant is online!${_RESET}\n"
  printf "${_BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${_RESET}\n"
  echo ""
}

# Print a step banner
# Usage: wiz_step 1 6 "Prerequisites Check"
wiz_step() {
  local current="$1"
  local total="$2"
  local title="$3"
  echo ""
  printf "${_BOLD}Step %d of %d: %s${_RESET}\n" "$current" "$total" "$title"
}

# ── Prompts ─────────────────────────────────────────────────────────────────

# Ask a yes/no question (returns 0=yes, 1=no)
# Usage: wiz_confirm "Proceed?" "Y" → default is yes
#        wiz_confirm "Enable feature?" "N" → default is no
wiz_confirm() {
  local prompt="$1"
  local default="${2:-Y}"

  local hint
  if [ "$default" = "Y" ] || [ "$default" = "y" ]; then
    hint="[Y/n]"
  else
    hint="[y/N]"
  fi

  if [ "${DRY_RUN:-}" = "true" ]; then
    printf "  ${_YELLOW}[DRY RUN]${_RESET} %s %s: " "$prompt" "$hint" >/dev/tty
    local answer
    read -r answer </dev/tty
    answer="${answer:-$default}"
    case "$answer" in
      [Yy]|[Yy][Ee][Ss]) return 0 ;;
      [Nn]|[Nn][Oo])     return 1 ;;
      *) [ "$default" = "Y" ] || [ "$default" = "y" ] && return 0 || return 1 ;;
    esac
  fi

  while true; do
    printf "  %s %s: " "$prompt" "$hint" >/dev/tty
    local answer
    read -r answer </dev/tty
    answer="${answer:-$default}"

    case "$answer" in
      [Yy]|[Yy][Ee][Ss]) return 0 ;;
      [Nn]|[Nn][Oo])     return 1 ;;
      *) echo "  Please answer y or n." >/dev/tty ;;
    esac
  done
}

# Present a numbered list of choices and return the selected index (1-based)
# Usage: choice=$(wiz_choose "What to do?" "Fresh setup" "Repair / health check")
#        → prints menu, returns "1" or "2" etc.
wiz_choose() {
  local prompt="$1"
  shift
  local -a options=("$@")
  local count=${#options[@]}

  if [ "${DRY_RUN:-}" = "true" ]; then
    printf "  ${_YELLOW}[DRY RUN]${_RESET} %s\n\n" "$prompt" >/dev/tty
    local i; for i in $(seq 1 "$count"); do
      printf "    ${_BOLD}%d)${_RESET}  %s\n" "$i" "${options[$((i-1))]}" >/dev/tty
    done
    echo "" >/dev/tty
    while true; do
      printf "  Choose [1-%d]: " "$count" >/dev/tty
      local answer
      read -r answer </dev/tty
      answer="${answer:-1}"
      if [[ "$answer" =~ ^[0-9]+$ ]] && [ "$answer" -ge 1 ] && [ "$answer" -le "$count" ]; then
        echo "$answer"
        return 0
      fi
      printf "  Please enter a number between 1 and %d.\n" "$count" >/dev/tty
    done
  fi

  printf "  %s\n\n" "$prompt" >/dev/tty
  local i
  for i in $(seq 1 "$count"); do
    printf "    ${_BOLD}%d)${_RESET}  %s\n" "$i" "${options[$((i-1))]}" >/dev/tty
  done
  echo "" >/dev/tty

  while true; do
    printf "  Choose [1-%d]: " "$count" >/dev/tty
    local answer
    read -r answer </dev/tty
    if [[ "$answer" =~ ^[0-9]+$ ]] && [ "$answer" -ge 1 ] && [ "$answer" -le "$count" ]; then
      echo "$answer"
      return 0
    fi
    printf "  Please enter a number between 1 and %d.\n" "$count" >/dev/tty
  done
}

# Ask for a single-line text input with optional default
# Usage: result=$(wiz_input "Agent name" "adjutant")
wiz_input() {
  local prompt="$1"
  local default="${2:-}"

  local dry_prefix=""
  [ "${DRY_RUN:-}" = "true" ] && dry_prefix="  ${_YELLOW}[DRY RUN]${_RESET}"

  if [ -n "$default" ]; then
    printf "%s  %s [%s]: " "$dry_prefix" "$prompt" "$default" >/dev/tty
  else
    printf "%s  %s: " "$dry_prefix" "$prompt" >/dev/tty
  fi

  local answer
  read -r answer </dev/tty
  answer="${answer:-$default}"
  echo "$answer"
}

# Ask for multiline text input (end with empty line)
# Usage: result=$(wiz_multiline "Describe your needs")
wiz_multiline() {
  local prompt="$1"

  local dry_prefix=""
  [ "${DRY_RUN:-}" = "true" ] && dry_prefix="  ${_YELLOW}[DRY RUN]${_RESET}"

  printf "%s  %s\n" "$dry_prefix" "$prompt" >/dev/tty
  printf "  ${_DIM}(Type your answer. Press Enter twice to finish.)${_RESET}\n" >/dev/tty
  printf "  > " >/dev/tty

  local result=""
  local line
  local prev_empty=false
  while true; do
    read -r line </dev/tty
    if [ -z "$line" ]; then
      if $prev_empty || [ -z "$result" ]; then
        break
      fi
      prev_empty=true
      result="${result}"$'\n'
      printf "  > " >/dev/tty
      continue
    fi
    prev_empty=false
    if [ -n "$result" ]; then
      result="${result}"$'\n'"${line}"
    else
      result="${line}"
    fi
    printf "  > " >/dev/tty
  done
  echo "$result"
}

# Ask for a secret input (no echo)
# Usage: token=$(wiz_secret "Paste your bot token")
wiz_secret() {
  local prompt="$1"

  local dry_prefix=""
  [ "${DRY_RUN:-}" = "true" ] && dry_prefix="  ${_YELLOW}[DRY RUN]${_RESET}"

  printf "%s  %s: " "$dry_prefix" "$prompt" >/dev/tty
  local answer
  read -r -s answer </dev/tty
  echo "" >/dev/tty  # newline after hidden input
  echo "$answer"
}

# ── Token Estimation ────────────────────────────────────────────────────────

# Rough token count (1 token ≈ 4 chars for English)
estimate_tokens() {
  local text="$1"
  local chars=${#text}
  echo $(( (chars + 3) / 4 ))
}

# Estimate cost in USD given input/output tokens and model
# Returns a string like "0.0012"
estimate_cost() {
  local input_tokens="$1"
  local output_tokens="$2"
  local model="$3"

  local cost
  case "$model" in
    *haiku*)
      cost=$(echo "scale=6; ($input_tokens * 0.80 + $output_tokens * 4.00) / 1000000" | bc 2>/dev/null || echo "0.01")
      ;;
    *sonnet*)
      cost=$(echo "scale=6; ($input_tokens * 3.00 + $output_tokens * 15.00) / 1000000" | bc 2>/dev/null || echo "0.05")
      ;;
    *opus*)
      cost=$(echo "scale=6; ($input_tokens * 15.00 + $output_tokens * 75.00) / 1000000" | bc 2>/dev/null || echo "0.25")
      ;;
    *)
      cost="0.01"
      ;;
  esac
  echo "$cost"
}

# Display a token estimate to the user
# Usage: wiz_show_estimate 2000 800 "haiku"
wiz_show_estimate() {
  local input_tokens="$1"
  local output_tokens="$2"
  local model="$3"
  local cost
  cost=$(estimate_cost "$input_tokens" "$output_tokens" "$model")
  printf "  ${_DIM}Estimated: ~%s input + ~%s output tokens${_RESET}\n" "$input_tokens" "$output_tokens"
  printf "  ${_DIM}Model: %s → ~\$%s${_RESET}\n" "$model" "$cost"
}

# ── YAML Helpers ────────────────────────────────────────────────────────────

# Read a simple value from adjutant.yaml (handles basic key: value lines)
# Doesn't handle nested keys with a full YAML parser — only flat lookups
# Usage: val=$(yaml_get "instance.name" "/path/to/adjutant.yaml")
yaml_get() {
  local key="$1"
  local file="${2:-${ADJ_DIR:-}/adjutant.yaml}"

  if [ ! -f "$file" ]; then
    return 1
  fi

  # For dotted keys like "messaging.backend", search for the last segment
  # after lines matching parent segments. This is a simple heuristic.
  local segments
  IFS='.' read -ra segments <<< "$key"

  if [ ${#segments[@]} -eq 1 ]; then
    # Simple key
    grep -E "^${segments[0]}:" "$file" | head -1 | sed 's/^[^:]*:[[:space:]]*//' | tr -d '"'"'"
  else
    # Nested key — find the last segment after the parent block
    local last_seg="${segments[${#segments[@]}-1]}"
    grep -E "^[[:space:]]+${last_seg}:" "$file" | head -1 | sed 's/^[^:]*:[[:space:]]*//' | tr -d '"'"'"
  fi
}

# Write/update a simple value in adjutant.yaml
# Usage: yaml_set "messaging.backend" "telegram" "/path/to/adjutant.yaml"
yaml_set() {
  local key="$1"
  local value="$2"
  local file="${3:-${ADJ_DIR:-}/adjutant.yaml}"

  if [ "${DRY_RUN:-}" = "true" ]; then
    dry_run_would "yaml_set ${key}=${value} in ${file}"
    return 0
  fi

  local segments
  IFS='.' read -ra segments <<< "$key"
  local last_seg="${segments[${#segments[@]}-1]}"

  if [ ${#segments[@]} -eq 1 ]; then
    # Top-level key
    if grep -qE "^${last_seg}:" "$file"; then
      sed -i.bak "s|^\(${last_seg}:\).*|\1 \"${value}\"|" "$file" && rm -f "${file}.bak"
    else
      echo "${last_seg}: \"${value}\"" >> "$file"
    fi
  else
    # Nested key — find and replace the indented line
    if grep -qE "^[[:space:]]+${last_seg}:" "$file"; then
      sed -i.bak "s|^\([[:space:]]*${last_seg}:\).*|\1 ${value}|" "$file" && rm -f "${file}.bak"
    fi
  fi
}

# ── Misc Helpers ────────────────────────────────────────────────────────────

# Check if a command exists
has_command() {
  command -v "$1" >/dev/null 2>&1
}

# Get version string of a command (first line of --version)
get_version() {
  local cmd="$1"
  "$cmd" --version 2>&1 | head -1
}

# Expand ~ to $HOME in a path
expand_path() {
  local path="$1"
  case "$path" in
    "~/"*) echo "${HOME}/${path#\~/}" ;;
    "~")   echo "${HOME}" ;;
    *)     echo "$path" ;;
  esac
}

# ── Dry-Run Helpers ─────────────────────────────────────────────────────────

# Print a dry-run action line inline where the real action would occur.
# Usage: dry_run_would "mkdir -p /foo/bar"
dry_run_would() {
  printf "  ${_YELLOW}[DRY RUN]${_RESET} Would: %s\n" "$*"
}
