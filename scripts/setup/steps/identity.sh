#!/bin/bash
# scripts/setup/steps/identity.sh — Step 3: LLM-Driven Identity Generation
#
# Generates soul.md and heart.md using OpenCode + Haiku based on user input.
# Shows token estimate before each LLM call and asks for confirmation.
#
# If soul.md/heart.md already exist, offers to keep or regenerate.
#
# Requires: helpers.sh sourced, ADJ_DIR set, opencode available

# Meta-prompt for soul.md generation
_SOUL_META_PROMPT='You are generating a soul.md file for an autonomous agent called Adjutant.

The soul.md defines the agent'\''s identity, personality, values, escalation rules, and behavioral constraints.

Based on the user'\''s description of what they need, generate a soul.md that follows this structure:

# Adjutant — Soul

**Identity**: [One sentence: what this agent IS]

**Personality**: [Adjective list: communication style]

**Values** (in order):
1. [Most important value]
2. [Second value]
3. [Third value]
4. [Fourth value]

**Escalate when**: [conditions that warrant proactive notification]
**Notify when**: [conditions for informational notifications]
**Stay silent when**: [when NOT to bother the user]
**Max notifications**: 2-3/day, batch minor items

**Telegram format**: `[Project] One sentence.` No greetings, no emoji, no sign-offs.

**Never**: [list of things the agent must never do — always include: edit project files autonomously, message anyone but the commander, invoke Opus automatically, notify > 3x/day without emergency]

Keep it concise. The soul.md should be under 40 lines. Match the user'\''s domain and concerns.'

# Meta-prompt for heart.md generation
_HEART_META_PROMPT='You are generating a heart.md file for an autonomous agent called Adjutant.

The heart.md defines the agent'\''s current priorities and active concerns. It changes frequently — the user edits it whenever their focus shifts.

Based on the user'\''s description, generate a heart.md that follows this structure:

# Adjutant — Heart

What matters right now. Edit this file whenever your focus shifts.
Adjutant reads this on every heartbeat to know what to pay attention to.

**Last updated**: [today'\''s date]

---

## Current Priorities

1. **[Priority name]** — [Brief description with any known dates/deadlines]
2. **[Priority name]** — [Brief description]

---

## Active Concerns

- [Things that need monitoring]
- [Potential issues to watch]

---

## Quiet Zones

Nothing muted right now.

---

## Notes

- [Planning horizon, cadence, constraints]
- Keep it to 1-3 priorities. If this list grows beyond 3, something needs to be deferred.

Keep it concise. Heart.md should be under 30 lines of content. Extract priorities from the user'\''s description.'

step_identity() {
  wiz_step 3 6 "Identity Setup"
  echo ""

  # Check for existing identity files
  local soul_exists=false
  local heart_exists=false
  [ -f "${ADJ_DIR}/identity/soul.md" ] && soul_exists=true
  [ -f "${ADJ_DIR}/identity/heart.md" ] && heart_exists=true

  if $soul_exists && $heart_exists; then
    wiz_ok "soul.md exists"
    wiz_ok "heart.md exists"
    echo ""
    if ! wiz_confirm "Regenerate identity files? (current ones will be backed up)" "N"; then
      wiz_info "Keeping existing identity files"
      return 0
    fi
    # Backup existing files
    if [ "${DRY_RUN:-}" = "true" ]; then
      dry_run_would "cp ${ADJ_DIR}/identity/soul.md soul.md.backup.<epoch>"
      dry_run_would "cp ${ADJ_DIR}/identity/heart.md heart.md.backup.<epoch>"
      wiz_ok "Would back up existing identity files"
    else
      cp "${ADJ_DIR}/identity/soul.md" "${ADJ_DIR}/identity/soul.md.backup.$(date +%s)"
      cp "${ADJ_DIR}/identity/heart.md" "${ADJ_DIR}/identity/heart.md.backup.$(date +%s)"
      wiz_ok "Backed up existing files"
    fi
    echo ""
  fi

  # Check if opencode is available for LLM generation
  if ! has_command opencode; then
    wiz_warn "opencode not found — cannot generate identity with LLM"
    _identity_write_templates
    return 0
  fi

  # Get user description
  local agent_name
  agent_name=$(wiz_input "What should your agent be called?" "adjutant")
  echo ""

  printf "  I'll generate your soul.md (personality/values) and heart.md (priorities)\n"
  printf "  using an LLM tailored to your needs.\n"
  echo ""

  local user_description
  user_description=$(wiz_multiline "Describe what you want your agent to monitor and help with")
  echo ""

  if [ -z "$user_description" ]; then
    wiz_warn "No description provided — writing template files instead"
    _identity_write_templates
    return 0
  fi

  # Generate soul.md
  _identity_generate_soul "$agent_name" "$user_description" || {
    wiz_warn "LLM generation failed — writing template files instead"
    _identity_write_templates
    return 0
  }

  # Generate heart.md
  _identity_generate_heart "$agent_name" "$user_description" || {
    wiz_warn "heart.md generation failed — writing template instead"
    _identity_write_heart_template
    return 0
  }

  echo ""
  wiz_ok "Identity files generated"
  wiz_info "Review and edit these files anytime:"
  wiz_info "  ${ADJ_DIR}/identity/soul.md"
  wiz_info "  ${ADJ_DIR}/identity/heart.md"

  # Also create registry.md if it doesn't exist
  if [ ! -f "${ADJ_DIR}/identity/registry.md" ]; then
    _identity_write_registry_template
  fi

  return 0
}

