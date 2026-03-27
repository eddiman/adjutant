"""Setup wizard: backend selection step (Step 3 of 8).

Asks the user which LLM backend to use (OpenCode or Claude CLI) and,
if Claude CLI, which permission mode. Writes the selection to
adjutant.yaml under llm.backend and llm.permission_mode.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from adjutant.setup.wizard import wiz_choose, wiz_info, wiz_ok, wiz_step, wiz_warn

if TYPE_CHECKING:
    from pathlib import Path


def _write_backend_to_yaml(adj_dir: Path, result: dict[str, str]) -> None:
    """Write llm.backend (and optionally llm.permission_mode) to adjutant.yaml."""
    config_path = adj_dir / "adjutant.yaml"
    if not config_path.is_file():
        return
    try:
        import yaml

        with open(config_path) as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            return
        llm = data.setdefault("llm", {})
        if not isinstance(llm, dict):
            data["llm"] = {}
            llm = data["llm"]
        llm["backend"] = result["backend"]
        if "permission_mode" in result:
            llm["permission_mode"] = result["permission_mode"]
        with open(config_path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    except Exception:  # noqa: BLE001 — best-effort config write
        pass


def step_backend(adj_dir: Path, *, dry_run: bool = False) -> dict[str, str]:
    """Run the backend selection step.

    Returns:
        Dict with keys 'backend' and optionally 'permission_mode'.
    """
    wiz_step(3, 8, "LLM Backend")
    print("", file=sys.stderr)

    choice = wiz_choose(
        "Which LLM backend would you like to use?",
        "OpenCode (default) — uses `opencode` CLI, requires API key",
        "Claude Code CLI — uses `claude` CLI, works with Claude subscription",
    )

    result: dict[str, str] = {}

    if choice == 1:
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
        if perm_choice == 1:
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

    if dry_run:
        wiz_info(f"[DRY RUN] Would write llm.backend: {result['backend']} to adjutant.yaml")
    else:
        _write_backend_to_yaml(adj_dir, result)

    print("", file=sys.stderr)
    return result
