# Plugin (Capability) Guide

A capability is a self-contained Python module that gives Adjutant a new skill — taking screenshots, querying an API, reading files, sending notifications to third-party services, etc.

The agent can invoke capabilities via OpenCode tool calls. Capabilities can also be wired to slash commands in `commands.py`.

---

## Anatomy of a Capability

```
src/adjutant/capabilities/
└── <name>/
    ├── __init__.py
    └── <name>.py          # Entry module (required)
```

Each capability lives in its own subdirectory under `src/adjutant/capabilities/`. The entry module is the only required file.

---

## Entry Module Contract

The entry module must:

1. Import `get_adj_dir()` and credentials via `core/` utilities
2. Accept arguments as function parameters
3. Return a result string or raise on failure
4. Log via `adj_log`, never `print()`

```python
# src/adjutant/capabilities/<name>/<name>.py
"""One-line description of what this capability does."""

from __future__ import annotations

from pathlib import Path

from adjutant.core.env import get_credential
from adjutant.core.logging import adj_log


def run_<name>(adj_dir: Path, arg: str) -> str:
    """Do the thing.

    Args:
        adj_dir: Adjutant root directory.
        arg: The primary argument.

    Returns:
        Result string on success.

    Raises:
        RuntimeError: If the operation fails.
    """
    adj_log("<name>", f"Starting with arg: {arg}")

    # --- Do the work ---
    result = _do_something(arg)

    adj_log("<name>", f"Completed: {arg}")
    return result
```

---

## Minimal Working Example

Here is the simplest possible capability — a date/time lookup:

```python
# src/adjutant/capabilities/datetime/datetime.py
"""Returns the current date and time."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from adjutant.core.logging import adj_log


def run_datetime(adj_dir: Path, timezone: str = "") -> str:
    """Return current date/time, optionally in a given timezone."""
    adj_log("datetime", f"Queried time (tz={timezone or 'local'})")

    if timezone:
        try:
            tz = ZoneInfo(timezone)
        except ZoneInfoNotFoundError:
            raise ValueError(f"Unknown timezone: {timezone}")
        return datetime.now(tz).strftime("%A, %B %-d %Y at %H:%M %Z")

    return datetime.now().strftime("%A, %B %-d %Y at %H:%M")
```

---

## Using Credentials

If your capability needs credentials, load them with `core/env.py`:

```python
from adjutant.core.env import get_credential

api_key = get_credential("MY_SERVICE_API_KEY")
if not api_key:
    raise RuntimeError("MY_SERVICE_API_KEY not set in .env")
```

Add the credential to `.env.example` so users know to configure it:

```
MY_SERVICE_API_KEY=your_api_key_here
```

---

## Wiring a Slash Command

To make your capability available as a `/command` in chat, add an async handler to `src/adjutant/messaging/telegram/commands.py`:

```python
async def cmd_datetime(
    arg: str,
    message_id: int,
    adj_dir: Path,
    *,
    bot_token: str,
    chat_id: str,
) -> None:
    from adjutant.capabilities.datetime.datetime import run_datetime
    try:
        result = run_datetime(adj_dir, arg.strip())
        msg_send_text(result, message_id)
    except Exception as exc:
        msg_send_text(f"Error: {exc}", message_id)
```

Then register the command in `dispatch.py`'s `if/elif` chain:

```python
elif text == "/datetime":
    await cmd_datetime("", message_id, adj_dir, bot_token=bot_token, chat_id=chat_id)
elif text.startswith("/datetime "):
    await cmd_datetime(text[len("/datetime "):], message_id, adj_dir, bot_token=bot_token, chat_id=chat_id)
```

For long-running commands, use `msg_typing_start()`/`msg_typing_stop()` and run as a background `asyncio.Task`.

### Feature Gating

If your capability should be toggleable via `adjutant.yaml`, add a feature gate:

