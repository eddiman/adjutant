#!/usr/bin/env bash
# block-env-access.sh — PreToolUse hook for Bash tool
# Blocks commands that would read .env files or dump environment variables.
# Returns exit 2 to deny the tool call (Claude Code convention).
#
# This hook fires even when --dangerously-skip-permissions is active,
# making it the PRIMARY technical defense for .env protection on the
# Claude CLI backend.

set -euo pipefail

# The tool input is passed via stdin as JSON.
# Extract the command field.
INPUT=$(cat)
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null || true)

if [ -z "$COMMAND" ]; then
    exit 0  # No command found — allow
fi

# Patterns that read .env files (excluding .env.example)
if echo "$COMMAND" | grep -qiE '(^|\s)(cat|head|tail|less|more|bat|view|nano|vim?|emacs)\s+.*\.env($|\s|/)' &&
   ! echo "$COMMAND" | grep -qiE '\.env\.example'; then
    echo '{"result": "DENIED: Reading .env files is not allowed. Use get_credential() from core/env.py."}' >&2
    exit 2
fi

# Patterns that source or eval .env files
if echo "$COMMAND" | grep -qiE '(^|\s)(source|\.)\s+.*\.env($|\s)'; then
    echo '{"result": "DENIED: Sourcing .env files is not allowed."}' >&2
    exit 2
fi

# Patterns that dump environment variables
if echo "$COMMAND" | grep -qiE '(^|\s)(printenv|env\s*$|export\s+-p|declare\s+-p|set\s*$)'; then
    echo '{"result": "DENIED: Dumping environment variables is not allowed."}' >&2
    exit 2
fi

# Patterns that use grep/awk/sed on .env files
if echo "$COMMAND" | grep -qiE '(grep|awk|sed)\s+.*\.env($|\s)' &&
   ! echo "$COMMAND" | grep -qiE '\.env\.example'; then
    echo '{"result": "DENIED: Reading .env files via text processing tools is not allowed."}' >&2
    exit 2
fi

exit 0  # Allow
