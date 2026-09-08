"""Backend-agnostic command dispatcher.

Replaces: scripts/messaging/dispatch.sh

Routes incoming text messages and photos to command handlers or natural language chat.
Handles rate limiting and in-flight job cancellation.

Rate limiting:
  - Rolling 60-second window stored in adj_dir/state/rate_limit_window
  - Max 10 messages per minute (configurable via ADJUTANT_RATE_LIMIT_MAX env var)

In-flight turn tracking:
  - Only one conversational turn runs at a time
  - Newer text and photo turns wait for earlier turns instead of cancelling them
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import time
from typing import TYPE_CHECKING

from adjutant.core.logging import adj_log

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from pathlib import Path

# In-flight conversational turns: message_id -> asyncio.Task
_INFLIGHT: dict[str, asyncio.Task[None]] = {}

_DEFAULT_RATE_LIMIT_WINDOW = 60  # seconds

# Feature-gated commands: slash command prefix → config feature name
_FEATURE_GATES: dict[str, str] = {
    "/screenshot": "screenshot",
    "/search": "search",
}
_PENDING_REFLECT_FILE_NAME = "pending_reflect"


def _rate_limit_config(adj_dir: Path) -> tuple[int, int]:
    """Return (max_messages, window_seconds) from config with env var override."""
    window = _DEFAULT_RATE_LIMIT_WINDOW
    max_msgs = 10
    try:
        from adjutant.core.config import load_typed_config

        config = load_typed_config(adj_dir / "adjutant.yaml")
        max_msgs = config.messaging.telegram.rate_limit.messages_per_minute
        window = config.messaging.telegram.rate_limit.window_seconds
    except Exception:  # noqa: BLE001 — fallback to defaults
        pass
    # Env var override for max (backwards compat)
    try:
        env_max = os.environ.get("ADJUTANT_RATE_LIMIT_MAX", "")
        if env_max:
            max_msgs = int(env_max)
    except ValueError:
        pass
    return max_msgs, window


def _check_rate_limit(adj_dir: Path) -> bool:
    """Append timestamp, prune old entries, return True if within limit.

    Returns:
        True if the message should be allowed, False if rate limit exceeded.
    """
    state_dir = adj_dir / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    rate_file = state_dir / "rate_limit_window"

    max_msgs, window = _rate_limit_config(adj_dir)
    now = int(time.time())
    cutoff = now - window

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
    with contextlib.suppress(OSError):
        rate_file.write_text("\n".join(str(t) for t in timestamps) + "\n")

    count = len(timestamps)
    if count > max_msgs:
        adj_log(
            "messaging",
            f"Rate limit exceeded: {count} messages in last {window}s "
            f"(max {max_msgs}). Dropping message.",
        )
        return False

    return True


async def _wait_for_predecessors(tasks: tuple[asyncio.Task[None], ...]) -> None:
    """Wait for earlier conversational turns without cancelling them."""
    for task in tasks:
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            if task.cancelled():
                continue
            raise
        except Exception as exc:  # noqa: BLE001 - a failed turn must not block the queue
            adj_log("messaging", f"Earlier conversational turn failed: {exc}")


def _queue_turn(
    message_id: str,
    handler: Callable[[], Awaitable[None]],
) -> asyncio.Task[None]:
    """Queue a text or photo turn after all conversational work already accepted."""
    predecessors = tuple(task for task in _INFLIGHT.values() if not task.done())
    if predecessors:
        adj_log(
            "messaging",
            f"Queued msg={message_id} behind {len(predecessors)} earlier turn(s)",
        )

    async def _ordered_turn() -> None:
        try:
            await _wait_for_predecessors(predecessors)
            await handler()
        finally:
            current = asyncio.current_task()
            if _INFLIGHT.get(message_id) is current:
                _INFLIGHT.pop(message_id, None)

    task = asyncio.create_task(_ordered_turn())
    _INFLIGHT[message_id] = task
    return task


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
        cmd_brief,
        cmd_digest,
        cmd_forget,
        cmd_help,
        cmd_kb,
        cmd_kill,
        cmd_model,
        cmd_pause,
        cmd_pulse,
        cmd_recall,
        cmd_reflect_confirm,
        cmd_reflect_request,
        cmd_remember,
        cmd_restart,
        cmd_resume,
        cmd_schedule,
        cmd_screenshot,
        cmd_search,
        cmd_self_assess,
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
            with contextlib.suppress(OSError):
                pending_reflect.unlink(missing_ok=True)
            _send("No problem — I've cancelled the reflection.")
            adj_log("messaging", "Reflect cancelled.")
        return

    # Feature gate check — reject commands for disabled features
    config_path = adj_dir / "adjutant.yaml"
    if config_path.is_file():
        for cmd_prefix, feature_name in _FEATURE_GATES.items():
            if text == cmd_prefix or text.startswith(f"{cmd_prefix} "):
                try:
                    from adjutant.core.config import load_typed_config

                    config = load_typed_config(config_path)
                    if not config.is_feature_enabled(feature_name):
                        _send(
                            f"{feature_name.title()} is not enabled. "
                            f"Run `adjutant setup` or set "
                            f"`features.{feature_name}.enabled: true` "
                            f"in adjutant.yaml to enable it."
                        )
                        return
                except Exception:
                    adj_log(
                        "messaging",
                        f"Config parse failed — rejecting gated command {cmd_prefix}",
                    )
                    _send(
                        f"Cannot verify whether {feature_name} is enabled "
                        f"(config error). Command rejected."
                    )
                    return
                break

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
    elif text == "/brief":
        await cmd_brief(message_id, adj_dir, bot_token=bot_token, chat_id=chat_id)
    elif text in ("/self-assess", "/selfassess", "/assess"):
        await cmd_self_assess(message_id, adj_dir, bot_token=bot_token, chat_id=chat_id)
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
    elif text == "/remember":
        _send("Usage: /remember <thing to remember>")
    elif text.startswith("/remember "):
        await cmd_remember(
            text[len("/remember ") :], message_id, adj_dir, bot_token=bot_token, chat_id=chat_id
        )
    elif text == "/forget":
        _send("Usage: /forget <topic to forget>")
    elif text.startswith("/forget "):
        await cmd_forget(
            text[len("/forget ") :], message_id, adj_dir, bot_token=bot_token, chat_id=chat_id
        )
    elif text == "/recall":
        await cmd_recall("", message_id, adj_dir, bot_token=bot_token, chat_id=chat_id)
    elif text.startswith("/recall "):
        await cmd_recall(
            text[len("/recall ") :], message_id, adj_dir, bot_token=bot_token, chat_id=chat_id
        )
    elif text == "/digest":
        await cmd_digest(message_id, adj_dir, bot_token=bot_token, chat_id=chat_id)
    else:
        # Natural language chat
        adj_log("messaging", f"Chat msg={message_id}: {text}")
        msg_id_str = str(message_id)

        msg_react(message_id, bot_token=bot_token, chat_id=chat_id)

        async def _chat_turn() -> None:
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
            except Exception as exc:  # noqa: BLE001 - keep listener alive and inform the user
                msg_send_text(
                    "I ran into a problem getting a response. Try again in a moment.",
                    message_id,
                    bot_token=bot_token,
                    chat_id=chat_id,
                )
                adj_log("messaging", f"Chat task for msg={message_id} failed: {exc}")
            finally:
                msg_typing_stop(typing_key)

        _queue_turn(msg_id_str, _chat_turn)


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

    # Authorization
    if str(from_id) != str(chat_id):
        adj_log("messaging", f"Rejected photo from unauthorized sender: {from_id}")
        return

    async def _photo_turn() -> None:
        await tg_handle_photo(
            from_id,
            message_id,
            file_ref,
            caption,
            bot_token=bot_token,
            chat_id=chat_id,
            adj_dir=adj_dir,
        )

    _queue_turn(str(message_id), _photo_turn)
