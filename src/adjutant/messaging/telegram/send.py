"""Telegram-specific send operations.

Replaces: scripts/messaging/telegram/send.sh

Provides low-level Telegram API primitives:
  msg_send_text  — sanitise + POST sendMessage
  msg_send_photo — multipart POST sendPhoto
  msg_react      — fire-and-forget setMessageReaction
  msg_typing_start / msg_typing_stop — background typing indicator loop
  msg_authorize  — sender authorisation
"""

from __future__ import annotations

import re
import threading
import time
from pathlib import Path
from typing import Any

from adjutant.core.logging import adj_log
from adjutant.lib.http import get_client

# Telegram maximum message length (matches reply.py)
_TELEGRAM_MAX_LEN = 4000

# Active typing threads: suffix → (Thread, stop_event)
_TYPING_THREADS: dict[str, tuple[threading.Thread, threading.Event]] = {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sanitize(msg: str) -> str:
    """Strip control characters and clamp to 4000 chars.

    Matches bash: tr -d '\\000-\\010\\013-\\037\\177' | cut -c1-4000
    Strips 0x00-0x08, 0x0B-0x1F, 0x7F. Newlines (0x0A) and tabs (0x09) kept.
    """
    msg = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", msg)
    return msg[:_TELEGRAM_MAX_LEN]


def _tg_url(bot_token: str, method: str) -> str:
    return f"https://api.telegram.org/bot{bot_token}/{method}"


# ---------------------------------------------------------------------------
# Send text
# ---------------------------------------------------------------------------


def msg_send_text(
    message: str,
    reply_to: int | None = None,
    *,
    bot_token: str,
    chat_id: str,
) -> None:
    """Send a Telegram text message with Markdown parse mode.

    Args:
        message: The text to send. Sanitised and clamped to 4000 chars.
        reply_to: Optional message ID to reply to.
        bot_token: Telegram bot token.
        chat_id: Target chat ID.
    """
    sanitized = _sanitize(message)
    if not sanitized:
        adj_log("telegram", "msg_send_text: empty message after sanitisation, skipping")
        return

    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "text": sanitized,
        "parse_mode": "Markdown",
    }
    if reply_to is not None:
        payload["reply_to_message_id"] = reply_to

    client = get_client()
    url = _tg_url(bot_token, "sendMessage")
    try:
        client.post(url, json_data=payload)
    except Exception as exc:
        # Telegram rejects messages with malformed Markdown (HTTP 400 parse
        # entity errors).  Retry without parse_mode so the message always
        # reaches the user, even if formatting is lost.
        err = str(exc)
        if "400" in err and "parse" in err.lower():
            adj_log("telegram", "msg_send_text: Markdown parse error, retrying as plain text")
            plain_payload = {k: v for k, v in payload.items() if k != "parse_mode"}
            try:
                client.post(url, json_data=plain_payload)
                return
            except Exception as exc2:
                adj_log("telegram", f"msg_send_text plain retry failed: {exc2}")
        adj_log("telegram", f"msg_send_text failed: {exc}")


# ---------------------------------------------------------------------------
# Send photo
# ---------------------------------------------------------------------------


def msg_send_photo(
    filepath: Path,
    caption: str = "",
    *,
    bot_token: str,
    chat_id: str,
) -> None:
    """Send a photo via Telegram sendPhoto (multipart).

    Args:
        filepath: Path to the image file.
        caption: Optional caption text.
        bot_token: Telegram bot token.
        chat_id: Target chat ID.
    """
    if not filepath.is_file():
        adj_log("telegram", f"msg_send_photo: file not found: {filepath}")
        return

    import httpx

    url = _tg_url(bot_token, "sendPhoto")
    try:
        with filepath.open("rb") as f:
            files = {"photo": (filepath.name, f, "application/octet-stream")}
            data: dict[str, str] = {"chat_id": chat_id}
            if caption:
                data["caption"] = caption
            with httpx.Client(timeout=60.0) as client:
                response = client.post(url, data=data, files=files)
                response.raise_for_status()
    except Exception as exc:
        adj_log("telegram", f"msg_send_photo failed: {exc}")


# ---------------------------------------------------------------------------
# React
# ---------------------------------------------------------------------------


