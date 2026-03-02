#!/bin/bash
# scripts/setup/steps/features.sh — Step 5: Feature Selection
#
# Asks which optional features to enable and updates adjutant.yaml.
#
# Features:
#   - News briefing (requires cron)
#   - Screenshot capability (requires Playwright)
#   - Vision capability (built-in)
#   - Usage tracking (built-in)
#
# Sets:
#   WIZARD_FEATURES_NEWS=true/false
#   WIZARD_FEATURES_SCREENSHOT=true/false
#   WIZARD_FEATURES_VISION=true/false
#   WIZARD_FEATURES_USAGE=true/false

# Requires: helpers.sh sourced, ADJ_DIR set

WIZARD_FEATURES_NEWS=false
WIZARD_FEATURES_SCREENSHOT=false
WIZARD_FEATURES_VISION=true
WIZARD_FEATURES_USAGE=true

step_features() {
  wiz_step 5 6 "Features"
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

  # Update each feature's enabled flag
  _features_yaml_set_bool "news" "$WIZARD_FEATURES_NEWS" "$config_file"
  _features_yaml_set_bool "screenshot" "$WIZARD_FEATURES_SCREENSHOT" "$config_file"
  _features_yaml_set_bool "vision" "$WIZARD_FEATURES_VISION" "$config_file"
  _features_yaml_set_bool "usage_tracking" "$WIZARD_FEATURES_USAGE" "$config_file"
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
