#!/usr/bin/env bash
# Install git hooks from hooks/ into .git/hooks/
set -euo pipefail

HOOKS_DIR="$(cd "$(dirname "$0")" && pwd)"
GIT_HOOKS_DIR="$(git -C "$HOOKS_DIR" rev-parse --git-dir)/hooks"

for hook in "$HOOKS_DIR"/commit-msg "$HOOKS_DIR"/pre-commit; do
    [ -f "$hook" ] || continue
    name="$(basename "$hook")"
    cp "$hook" "$GIT_HOOKS_DIR/$name"
    chmod +x "$GIT_HOOKS_DIR/$name"
    echo "Installed $name hook"
done
