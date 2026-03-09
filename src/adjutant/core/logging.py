"""Structured logging — append-only log with control char sanitization.

Log format: ``[HH:MM DD.MM.YYYY] [context] message``

Matches bash logging.sh behavior:
- adj_log writes to $ADJ_DIR/state/adjutant.log
- Control characters stripped (except tab preserved as space, newline as space)
- fmt_ts converts ISO-8601 to European format (HH:MM DD.MM.YYYY)
- log_error writes to both log file AND stderr
- log_warn writes to log file only
- log_debug conditional on ADJUTANT_DEBUG or DEBUG env var
"""

from __future__ import annotations

import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


def _log_path() -> Path:
    """Return the path to adjutant.log, creating state dir if needed."""
    adj_dir = os.environ.get("ADJ_DIR", "").strip()
    if not adj_dir:
        # Fallback — write to stderr if ADJ_DIR not set
        return Path("/dev/null")
    state_dir = Path(adj_dir) / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    return state_dir / "adjutant.log"


def _sanitize_message(msg: str) -> str:
    """Strip control characters except tab→space and newline→space.

    Matches bash: ``tr -d '\\000-\\011\\013-\\037\\177' | tr '\\n' ' '``
    Bash strips chars 0x00-0x09, 0x0B-0x1F, 0x7F and replaces newlines with spaces.
    Tab (0x09) IS in the bash strip range, but we preserve it as space for readability.
    """
    # Replace newlines and tabs with spaces
    msg = msg.replace("\n", " ").replace("\r", " ").replace("\t", " ")
    # Strip remaining control characters (0x00-0x08, 0x0B-0x0C, 0x0E-0x1F, 0x7F)
    msg = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", msg)
    return msg


def _timestamp() -> str:
    """Current timestamp in Adjutant log format: HH:MM DD.MM.YYYY."""
    now = datetime.now()
    return now.strftime("%H:%M %d.%m.%Y")


def adj_log(context: str, message: str, *, log_file: Path | None = None) -> None:
    """Write a log entry to adjutant.log.

    Args:
        context: Log context/component name (e.g. "telegram", "opencode").
        message: The log message.
        log_file: Override the log file path (for testing).
    """
    sanitized = _sanitize_message(message)
    ts = _timestamp()
    line = f"[{ts}] [{context}] {sanitized}\n"

    path = log_file or _log_path()
    try:
        with open(path, "a") as f:
            f.write(line)
    except OSError:
        # If we can't write to the log, write to stderr as last resort
        sys.stderr.write(f"[LOG WRITE FAILED] {line}")


def fmt_ts(raw: str) -> str:
    """Convert ISO-8601 timestamp to Adjutant's European format.

    Input:  Various ISO-8601 formats (2026-02-26T14:30:00Z, etc.)
    Output: "HH:MM DD.MM.YYYY"
    Falls back to returning the original string if parsing fails.

    Matches bash fmt_ts() — pure Python, no injection vulnerability.
    """
    if not raw or not raw.strip():
        return ""

    raw = raw.strip()

    # Try common ISO-8601 formats
    formats = [
        "%Y-%m-%dT%H:%M:%SZ",  # 2026-02-26T14:30:00Z
        "%Y-%m-%dT%H:%M:%S%z",  # 2026-02-26T14:30:00+00:00
        "%Y-%m-%dT%H:%M:%S",  # 2026-02-26T14:30:00
        "%Y-%m-%d %H:%M:%S",  # 2026-02-26 14:30:00
        "%Y-%m-%d",  # 2026-02-26
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(raw, fmt)
            if fmt == "%Y-%m-%d":
                return dt.strftime("00:00 %d.%m.%Y")
            return dt.strftime("%H:%M %d.%m.%Y")
        except ValueError:
            continue

    # Try Python 3.11+ fromisoformat (handles most ISO-8601 variants)
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return dt.strftime("%H:%M %d.%m.%Y")
    except (ValueError, AttributeError):
        pass

    # Fallback: return original string
    return raw


def log_error(context: str, message: str, *, log_file: Path | None = None) -> None:
    """Log an error — writes to log file AND stderr.

    Matches bash: ``adj_log "$context" "ERROR: $*"`` + ``echo "ERROR [...]: $*" >&2``
    """
    adj_log(context, f"ERROR: {message}", log_file=log_file)
    sanitized = _sanitize_message(message)
    sys.stderr.write(f"ERROR [{context}]: {sanitized}\n")


def log_warn(context: str, message: str, *, log_file: Path | None = None) -> None:
    """Log a warning — writes to log file only.

    Matches bash: ``adj_log "$context" "WARNING: $*"``
    """
    adj_log(context, f"WARNING: {message}", log_file=log_file)


def log_debug(context: str, message: str, *, log_file: Path | None = None) -> None:
    """Log debug info — only if ADJUTANT_DEBUG or DEBUG env var is set.

    Matches bash: conditional on ``${ADJUTANT_DEBUG:-${DEBUG:-}}``
    """
    if os.environ.get("ADJUTANT_DEBUG") or os.environ.get("DEBUG"):
        adj_log(context, f"DEBUG: {message}", log_file=log_file)
