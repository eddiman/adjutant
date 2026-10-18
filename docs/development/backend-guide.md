# Backend Developer Guide

How to work with the backend abstraction when developing Adjutant features.

---

## Using the backend in call sites

Always use `get_backend()` from `core/backend.py`. Never import backend implementations directly.

```python
from adjutant.core.backend import get_backend

backend = get_backend()
result = await backend.run(
    prompt,
    agent="adjutant",
    workdir=adj_dir,
    model=model,
    session_id=session_id,
    correlation_id=operation_id,
)
```

Pass a stable `correlation_id` when the call belongs to a Telegram update or
tracked operation. Both backend implementations include this identifier in
their logs and expose it on `LLMResult`. When the caller omits it, the backend
generates an invocation identifier.

### Check capabilities before optional features

```python
backend = get_backend()

# Vision
if backend.capabilities.vision:
    result = await backend.run(prompt, files=[image_path])
else:
    return "Vision is not supported on the current backend."

# Model listing
if backend.capabilities.model_listing:
    models = await backend.list_models()
else:
    models = "Model listing not available."

# Process reaping
if backend.capabilities.reaping:
    count = await backend.reap(adj_dir)
```

### Handle `LLMResult`

```python
from adjutant.core.backend import LLMResult

result: LLMResult = await backend.run(prompt)

if result.error_type:
    # Handle error — check error_type against the taxonomy
    if result.error_type == "vision_unsupported":
        await msg_send("Switch to the opencode backend for image analysis.")
    elif result.error_type == "auth_failure":
        await msg_send("Backend authentication failed. Check your credentials.")
    else:
        await msg_send(f"Error: {result.text}")
else:
    # Use result.text as the response
    await msg_send(result.text)

if result.timings:
    observe(
        correlation_id=result.correlation_id,
        spawn=result.timings.spawn_seconds,
        execution=result.timings.execution_seconds,
        cleanup=result.timings.cleanup_seconds,
        parsing=result.timings.parse_seconds,
        total=result.timings.total_seconds,
    )
```

`timed_out=True` can accompany partial `text`. Preserve that text as operation
evidence even when the user-facing response reports a timeout.

### Three invocation modes

| Method | Use case | Returns |
|--------|----------|---------|
| `await backend.run(...)` | Async — chat, commands, queries, analysis | `LLMResult` |
| `backend.run_detached(...)` | Fire-and-forget — KB write operations | `None` |
| `backend.run_sync(...)` | Synchronous — cron jobs | `int` (exit code) |

### Event-producing execution

Durable workers use the typed `ExecutionRequest` and `backend.execute()` interface:

```python
from adjutant.core.backend import ExecutionEventType, ExecutionRequest

request = ExecutionRequest(
    prompt=prompt,
    workdir=adj_dir,
    model=model,
    correlation_id=operation_id,
    startup_timeout=60,
    connection_timeout=30,
    timeout=1800,
)

async for event in backend.execute(request):
    if event.type is ExecutionEventType.TOOL_FINISHED:
        persist_public_progress(event.public_message)
    if event.result is not None:
        result = event.result
```

The normalized event types are `started`, `session_started`, `tool_started`, `tool_finished`, `text_delta`, `usage`, `waiting_input`, `completed`, and `failed`. Public progress may use `public_message`; it must not forward hidden reasoning or tool arguments. `run()` remains the compatibility adapter that collects the final event into `LLMResult`.

OpenCode parses NDJSON as it arrives and drains stdout and stderr concurrently. It retains a bounded raw-output head and tail while the semantic parser keeps the complete text result and at most 100 recent raw event objects. Claude CLI currently emits lifecycle events around its collected JSON response.

---

## Adding a new call site

1. Import `get_backend`:
   ```python
   from adjutant.core.backend import get_backend
   ```
2. Call `get_backend()` — it reads the active backend from config
3. Use `backend.run()` with appropriate parameters
4. Handle `LLMResult.error_type` for error cases
5. Pass the parent operation's correlation ID when one exists
6. Check `backend.capabilities.*` before using optional features

### Process ownership

OpenCode invocations run in separate process groups. Timeout and Python-task
cancellation signal only the group created for that invocation, then reap the
parent and collect partial output. Do not restore process cleanup based on a
global before-and-after PID scan because concurrent invocations can create
language servers during the same interval.

Startup timeout and runtime timeout are separate inputs. The operation layer also owns acknowledgement targets, quiet-progress warnings, connection timeout for reconnectable transports, lease expiry, and cancellation grace. Do not collapse these into one deadline because each timeout implies a different recovery action.

Durable workers pass the remaining persisted deadline to `ExecutionRequest.timeout`. OpenCode emits owned-process evidence immediately after `create_subprocess_exec`, and the worker writes that evidence plus session and server IDs to the current attempt as events arrive. Attempt updates must retain the current-attempt fence. A terminal result from a revoked attempt must fail instead of creating a second delivery.

Nested OpenCode KB calls use the repository `tool.execute.before` plugin. Keep the matcher limited to a standalone Adjutant KB command with `ADJUTANT_PARENT_OPERATION_ID`; do not increase the timeout for general shell calls. The plugin asks `adjutant operation-context` for the validated remaining budget and adds the backend session and tool-call IDs to the child environment.

---

## Model aliases

Use config tier names (`cheap`, `medium`, `expensive`) or short aliases (`haiku`, `sonnet`, `opus`). The backend's `resolve_alias()` handles translation:

