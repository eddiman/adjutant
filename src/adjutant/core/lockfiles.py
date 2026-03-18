"""KILLED/PAUSED state management via lockfiles and active operation tracking.

Two lockfile types:
  - KILLED: Hard stop — system is shut down. Created by emergency_kill.
  - PAUSED: Soft stop — system is temporarily paused. Created by pause command.

Stored as $ADJ_DIR/KILLED and $ADJ_DIR/PAUSED (empty files).

Active operation tracking:
  - state/active_operation.json — written when a pulse/review starts, removed when done.
  - Allows any client (Mariposa, Telegram, CLI) to observe running state.

Matches bash lockfiles.sh behavior exactly:
  - check_* functions emit stderr messages and return False if locked
  - is_* functions are silent boolean queries
  - check_operational checks killed BEFORE paused (order matters)
"""

from __future__ import annotations

import contextlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


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


# --- Active operation tracking ---

_STALE_SECONDS = 1800  # 30 minutes


def _pid_alive(pid: int) -> bool:
    """Check if a process with the given PID exists."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        # EPERM — process exists but we can't signal it
        return True
    return True


def get_active_operation(adj_dir: Path | None = None) -> dict[str, Any] | None:
    """Read state/active_operation.json if it exists and is not stale.

    Returns the parsed dict, or None if no operation is running.
    A marker is considered stale if started_at is older than 30 minutes
    AND the recorded PID is no longer alive.  Stale markers are removed.
    """
    d = adj_dir or _adj_dir()
    op_file = d / "state" / "active_operation.json"
    if not op_file.is_file():
        return None

    try:
        data = json.loads(op_file.read_text())
    except (json.JSONDecodeError, OSError):
        return None

    # Staleness check
    raw_ts = data.get("started_at", "")
    try:
        started = datetime.fromisoformat(raw_ts)
        if started.tzinfo is None:
            started = started.replace(tzinfo=UTC)
        age = (datetime.now(UTC) - started).total_seconds()
    except (ValueError, TypeError):
        age = _STALE_SECONDS + 1  # unparseable timestamp → treat as stale

    if age > _STALE_SECONDS:
        pid = data.get("pid")
        if not pid or not _pid_alive(int(pid)):
            with contextlib.suppress(FileNotFoundError):
                op_file.unlink()
            return None

    return data


def set_active_operation(
    action: str,
    source: str,
    adj_dir: Path | None = None,
) -> None:
    """Write state/active_operation.json to mark an operation as in-progress.

    Args:
        action: The operation type (e.g. "pulse", "review").
        source: Where the trigger came from ("cron", "telegram", "mariposa").
        adj_dir: Adjutant root directory.
    """
    d = adj_dir or _adj_dir()
    op_file = d / "state" / "active_operation.json"
    op_file.parent.mkdir(parents=True, exist_ok=True)
    op_file.write_text(
        json.dumps(
            {
                "action": action,
                "started_at": datetime.now(UTC).isoformat(),
                "pid": os.getpid(),
                "source": source,
            },
        ),
    )


def clear_active_operation(adj_dir: Path | None = None) -> None:
    """Remove state/active_operation.json if it exists."""
    d = adj_dir or _adj_dir()
    with contextlib.suppress(FileNotFoundError):
        (d / "state" / "active_operation.json").unlink()
