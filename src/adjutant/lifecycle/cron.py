"""Cron job wrappers — pulse and review autonomous runs.

Replaces bash scripts:
  - scripts/lifecycle/pulse_cron.sh
  - scripts/lifecycle/review_cron.sh

Both are thin wrappers called by crontab. They read a prompt file and
exec opencode to run it.  The Python equivalents use os.execvp so the
opencode process replaces the current process (same semantics as bash exec).
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from adjutant.core.paths import get_adj_dir, init_adj_dir, AdjutantDirNotFoundError


def _find_opencode() -> str:
    """Return path to the opencode binary or raise SystemExit."""
    path = shutil.which("opencode")
    if path is None:
        sys.stderr.write("ERROR: opencode not found on PATH\n")
        raise SystemExit(1)
    return path


def run_cron_prompt(prompt_file: Path, *, adj_dir: Path | None = None) -> None:
    """Read a prompt file and exec opencode to run it.

    Replaces the shared pattern in pulse_cron.sh / review_cron.sh:
        exec opencode run --dir "$ADJ_DIR" "$(cat "$PROMPT")"

    Args:
        prompt_file: Absolute path to the prompt markdown file.
        adj_dir: Adjutant root directory.  Defaults to $ADJ_DIR.

    Raises:
        SystemExit: On any error (missing prompt, missing opencode, etc.)
    """
    if adj_dir is None:
        adj_dir_env = os.environ.get("ADJ_DIR", "").strip()
        if not adj_dir_env:
            sys.stderr.write("ERROR: ADJ_DIR not set\n")
            raise SystemExit(1)
        adj_dir = Path(adj_dir_env)

    if not prompt_file.is_file():
        sys.stderr.write(f"ERROR: Prompt file not found at {prompt_file}\n")
        raise SystemExit(1)

    prompt_text = prompt_file.read_text()
    opencode = _find_opencode()

    # exec — replaces this process (matches bash `exec opencode run ...`)
    os.execvp(opencode, [opencode, "run", "--dir", str(adj_dir), prompt_text])


def pulse_cron(adj_dir: Path | None = None) -> None:
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
    run_cron_prompt(prompt_file, adj_dir=adj_dir)


def review_cron(adj_dir: Path | None = None) -> None:
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
    run_cron_prompt(prompt_file, adj_dir=adj_dir)
