# Messaging Architecture

How Adjutant receives messages, routes them, and sends responses.

---

## Adaptor Interface — `scripts/messaging/adaptor.sh`

Adjutant is backend-agnostic. Any messaging platform can be supported by implementing eight functions defined in `adaptor.sh`. This file ships no-op or error-returning defaults; a concrete adaptor overrides them by sourcing its own implementation after this file.

**Required functions** (return 1 if not implemented):

| Function | Signature | Description |
|----------|-----------|-------------|
| `msg_send_text` | `TEXT [REPLY_TO_ID]` | Send a text message |
| `msg_send_photo` | `FILE_PATH [CAPTION]` | Send an image |
| `msg_start_listener` | — | Start the polling/listening loop |
| `msg_stop_listener` | — | Stop the listener gracefully |

**Optional functions** (no-op defaults — return 0 silently):

| Function | Signature | Description |
|----------|-----------|-------------|
| `msg_react` | `MSG_ID [EMOJI]` | Add a reaction to a message |
| `msg_typing` | `start\|stop [SUFFIX]` | Show/hide typing indicator |
| `msg_authorize` | `SENDER_ID` | Validate sender; return 0 to allow, 1 to reject |
| `msg_get_user_id` | — | Return the authenticated user ID |

All dispatch logic calls these functions exclusively. The dispatcher never calls Telegram-specific API endpoints or variables.

---

## Backend-Agnostic Dispatcher — `scripts/messaging/dispatch.sh`

`dispatch.sh` is called by every adaptor's listener with a normalized message. It handles all shared concerns:

### 1. Authorization

Calls `msg_authorize SENDER_ID`. If it returns 1, the message is dropped silently.

### 2. Rate Limiting

Sliding-window counter stored in `state/rate_limit_window`. Default: 10 messages per 60 seconds. Configurable via `ADJUTANT_RATE_LIMIT_MAX` in `adjutant.yaml`. When the limit is exceeded, the sender receives a "slow down" message.

### 3. Pending State

Checks `state/pending_reflect` for multi-turn confirmation flows. If a `/reflect` confirmation is pending:
- `/confirm` — proceeds with the reflect task
- Any other text — cancels the pending task and resumes normal routing

### 4. Command Routing

`case` on slash-command prefix. Each `/command` maps to a `cmd_*` function defined in the backend's `commands.sh`. Unknown commands fall through to the natural language path.

### 5. Natural Language

All non-command text is forwarded to `chat.sh` in a **background subshell**. If a new message arrives before the previous response is complete, the in-flight job is killed (via a tracked PID file) before the new one starts. This prevents pileups and ensures the user's latest message always gets a response.

---

## Data Flow: Incoming Message

```
Telegram API
    │
    │  getUpdates (long-poll, 10s)
    ▼
listener.sh
    │  jq parse
    ├─► dispatch_photo()  ─► tg_handle_photo ─► vision ─► chat.sh ─► opencode_run
    └─► dispatch_message()
            │
            ├─ auth check (msg_authorize)
            ├─ rate limit check (_check_rate_limit)
            ├─ pending state check (pending_reflect)
            │
            ├─ /command  ─► cmd_* (commands.sh)
            │                  │
            │                  ├─ inline response (msg_send_text)
            │                  └─ complex tasks (opencode_run)
            │
            └─ text  ─► chat.sh (background subshell)
                            │
                            ▼
                        opencode_run
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
scripts/messaging/telegram/notify.sh
    │  require_telegram_credentials
    │  curl sendMessage
    ▼
Telegram API
```

`notify.sh` is standalone — it sends a message without requiring the listener to be running. Used for proactive notifications, scheduled briefings, and emergency kill confirmations.

---

## Telegram Adaptor — `scripts/messaging/telegram/`

The only currently implemented backend.

| File | Responsibility |
|------|---------------|
| `listener.sh` | Main polling loop. Sources all modules, acquires `state/listener.lock`, polls `getUpdates` (10s long-poll), parses JSON with `jq`, calls `dispatch_message` or `dispatch_photo`. |
| `send.sh` | Overrides `msg_send_text`, `msg_send_photo`, `msg_react`, `msg_typing` with real Telegram API calls. |
| `photos.sh` | `tg_download_photo` (downloads from Telegram CDN) + `tg_handle_photo` (vision analysis → chat response). |
| `commands.sh` | `cmd_*` functions for every slash command. |
| `chat.sh` | Invokes `opencode_run` with the user message and returns the agent reply. Manages session continuity (reuses session ID within a 2-hour window). |
| `notify.sh` | Standalone notifier — sends a message without requiring the listener to be running. |
| `service.sh` | Process manager: `start` (fork listener to background), `stop` (kill by PID), `status`. |

### Listener Process Management

The listener's PID is tracked by a single authoritative function `_find_listener_pid()` in `service.sh`. It checks three sources in priority order:

1. **`state/listener.lock/pid`** — written by `listener.sh` itself (most reliable)
2. **`state/telegram.pid`** — written by `service.sh` on startup
3. **`pgrep -f listener.sh`** — fallback pattern match

All other scripts (`startup.sh`, `adjutant doctor`, `emergency_kill.sh`) delegate to `service.sh status` instead of implementing their own PID detection. This eliminates the root cause of duplicate listener instances.

`service.sh start` waits up to 5 seconds for `listener.lock/pid` to appear, confirming the listener initialized successfully before reporting success and syncing `telegram.pid`.

---

## Adding a New Backend

See [Adaptor Guide](../development/adaptor-guide.md) for step-by-step instructions on implementing the 8-function interface for a new messaging platform.