# Generate soul.md via opencode
_identity_generate_soul() {
  local agent_name="$1"
  local user_description="$2"

  local full_prompt="${_SOUL_META_PROMPT}

The agent is called: ${agent_name}

User's description of their needs:
${user_description}

Generate the soul.md content now. Output ONLY the markdown content, no code fences."

  local input_tokens
  input_tokens=$(estimate_tokens "$full_prompt")
  local output_tokens=600  # soul.md is ~40 lines

  echo ""
  printf "  ${_BOLD}Generating soul.md...${_RESET}\n"
  wiz_show_estimate "$input_tokens" "$output_tokens" "haiku"

  if ! wiz_confirm "Proceed?" "Y"; then
    return 1
  fi

  if [ "${DRY_RUN:-}" = "true" ]; then
    dry_run_would "opencode run --model anthropic/claude-haiku-4-5 --format json (soul prompt, ~${input_tokens} in / ${output_tokens} out tokens)"
    dry_run_would "write ${ADJ_DIR}/identity/soul.md"
    wiz_ok "Would generate soul.md"
    return 0
  fi

  local result
  result=$(opencode run \
    --model "anthropic/claude-haiku-4-5" \
    --format json \
    --dir "${ADJ_DIR}" \
    "$full_prompt" 2>/dev/null | _extract_opencode_text) || {
    wiz_fail "Failed to call opencode for soul.md"
    return 1
  }

  if [ -z "$result" ]; then
    wiz_fail "Empty response from LLM"
    return 1
  fi

  mkdir -p "${ADJ_DIR}/identity"
  printf '%s\n' "$result" > "${ADJ_DIR}/identity/soul.md"
  wiz_ok "soul.md generated"
  return 0
}

# Generate heart.md via opencode
_identity_generate_heart() {
  local agent_name="$1"
  local user_description="$2"

  local today
  today=$(date +%Y-%m-%d)
  local full_prompt="${_HEART_META_PROMPT}

The agent is called: ${agent_name}
Today's date: ${today}

User's description of their needs:
${user_description}

Generate the heart.md content now. Output ONLY the markdown content, no code fences."

  local input_tokens
  input_tokens=$(estimate_tokens "$full_prompt")
  local output_tokens=400  # heart.md is ~25 lines

  echo ""
  printf "  ${_BOLD}Generating heart.md...${_RESET}\n"
  wiz_show_estimate "$input_tokens" "$output_tokens" "haiku"

  if ! wiz_confirm "Proceed?" "Y"; then
    return 1
  fi

  if [ "${DRY_RUN:-}" = "true" ]; then
    dry_run_would "opencode run --model anthropic/claude-haiku-4-5 --format json (heart prompt, ~${input_tokens} in / ${output_tokens} out tokens)"
    dry_run_would "write ${ADJ_DIR}/identity/heart.md"
    wiz_ok "Would generate heart.md"
    return 0
  fi

  local result
  result=$(opencode run \
    --model "anthropic/claude-haiku-4-5" \
    --format json \
    --dir "${ADJ_DIR}" \
    "$full_prompt" 2>/dev/null | _extract_opencode_text) || {
    wiz_fail "Failed to call opencode for heart.md"
    return 1
  }

  if [ -z "$result" ]; then
    wiz_fail "Empty response from LLM"
    return 1
  fi

  mkdir -p "${ADJ_DIR}/identity"
  printf '%s\n' "$result" > "${ADJ_DIR}/identity/heart.md"
  wiz_ok "heart.md generated"
  return 0
}

