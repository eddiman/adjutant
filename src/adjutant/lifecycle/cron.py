"""Cron job wrappers — pulse and review autonomous runs.

Replaces bash scripts:
  - scripts/lifecycle/pulse_cron.sh
  - scripts/lifecycle/review_cron.sh

Both are thin wrappers called by crontab.  They read a prompt file,
write an active-operation marker, run opencode as a subprocess, and
clean up the marker when done.  The opencode exit code is propagated
via sys.exit so cron sees the real result.

After a successful pulse or review, a Telegram notification is sent
with a summary of what was found (budget-guarded, best-effort).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from adjutant.core.backend import BackendNotFoundError, get_backend
from adjutant.core.lockfiles import clear_active_operation, set_active_operation
from adjutant.core.paths import AdjutantDirNotFoundError, get_adj_dir, init_adj_dir


def _format_heartbeat(data: dict[str, Any], action: str, source: str) -> str:  # noqa: C901
    """Format last_heartbeat.json into a natural-language notification."""
    kbs = data.get("kbs_checked", [])
    issues = data.get("issues_found", [])
    escalated = data.get("escalated", False)

    emoji = "\U0001f4e1" if action == "pulse" else "\U0001f4dd"  # 📡 or 📝
    kb_count = len(kbs)
    issue_count = len(issues)

    # Build a natural opening line
    if kb_count == 0:
        opening = f"{emoji} Ran a {action}, nothing to check."
    elif issue_count == 0:
        if kb_count == 1:
            opening = f"{emoji} Checked {kbs[0]}. All clear."
        else:
            opening = f"{emoji} Checked {kb_count} KBs. Everything looks good."
    else:
        if kb_count == 1:
            opening = f"{emoji} Checked {kbs[0]}."
        else:
            opening = f"{emoji} Checked {kb_count} KBs."
        if issue_count == 1:
            opening += f" Found one issue: {issues[0]}"
        else:
            opening += f" Found {issue_count} issues."

    parts = [opening]

    # List issues only when there are multiple (single already inlined above)
    if issue_count > 1:
        for issue in issues[:8]:
            parts.append(f"\u2022 {issue}")
        if issue_count > 8:
            parts.append(f"  ...plus {issue_count - 8} more")

    if escalated:
        parts.append("\n\u26a0\ufe0f Flagged for your attention.")

    return "\n".join(parts)


def _notify_completion(adj_dir: Path, action: str, source: str) -> None:
    """Send a Telegram notification with the pulse/review results.

    Reads state/last_heartbeat.json, formats a summary, and sends via
    send_notify.  Best-effort: silently swallows all errors (missing
    heartbeat, budget exceeded, missing credentials, network errors).
    """
    try:
        heartbeat_file = adj_dir / "state" / "last_heartbeat.json"
        if not heartbeat_file.is_file():
            return

        data = json.loads(heartbeat_file.read_text())
        message = _format_heartbeat(data, action, source)

        from adjutant.messaging.telegram.notify import send_notify

        send_notify(message, adj_dir)
    except Exception:  # noqa: BLE001 — best-effort, never crash the cron job
        pass


def run_cron_prompt(
    prompt_file: Path,
    *,
    adj_dir: Path | None = None,
    action: str = "unknown",
    source: str = "cron",
) -> None:
    """Read a prompt file and run opencode as a subprocess.

    Writes state/active_operation.json before starting and removes it
    when done (success or failure).  On success, sends a Telegram
    notification with the results.  Propagates the opencode exit code
    via sys.exit so cron sees the real result.

    Args:
        prompt_file: Absolute path to the prompt markdown file.
        adj_dir: Adjutant root directory.  Defaults to $ADJ_DIR.
        action: Operation name for the active-operation marker (e.g. "pulse").
        source: Trigger source for the marker (e.g. "cron", "adjutant-web").

    Raises:
        SystemExit: Always — either with the opencode exit code or 1 on error.
    """
    if adj_dir is None:
        try:
            adj_dir = get_adj_dir()
        except AdjutantDirNotFoundError:
            sys.stderr.write("ERROR: ADJ_DIR not set\n")
            raise SystemExit(1)

    if not prompt_file.is_file():
        sys.stderr.write(f"ERROR: Prompt file not found at {prompt_file}\n")
        raise SystemExit(1)

    prompt_text = prompt_file.read_text()

    try:
        backend = get_backend()
    except (BackendNotFoundError, ValueError) as exc:
        sys.stderr.write(f"ERROR: {exc}\n")
        raise SystemExit(1) from exc

    if not backend.find_binary():
        sys.stderr.write(f"ERROR: {backend.name} binary not found on PATH\n")
        raise SystemExit(1)

    set_active_operation(action, source, adj_dir=adj_dir)
    try:
        returncode = backend.run_sync(prompt_text, workdir=adj_dir)
        if returncode == 0 and action != "unknown":
            _notify_completion(adj_dir, action, source)
        sys.exit(returncode)
    except KeyboardInterrupt:
        sys.exit(130)
    finally:
        clear_active_operation(adj_dir=adj_dir)


def pulse_cron(adj_dir: Path | None = None, *, source: str = "cron") -> None:
    """Cron entry point for the autonomous pulse job.

    Replaces: scripts/lifecycle/pulse_cron.sh
    """
    if adj_dir is None:
        try:
            adj_dir = init_adj_dir()
        except AdjutantDirNotFoundError as exc:
            sys.stderr.write(f"ERROR: {exc}\n")
            raise SystemExit(1) from exc

    prompt_file = adj_dir / "prompts" / "pulse.md"
    run_cron_prompt(prompt_file, adj_dir=adj_dir, action="pulse", source=source)


def review_cron(adj_dir: Path | None = None, *, source: str = "cron") -> None:
    """Cron entry point for the autonomous daily review job.

    Replaces: scripts/lifecycle/review_cron.sh
    """
    if adj_dir is None:
        try:
            adj_dir = init_adj_dir()
        except AdjutantDirNotFoundError as exc:
            sys.stderr.write(f"ERROR: {exc}\n")
            raise SystemExit(1) from exc

    prompt_file = adj_dir / "prompts" / "review.md"
    run_cron_prompt(prompt_file, adj_dir=adj_dir, action="review", source=source)


def brief_cron(adj_dir: Path | None = None, *, source: str = "cron") -> None:
    """Cron entry point for the proactive morning brief.

    Reads prompts/morning_brief.md, runs the backend, and sends
    a Telegram notification with the daily brief.
    """
    if adj_dir is None:
        try:
            adj_dir = init_adj_dir()
        except AdjutantDirNotFoundError as exc:
            sys.stderr.write(f"ERROR: {exc}\n")
            raise SystemExit(1) from exc

    prompt_file = adj_dir / "prompts" / "morning_brief.md"
    run_cron_prompt(prompt_file, adj_dir=adj_dir, action="brief", source=source)


def self_assess_cron(adj_dir: Path | None = None, *, source: str = "cron") -> None:
    """Cron entry point for the weekly self-assessment.

    Reads prompts/self_assess.md, runs the backend, and writes
    proposed changes to insights/pending/ for user review.
    """
    if adj_dir is None:
        try:
            adj_dir = init_adj_dir()
        except AdjutantDirNotFoundError as exc:
            sys.stderr.write(f"ERROR: {exc}\n")
            raise SystemExit(1) from exc

    prompt_file = adj_dir / "prompts" / "self_assess.md"
    run_cron_prompt(prompt_file, adj_dir=adj_dir, action="self-assess", source=source)
