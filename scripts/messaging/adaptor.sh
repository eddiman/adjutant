#!/bin/bash
# scripts/messaging/adaptor.sh — Messaging Adaptor Interface Contract
#
# Any backend (Telegram, Slack, Discord, CLI) must implement these functions.
#
# To create a new adaptor:
# 1. Create scripts/messaging/<backend>/
# 2. Implement all REQUIRED functions below (override these defaults)
# 3. Implement optional functions if supported
# 4. Set messaging.backend in adjutant.yaml
# 5. Source this file FIRST, then source your adaptor's send.sh to override
#
# The defaults here are no-op stubs that print errors for required functions
# and silently succeed for optional ones. A concrete adaptor (e.g. telegram/send.sh)
# overrides these with real implementations.

# ===== REQUIRED FUNCTIONS =====

# Send a text message to the user
# Args: $1 = message text, $2 = optional reply-to message ID
# Returns: 0 on success, 1 on failure
msg_send_text() {
  echo "ERROR: msg_send_text() not implemented by adaptor" >&2
  return 1
}

# Send a photo/image to the user
# Args: $1 = file path to image, $2 = optional caption
# Returns: 0 on success, 1 on failure
msg_send_photo() {
  echo "ERROR: msg_send_photo() not implemented by adaptor" >&2
  return 1
}

# Start the message polling/listening loop
# This should run indefinitely, calling dispatch_message() / dispatch_photo()
# for each received message. The loop should respect KILLED/PAUSED lockfiles.
msg_start_listener() {
  echo "ERROR: msg_start_listener() not implemented by adaptor" >&2
  return 1
}

# Stop the listener gracefully
# Returns: 0 on success, 1 on failure
msg_stop_listener() {
  echo "ERROR: msg_stop_listener() not implemented by adaptor" >&2
  return 1
}

# ===== OPTIONAL FUNCTIONS (safe defaults) =====

# Add a reaction (emoji) to a message
# Args: $1 = message ID, $2 = emoji
# Default: no-op
msg_react() {
  return 0
}

# Show/hide typing indicator
# Args: $1 = start|stop, $2 = optional identifier suffix
# Default: no-op
msg_typing() {
  return 0
}

# Validate sender identity
# Args: $1 = sender ID (adaptor-specific)
# Returns: 0 if authorized, 1 if not
# Default: allow all
msg_authorize() {
  return 0
}

# Get the authenticated user ID
# Returns: user ID string on stdout
msg_get_user_id() {
  echo "unknown"
}
