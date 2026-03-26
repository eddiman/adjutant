# Backend Architecture

How Adjutant abstracts LLM interactions behind a pluggable backend protocol.

---

## Design Principle

Python owns orchestration; the backend owns LLM execution. The boundary is a subprocess call. Python builds the invocation, the backend executes the LLM query and returns structured output. Python never enters the LLM loop. The backend never touches Telegram, registries, or identity files.

---

## Protocol: `LLMBackend`

Defined in `src/adjutant/core/backend.py`. All backends implement this protocol:

```python
class LLMBackend(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def capabilities(self) -> BackendCapabilities: ...

    async def run(self, prompt, *, agent, workdir, model, session_id, timeout, env, files) -> LLMResult: ...
    def run_detached(self, prompt, *, agent, workdir, model, log_path) -> None: ...
    def run_sync(self, prompt, *, workdir, timeout) -> int: ...

    async def reap(self, adj_dir) -> int: ...
    async def health_check(self, adj_dir) -> bool: ...
    async def list_models(self) -> str: ...
    def find_binary(self) -> str | None: ...
    def resolve_alias(self, alias) -> str: ...
    def translate_model_id(self, model_id) -> str: ...
```

### Key design choices

1. **`LLMResult` is the universal contract.** All backends return the same dataclass: `text`, `session_id`, `error_type`, `returncode`, `timed_out`, `cost_usd`.

2. **Three invocation modes** cover all use cases:
   - `run()` — async, returns `LLMResult`. Used by chat, commands, queries, vision, analysis.
   - `run_detached()` — fire-and-forget subprocess. Used by KB write operations.
   - `run_sync()` — synchronous, returns exit code only. Used by cron jobs.

3. **Capabilities are declared, not discovered.** Each backend exposes a frozen `BackendCapabilities` dataclass. Call sites check capabilities before calling optional methods:
   ```python
   if backend.capabilities.vision:
       result = await backend.run(prompt, files=[image])
   else:
       await msg_send("Vision not supported on this backend.")
   ```

4. **Model aliases are backend-specific.** `resolve_alias("sonnet")` returns `"anthropic/claude-sonnet-4-6"` on OpenCode and `"sonnet"` on Claude CLI. `translate_model_id()` converts between backend formats during backend switches.

5. **Backends are stateless.** `get_backend()` creates a new instance per call. Session state lives in `state/telegram_session.json`, not in the backend object.

---

## Factory: `get_backend()`

```python
def get_backend(backend_name: str | None = None) -> LLMBackend:
```

Reads `llm.backend` from `adjutant.yaml` (via `load_typed_config()`) and returns the appropriate implementation. Call sites never import backend implementations directly.

---

## Backend Implementations

### `OpenCodeBackend` (`backend_opencode.py`)

Wraps the existing `core/opencode.py` module. Delegates to `opencode_run()` for async calls and `_find_opencode()` for binary lookup. Parses NDJSON output via `lib/ndjson.py`.

**Capabilities:** vision, model_listing, reaping, web_server, streaming.

### `ClaudeCLIBackend` (`backend_claude_cli.py`)

Invokes `claude -p --output-format json` directly. Parses JSON output via `lib/claude_json.py`. Handles agent prompts by stripping YAML frontmatter from `.opencode/agents/*.md` and passing the body via `--system-prompt-file`.

**Capabilities:** remote_session, cost_tracking.

---

## Error Taxonomy

All backends map their errors to a shared taxonomy so call sites handle errors consistently:

| Error type | Meaning |
|-----------|---------|
| `model_not_found` | Invalid model identifier |
| `auth_failure` | Not authenticated or subscription expired |
| `rate_limited` | Too many requests / throttled |
| `context_overflow` | Input exceeds context window |
| `permission_denied` | Sandbox or permission system blocked the operation |
| `vision_unsupported` | Backend does not support native vision input |
| `timeout` | Request exceeded deadline |
| `parse_error` | Could not parse backend output |
| `error` | Unclassified backend error |

---

## Observability

Every `run()` and `run_sync()` call logs:
- Backend name
- Wall-clock duration
- Model and agent used
- Error type (if any)
- Cost in USD (Claude CLI only)

Logs go to `state/adjutant.log` via `adj_log("backend", ...)`.

---

## Backend Switch Detection

At startup, `lifecycle/control.py` compares `adjutant.yaml`'s `llm.backend` against `state/backend.txt`. On mismatch:

1. Stop the old backend's service (OpenCode web or Claude remote session)
2. Translate `state/telegram_model.txt` to the new backend's format
3. Clear `state/telegram_session.json`
4. Update `state/backend.txt`
5. Log the switch

This is handled by `_detect_backend_change()` and `_handle_backend_switch()`.

---

## KB Sub-Agents

KB query and run operations use the same backend abstraction. The backend's `run()` method receives `workdir=kb_path` and `agent="kb"`, which scopes the invocation to the KB's workspace.

KB scheduled operations (`kb_run`) do **not** use the backend — they invoke the KB's own Python CLI or shell scripts directly.

---

## Further Reading

- [Backends User Guide](../guides/backends.md) — choosing, configuring, and switching backends
- [Configuration](../guides/configuration.md) — `adjutant.yaml` backend settings
- [Design Decisions](design-decisions.md) — why dual backends, tradeoffs
