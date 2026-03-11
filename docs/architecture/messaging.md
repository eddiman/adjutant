# Messaging Architecture

How Adjutant receives messages, routes them, and sends responses.

---

## Adaptor Interface — `src/adjutant/messaging/adaptor.py`

Adjutant is backend-agnostic. Any messaging platform can be supported by implementing the functions defined in `adaptor.py`. This module provides the shared interface that all backends implement.

**Send functions** (implemented per backend):

| Function | Signature | Description |
|----------|-----------|-------------|
| `msg_send_text` | `text, reply_to_id` | Send a text message |
| `msg_send_photo` | `file_path, caption` | Send an image |
| `msg_react` | `msg_id, emoji` | Add a reaction to a message |
| `msg_typing_start` | `suffix` | Show typing indicator |
| `msg_typing_stop` | `suffix` | Hide typing indicator |

All dispatch logic calls these functions. The dispatcher never calls Telegram-specific API endpoints or variables directly.

---

## Backend-Agnostic Dispatcher — `src/adjutant/messaging/dispatch.py`

`dispatch.py` is called by every adaptor's listener with a normalized message. It handles all shared concerns:

### 1. Authorization

Checks `TELEGRAM_CHAT_ID` against the configured allowed chat ID. If it doesn't match, the message is dropped silently.

### 2. Rate Limiting

Rolling 60-second window counter stored in `state/rate_limit_window`. Default: 10 messages per 60 seconds. Configurable via the `ADJUTANT_RATE_LIMIT_MAX` environment variable. When the limit is exceeded, the sender receives a "slow down" message.

### 3. Pending State

Checks `state/pending_reflect` for multi-turn confirmation flows. If a `/reflect` confirmation is pending:
- `/confirm` — proceeds with the reflect task
- Any other text — cancels the pending task and resumes normal routing

### 4. Command Routing

`if/elif` chain on slash-command prefix. Each `/command` maps to an `async` `cmd_*` function defined in `messaging/telegram/commands.py`. Unknown commands fall through to the natural language path.

### 5. Natural Language Model-Switch Detection

Before falling through to chat, the dispatcher checks whether the message matches a natural-language model-switch pattern (e.g. "switch to opus", "use kimi", "change model to sonnet"). If matched, it routes to the model-switch handler instead of the chat agent.

### 6. Natural Language Chat

All non-command text is forwarded to `chat.py` as an `asyncio.Task`. If a new message arrives before the previous response is complete, the in-flight task is cancelled before the new one starts. This prevents response pileups and ensures the user's latest message always gets a response.

---

## Data Flow: Incoming Message

```
Telegram API
    │
    │  getUpdates (long-poll)
    ▼
listener.py (async loop)
    │
    ├─► dispatch_photo()  ─► tg_handle_photo ─► vision ─► chat.py ─► claude_run
    └─► dispatch_message()
            │
            ├─ auth check (chat_id match)
            ├─ rate limit check (_check_rate_limit)
            ├─ pending state check (pending_reflect)
            │
            ├─ /command  ─► cmd_* (commands.py)  [async]
            │                  │
            │                  ├─ inline response (msg_send_text)
            │                  └─ complex tasks (claude_run)
            │
            ├─ model-switch intent ─► cmd_model()
            │
            └─ text  ─► chat.py (asyncio.Task)
                            │
                            ▼
                        claude_run
                            │
                            ▼
                        msg_send_text (reply)
```

---

## Data Flow: Outgoing Notification

```
adjutant notify "text"
    │
    ▼
messaging/telegram/notify.py
    │  load credentials from .env
    │  HTTP POST sendMessage
    ▼
Telegram API
```

`notify.py` is standalone — it sends a message without requiring the listener to be running. Used for proactive notifications, scheduled briefings, and emergency kill confirmations.

---

## Telegram Adaptor — `src/adjutant/messaging/telegram/`

The only currently implemented backend.

| Module | Responsibility |
|--------|---------------|
| `listener.py` | Main async polling loop. Acquires `state/listener.lock/`, polls `getUpdates`, calls `dispatch_message` or `dispatch_photo`. |
| `send.py` | Implements `msg_send_text`, `msg_send_photo`, `msg_react`, `msg_typing_start`, `msg_typing_stop` with real Telegram API calls. |
| `photos.py` | `tg_download_photo` (downloads from Telegram CDN) + `tg_handle_photo` (vision analysis → chat response). |
| `commands.py` | `async cmd_*` functions for every slash command. |
| `chat.py` | Invokes `claude_run` with the user message and returns the agent reply. Manages session continuity (reuses session ID within a configured window). |
| `notify.py` | Standalone notifier — sends a message without requiring the listener to be running. |
| `reply.py` | Reply helper used by scheduled job results and KB operation output. |
| `service.py` | Process manager: `start` (fork listener to background), `stop` (kill by PID), `status`. |

### Listener Process Management

The listener's PID is tracked by `service.py`. It checks two sources in priority order:

1. **`state/listener.lock/pid`** — written by `listener.py` itself (most reliable)
2. **`state/telegram.pid`** — written by `service.py` on startup

`service.py start` waits for `listener.lock/pid` to appear, confirming the listener initialized successfully before reporting success.

---

## Adding a New Backend

See [Adaptor Guide](../development/adaptor-guide.md) for step-by-step instructions on implementing the interface for a new messaging platform.
