"""Backend-agnostic command dispatcher.

Replaces: scripts/messaging/dispatch.sh

Routes incoming text messages and photos to command handlers or natural language chat.
Handles rate limiting and in-flight job cancellation.

Rate limiting:
  - Rolling 60-second window stored in adj_dir/state/rate_limit_window
  - Max 10 messages per minute (configurable via ADJUTANT_RATE_LIMIT_MAX env var)

In-flight job tracking:
  - Only one chat Task runs at a time per conversation
  - A newer message cancels the previous in-flight task
"""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path

from adjutant.core.logging import adj_log


# In-flight chat tasks: message_id -> asyncio.Task
_INFLIGHT: dict[str, asyncio.Task[None]] = {}

_RATE_LIMIT_WINDOW = 60  # seconds
_PENDING_REFLECT_FILE_NAME = "pending_reflect"


def _rate_limit_max() -> int:
    try:
        return int(os.environ.get("ADJUTANT_RATE_LIMIT_MAX", "10"))
    except ValueError:
        return 10


def _check_rate_limit(adj_dir: Path) -> bool:
    """Append timestamp, prune old entries, return True if within limit.

    Returns:
        True if the message should be allowed, False if rate limit exceeded.
    """
    state_dir = adj_dir / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    rate_file = state_dir / "rate_limit_window"

    now = int(time.time())
    cutoff = now - _RATE_LIMIT_WINDOW
    max_msgs = _rate_limit_max()

    # Read existing timestamps
    timestamps: list[int] = []
    if rate_file.is_file():
        try:
            for line in rate_file.read_text().splitlines():
                line = line.strip()
                if line.isdigit():
                    ts = int(line)
                    if ts > cutoff:
                        timestamps.append(ts)
        except OSError:
            pass

    # Append current timestamp
    timestamps.append(now)

    # Rewrite pruned window
    try:
        rate_file.write_text("\n".join(str(t) for t in timestamps) + "\n")
    except OSError:
        pass

    count = len(timestamps)
    if count > max_msgs:
        adj_log(
            "messaging",
            f"Rate limit exceeded: {count} messages in last {_RATE_LIMIT_WINDOW}s "
            f"(max {max_msgs}). Dropping message.",
        )
        return False

    return True


def _cancel_inflight(current_msg_id: str) -> None:
    """Cancel any in-flight chat task that is not the current message."""
    to_cancel = [mid for mid in list(_INFLIGHT) if mid != current_msg_id]
    for mid in to_cancel:
        task = _INFLIGHT.pop(mid, None)
        if task and not task.done():
            task.cancel()
            adj_log(
                "messaging",
                f"Cancelled in-flight job for msg={mid} (superseded by msg={current_msg_id})",
            )


