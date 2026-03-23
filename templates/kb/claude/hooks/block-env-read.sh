#!/usr/bin/env bash
# block-env-read.sh — PreToolUse hook for Read tool (KB template)
# Blocks Read tool calls targeting .env files or credential files.

set -euo pipefail

INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | grep -oP '"file_path"\s*:\s*"([^"]*)"' | head -1 | sed 's/.*"file_path"\s*:\s*"//;s/"$//' || true)

if [ -z "$FILE_PATH" ]; then
    exit 0
fi

if echo "$FILE_PATH" | grep -qiE '(^|/)\.env($|/)' &&
   ! echo "$FILE_PATH" | grep -qiE '\.env\.example'; then
    echo '{"result": "DENIED: Reading .env files is not allowed."}' >&2
    exit 2
fi

if echo "$FILE_PATH" | grep -qiE '(secret|credential|password|token)'; then
    if echo "$FILE_PATH" | grep -qiE '\.(py|js|ts|md|txt|yaml|yml|json|sh)$'; then
        exit 0
    fi
    echo '{"result": "DENIED: Reading credential files is not allowed."}' >&2
    exit 2
fi

exit 0
