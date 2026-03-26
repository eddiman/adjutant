#!/usr/bin/env bash
# block-env-read.sh — PreToolUse hook for Read tool
# Blocks Read tool calls targeting .env files or credential files.
# Returns exit 2 to deny the tool call (Claude Code convention).
#
# Belt-and-suspenders with permission deny rules. When
# --dangerously-skip-permissions is active, this hook is the
# only defense against Read-based .env access.

set -euo pipefail

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null || true)

if [ -z "$FILE_PATH" ]; then
    exit 0  # No file path — allow
fi

# Block .env files (but allow .env.example)
if echo "$FILE_PATH" | grep -qiE '(^|/)\.env($|/)' &&
   ! echo "$FILE_PATH" | grep -qiE '\.env\.example'; then
    echo '{"result": "DENIED: Reading .env files is not allowed. Use get_credential() from core/env.py."}' >&2
    exit 2
fi

# Block credential/secret files
if echo "$FILE_PATH" | grep -qiE '(secret|credential|password|token)'; then
    # Allow if it's a code file discussing these concepts
    if echo "$FILE_PATH" | grep -qiE '\.(py|js|ts|md|txt|yaml|yml|json|sh)$'; then
        exit 0
    fi
    echo '{"result": "DENIED: Reading credential files is not allowed."}' >&2
    exit 2
fi

exit 0  # Allow
