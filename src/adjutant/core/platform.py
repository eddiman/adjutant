"""OS detection and portable platform utilities.

Replaces bash platform.sh — eliminates macOS vs Linux branching for
date arithmetic, file stats, and PATH setup.

Python's stdlib handles all of these natively, so the platform detection
is mainly for compatibility checks and the rare platform-specific path.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


def detect_os() -> str:
    """Detect the operating system.

    Returns:
        "macos", "linux", or "unknown".
    """
    platform = sys.platform
    if platform == "darwin":
        return "macos"
    elif platform.startswith("linux"):
        return "linux"
    return "unknown"


# Module-level constant — matches bash ``ADJUTANT_OS``
ADJUTANT_OS: str = detect_os()


def date_subtract(amount: int, unit: str) -> str:
    """Subtract a duration from the current UTC time, return ISO-8601.

    Replaces the macOS/Linux branching in bash ``date_subtract()``.
    Python's datetime handles this portably.

    Args:
        amount: Number of units to subtract.
        unit: One of "hours", "hour", "days", "day", "minutes", "minute",
              "seconds", "second".

    Returns:
        ISO-8601 UTC string: "YYYY-MM-DDTHH:MM:SSZ"

    Raises:
        ValueError: If the unit is not recognized.
    """
    unit_map = {
        "hours": "hours",
        "hour": "hours",
        "days": "days",
        "day": "days",
        "minutes": "minutes",
        "minute": "minutes",
        "seconds": "seconds",
        "second": "seconds",
    }

    normalized = unit_map.get(unit)
    if normalized is None:
        raise ValueError(f"Unknown unit: {unit}")

    delta = timedelta(**{normalized: amount})
    result = datetime.now(timezone.utc) - delta
    return result.strftime("%Y-%m-%dT%H:%M:%SZ")


def date_subtract_epoch(amount: int, unit: str) -> int:
    """Subtract a duration from the current UTC time, return epoch seconds.

    Args:
        amount: Number of units to subtract.
        unit: Time unit (hours/days/minutes/seconds).

    Returns:
        Unix epoch seconds as integer.
    """
    unit_map = {
        "hours": "hours",
        "hour": "hours",
        "days": "days",
        "day": "days",
        "minutes": "minutes",
        "minute": "minutes",
        "seconds": "seconds",
        "second": "seconds",
    }

    normalized = unit_map.get(unit)
    if normalized is None:
        raise ValueError(f"Unknown unit: {unit}")

    delta = timedelta(**{normalized: amount})
    result = datetime.now(timezone.utc) - delta
    return int(result.timestamp())


def file_mtime(filepath: Path) -> tuple[int, bool]:
    """Get file modification time in epoch seconds.

    Returns:
        Tuple of (epoch_seconds, success). Returns (0, False) if file doesn't exist.
        Matches bash: returns "0" + exit 1 on missing file.
    """
    try:
        return int(filepath.stat().st_mtime), True
    except (OSError, FileNotFoundError):
        return 0, False


def file_size(filepath: Path) -> tuple[int, bool]:
    """Get file size in bytes.

    Returns:
        Tuple of (bytes, success). Returns (0, False) if file doesn't exist.
        Matches bash: returns "0" + exit 1 on missing file.

    Bug fix over bash: Uses Path.stat() — no platform-specific stat flags needed.
    """
    try:
        return filepath.stat().st_size, True
    except (OSError, FileNotFoundError):
        return 0, False


def ensure_path() -> None:
    """Ensure common tool directories are on PATH.

    Idempotently prepends /opt/homebrew/bin, /usr/local/bin, etc.
    Matches bash ``ensure_path()`` in platform.sh.
    """
    dirs = [
        "/opt/homebrew/bin",
        "/opt/homebrew/sbin",
        "/usr/local/bin",
        "/usr/bin",
        "/bin",
        "/usr/sbin",
        "/sbin",
    ]

    current_path = os.environ.get("PATH", "")
    path_entries = current_path.split(os.pathsep)

    for d in reversed(dirs):
        if os.path.isdir(d) and d not in path_entries:
            path_entries.insert(0, d)

    os.environ["PATH"] = os.pathsep.join(path_entries)
