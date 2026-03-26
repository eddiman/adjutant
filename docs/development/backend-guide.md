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
)
```

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
```

### Three invocation modes

| Method | Use case | Returns |
|--------|----------|---------|
| `await backend.run(...)` | Async — chat, commands, queries, analysis | `LLMResult` |
| `backend.run_detached(...)` | Fire-and-forget — KB write operations | `None` |
| `backend.run_sync(...)` | Synchronous — cron jobs | `int` (exit code) |

---

## Adding a new call site

1. Import `get_backend`:
   ```python
   from adjutant.core.backend import get_backend
   ```
2. Call `get_backend()` — it reads the active backend from config
3. Use `backend.run()` with appropriate parameters
4. Handle `LLMResult.error_type` for error cases
5. Check `backend.capabilities.*` before using optional features

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
