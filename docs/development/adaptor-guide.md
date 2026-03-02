# Adaptor Guide

An adaptor connects Adjutant to a messaging backend (Telegram, Slack, Discord, CLI, etc.). The framework ships a Telegram adaptor. This guide explains how to build a new one.

---

## What an Adaptor Does

The listener → dispatch → adaptor pipeline works as follows:

1. Your adaptor's **listener** polls (or subscribes to) the backend for new messages.
2. For each message it calls `dispatch_message` or `dispatch_photo` from `dispatch.sh`.
3. `dispatch.sh` handles auth, rate limiting, command routing, and natural language chat — all backend-agnostic.
4. When a response is ready, `dispatch.sh` calls `msg_send_text` or `msg_send_photo` — functions your adaptor provides.

You write the polling loop and the send functions. Everything else is handled for you.

---

## Directory Structure

Create your adaptor under `scripts/messaging/<backend>/`:

```
scripts/messaging/
├── adaptor.sh              # Interface contract (do not modify)
├── dispatch.sh             # Backend-agnostic dispatcher (do not modify)
└── <backend>/
    ├── listener.sh         # REQUIRED: polling loop
    ├── send.sh             # REQUIRED: send functions
    ├── service.sh          # REQUIRED: start/stop/status process manager
    ├── commands.sh         # OPTIONAL: /command handlers (can reuse telegram's)
    ├── photos.sh           # OPTIONAL: photo handling
    ├── chat.sh             # OPTIONAL: chat bridge (usually shared)
    └── notify.sh           # OPTIONAL: standalone notifier
```

---

## The Interface Contract

`scripts/messaging/adaptor.sh` defines 8 functions. Your adaptor **must** override the 4 required ones. The 4 optional ones have safe no-op defaults.

### Required

#### `msg_send_text TEXT [REPLY_TO_ID]`

Send a plain text message to the user.

- `TEXT` — the message string (may contain newlines)
- `REPLY_TO_ID` — optional; the message ID to reply to (use if the backend supports threading)
- Returns 0 on success, 1 on failure

```bash
msg_send_text() {
  local text="$1"
  local reply_to="${2:-}"

  curl -s -X POST "https://api.example.com/messages" \
    -d "token=${MY_BOT_TOKEN}" \
    -d "channel=${MY_CHANNEL_ID}" \
    -d "text=${text}" > /dev/null
}
```

#### `msg_send_photo FILE_PATH [CAPTION]`

Send an image file.

- `FILE_PATH` — absolute path to the image on disk
- `CAPTION` — optional text caption (max length varies by backend)
- Returns 0 on success, 1 on failure

#### `msg_start_listener`

Start the polling loop. This function should run indefinitely. It calls `dispatch_message` or `dispatch_photo` for each received message.

#### `msg_stop_listener`

Stop the listener gracefully (e.g., send SIGTERM to the PID stored in a lockfile).

---

### Optional

#### `msg_react MSG_ID [EMOJI]`

Add a reaction to a message. Used by the dispatcher to acknowledge receipt before a long-running task completes. Default: no-op.

#### `msg_typing start|stop [SUFFIX]`

Show or hide a typing indicator. `SUFFIX` is an arbitrary string used to namespace concurrent indicators. Default: no-op.

#### `msg_authorize SENDER_ID`

Called by `dispatch.sh` before processing any message. Return 0 to allow, 1 to reject.

The default (in `adaptor.sh`) allows everyone. Override this to restrict to a known user ID:

```bash
msg_authorize() {
  local sender_id="$1"
  [ "${sender_id}" = "${MY_ALLOWED_USER_ID}" ]
}
```

#### `msg_get_user_id`

Return the authenticated user's ID as a string. Used for display/logging. Default: returns `"unknown"`.

---

## Writing `listener.sh`

Your listener must:

1. Source common utilities and all messaging modules
2. Call `check_killed` before entering the loop
3. Acquire a single-instance lock
4. Poll the backend in a loop, checking `is_killed` each iteration
5. Call `dispatch_message TEXT MESSAGE_ID SENDER_ID` for text messages
6. Call `dispatch_photo SENDER_ID MESSAGE_ID FILE_REF [CAPTION]` for images

