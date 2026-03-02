#!/bin/bash
# scripts/setup/steps/messaging.sh — Step 4: Telegram Credential Setup
#
# Walks the user through creating a Telegram bot and obtaining credentials.
# If .env already has valid credentials, skips with a success message.
#
# Sets:
#   WIZARD_TELEGRAM_TOKEN  — the bot token
#   WIZARD_TELEGRAM_CHAT_ID — the chat ID

# Requires: helpers.sh sourced, ADJ_DIR set

step_messaging() {
  wiz_step 4 6 "Messaging — Telegram Setup"
  echo ""

  # Top-level skip — Telegram is optional
  if ! wiz_confirm "Set up Telegram messaging? (you can do this later with 'adjutant setup')" "Y"; then
    wiz_info "Skipping Telegram setup"
    wiz_info "Run 'adjutant setup' at any time to configure messaging"
    WIZARD_TELEGRAM_ENABLED=false
    return 0
  fi
  WIZARD_TELEGRAM_ENABLED=true

  local env_file="${ADJ_DIR}/.env"

  # Check for existing valid credentials
  if [ -f "$env_file" ]; then
    local existing_token existing_chatid
    existing_token=$(grep -E '^TELEGRAM_BOT_TOKEN=' "$env_file" | head -1 | cut -d'=' -f2- | tr -d "'\"")
    existing_chatid=$(grep -E '^TELEGRAM_CHAT_ID=' "$env_file" | head -1 | cut -d'=' -f2- | tr -d "'\"")

    if [ -n "$existing_token" ] && [ "$existing_token" != "your-bot-token-here" ] && \
       [ -n "$existing_chatid" ] && [ "$existing_chatid" != "your-chat-id-here" ]; then
      wiz_ok "Telegram bot token configured"
      wiz_ok "Telegram chat ID configured (${existing_chatid})"
      echo ""
      if ! wiz_confirm "Re-configure Telegram credentials?" "N"; then
        WIZARD_TELEGRAM_TOKEN="$existing_token"
        WIZARD_TELEGRAM_CHAT_ID="$existing_chatid"
        return 0
      fi
    fi
  fi

  # Ask if user already has a token
  echo ""
  if wiz_confirm "Do you have a Telegram bot token?" "N"; then
    _messaging_get_existing_token
  else
    _messaging_create_new_bot
  fi

  # Get the chat ID
  echo ""
  _messaging_get_chat_id || return 1

  # Write to .env
  _messaging_write_env
  wiz_ok "Saved credentials to .env"

  return 0
}

# User already has a token — just paste it
_messaging_get_existing_token() {
  echo ""
  WIZARD_TELEGRAM_TOKEN=$(wiz_input "Paste your bot token")

  if [ -z "$WIZARD_TELEGRAM_TOKEN" ]; then
    wiz_fail "No token provided"
    return 1
  fi

  # Validate token format (roughly: digits:alphanumeric)
  if ! echo "$WIZARD_TELEGRAM_TOKEN" | grep -qE '^[0-9]+:[A-Za-z0-9_-]+$'; then
    wiz_warn "Token format looks unusual (expected: 123456789:ABCdefGHI...)"
    if ! wiz_confirm "Use this token anyway?" "N"; then
      return 1
    fi
  fi

  # Test the token
  printf "  Testing bot token... "
  if [ "${DRY_RUN:-}" = "true" ]; then
    printf "\n"
    dry_run_would "curl https://api.telegram.org/bot<token>/getMe (validate token)"
    wiz_ok "Would verify bot token"
    WIZARD_TELEGRAM_TOKEN="${WIZARD_TELEGRAM_TOKEN:-dry-run-token}"
    return 0
  fi
  local test_resp
  test_resp=$(curl -s "https://api.telegram.org/bot${WIZARD_TELEGRAM_TOKEN}/getMe" 2>/dev/null)
  if echo "$test_resp" | jq -e '.ok == true' >/dev/null 2>&1; then
    local bot_name
    bot_name=$(echo "$test_resp" | jq -r '.result.username // "unknown"')
    printf "\n"
    wiz_ok "Bot verified: @${bot_name}"
  else
    printf "\n"
    wiz_warn "Could not verify token (network issue or invalid token)"
    if ! wiz_confirm "Continue anyway?" "N"; then
      return 1
    fi
  fi
}

# Walk user through creating a new bot
_messaging_create_new_bot() {
  echo ""
  printf "  Let me walk you through creating a Telegram bot:\n"
  echo ""
  printf "  ${_BOLD}1.${_RESET} Open Telegram and search for ${_BOLD}@BotFather${_RESET}\n"
  printf "  ${_BOLD}2.${_RESET} Send ${_BOLD}/newbot${_RESET} and follow the prompts\n"
  printf "  ${_BOLD}3.${_RESET} BotFather will give you a bot token\n"
  echo ""

  WIZARD_TELEGRAM_TOKEN=$(wiz_input "Paste the bot token here")

  if [ -z "$WIZARD_TELEGRAM_TOKEN" ]; then
    wiz_fail "No token provided"
    return 1
  fi

  # Validate
  printf "  Testing bot token... "
  if [ "${DRY_RUN:-}" = "true" ]; then
    printf "\n"
    dry_run_would "curl https://api.telegram.org/bot<token>/getMe (validate token)"
    wiz_ok "Would verify bot token"
    return 0
  fi
  local test_resp
  test_resp=$(curl -s "https://api.telegram.org/bot${WIZARD_TELEGRAM_TOKEN}/getMe" 2>/dev/null)
  if echo "$test_resp" | jq -e '.ok == true' >/dev/null 2>&1; then
    local bot_name
    bot_name=$(echo "$test_resp" | jq -r '.result.username // "unknown"')
    printf "\n"
    wiz_ok "Bot verified: @${bot_name}"
  else
    printf "\n"
    wiz_warn "Could not verify token — continuing anyway"
  fi
}