```python
# Both work on both backends:
result = await backend.run(prompt, model="sonnet")
result = await backend.run(prompt, model="anthropic/claude-sonnet-4-6")
```

---

## Agent prompts

The `agent` parameter selects an agent definition from `.opencode/agents/<agent>.md`:

- OpenCode: passes `--agent <agent>` directly
- Claude CLI: reads the file, strips YAML frontmatter, writes to a temp file, passes via `--system-prompt-file`

Both backends read from the same `.opencode/agents/` directory — one source of truth for prompts.

---

## Testing with backends

### Fixtures

- `mock_opencode` — creates a mock `opencode` binary that returns NDJSON
- `mock_claude` — creates a mock `claude` binary that returns JSON

### Markers

```python
import pytest

pytestmark = pytest.mark.backend_claude_cli  # only runs when claude-cli is active
pytestmark = pytest.mark.backend_opencode    # only runs when opencode is active
```

Tests with backend markers auto-skip unless that backend is active. Use `--run-all-backends` to force all tests:

```bash
.venv/bin/pytest tests/ --run-all-backends
```

### Mocking the backend in consumer tests

```python
from adjutant.core.backend import LLMResult

def _llm_result(text="OK", **kwargs):
    return LLMResult(text=text, **kwargs)

# Patch get_backend to return a mock
with patch("your_module.get_backend") as mock_gb:
    mock_backend = MagicMock()
    mock_backend.run = AsyncMock(return_value=_llm_result("response text"))
    mock_backend.capabilities = BackendCapabilities(vision=True)
    mock_gb.return_value = mock_backend

    result = await your_function_under_test()
```

---

## KB-internal LLM calls

Some KBs have their own Python pipelines that need to call an LLM directly (e.g. portfolio-kb's analyze pipeline generates trade signals via LLM inference). These KBs cannot use `get_backend()` — they are independent projects that don't import Adjutant's code.

### Pattern: read backend from Adjutant's config

KBs should discover the active backend via the `ADJ_DIR` environment variable, which Adjutant always sets when running KB operations:

```python
import os
import re
from pathlib import Path

def _read_adjutant_backend() -> str:
    """Read the active LLM backend from Adjutant's config."""
    adj_dir = os.environ.get("ADJ_DIR", "").strip()
    if not adj_dir:
        return "opencode"  # fallback for manual invocation

    config_path = Path(adj_dir) / "adjutant.yaml"
    if not config_path.is_file():
        return "opencode"

    try:
        text = config_path.read_text()
        match = re.search(
            r'^\s+backend:\s*["\']?(opencode|claude-cli)["\']?',
            text, re.MULTILINE,
        )
        if match:
            return match.group(1)
    except OSError:
        pass

    return "opencode"
```

Note: This uses a simple regex instead of `yaml.safe_load()` to avoid requiring PyYAML as a KB dependency.

### Model alias translation

OpenCode and Claude CLI use different model ID formats. Embed a simple alias map:

```python
_OPENCODE_TO_CLAUDE = {
    "anthropic/claude-haiku-4-5": "haiku",
    "anthropic/claude-sonnet-4-6": "sonnet",
    "anthropic/claude-opus-4-6": "opus",
}
```

### Agent prompt handling

Both backends read agent definitions from `.opencode/agents/<agent>.md`. For Claude CLI, strip the YAML frontmatter and pass the body via `--system-prompt-file`:

```python
def _extract_prompt_body(agent_file: Path) -> str:
    content = agent_file.read_text()
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            return parts[2].strip()
    return content
```

### Output format differences

| Backend | Output format | How to parse |
|---------|--------------|-------------|
| OpenCode | NDJSON lines with `{"type": "text", "part": {"text": "..."}}` | Iterate lines, extract text parts |
| Claude CLI | Single JSON `{"result": "...", "is_error": false, "cost_usd": 0.004}` | Parse once, read `.result` field |

### Reference implementation

See `portfolio-kb/src/pipeline/analyze.py` for a complete working example of a KB that supports both backends.

---

## Adding a new backend (hypothetical)

1. Create `src/adjutant/core/backend_<name>.py`
2. Implement the `LLMBackend` protocol (all methods)
3. Declare `BackendCapabilities` with appropriate flags
4. Add the backend name to `get_backend()` factory in `backend.py`
5. Add the name to `LLMConfig.validate_backend()` in `config.py`
6. Create `lib/<name>_parser.py` if the output format differs
7. Add tests: `tests/unit/test_backend_<name>.py`
8. Add marker to `pyproject.toml`: `"backend_<name>: ..."`
9. Update conftest.py auto-skip logic

---

## Web UI

Backend-native web servers are retired on both backends. Adjutant's browser UI is the `web/` app in this monorepo, started with `adjutant web` during development.

---

## File inventory

| File | Purpose |
|------|---------|
| `core/backend.py` | Protocol, `LLMResult`, `BackendCapabilities`, `get_backend()` factory |
| `core/backend_opencode.py` | OpenCode implementation |
| `core/backend_claude_cli.py` | Claude CLI implementation |
| `core/opencode.py` | Low-level OpenCode process management (used by `backend_opencode.py`) |
| `lib/ndjson.py` | OpenCode NDJSON output parser |
| `lib/claude_json.py` | Claude Code JSON output parser |
| `setup/steps/backend.py` | Setup wizard backend selection step |
