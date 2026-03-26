#!/usr/bin/env bash
# block-kb-read.sh — PreToolUse hook for file-access tools
# Blocks direct read/write/search access to knowledge base directories.
# KBs must be queried via: .venv/bin/python -m adjutant kb query <name> "<question>"
# Returns exit 2 to deny the tool call.

set -euo pipefail

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-}"
if [ -z "$PROJECT_DIR" ]; then
    exit 0
fi

REGISTRY="$PROJECT_DIR/knowledge_bases/registry.yaml"
if [ ! -f "$REGISTRY" ]; then
    exit 0  # No registry — nothing to protect
fi

# Parse KB paths from registry.yaml
KB_PATHS=()
while IFS= read -r line; do
    path=$(echo "$line" | sed -n 's/.*path:\s*//p' | xargs)
    [ -z "$path" ] && continue
    if [[ "$path" != /* ]]; then
        path="$PROJECT_DIR/$path"
    fi
    if [ -e "$path" ]; then
        path=$(cd "$path" 2>/dev/null && pwd -P) || path="$path"
    fi
    KB_PATHS+=("$path")
done < "$REGISTRY"

# Also block the knowledge_bases/ directory itself
KB_PATHS+=("$PROJECT_DIR/knowledge_bases")

[ ${#KB_PATHS[@]} -eq 0 ] && exit 0

DENY_MSG="DENIED: Direct KB file access is not allowed. Use: .venv/bin/python -m adjutant kb query <name> \\\"<question>\\\""

check_kb_path() {
    local target="$1"
    [ -z "$target" ] && return 0

    target="${target/#\~/$HOME}"
    if [[ "$target" != /* ]]; then
        target="$PROJECT_DIR/$target"
    fi
    if [ -e "$target" ]; then
        resolved=$(cd "$(dirname "$target")" 2>/dev/null && pwd -P)/$(basename "$target") || resolved="$target"
    else
        resolved="$target"
    fi

    for kb in "${KB_PATHS[@]}"; do
        if [[ "$resolved" = "$kb"* ]]; then
            echo "{\"result\": \"$DENY_MSG\"}" >&2
            exit 2
        fi
    done
}

INPUT=$(cat)
TOOL_NAME="${CLAUDE_TOOL_NAME:-}"

case "$TOOL_NAME" in
    Read|Edit|Write)
        FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null || true)
        check_kb_path "$FILE_PATH"
        ;;
    Glob|Grep)
        SEARCH_PATH=$(echo "$INPUT" | jq -r '.tool_input.path // empty' 2>/dev/null || true)
        check_kb_path "$SEARCH_PATH"
        ;;
    Bash)
        COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null || true)
        [ -z "$COMMAND" ] && exit 0

        for kb in "${KB_PATHS[@]}"; do
            if echo "$COMMAND" | grep -qF "$kb"; then
                echo "{\"result\": \"$DENY_MSG\"}" >&2
                exit 2
            fi
        done
        # Check for relative references to knowledge_bases/
        if echo "$COMMAND" | grep -qE 'knowledge_bases'; then
            echo "{\"result\": \"$DENY_MSG\"}" >&2
            exit 2
        fi
        ;;
esac

exit 0
