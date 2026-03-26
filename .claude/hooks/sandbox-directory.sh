#!/usr/bin/env bash
# sandbox-directory.sh — PreToolUse hook for all file-access tools
# Blocks tool calls that target paths outside the project directory.
# Returns exit 2 to deny the tool call.

set -euo pipefail

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-}"
if [ -z "$PROJECT_DIR" ]; then
    exit 0  # Can't enforce without knowing the project dir
fi

# Resolve project dir to absolute path (follow symlinks)
PROJECT_DIR=$(cd "$PROJECT_DIR" && pwd -P)

INPUT=$(cat)
TOOL_NAME="${CLAUDE_TOOL_NAME:-}"

check_path() {
    local raw_path="$1"
    [ -z "$raw_path" ] && return 0

    # Expand ~ to home directory
    raw_path="${raw_path/#\~/$HOME}"

    # Resolve to absolute path
    if [[ "$raw_path" = /* ]]; then
        if [ -e "$raw_path" ]; then
            resolved=$(cd "$(dirname "$raw_path")" 2>/dev/null && pwd -P)/$(basename "$raw_path")
        else
            resolved="$raw_path"
        fi
    else
        resolved="$PROJECT_DIR/$raw_path"
    fi

    if [[ "$resolved" != "$PROJECT_DIR"* ]]; then
        echo "{\"result\": \"DENIED: Access outside project directory is not allowed. Path: $raw_path\"}" >&2
        exit 2
    fi
}

case "$TOOL_NAME" in
    Read|Edit|Write)
        FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null || true)
        check_path "$FILE_PATH"
        ;;
    Glob|Grep)
        SEARCH_PATH=$(echo "$INPUT" | jq -r '.tool_input.path // empty' 2>/dev/null || true)
        if [ -n "$SEARCH_PATH" ]; then
            check_path "$SEARCH_PATH"
        fi
        ;;
    Bash)
        COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null || true)
        [ -z "$COMMAND" ] && exit 0

        # Allow safe commands that don't access arbitrary paths
        if echo "$COMMAND" | grep -qE '^\s*(git\s|\.venv/|python\s+-m\s+adjutant)'; then
            exit 0
        fi

        # Scan for absolute paths outside project dir
        for path in $(echo "$COMMAND" | grep -oE '(/[a-zA-Z][a-zA-Z0-9_./-]+|~/[a-zA-Z0-9_./-]+)' || true); do
            expanded="${path/#\~/$HOME}"
            if [[ "$expanded" = /* ]] && [[ "$expanded" != "$PROJECT_DIR"* ]] && [[ "$expanded" != "/dev/"* ]]; then
                echo "{\"result\": \"DENIED: Bash command references path outside project directory: $path\"}" >&2
                exit 2
            fi
        done
        ;;
esac

exit 0