def msg_react(
    message_id: int,
    emoji: str = "👀",
    *,
    bot_token: str,
    chat_id: str,
) -> None:
    """Add a reaction emoji to a message. Fire-and-forget in a background thread.

    Args:
        message_id: The message to react to.
        emoji: The emoji to use.
        bot_token: Telegram bot token.
        chat_id: Target chat ID.
    """
    if not message_id:
        return

    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "reaction": [{"type": "emoji", "emoji": emoji}],
    }
    url = _tg_url(bot_token, "setMessageReaction")

    def _fire() -> None:
        try:
            client = get_client()
            client.post(url, json_data=payload)
        except Exception as exc:
            adj_log("telegram", f"msg_react failed: {exc}")

    t = threading.Thread(target=_fire, daemon=True)
    t.start()


# ---------------------------------------------------------------------------
# Typing indicator
# ---------------------------------------------------------------------------


_TYPING_MAX_DURATION = 300  # seconds — hard ceiling to prevent infinite typing loops


def msg_typing_start(
    suffix: str, bot_token: str, chat_id: str, *, max_duration: float = _TYPING_MAX_DURATION
) -> None:
    """Start a looping typing indicator for the given suffix.

    Sends 'typing' chatAction every 4 seconds until msg_typing_stop() is called
    or max_duration seconds have elapsed (whichever comes first).

    Args:
        suffix: Unique key to identify this typing indicator (e.g. 'chat_42').
        bot_token: Telegram bot token.
        chat_id: Target chat ID.
        max_duration: Safety ceiling in seconds. The loop auto-stops after this
            even if msg_typing_stop() is never called. Defaults to 300s.
    """
    msg_typing_stop(suffix)  # stop any existing one for this suffix

    stop_event = threading.Event()
    url = _tg_url(bot_token, "sendChatAction")
    payload: dict[str, Any] = {"chat_id": chat_id, "action": "typing"}

    def _loop() -> None:
        deadline = time.monotonic() + max_duration
        while not stop_event.is_set():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                adj_log(
                    "telegram",
                    f"Typing indicator '{suffix}' auto-stopped after {max_duration}s ceiling",
                )
                break
            try:
                client = get_client()
                client.post(url, json_data=payload)
            except Exception:
                pass
            stop_event.wait(min(4.0, remaining))

    t = threading.Thread(target=_loop, daemon=True, name=f"typing-{suffix}")
    _TYPING_THREADS[suffix] = (t, stop_event)
    t.start()


def msg_typing_stop(suffix: str) -> None:
    """Stop the typing indicator for the given suffix.

    Args:
        suffix: The same key passed to msg_typing_start().
    """
    entry = _TYPING_THREADS.pop(suffix, None)
    if entry is not None:
        _thread, stop_event = entry
        stop_event.set()


# ---------------------------------------------------------------------------
# Authorisation
# ---------------------------------------------------------------------------


def msg_authorize(from_id: str, chat_id: str) -> bool:
    """Return True if the sender is the authorised chat.

    Matches bash: [ "$from_id" = "$TELEGRAM_CHAT_ID" ]
    """
    return str(from_id) == str(chat_id)


# ---------------------------------------------------------------------------
# TelegramSender — adaptor partial implementation
# ---------------------------------------------------------------------------


class TelegramSender:
    """Wraps the Telegram send functions with bound bot_token and chat_id.

    Partially implements MessagingAdaptor (send methods only — not listener).
    """

    def __init__(self, bot_token: str, chat_id: str) -> None:
        self.bot_token = bot_token
        self.chat_id = chat_id

    async def send_text(self, message: str, reply_to_message_id: int | None = None) -> None:
        """Async wrapper for msg_send_text."""
        import asyncio

        await asyncio.to_thread(
            msg_send_text,
            message,
            reply_to_message_id,
            bot_token=self.bot_token,
            chat_id=self.chat_id,
        )

    async def send_photo(self, file_path: Path, caption: str = "") -> None:
        """Async wrapper for msg_send_photo."""
        import asyncio

        await asyncio.to_thread(
            msg_send_photo,
            file_path,
            caption,
            bot_token=self.bot_token,
            chat_id=self.chat_id,
        )

    async def react(self, message_id: int, emoji: str = "👀") -> None:
        """Async wrapper for msg_react (fire-and-forget)."""
        msg_react(message_id, emoji, bot_token=self.bot_token, chat_id=self.chat_id)

    async def typing(self, action: str, suffix: str = "default") -> None:
        """Start or stop typing indicator."""
        if action == "start":
            msg_typing_start(suffix, self.bot_token, self.chat_id)
        elif action == "stop":
            msg_typing_stop(suffix)

    def authorize(self, from_id: str) -> bool:
        """Return True if from_id matches this sender's chat_id."""
        return msg_authorize(from_id, self.chat_id)

    def get_user_id(self) -> str:
        return self.chat_id