Minimal skeleton:

```bash
#!/bin/bash
# scripts/messaging/<backend>/listener.sh

source "$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/common/paths.sh"
source "${ADJ_DIR}/scripts/common/env.sh"
source "${ADJ_DIR}/scripts/common/logging.sh"
source "${ADJ_DIR}/scripts/common/lockfiles.sh"
source "${ADJ_DIR}/scripts/common/platform.sh"
source "${ADJ_DIR}/scripts/common/opencode.sh"

# Load adaptor interface defaults first, then override with your implementations
source "${ADJ_DIR}/scripts/messaging/adaptor.sh"
source "${ADJ_DIR}/scripts/messaging/<backend>/send.sh"
source "${ADJ_DIR}/scripts/messaging/<backend>/commands.sh"
source "${ADJ_DIR}/scripts/messaging/dispatch.sh"

check_killed || exit 1
require_<backend>_credentials || exit 1

# Single-instance guard
LISTENER_LOCK="${ADJ_DIR}/state/listener.lock"
if ! mkdir "${LISTENER_LOCK}" 2>/dev/null; then
  echo "Another listener is already running." >&2
  exit 1
fi
echo $$ > "${LISTENER_LOCK}/pid"
trap 'rm -rf "${LISTENER_LOCK}"; adj_log <backend> "Listener stopped."' EXIT

adj_log <backend> "Listener started."

while true; do
  is_killed && break

  # Poll the backend for new messages...
  MESSAGES="$(fetch_new_messages)"

  for msg in ${MESSAGES}; do
    text="$(extract_text "${msg}")"
    msg_id="$(extract_id "${msg}")"
    sender="$(extract_sender "${msg}")"
    dispatch_message "${text}" "${msg_id}" "${sender}"
  done

  sleep 1
done
```

---

## Writing `send.sh`

Source `adaptor.sh` first (it defines the function signatures), then override:

```bash
#!/bin/bash
# scripts/messaging/<backend>/send.sh

# Override required functions
msg_send_text() {
  local text="$1"
  local reply_to="${2:-}"
  # ... backend API call ...
}

msg_send_photo() {
  local file_path="$1"
  local caption="${2:-}"
  # ... backend API call ...
}

msg_start_listener() {
  exec bash "${ADJ_DIR}/scripts/messaging/<backend>/listener.sh"
}

msg_stop_listener() {
  local pid_file="${ADJ_DIR}/state/listener.lock/pid"
  [ -f "${pid_file}" ] && kill "$(cat "${pid_file}")"
}

# Override optional functions if supported
msg_react() { return 0; }
msg_typing() { return 0; }
msg_authorize() {
  local sender_id="$1"
  [ "${sender_id}" = "${MY_ALLOWED_ID}" ]
}
```

---

## Writing `service.sh`

The service script is called by `adjutant start` / `adjutant stop`. It should:

- `start` — fork `listener.sh` to the background, log the PID
- `stop` — kill the PID from the lock file
- `status` — print `Running (PID X)` or `Stopped`

---

## Registering Your Adaptor

In `adjutant.yaml`, set:

```yaml
messaging:
  backend: <backend>   # e.g. "slack", "discord", "cli"
```

Then update `adjutant start` and `adjutant stop` in the `adjutant` CLI to call your `service.sh` instead of (or in addition to) `telegram/service.sh`.

---

## Testing Your Adaptor

Use the bats test suite:

```bash
bats tests/unit/messaging/
bats tests/integration/
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

- `scripts/messaging/telegram/send.sh` — `msg_send_text`, `msg_send_photo`, `msg_react`, `msg_typing`
- `scripts/messaging/telegram/listener.sh` — polling loop, jq parsing, `dispatch_message` / `dispatch_photo` calls
- `scripts/messaging/telegram/service.sh` — start/stop/status
- `scripts/messaging/telegram/commands.sh` — all `cmd_*` handlers