# Get the chat ID — either auto-detect or manual entry
_messaging_get_chat_id() {
  printf "  Now I need your chat ID.\n"
  echo ""
  printf "  ${_BOLD}1.${_RESET} Send any message to your new bot in Telegram\n"
  printf "  ${_BOLD}2.${_RESET} I'll check for it automatically\n"
  echo ""

  if wiz_confirm "Ready? (press Enter after sending a message to the bot)" "Y"; then
    if [ "${DRY_RUN:-}" = "true" ]; then
      dry_run_would "curl https://api.telegram.org/bot<token>/getUpdates (detect chat ID)"
      WIZARD_TELEGRAM_CHAT_ID="0"
      wiz_ok "Would auto-detect chat ID (using placeholder 0)"
      return 0
    fi
    printf "  Checking for messages... "
    local resp
    resp=$(curl -s "https://api.telegram.org/bot${WIZARD_TELEGRAM_TOKEN}/getUpdates?limit=5" 2>/dev/null)

    if echo "$resp" | jq -e '.ok == true' >/dev/null 2>&1; then
      local chat_id
      chat_id=$(echo "$resp" | jq -r '.result[-1].message.chat.id // empty' 2>/dev/null)

      if [ -n "$chat_id" ]; then
        printf "\n"
        wiz_ok "Found chat ID: ${chat_id}"
        WIZARD_TELEGRAM_CHAT_ID="$chat_id"
        return 0
      fi
    fi

    printf "\n"
    wiz_warn "Couldn't auto-detect chat ID"
  fi

  # Manual fallback
  echo ""
  printf "  To find your chat ID manually:\n"
  printf "  ${_DIM}Visit: https://api.telegram.org/bot<TOKEN>/getUpdates${_RESET}\n"
  printf "  ${_DIM}Look for \"chat\":{\"id\":NNNNN} in the response${_RESET}\n"
  echo ""

  WIZARD_TELEGRAM_CHAT_ID=$(wiz_input "Enter your chat ID")

  if [ -z "$WIZARD_TELEGRAM_CHAT_ID" ]; then
    wiz_fail "No chat ID provided"
    return 1
  fi

  # Validate it's numeric
  if ! echo "$WIZARD_TELEGRAM_CHAT_ID" | grep -qE '^-?[0-9]+$'; then
    wiz_warn "Chat ID should be numeric"
    if ! wiz_confirm "Use this value anyway?" "N"; then
      return 1
    fi
  fi

  wiz_ok "Chat ID set: ${WIZARD_TELEGRAM_CHAT_ID}"
  return 0
}

# Write credentials to .env
_messaging_write_env() {
  local env_file="${ADJ_DIR}/.env"

  if [ "${DRY_RUN:-}" = "true" ]; then
    dry_run_would "write/update ${env_file} (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)"
    dry_run_would "chmod 600 ${env_file}"
    return 0
  fi

  # If .env exists, update in-place; otherwise create from scratch
  if [ -f "$env_file" ]; then
    # Update or append TELEGRAM_BOT_TOKEN
    if grep -q '^TELEGRAM_BOT_TOKEN=' "$env_file"; then
      sed -i.bak "s|^TELEGRAM_BOT_TOKEN=.*|TELEGRAM_BOT_TOKEN=${WIZARD_TELEGRAM_TOKEN}|" "$env_file" && rm -f "${env_file}.bak"
    else
      echo "TELEGRAM_BOT_TOKEN=${WIZARD_TELEGRAM_TOKEN}" >> "$env_file"
    fi

    # Update or append TELEGRAM_CHAT_ID
    if grep -q '^TELEGRAM_CHAT_ID=' "$env_file"; then
      sed -i.bak "s|^TELEGRAM_CHAT_ID=.*|TELEGRAM_CHAT_ID=${WIZARD_TELEGRAM_CHAT_ID}|" "$env_file" && rm -f "${env_file}.bak"
    else
      echo "TELEGRAM_CHAT_ID=${WIZARD_TELEGRAM_CHAT_ID}" >> "$env_file"
    fi
  else
    cat > "$env_file" <<ENV
# Adjutant — Credentials
# Generated by setup wizard on $(date +%Y-%m-%d)
TELEGRAM_BOT_TOKEN=${WIZARD_TELEGRAM_TOKEN}
TELEGRAM_CHAT_ID=${WIZARD_TELEGRAM_CHAT_ID}
ENV
  fi

  # Restrict permissions — secrets file
  chmod 600 "$env_file"
}
