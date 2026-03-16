"""Step 2: Installation path selection.

Replaces: scripts/setup/steps/install_path.sh

Confirms or selects the installation directory. For an existing install, shows
the current path and returns. For a fresh install, prompts the user for a path
and creates the directory structure.

Returns a Path object on success, None on cancellation/failure.
"""

from __future__ import annotations

import sys
from pathlib import Path

from adjutant.setup.wizard import (
    expand_path,
    wiz_confirm,
    wiz_fail,
    wiz_input,
    wiz_ok,
    wiz_step,
)

# Directories to create under the installation root
_BASE_DIRS = [
    "state",
    "journal",
    "identity",
    "prompts",
    "photos",
    "screenshots",
    "scripts",
    "docs",
]


def step_install_path(
    adj_dir: Path | None = None,
    *,
    dry_run: bool = False,
) -> Path | None:
    """Run Step 2: Installation path.

    Args:
        adj_dir: Existing ADJ_DIR if known (e.g. from environment or prior detection).
        dry_run: Simulation mode — print what would be done without writing anything.

    Returns:
        Path to the chosen (and possibly created) installation directory,
        or None if the user cancelled.
    """
    wiz_step(2, 7, "Installation Path")
    print("", file=sys.stderr)

    # Existing install detected
    if adj_dir is not None and adj_dir.is_dir() and (adj_dir / "adjutant.yaml").is_file():
        wiz_ok(f"Existing installation found at: {adj_dir}")
        return adj_dir

    # Fresh install — default to cwd
    default_path = str(Path.cwd())
    raw = wiz_input("Installation path", default_path)
    chosen_path = Path(expand_path(raw))

    # Already an install at the chosen path?
    if (chosen_path / "adjutant.yaml").is_file():
        wiz_ok(f"Found existing installation at: {chosen_path}")
        return chosen_path

    # Create directory if it doesn't exist
    if not chosen_path.is_dir():
        if not wiz_confirm(f"Directory doesn't exist. Create {chosen_path}?", "Y"):
            wiz_fail("Installation cancelled — no directory created")
            return None
        if dry_run:
            wiz_ok(f"[DRY RUN] Would create {chosen_path}")
        else:
            try:
                chosen_path.mkdir(parents=True, exist_ok=True)
                wiz_ok(f"Created {chosen_path}")
            except OSError as exc:
                wiz_fail(f"Could not create {chosen_path}: {exc}")
                return None

    # Create base directory structure
    for d in _BASE_DIRS:
        target = chosen_path / d
        if dry_run:
            pass  # silent in dry-run; summary below
        else:
            target.mkdir(parents=True, exist_ok=True)

    if dry_run:
        wiz_ok("[DRY RUN] Would create directory structure")
    else:
        wiz_ok("Created directory structure")

    return chosen_path
