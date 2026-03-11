# Adaptor Guide

An adaptor connects Adjutant to a messaging backend (Telegram, Slack, Discord, CLI, etc.). The framework ships a Telegram adaptor. This guide explains how to build a new one.

---

## What an Adaptor Does

The listener → dispatch → adaptor pipeline works as follows:

1. Your adaptor's **listener** polls (or subscribes to) the backend for new messages.
2. For each message it calls `dispatch_message` or `dispatch_photo` from `dispatch.py`.
3. `dispatch.py` handles auth, rate limiting, command routing, and natural language chat — all backend-agnostic.
4. When a response is ready, `dispatch.py` calls `msg_send_text` or `msg_send_photo` — functions your adaptor provides.

You write the polling loop and the send functions. Everything else is handled for you.

---

## Directory Structure

Create your adaptor under `src/adjutant/messaging/<backend>/`:

```
src/adjutant/messaging/
├── adaptor.py              # Interface contract (do not modify)
├── dispatch.py             # Backend-agnostic dispatcher (do not modify)
└── <backend>/
    ├── listener.py         # REQUIRED: async polling loop
    ├── send.py             # REQUIRED: send functions
    ├── service.py          # REQUIRED: start/stop/status process manager
    ├── commands.py         # OPTIONAL: /command handlers (can reuse telegram's)
    ├── photos.py           # OPTIONAL: photo handling
    ├── chat.py             # OPTIONAL: chat bridge (usually shared)
    └── notify.py           # OPTIONAL: standalone notifier
```

---

## The Interface Contract

`src/adjutant/messaging/adaptor.py` defines the send functions your adaptor must implement.

### Required

#### `msg_send_text(text: str, reply_to_id: int | None = None) -> None`

Send a plain text message to the user.

- `text` — the message string (may contain newlines)
- `reply_to_id` — optional; the message ID to reply to (use if the backend supports threading)

```python
def msg_send_text(text: str, reply_to_id: int | None = None) -> None:
    requests.post(
        f"https://api.example.com/messages",
        json={"token": MY_BOT_TOKEN, "channel": MY_CHANNEL_ID, "text": text},
    )
```

#### `msg_send_photo(file_path: str, caption: str = "") -> None`

Send an image file.

- `file_path` — absolute path to the image on disk
- `caption` — optional text caption

### Optional

#### `msg_react(msg_id: int, emoji: str = "") -> None`

Add a reaction to a message. Used by the dispatcher to acknowledge receipt before a long-running task completes.

#### `msg_typing_start(suffix: str = "") -> None` / `msg_typing_stop(suffix: str = "") -> None`

Show or hide a typing indicator. `suffix` is an arbitrary string used to namespace concurrent indicators.

#### `msg_authorize(sender_id: str) -> bool`

Called by `dispatch.py` before processing any message. Return `True` to allow, `False` to reject. The default allows everyone — override to restrict to a known user ID.

---

## Writing `listener.py`

Your listener must:

1. Import common utilities and all messaging modules
2. Check the `KILLED` lockfile before entering the loop
3. Acquire a single-instance lock
4. Poll the backend in an async loop
5. Call `dispatch_message(text, message_id, sender_id, adj_dir, ...)` for text messages
6. Call `dispatch_photo(sender_id, message_id, file_ref, caption, adj_dir, ...)` for images

Minimal async skeleton:

```python
# src/adjutant/messaging/<backend>/listener.py
import asyncio
from pathlib import Path

from adjutant.core.lockfiles import check_killed, is_killed
from adjutant.core.logging import adj_log
from adjutant.core.paths import get_adj_dir
from adjutant.messaging.dispatch import dispatch_message


async def run_listener(adj_dir: Path, bot_token: str, chat_id: str) -> None:
    check_killed(adj_dir)

    lock_dir = adj_dir / "state" / "listener.lock"
    lock_dir.mkdir(parents=True, exist_ok=False)  # raises if already exists
    pid_file = lock_dir / "pid"
    pid_file.write_text(str(os.getpid()))

    adj_log("<backend>", "Listener started.")

    try:
        while True:
            if is_killed(adj_dir):
                break

            messages = await fetch_new_messages()
            for msg in messages:
                await dispatch_message(
                    msg.text, msg.id, msg.sender,
                    adj_dir=adj_dir,
                    bot_token=bot_token,
                    chat_id=chat_id,
                )

            await asyncio.sleep(1)
    finally:
        import shutil
        shutil.rmtree(lock_dir, ignore_errors=True)
        adj_log("<backend>", "Listener stopped.")
```

---

## Writing `service.py`

The service module is called by `adjutant start` / `adjutant stop`. It should provide:

- `start_listener(adj_dir, bot_token, chat_id)` — fork the listener to the background, write the PID
- `stop_listener(adj_dir)` — kill the PID from the lock file
- `get_status(adj_dir)` — return `"running"`, `"stopped"`, or `"paused"`

---

## Registering Your Adaptor

In `adjutant.yaml`, set:

```yaml
messaging:
  backend: <backend>   # e.g. "slack", "discord", "cli"
```

Then update `src/adjutant/messaging/dispatch.py` and `src/adjutant/cli.py` to import your `service.py` and route `adjutant start`/`stop` to it.

---

## Testing Your Adaptor

Use pytest:

```bash
.venv/bin/pytest tests/unit/test_messaging_<backend>.py -v
```

For manual smoke testing:

1. Run `adjutant doctor` — verify your credentials and dependencies appear
2. Run `adjutant start` — listener should start without errors
3. Send a `/status` message from your client — you should get a reply
4. Send a natural language message — the agent should respond
5. Run `adjutant stop` — listener should stop cleanly

---

## Reference: Telegram Adaptor

The Telegram adaptor is the reference implementation. Read it before writing your own:

- `src/adjutant/messaging/telegram/send.py` — `msg_send_text`, `msg_send_photo`, `msg_react`, `msg_typing_start`/`stop`
- `src/adjutant/messaging/telegram/listener.py` — async polling loop, `dispatch_message` / `dispatch_photo` calls
- `src/adjutant/messaging/telegram/service.py` — start/stop/status
- `src/adjutant/messaging/telegram/commands.py` — all `async cmd_*` handlers
