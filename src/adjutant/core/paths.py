"""ADJ_DIR resolution — find the Adjutant root directory.

Resolution order (matches bash paths.sh):
  1. ADJUTANT_HOME env var if set (explicit override)
  2. Walk up from caller/cwd to find .adjutant-root marker
  3. Walk up from caller/cwd to find adjutant.yaml (legacy fallback)
  4. Fall back to ~/.adjutant

Exports both ADJ_DIR and ADJUTANT_DIR (legacy alias) into os.environ.
"""

from __future__ import annotations

import os
from pathlib import Path


class AdjutantDirNotFoundError(Exception):
    """Raised when the Adjutant directory cannot be found."""


def _walk_up_for(start: Path, marker: str) -> Path | None:
    """Walk up the directory tree from `start` looking for `marker`."""
    current = start.resolve()
    while True:
        candidate = current / marker
        if candidate.exists():
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None


def resolve_adj_dir(start_dir: Path | None = None) -> Path:
    """Resolve the Adjutant root directory.

    Args:
        start_dir: Directory to start walk-up from. Defaults to cwd.

    Returns:
        Resolved Path to the Adjutant root directory.

    Raises:
        AdjutantDirNotFoundError: If the resolved directory does not exist.
    """
    # 1. Explicit environment override
    env_home = os.environ.get("ADJUTANT_HOME", "").strip()
    if env_home:
        adj_dir = Path(env_home)
        if not adj_dir.is_dir():
            raise AdjutantDirNotFoundError(
                f"ADJUTANT_HOME points to non-existent directory: {adj_dir}\n"
                "Set ADJUTANT_HOME to a valid directory, or ensure .adjutant-root "
                "exists in the project root."
            )
        return adj_dir

    origin = start_dir or Path.cwd()

    # 2. Walk up for .adjutant-root marker
    found = _walk_up_for(origin, ".adjutant-root")
    if found is not None:
        return found

    # 3. Walk up for adjutant.yaml (legacy)
    found = _walk_up_for(origin, "adjutant.yaml")
    if found is not None:
        return found

    # 4. Legacy fallback: ~/.adjutant
    fallback = Path.home() / ".adjutant"
    if fallback.is_dir():
        return fallback

    raise AdjutantDirNotFoundError(
        f"Adjutant directory not found (searched from {origin}).\n"
        "Set ADJUTANT_HOME, or ensure .adjutant-root exists in the project root."
    )


def init_adj_dir(start_dir: Path | None = None) -> Path:
    """Resolve ADJ_DIR and export it to os.environ.

    This is the main entry point — call once at startup.
    Subsequent code can use ``get_adj_dir()`` to read the cached value.

    Returns:
        The resolved Adjutant root directory.
    """
    adj_dir = resolve_adj_dir(start_dir)
    os.environ["ADJ_DIR"] = str(adj_dir)
    os.environ["ADJUTANT_DIR"] = str(adj_dir)  # Legacy alias
    return adj_dir


def get_adj_dir() -> Path:
    """Return the cached ADJ_DIR from the environment.

    Must be called after ``init_adj_dir()``.

    Raises:
        AdjutantDirNotFoundError: If ADJ_DIR is not set in the environment.
    """
    raw = os.environ.get("ADJ_DIR", "").strip()
    if not raw:
        raise AdjutantDirNotFoundError(
            "ADJ_DIR not set. Call init_adj_dir() before using get_adj_dir()."
        )
    return Path(raw)
