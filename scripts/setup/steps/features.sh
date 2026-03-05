#!/bin/bash
# scripts/setup/steps/features.sh — Step 5: Feature Selection
#
# Asks which optional features to enable and updates adjutant.yaml.
#
# Features:
#   - News briefing (requires cron)
#   - Screenshot capability (requires Playwright)
#   - Vision capability (built-in)
#   - Web search (requires Brave Search API key)
#   - Usage tracking (built-in)
#
# Sets:
#   WIZARD_FEATURES_NEWS=true/false
#   WIZARD_FEATURES_SCREENSHOT=true/false
#   WIZARD_FEATURES_VISION=true/false
#   WIZARD_FEATURES_SEARCH=true/false
#   WIZARD_FEATURES_USAGE=true/false

# Requires: helpers.sh sourced, ADJ_DIR set

WIZARD_FEATURES_NEWS=false
WIZARD_FEATURES_SCREENSHOT=false
WIZARD_FEATURES_VISION=true
WIZARD_FEATURES_SEARCH=false
WIZARD_FEATURES_USAGE=true

step_features() {
  wiz_step 5 7 "Features"
  echo ""

  # News briefing
  local news_hint=""
  if ! has_command opencode; then
    news_hint=" (requires opencode)"
  fi
  if wiz_confirm "Enable news briefing?${news_hint} (fetches AI news daily)" "N"; then
    WIZARD_FEATURES_NEWS=true
    wiz_ok "News briefing enabled"

    # Create default news_config.json if missing
    if [ ! -f "${ADJ_DIR}/news_config.json" ]; then
      _features_write_news_config
      wiz_info "Created default news_config.json"
    fi

    echo ""
    printf "  ${_BOLD}Configuring news sources:${_RESET}\n"
    echo ""
    printf "  Edit ${_BOLD}${ADJ_DIR}/news_config.json${_RESET} to customise what you receive:\n"
    echo ""
    printf "  ${_DIM}keywords${_RESET}        — topics to prioritise (e.g. \"AI agent\", \"LLM\")\n"
    printf "  ${_DIM}hackernews${_RESET}      — enabled by default, set max_items / lookback_hours\n"
    printf "  ${_DIM}reddit${_RESET}          — disabled by default, add subreddits and set enabled: true\n"
    printf "  ${_DIM}blogs${_RESET}           — disabled by default, add RSS/Atom feed URLs and set enabled: true\n"
    echo ""
    printf "  Example blog entry:\n"
    printf "  ${_DIM}\"urls\": [\"https://simonwillison.net/atom/everything/\"]${_RESET}\n"
    echo ""
    wiz_info "Run 'adjutant news' to test the briefing manually after setup"
    wiz_info "The news_briefing cron job will be enabled in schedules: during service installation."
  else
    WIZARD_FEATURES_NEWS=false
    wiz_info "News briefing disabled"
  fi
  echo ""

  # Screenshot — requires Telegram to deliver the image
  if [ "${WIZARD_TELEGRAM_ENABLED:-true}" = "false" ]; then
    WIZARD_FEATURES_SCREENSHOT=false
    wiz_info "Screenshot disabled (requires Telegram)"
  else
    local screenshot_available=true
    if ! (has_command npx && npx playwright --version >/dev/null 2>&1); then
      screenshot_available=false
    fi
    if $screenshot_available; then
      if wiz_confirm "Enable screenshot capability?" "Y"; then
        WIZARD_FEATURES_SCREENSHOT=true
        wiz_ok "Screenshot enabled"
      else
        WIZARD_FEATURES_SCREENSHOT=false
        wiz_info "Screenshot disabled"
      fi
    else
      wiz_warn "Screenshot requires Playwright (not installed)"
      if wiz_confirm "Enable anyway? (you can install Playwright later)" "N"; then
        WIZARD_FEATURES_SCREENSHOT=true
        wiz_ok "Screenshot enabled (install Playwright with: npx playwright install chromium)"
      else
        WIZARD_FEATURES_SCREENSHOT=false
        wiz_info "Screenshot disabled"
      fi
    fi
  fi
  echo ""

  # Vision — requires Telegram (triggered by receiving photos from the bot)
  if [ "${WIZARD_TELEGRAM_ENABLED:-true}" = "false" ]; then
    WIZARD_FEATURES_VISION=false
    wiz_info "Vision disabled (requires Telegram)"
  else
    if wiz_confirm "Enable vision capability? (analyze photos sent to bot)" "Y"; then
      WIZARD_FEATURES_VISION=true
      wiz_ok "Vision enabled"
    else
      WIZARD_FEATURES_VISION=false
      wiz_info "Vision disabled"
    fi
  fi
  echo ""

  # Web search — standalone, no Telegram required
  if wiz_confirm "Enable web search? (Brave Search API — no bot detection, low token cost)" "Y"; then
    # Check for existing key first
    local existing_brave_key=""
    if [ -f "${ADJ_DIR}/.env" ]; then
      existing_brave_key="$(grep -E '^BRAVE_API_KEY=' "${ADJ_DIR}/.env" 2>/dev/null | head -1 | cut -d= -f2- | tr -d "'\"")"
    fi

    if [ -n "${existing_brave_key}" ] && [ "${existing_brave_key}" != "your-brave-api-key-here" ]; then
      WIZARD_FEATURES_SEARCH=true
      wiz_ok "Web search enabled (existing API key found)"
    else
      echo ""
      printf "  ${_BOLD}Brave Search API key required${_RESET}\n"
      printf "  Free tier: 2,000 queries/month\n"
      printf "  Get a key at: ${_CYAN}https://api.search.brave.com${_RESET}\n"
      echo ""
      local brave_key
      brave_key="$(wiz_secret "Paste your Brave API key (or press Enter to skip)")"
      echo ""

      if [ -n "${brave_key}" ]; then
        _features_write_brave_key "${brave_key}"
        WIZARD_FEATURES_SEARCH=true
        wiz_ok "Web search enabled"
        wiz_info "Key saved to .env"
      else
        WIZARD_FEATURES_SEARCH=false
        wiz_info "Web search disabled (no key provided — add BRAVE_API_KEY to .env later to enable)"
      fi
    fi
  else
    WIZARD_FEATURES_SEARCH=false
    wiz_info "Web search disabled"
  fi
  echo ""

  # Usage tracking
  if wiz_confirm "Enable usage tracking?" "Y"; then
    WIZARD_FEATURES_USAGE=true
    wiz_ok "Usage tracking enabled"
  else
    WIZARD_FEATURES_USAGE=false
    wiz_info "Usage tracking disabled"
  fi

  # Update adjutant.yaml
  _features_update_config
  echo ""
  wiz_ok "Feature configuration saved"

  return 0
}