1. Add the feature flag to `core/config.py`'s `FeaturesConfig` model
2. Add the feature to `adjutant.yaml.example` under `features:`
3. Add the command prefix to `_FEATURE_GATES` in `dispatch.py`:
   ```python
   _FEATURE_GATES: dict[str, str] = {
       "/screenshot": "screenshot",
       "/search": "search",
       "/datetime": "datetime",  # add your command here
   }
   ```

When a feature is disabled in config, `dispatch.py` will reject the command with a message telling the user how to enable it. Commands not listed in `_FEATURE_GATES` (like `/status`, `/help`, `/kb`) are always available.

---

## Wiring the Agent

The agent (OpenCode) can call any capability via the bash tool or Python tool. Document the capability in `.opencode/agents/adjutant.md` so the agent knows it exists:

```markdown
## Available Tools

### datetime
Get the current date and time.
Usage: `adjutant datetime [timezone]`
Or call via Python: `from adjutant.capabilities.datetime.datetime import run_datetime`
```

---

## Sending Output to the User

Capabilities do not send messages themselves — they return results to the caller. The caller (a `cmd_*` function or the agent) is responsible for sending the reply.

If your capability generates a file (e.g., a screenshot, a PDF, a CSV), return its path as a string. The caller can then pass it to `msg_send_photo` or a file-send function.

---

## Logging

Always log the start and end of significant operations using `adj_log`:

```python
adj_log("<name>", f"Starting: {arg}")
# ... work ...
adj_log("<name>", f"Completed: {arg}")
```

Log failures with enough context to debug:

```python
adj_log("<name>", f"FAILED for {arg}: {exc}")
```

Logs go to `state/adjutant.log`. View with `adjutant logs`.

---

## Error Handling

- Raise `RuntimeError` or a domain-specific exception on failure; never return an error string
- Use `tempfile.NamedTemporaryFile(delete=False)` + `finally: os.unlink(tmp)` for temp files
- The `cmd_*` handler is responsible for catching exceptions and sending an error message to the user

---

## Registering a Scheduled Job

Any executable that can be invoked without interactive input can be registered as a scheduled job.

### Using KB operations (preferred for KB-backed jobs)

```yaml
schedules:
  - name: "my-kb-fetch"
    description: "Fetch and update my KB data"
    schedule: "0 9 * * 1-5"
    kb_name: "my-kb"
    kb_operation: "fetch"
    log: "state/my-kb-fetch.log"
    enabled: true
```

This runs `adjutant kb run my-kb fetch` on schedule. No absolute paths needed.

### Using a script path (for non-KB jobs)

```yaml
schedules:
  - name: "my-report"
    description: "Generate daily report"
    schedule: "0 8 * * 1-5"
    script: "/absolute/path/to/report.sh"
    log: "state/my-report.log"
    enabled: true
```

Then: `adjutant schedule sync`

See [docs/guides/schedules.md](../guides/schedules.md) for the full guide.

---

## Adding a Capability: Checklist

1. Create `src/adjutant/capabilities/<name>/<name>.py` — return result string or raise
2. Add `async cmd_<name>()` handler in `src/adjutant/messaging/telegram/commands.py`
3. Register in the `if/elif` dispatch chain in `src/adjutant/messaging/dispatch.py`
4. Add the CLI command in `src/adjutant/cli.py`
5. Document in `.opencode/agents/adjutant.md` so the agent knows it exists
6. Add unit test at `tests/unit/test_<name>.py`
7. Add to `docs/guides/commands.md`

Full guide: this file.

---

## Reference: Screenshot Capability

`src/adjutant/capabilities/screenshot/screenshot.py` is the most complete example:

- Validates the URL argument
- Loads credentials via `get_credential()`
- Spawns a Node.js Playwright helper for the actual screenshot
- Falls back from `sendPhoto` to `sendDocument` on Telegram size limits
- Calls the vision capability for an automatic caption
- Returns the file path on success

Read it before writing any capability that involves external processes or file output.
