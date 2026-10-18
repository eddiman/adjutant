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

    async def run(
        self,
        prompt,
        *,
        agent,
        workdir,
        model,
        session_id,
        timeout,
        env,
        files,
        correlation_id,
    ) -> LLMResult: ...
    def execute(self, request: ExecutionRequest) -> AsyncIterator[ExecutionEvent]: ...
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

1. **`LLMResult` is the universal contract.** All backends return the same dataclass: `text`, `session_id`, `error_type`, `returncode`, `timed_out`, `cost_usd`, `correlation_id`, and phase `timings`.

2. **Four invocation modes** cover compatibility and migration use cases:
   - `execute()` yields normalized start, session, tool, text, usage, wait, failure, and completion events. The durable worker uses this interface.
   - `run()` — async, returns `LLMResult`. Used by chat, commands, queries, vision, analysis.
   - `run_detached()` is retained for rollback while durable operations are disabled.
   - `run_sync()` is retained for rollback and untracked compatibility callers.

3. **Capabilities are declared, not discovered.** Each backend exposes a frozen `BackendCapabilities` dataclass. Call sites check capabilities before calling optional methods:
   ```python
   if backend.capabilities.vision:
       result = await backend.run(prompt, files=[image])
   else:
       await msg_send("Vision not supported on this backend.")
   ```

4. **Model aliases are backend-specific.** `resolve_alias("sonnet")` returns `"anthropic/claude-sonnet-4-6"` on OpenCode and `"sonnet"` on Claude CLI. `translate_model_id()` converts between backend formats during backend switches.

5. **Backend adapter objects are stateless.** `get_backend()` creates a new adapter per call. When persistent OpenCode is enabled, adapters share an Adjutant-owned server through persisted ownership metadata. Operation sessions remain separate and each operation has one writer.

6. **Durable execution is outside the backend.** The operation worker freezes the selected backend, model, variant, agent, and work directory on acceptance. It passes the operation ID as the backend correlation ID, records each attempt, and persists the result before Telegram delivery. See [Durable Operations](operations.md).

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

Each invocation owns a process group. Timeout or cancellation signals that
group, preserves bounded partial output, and does not scan for unrelated
language-server processes.

The OpenCode adapter publishes the CLI PID, process birth time, and process-group ID immediately after spawn. Session and managed-server IDs are persisted as soon as their events arrive instead of waiting for the terminal result. This gives lease recovery exact ownership evidence even when the caller disappears.

**Capabilities:** vision, model_listing, reaping, streaming, persistent_transport, reconnect, native_abort.

OpenCode's streaming capability is caller-visible. The adapter drains both pipes while the process runs, parses complete NDJSON lines incrementally, and maps them to the shared execution-event types. It stores complete answer text separately from a bounded raw-event and diagnostic buffer.

With `operations.persistent_opencode.enabled`, the adapter starts an authenticated server on loopback and invokes the existing CLI as `opencode run --attach <url>`. The state file records the server instance ID, PID, process creation time, URL, version, lifecycle state, and last-use time. The password lives in a separate mode-0600 file and never appears in the state or logs. A PID is signalled only when its creation time still matches and its command line still identifies an OpenCode server.

The adapter queries the documented session status endpoint after an attached CLI disconnect. It records `reconciliation_required` and does not submit the prompt again. Timeout and Python cancellation call the documented session abort endpoint when a session ID was observed. Soft memory pressure marks the server as draining, lets attached work finish, and routes new work through an isolated CLI process. Maintenance stops the drained server after active operations reach zero, even if a completed child process has already reduced RSS. Hard pressure stops only the owned process group. RSS accounting includes descendants.

OpenCode's ordinary `bash` tool defaults to two minutes independently of the operation worker. The repository plugin `.opencode/plugins/adjutant-kb-timeout.js` changes that timeout only for one standalone `adjutant kb query`, `write`, `query-all`, or `cross-query` command carrying a validated parent operation ID. The hidden `operation-context` CLI command verifies the active attempt and returns the remaining persisted budget. Unrelated shell calls keep OpenCode's default, and compound shell commands are rejected on this extended-timeout path.

### `ClaudeCLIBackend` (`backend_claude_cli.py`)

Invokes `claude -p --output-format json` directly. Parses JSON output via `lib/claude_json.py`. Handles agent prompts by stripping YAML frontmatter from `.opencode/agents/*.md` and passing the body via `--system-prompt-file`.

Standalone durable Claude operations retain their existing process timeout and reconciliation behavior. Attached durable KB children are rejected until the Claude adapter emits early owned-process evidence and passes the same caller-death fixture as OpenCode.

**Capabilities:** model_listing, streaming lifecycle events, cost_tracking.

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
| `reconciliation_required` | Attached execution outcome is uncertain; inspect the recorded session instead of replaying it |
| `parse_error` | Could not parse backend output |
| `error` | Unclassified backend error |

---

## Observability

Every `run()` and `run_sync()` call logs:
- Backend name
- Correlation ID
- Wall-clock duration
- Spawn, execution, cleanup, and parsing duration where available
- Model and agent used
- Error type (if any)
- Cost in USD (Claude CLI only)

Logs go to `state/adjutant.log` via `adj_log("backend", ...)`.

The durable operation worker owns cancellation and lease renewal above this interface. Backend cancellation terminates and reaps only the CLI process group that belongs to the invocation. For attached OpenCode sessions, the adapter also sends native abort to the recorded session.

---

## Backend Switch Detection

At startup, `lifecycle/control.py` compares `adjutant.yaml`'s `llm.backend` against `state/backend.txt`. On mismatch:

1. Drain and stop any Adjutant-owned persistent transport from the old backend
2. Translate `state/telegram_model.txt` to the new backend's format
3. Clear `state/telegram_session.json`
4. Update `state/backend.txt`
5. Log the switch

Backend-native web servers are retired on both backends, so the switch now translates model/session state only.

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