# Update the features section of adjutant.yaml
_features_update_config() {
  local config_file="${ADJ_DIR}/adjutant.yaml"
  [ ! -f "$config_file" ] && return 0

  [ "${DRY_RUN:-}" = "true" ] && { dry_run_would "update features in ${config_file}"; return 0; }

  # Update each feature's enabled flag
  _features_yaml_set_bool "news" "$WIZARD_FEATURES_NEWS" "$config_file"
  _features_yaml_set_bool "screenshot" "$WIZARD_FEATURES_SCREENSHOT" "$config_file"
  _features_yaml_set_bool "vision" "$WIZARD_FEATURES_VISION" "$config_file"
  _features_yaml_set_bool "search" "$WIZARD_FEATURES_SEARCH" "$config_file"
  _features_yaml_set_bool "usage_tracking" "$WIZARD_FEATURES_USAGE" "$config_file"

  # Sync news_briefing schedule entry with news feature state
  if type schedule_set_enabled &>/dev/null || source "${ADJ_DIR}/scripts/capabilities/schedule/manage.sh" 2>/dev/null; then
    if type schedule_exists &>/dev/null && schedule_exists "news_briefing" 2>/dev/null; then
      schedule_set_enabled "news_briefing" "${WIZARD_FEATURES_NEWS}" 2>/dev/null || true
    fi
  fi
}

# Set a feature's enabled: true/false in adjutant.yaml
# This uses sed to find the feature block and update the enabled line
_features_yaml_set_bool() {
  local feature="$1"
  local value="$2"
  local file="$3"

  # Find the feature section and update enabled: on the next line
  # This handles the pattern:
  #   feature_name:
  #     enabled: true/false
  if grep -qE "^  ${feature}:" "$file" 2>/dev/null; then
    # Use awk to find the section and update the enabled line
    local tmpfile="${file}.tmp.$$"
    awk -v feat="  ${feature}:" -v val="$value" '
      $0 == feat { print; found=1; next }
      found && /enabled:/ { sub(/enabled:.*/, "enabled: " val); found=0 }
      { print }
    ' "$file" > "$tmpfile" && mv "$tmpfile" "$file"
  fi
}

# Write or update BRAVE_API_KEY in .env
_features_write_brave_key() {
  local key="$1"
  local env_file="${ADJ_DIR}/.env"

  if [ "${DRY_RUN:-}" = "true" ]; then
    dry_run_would "write BRAVE_API_KEY to ${env_file}"
    return 0
  fi

  if [ ! -f "${env_file}" ]; then
    # Create minimal .env if it doesn't exist yet
    touch "${env_file}"
    chmod 600 "${env_file}"
  fi

  if grep -qE '^BRAVE_API_KEY=' "${env_file}" 2>/dev/null; then
    # Update existing entry
    local tmpfile="${env_file}.tmp.$$"
    awk -v key="BRAVE_API_KEY=${key}" '/^BRAVE_API_KEY=/ { print key; next } { print }' "${env_file}" > "${tmpfile}" \
      && mv "${tmpfile}" "${env_file}"
  else
    # Append new entry
    printf '\n# Brave Search API — /search command and agent web search\nBRAVE_API_KEY=%s\n' "${key}" >> "${env_file}"
  fi

  chmod 600 "${env_file}"
}

# Write a default news_config.json
_features_write_news_config() {
  if [ "${DRY_RUN:-}" = "true" ]; then
    dry_run_would "write ${ADJ_DIR}/news_config.json (default news config)"
    return 0
  fi
  cat > "${ADJ_DIR}/news_config.json" <<'JSON'
{
  "keywords": ["AI agent", "autonomous agent", "LLM", "Claude", "GPT"],
  "sources": {
    "hackernews": {
      "enabled": true,
      "max_items": 30,
      "lookback_hours": 24
    },
    "reddit": {
      "enabled": false,
      "subreddits": ["MachineLearning", "LocalLLaMA"],
      "max_items": 20,
      "lookback_hours": 24
    },
    "blogs": {
      "enabled": false,
      "urls": []
    }
  },
  "analysis": {
    "prefilter_limit": 10,
    "top_n": 5,
    "model": "anthropic/claude-haiku-4-5"
  },
  "delivery": {
    "telegram": true,
    "journal": true
  },
  "deduplication": {
    "window_days": 30
  },
  "cleanup": {
    "raw_retention_days": 7,
    "analyzed_retention_days": 7
  }
}
JSON
}
