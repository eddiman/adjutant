"""Cron job wrappers — pulse and review autonomous runs.

Replaces bash scripts:
  - scripts/lifecycle/pulse_cron.sh
  - scripts/lifecycle/review_cron.sh

Both are thin wrappers called by crontab.  They read a prompt file,
write an active-operation marker, run opencode as a subprocess, and
clean up the marker when done.  The opencode exit code is propagated
via sys.exit so cron sees the real result.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from adjutant.core.lockfiles import clear_active_operation, set_active_operation
from adjutant.core.paths import AdjutantDirNotFoundError, get_adj_dir, init_adj_dir


def _find_opencode() -> str:
    """Return path to the opencode binary or raise SystemExit."""
    path = shutil.which("opencode")
    if path is None:
        sys.stderr.write("ERROR: opencode not found on PATH\n")
        raise SystemExit(1)
    return path


def run_cron_prompt(
    prompt_file: Path,
    *,
    adj_dir: Path | None = None,
    action: str = "unknown",
    source: str = "cron",
) -> None:
    """Read a prompt file and run opencode as a subprocess.

    Writes state/active_operation.json before starting and removes it
    when done (success or failure).  Propagates the opencode exit code
    via sys.exit so cron sees the real result.

    Args:
        prompt_file: Absolute path to the prompt markdown file.
        adj_dir: Adjutant root directory.  Defaults to $ADJ_DIR.
        action: Operation name for the active-operation marker (e.g. "pulse").
        source: Trigger source for the marker (e.g. "cron", "mariposa").

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
    opencode = _find_opencode()

    set_active_operation(action, source, adj_dir=adj_dir)
    try:
        result = subprocess.run(
            [opencode, "run", "--dir", str(adj_dir), prompt_text],
        )
        sys.exit(result.returncode)
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
