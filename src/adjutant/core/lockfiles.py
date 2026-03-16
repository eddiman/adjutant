"""KILLED/PAUSED state management via lockfiles.

Two lockfile types:
  - KILLED: Hard stop — system is shut down. Created by emergency_kill.
  - PAUSED: Soft stop — system is temporarily paused. Created by pause command.

Stored as $ADJ_DIR/KILLED and $ADJ_DIR/PAUSED (empty files).

Matches bash lockfiles.sh behavior exactly:
  - check_* functions emit stderr messages and return False if locked
  - is_* functions are silent boolean queries
  - check_operational checks killed BEFORE paused (order matters)
"""

from __future__ import annotations

import contextlib
import os
import sys
from pathlib import Path


def _adj_dir() -> Path:
    """Get ADJ_DIR from environment."""
    raw = os.environ.get("ADJ_DIR", "").strip()
    if not raw:
        raise RuntimeError("ADJ_DIR not set. Call init_adj_dir() first.")
    return Path(raw)


# --- Silent boolean queries (no stderr output) ---


def is_killed(adj_dir: Path | None = None) -> bool:
    """Check if KILLED lockfile exists. Silent — no stderr."""
    d = adj_dir or _adj_dir()
    return (d / "KILLED").exists()


def is_paused(adj_dir: Path | None = None) -> bool:
    """Check if PAUSED lockfile exists. Silent — no stderr."""
    d = adj_dir or _adj_dir()
    return (d / "PAUSED").exists()


def is_operational(adj_dir: Path | None = None) -> bool:
    """Check that neither KILLED nor PAUSED is set. Silent — no stderr."""
    d = adj_dir or _adj_dir()
    return not is_killed(d) and not is_paused(d)


# --- Verbose check functions (emit stderr messages, return bool) ---


def check_killed(adj_dir: Path | None = None) -> bool:
    """Check if KILLED lockfile exists. Emits stderr message if killed.

    Returns:
        True if NOT killed (operational). False if killed.
    """
    d = adj_dir or _adj_dir()
    if (d / "KILLED").exists():
        sys.stderr.write(f"KILLED lockfile exists at {d}/KILLED\n")
        sys.stderr.write("Run startup.sh to restore Adjutant.\n")
        return False
    return True


def check_paused(adj_dir: Path | None = None) -> bool:
    """Check if PAUSED lockfile exists. Emits stderr message if paused.

    Returns:
        True if NOT paused (operational). False if paused.
    """
    d = adj_dir or _adj_dir()
    if (d / "PAUSED").exists():
        sys.stderr.write(f"Adjutant is paused ({d}/PAUSED exists).\n")
        return False
    return True


def check_operational(adj_dir: Path | None = None) -> bool:
    """Check that system is neither KILLED nor PAUSED.

    Checks killed BEFORE paused (matches bash order — killed is more severe).

    Returns:
        True if operational. False if killed or paused (with stderr messages).
    """
    d = adj_dir or _adj_dir()
    if not check_killed(d):
        return False
    return check_paused(d)


# --- State mutation ---


def set_paused(adj_dir: Path | None = None) -> None:
    """Create the PAUSED lockfile."""
    d = adj_dir or _adj_dir()
    (d / "PAUSED").touch()


def set_killed(adj_dir: Path | None = None) -> None:
    """Create the KILLED lockfile."""
    d = adj_dir or _adj_dir()
    (d / "KILLED").touch()


def clear_paused(adj_dir: Path | None = None) -> None:
    """Remove the PAUSED lockfile if it exists."""
    d = adj_dir or _adj_dir()
    with contextlib.suppress(FileNotFoundError):
        (d / "PAUSED").unlink()


def clear_killed(adj_dir: Path | None = None) -> None:
    """Remove the KILLED lockfile if it exists."""
    d = adj_dir or _adj_dir()
    with contextlib.suppress(FileNotFoundError):
        (d / "KILLED").unlink()