# Extract text from opencode NDJSON output
_extract_opencode_text() {
  local assembled=""
  while IFS= read -r line; do
    local text_part
    text_part=$(printf '%s' "$line" | jq -r '.part.text // empty' 2>/dev/null)
    if [ -n "$text_part" ]; then
      assembled="${assembled}${text_part}"
    fi
  done
  echo "$assembled"
}

# Write template soul.md (fallback when LLM unavailable)
_identity_write_templates() {
  _identity_write_soul_template
  _identity_write_heart_template
  _identity_write_registry_template
  wiz_ok "Template identity files written"
  wiz_info "Edit these files to customize your agent:"
  wiz_info "  ${ADJ_DIR}/identity/soul.md"
  wiz_info "  ${ADJ_DIR}/identity/heart.md"
  wiz_info "  ${ADJ_DIR}/identity/registry.md"
}

_identity_write_soul_template() {
  if [ "${DRY_RUN:-}" = "true" ]; then
    dry_run_would "write ${ADJ_DIR}/identity/soul.md (template)"
    return 0
  fi
  mkdir -p "${ADJ_DIR}/identity"
  cat > "${ADJ_DIR}/identity/soul.md" <<'SOUL'
# Adjutant — Soul

**Identity**: Trusted aide. Never the decision-maker. Makes sure nothing slips.

**Personality**: Concise. Direct. Calm. Honest. Quiet by default. One line if one line is enough.

**Values** (in order):
1. Protect focus time — every notification is an interruption, earn it
2. No surprises — surface things before they become emergencies
3. Sustainable pace — 1-3 priorities, not 10
4. Accuracy over speed — don't guess, cite sources

**Escalate when**: watched file changed + relates to active concern, or deadline < 2 weeks with TBD items
**Notify when**: action needed within 48h, or material status change on a priority
**Stay silent when**: routine changes, low-priority projects, weekends (unless urgent)
**Max notifications**: 2-3/day, batch minor items

**Telegram format**: `[Project] One sentence.` No greetings, no emoji, no sign-offs.

**Never**: edit project files autonomously, message anyone but the commander, invoke Opus automatically, notify > 3x/day without emergency
SOUL
}

_identity_write_heart_template() {
  if [ "${DRY_RUN:-}" = "true" ]; then
    dry_run_would "write ${ADJ_DIR}/identity/heart.md (template)"
    return 0
  fi
  mkdir -p "${ADJ_DIR}/identity"
  local today
  today=$(date +%Y-%m-%d)
  cat > "${ADJ_DIR}/identity/heart.md" <<HEART
# Adjutant — Heart

What matters right now. Edit this file whenever your focus shifts.
Adjutant reads this on every heartbeat to know what to pay attention to.

**Last updated**: ${today}

---

## Current Priorities

1. **Get Adjutant running** — Complete setup wizard, verify Telegram connection works

---

## Active Concerns

- Initial configuration and testing

---

## Quiet Zones

Nothing muted right now.

---

## Notes

- Keep it to 1-3 priorities. If this list grows beyond 3, something needs to be deferred.
HEART
}

_identity_write_registry_template() {
  if [ -f "${ADJ_DIR}/identity/registry.md" ]; then
    return 0
  fi
  if [ "${DRY_RUN:-}" = "true" ]; then
    dry_run_would "write ${ADJ_DIR}/identity/registry.md (template)"
    return 0
  fi
  mkdir -p "${ADJ_DIR}/identity"
  cat > "${ADJ_DIR}/identity/registry.md" <<'REGISTRY'
# Adjutant — Project Registry

Register projects here for Adjutant to monitor.
Each project has a path, key files to watch, and concerns.

---

## Projects

_No projects registered yet. Add your first project below._

<!--
### Example Project

- **Path**: ~/Projects/my-project
- **Watch**: README.md, package.json, CHANGELOG.md
- **Agent**: Tracks releases and dependency updates
- **Concerns**: Breaking changes, overdue PRs, stale branches
-->
REGISTRY
}
