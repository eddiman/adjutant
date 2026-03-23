"""Setup wizard: backend selection step.

Asks the user which LLM backend to use (OpenCode or Claude CLI) and,
if Claude CLI, which permission mode. Writes the selection to
adjutant.yaml under llm.backend and llm.permission_mode.
"""

from __future__ import annotations

import sys
from pathlib import Path

from adjutant.setup.wizard import wiz_choose, wiz_ok, wiz_step, wiz_warn


def step_backend(adj_dir: Path, *, dry_run: bool = False) -> dict[str, str]:
    """Run the backend selection step.

    Returns:
        Dict with keys 'backend' and optionally 'permission_mode'.
    """
    wiz_step(2, 7, "LLM Backend")
    print("", file=sys.stderr)

    choice = wiz_choose(
        "Which LLM backend would you like to use?",
        "OpenCode (default) — uses `opencode` CLI, requires API key",
        "Claude Code CLI — uses `claude` CLI, works with Claude subscription",
    )

    result: dict[str, str] = {}

    if choice == 0:
        result["backend"] = "opencode"
        wiz_ok("Backend: OpenCode")
    else:
        result["backend"] = "claude-cli"
        wiz_ok("Backend: Claude Code CLI")

        # Permission mode sub-question
        print("", file=sys.stderr)
        perm_choice = wiz_choose(
            "Permission mode for Claude CLI:",
            "Skip all permissions (default, recommended) — non-interactive, hooks guard .env",
            "Use allowlist — .claude/settings.json deny rules stay active",
        )
        if perm_choice == 0:
            result["permission_mode"] = "skip"
            wiz_ok("Permission mode: skip (hooks are primary defense)")
        else:
            result["permission_mode"] = "allowlist"
            wiz_ok("Permission mode: allowlist (deny rules + hooks)")

        # Check binary availability
        from adjutant.core.backend import get_backend

        backend = get_backend("claude-cli")
        if not backend.find_binary():
            wiz_warn("claude binary not found — install Claude Code CLI before use")

    print("", file=sys.stderr)
    return result