async def dispatch_message(
    text: str,
    message_id: int,
    from_id: str,
    adj_dir: Path,
    *,
    bot_token: str,
    chat_id: str,
) -> None:
    """Route a text message to the appropriate handler.

    Args:
        text: The message text.
        message_id: Telegram message ID.
        from_id: Sender's user/chat ID (used for auth).
        adj_dir: Adjutant root directory.
        bot_token: Telegram bot token.
        chat_id: Authorized chat ID.
    """
    from adjutant.messaging.telegram.commands import (
        cmd_help,
        cmd_kb,
        cmd_kill,
        cmd_model,
        cmd_pause,
        cmd_pulse,
        cmd_reflect_confirm,
        cmd_reflect_request,
        cmd_restart,
        cmd_resume,
        cmd_schedule,
        cmd_screenshot,
        cmd_search,
        cmd_status,
    )
    from adjutant.messaging.telegram.send import (
        msg_react,
        msg_send_text,
        msg_typing_start,
        msg_typing_stop,
    )

    def _send(msg: str) -> None:
        msg_send_text(msg, message_id, bot_token=bot_token, chat_id=chat_id)

    # Authorization: only accept messages from the configured chat_id
    if str(from_id) != str(chat_id):
        adj_log("messaging", f"Rejected unauthorized sender: {from_id}")
        return

    # Rate limit
    if not _check_rate_limit(adj_dir):
        _send("I'm receiving messages too quickly. Please wait a moment before sending another.")
        return

    adj_log("messaging", f"Received msg={message_id}: {text}")

    # Pending reflect confirmation flow
    pending_reflect = adj_dir / "state" / _PENDING_REFLECT_FILE_NAME
    if pending_reflect.is_file():
        if text == "/confirm":
            await cmd_reflect_confirm(message_id, adj_dir, bot_token=bot_token, chat_id=chat_id)
        else:
            try:
                pending_reflect.unlink(missing_ok=True)
            except OSError:
                pass
            _send("No problem — I've cancelled the reflection.")
            adj_log("messaging", "Reflect cancelled.")
        return

    # Command dispatch
    if text == "/status":
        await cmd_status(message_id, adj_dir, bot_token=bot_token, chat_id=chat_id)
    elif text == "/pause":
        await cmd_pause(message_id, adj_dir, bot_token=bot_token, chat_id=chat_id)
    elif text == "/resume":
        await cmd_resume(message_id, adj_dir, bot_token=bot_token, chat_id=chat_id)
    elif text == "/kill":
        await cmd_kill(message_id, adj_dir, bot_token=bot_token, chat_id=chat_id)
    elif text == "/pulse":
        await cmd_pulse(message_id, adj_dir, bot_token=bot_token, chat_id=chat_id)
    elif text == "/restart":
        await cmd_restart(message_id, adj_dir, bot_token=bot_token, chat_id=chat_id)
    elif text == "/reflect":
        await cmd_reflect_request(message_id, adj_dir, bot_token=bot_token, chat_id=chat_id)
    elif text in ("/help", "/start"):
        await cmd_help(message_id, adj_dir, bot_token=bot_token, chat_id=chat_id)
    elif text == "/model":
        await cmd_model("", message_id, adj_dir, bot_token=bot_token, chat_id=chat_id)
    elif text.startswith("/model "):
        await cmd_model(
            text[len("/model ") :], message_id, adj_dir, bot_token=bot_token, chat_id=chat_id
        )
    elif text.startswith("/screenshot "):
        await cmd_screenshot(
            text[len("/screenshot ") :], message_id, adj_dir, bot_token=bot_token, chat_id=chat_id
        )
    elif text == "/screenshot":
        _send("Please provide a URL. Example: /screenshot https://example.com")
    elif text.startswith("/search "):
        await cmd_search(
            text[len("/search ") :], message_id, adj_dir, bot_token=bot_token, chat_id=chat_id
        )
    elif text == "/search":
        _send("Please provide a search query. Example: /search latest AI news")
    elif text == "/kb":
        await cmd_kb("list", message_id, adj_dir, bot_token=bot_token, chat_id=chat_id)
    elif text.startswith("/kb "):
        await cmd_kb(text[len("/kb ") :], message_id, adj_dir, bot_token=bot_token, chat_id=chat_id)
    elif text == "/schedule":
        await cmd_schedule("list", message_id, adj_dir, bot_token=bot_token, chat_id=chat_id)
    elif text.startswith("/schedule "):
        await cmd_schedule(
            text[len("/schedule ") :], message_id, adj_dir, bot_token=bot_token, chat_id=chat_id
        )
    else:
        # Natural language chat
        adj_log("messaging", f"Chat msg={message_id}: {text}")
        msg_id_str = str(message_id)

        _cancel_inflight(msg_id_str)
        msg_react(message_id, bot_token=bot_token, chat_id=chat_id)

        async def _chat_task() -> None:
            from adjutant.messaging.telegram.chat import run_chat

            typing_key = f"chat_{message_id}"
            msg_typing_start(typing_key, bot_token=bot_token, chat_id=chat_id)
            try:
                reply = await run_chat(text, adj_dir)
                if reply:
                    msg_send_text(reply, message_id, bot_token=bot_token, chat_id=chat_id)
                    adj_log("messaging", f"Reply sent for msg={message_id}")
                else:
                    msg_send_text(
                        "I ran into a problem getting a response. Try again in a moment.",
                        message_id,
                        bot_token=bot_token,
                        chat_id=chat_id,
                    )
                    adj_log("messaging", f"Fallback reply sent for msg={message_id}")
            except asyncio.CancelledError:
                adj_log("messaging", f"Chat task for msg={message_id} was cancelled")
                raise
            finally:
                msg_typing_stop(typing_key)
                _INFLIGHT.pop(msg_id_str, None)

        task = asyncio.create_task(_chat_task())
        _INFLIGHT[msg_id_str] = task


async def dispatch_photo(
    from_id: str,
    message_id: int,
    file_ref: str,
    adj_dir: Path,
    *,
    bot_token: str,
    chat_id: str,
    caption: str = "",
) -> None:
    """Route a photo message to the Telegram photo handler.

    Args:
        from_id: Sender's user/chat ID (used for auth).
        message_id: Telegram message ID.
        file_ref: Telegram file_id for the photo.
        adj_dir: Adjutant root directory.
        bot_token: Telegram bot token.
        chat_id: Authorized chat ID.
        caption: Optional caption accompanying the photo.
    """
    from adjutant.messaging.telegram.photos import tg_handle_photo
    from adjutant.messaging.telegram.send import msg_send_text

    # Authorization
    if str(from_id) != str(chat_id):
        adj_log("messaging", f"Rejected photo from unauthorized sender: {from_id}")
        return

    await tg_handle_photo(
        from_id,
        message_id,
        file_ref,
        caption,
        bot_token=bot_token,
        chat_id=chat_id,
        adj_dir=adj_dir,
    )
