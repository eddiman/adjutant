"""Natural conversation via opencode — session management and chat routing.

Replaces: scripts/messaging/telegram/chat.sh

Session continuity:
  - Session ID stored in adj_dir/state/telegram_session.json
  - Sessions reused within SESSION_TIMEOUT (7200s = 2 hours)
  - After timeout, a fresh session is started
"""

from __future__ import annotations

import contextlib
import json
import time
from datetime import datetime
from typing import TYPE_CHECKING

from adjutant.core.logging import adj_log

if TYPE_CHECKING:
    from pathlib import Path

_DEFAULT_SESSION_TIMEOUT = 7200  # seconds (2 hours)
_DEFAULT_CHAT_TIMEOUT = 240  # seconds
_SESSION_FILE_NAME = "telegram_session.json"


def _get_config_timeouts(adj_dir: Path) -> tuple[int, int]:
    """Read session and chat timeouts from adjutant.yaml.

    Returns:
        (session_timeout, chat_timeout) tuple with defaults as fallback.
    """
    try:
        from adjutant.core.config import load_typed_config

        config = load_typed_config(adj_dir / "adjutant.yaml")
        return (
            config.messaging.telegram.session_timeout_seconds,
            config.messaging.telegram.chat_timeout_seconds,
        )
    except Exception:  # noqa: BLE001 — fallback to defaults
        return _DEFAULT_SESSION_TIMEOUT, _DEFAULT_CHAT_TIMEOUT


# Module-level aliases for backwards compatibility
SESSION_TIMEOUT = _DEFAULT_SESSION_TIMEOUT
_CHAT_TIMEOUT = _DEFAULT_CHAT_TIMEOUT


# ---------------------------------------------------------------------------
# Model resolution
# ---------------------------------------------------------------------------


def get_model(adj_dir: Path) -> str:
    """Get the current chat model.

    Reads adj_dir/state/telegram_model.txt; fallback: anthropic/claude-haiku-4-5.
    """
    model_file = adj_dir / "state" / "telegram_model.txt"
    if model_file.is_file():
        model = model_file.read_text().strip()
        if model:
            return model
    return "anthropic/claude-haiku-4-5"


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------


def get_session_id(adj_dir: Path, *, model: str | None = None) -> str | None:
    """Return the current session ID if it exists and is within timeout.

    Args:
        adj_dir: Adjutant root directory.
        model: If provided, the session is only returned when its stored model
            matches. A model mismatch (e.g. switching from Sonnet to Opus)
            invalidates the session because opencode may hang when resuming a
            session with a different model.

    Returns:
        session_id string if valid, None if expired, missing, or model-mismatched.
    """
    session_file = adj_dir / "state" / _SESSION_FILE_NAME
    if not session_file.is_file():
        return None

    try:
        data = json.loads(session_file.read_text())
    except (json.JSONDecodeError, OSError):
        return None

    session_id_raw = data.get("session_id")
    session_id: str | None = str(session_id_raw) if session_id_raw else None
    last_epoch = data.get("last_message_epoch", 0)

    if not session_id:
        return None

    # Model mismatch → stale session (opencode hangs on cross-model resume)
    if model is not None:
        stored_model = data.get("model", "")
        if stored_model and stored_model != model:
            adj_log(
                "telegram", f"Session model mismatch ({stored_model} → {model}), starting fresh"
            )
            return None

    # Truncate to int in case it was written as float by an older version
    try:
        age = int(time.time()) - int(float(last_epoch))
    except (TypeError, ValueError):
        age = _DEFAULT_SESSION_TIMEOUT + 1  # force expiry

    # Use configured timeout when adj_dir is available via the session file path
    timeout = _DEFAULT_SESSION_TIMEOUT
    if age < timeout:
        return session_id

    return None


def save_session(session_id: str, adj_dir: Path, *, model: str = "") -> None:
    """Write a new session to state/telegram_session.json."""
    session_file = adj_dir / "state" / _SESSION_FILE_NAME
    session_file.parent.mkdir(parents=True, exist_ok=True)

    now_epoch = int(time.time())
    now_human = datetime.now().strftime("%H:%M %d.%m.%Y")

    data = {
        "session_id": session_id,
        "last_message_epoch": now_epoch,
        "last_message_at": now_human,
        "model": model,
    }
    session_file.write_text(json.dumps(data))


def touch_session(adj_dir: Path) -> None:
    """Update the timestamps in an existing session file."""
    session_file = adj_dir / "state" / _SESSION_FILE_NAME
    if not session_file.is_file():
        return

    try:
        data = json.loads(session_file.read_text())
    except (json.JSONDecodeError, OSError):
        return

    now_epoch = int(time.time())
    now_human = datetime.now().strftime("%H:%M %d.%m.%Y")
    data["last_message_epoch"] = now_epoch
    data["last_message_at"] = now_human

    with contextlib.suppress(OSError):
        session_file.write_text(json.dumps(data))


# ---------------------------------------------------------------------------
# Core chat runner
# ---------------------------------------------------------------------------


async def run_chat(message: str, adj_dir: Path) -> str:
    """Send a message to opencode and return the plain-text reply.

    Manages session continuity automatically. Uses the model from
    state/telegram_model.txt (or the haiku fallback).

    Args:
        message: The user's message text.
        adj_dir: Adjutant root directory.

    Returns:
        The reply text, or an appropriate error string.
    """
    from adjutant.core.opencode import OpenCodeNotFoundError, opencode_run
    from adjutant.lib.ndjson import parse_ndjson

    model = get_model(adj_dir)
    existing_session = get_session_id(adj_dir, model=model)

    args = [
        "run",
        "--agent",
        "adjutant",
        "--dir",
        str(adj_dir),
        "--format",
        "json",
        "--model",
        model,
    ]
    if existing_session:
        args += ["--session", existing_session]
    args.append(message)

    _, chat_timeout = _get_config_timeouts(adj_dir)
    adj_log("telegram", f"Chat: model={model} session={'yes' if existing_session else 'new'}")

    try:
        result = await opencode_run(args, timeout=chat_timeout)
    except OpenCodeNotFoundError:
        return "opencode is not available. Please check your installation."

    # Handle timeout (asyncio.TimeoutError → timed_out=True, returncode=-1)
    if result.timed_out:
        adj_log("telegram", "Chat timed out after 240s")
        if model.startswith("anthropic/"):
            return (
                "Request timed out after 240s. If this keeps happening, you may have hit your "
                "Anthropic 5-hour usage limit — check usage.anthropic.com. "
                "Otherwise the server may just be slow; try again in a moment."
            )
        return "Request timed out after 240s — the AI server may be slow. Try again in a moment."

    parsed = parse_ndjson(result.stdout)

    # Check for model-not-found error
    if parsed.error_type == "model_not_found":
        return f"The model `{model}` is no longer available. Use /model to switch to a valid one."

    reply = parsed.text

    # Persist / touch session
    new_sid = parsed.session_id
    if new_sid:
        if not existing_session:
            save_session(new_sid, adj_dir, model=model)
        else:
            touch_session(adj_dir)

    if not reply:
        adj_log("telegram", "Chat returned empty reply")
        return "I didn't get a response — something may have gone wrong. Try again."

    return reply
