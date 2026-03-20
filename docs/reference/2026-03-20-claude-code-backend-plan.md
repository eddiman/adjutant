# Claude Code Backend — Comprehensive Implementation Plan

**Status**: Final plan — ready for implementation
**Created**: 2026-03-20
**Updated**: 2026-03-20 (dropped claude-sdk; added KB review; added remediation, switch detection, docs plan, backend-aware tests; review pass: error taxonomy, capabilities protocol, vision handling, security/permissions audit, observability, contract tests, single source of truth for prompts)
**Objective**: Abstract Adjutant's LLM backend so users can choose between OpenCode (API key) and Claude Code CLI (Anthropic subscription), selected via `adjutant.yaml`.

---

## Table of Contents

1. [Context & Problem](#1-context--problem)
2. [Architecture Decision: Two Backends](#2-architecture-decision-two-backends)
3. [Separation of Concerns: Python vs Backend](#3-separation-of-concerns-python-vs-backend)
4. [Detailed Coupling Analysis](#4-detailed-coupling-analysis)
5. [Phase 1: Backend Abstraction Layer](#5-phase-1-backend-abstraction-layer)
6. [Phase 2: Claude Code CLI Backend](#6-phase-2-claude-code-cli-backend)
7. [Phase 3: Call Site Migration](#7-phase-3-call-site-migration)
8. [Phase 4: Agent Definitions & Permissions](#8-phase-4-agent-definitions--permissions)
9. [Phase 5: KB Review & Migration](#9-phase-5-kb-review--migration)
10. [Phase 6: KB Template System](#10-phase-6-kb-template-system)
11. [Phase 7: Config, Setup & Model Resolution](#11-phase-7-config-setup--model-resolution)
12. [Phase 8: Backend-Aware Test Organization](#12-phase-8-backend-aware-test-organization)
13. [CLAUDE.md Conflict Resolution](#13-claudemd-conflict-resolution)
14. [Billing & Rate Limiting](#14-billing--rate-limiting)
15. [Process Lifecycle & Orphan Management](#15-process-lifecycle--orphan-management)
16. [Backend Switch Detection & Side Effects](#16-backend-switch-detection--side-effects)
17. [Migration Checklist](#17-migration-checklist)
18. [Risk Register](#18-risk-register)
19. [Environment File Security (Hooks & Defense-in-Depth)](#19-environment-file-security-hooks--defense-in-depth)
20. [Documentation Plan](#20-documentation-plan)
21. [Implementation Order](#21-implementation-order)

---

## 1. Context & Problem

Anthropic has blocked OpenCode from using their subscription-based auth. Adjutant's
configured Anthropic models (`anthropic/claude-haiku-4-5`, `anthropic/claude-sonnet-4-6`,
`anthropic/claude-opus-4-6`) still work through OpenCode with API keys, but users
on Claude Pro/Team/Enterprise subscriptions cannot use OpenCode.

Adjutant uses OpenCode **exclusively as a CLI subprocess** -- no library imports,
no API calls. Every LLM interaction flows through `opencode run ...` spawned as
a child process from `core/opencode.py`.

### Coupling Inventory

| Category | Count | Files |
|----------|-------|-------|
| Direct `opencode_run()` callers | 6 | chat.py, commands.py, query.py, vision.py, analyze.py, identity.py |
| Direct `opencode` subprocess callers (bypass `opencode_run`) | 3 | cron.py, control.py, commands.py |
| `opencode_reap()` callers | 2 | listener.py, commands.py |
| `parse_ndjson()` callers | 5 | chat.py, commands.py, query.py, vision.py, analyze.py |
| Custom NDJSON parser (not using lib) | 1 | identity.py |
| `shutil.which("opencode")` checks | 7 | commands.py, query.py, prerequisites.py, install.py, repair.py, features.py, identity.py |
| `_find_opencode()` callers | 1 | cron.py |
| Process kill patterns | 3 | control.py, uninstall.py |
| Config defaults referencing "opencode" | 2 | config.py |
| CLI doctor checks | 1 | cli.py |

---

## 2. Architecture Decision: Two Backends

Anthropic API keys still work with OpenCode. Only Claude **subscriptions**
(Pro/Team/Enterprise) are blocked from OpenCode. So we need two backends:

- **`opencode`** -- existing path, uses Anthropic API key (or any other provider)
- **`claude-cli`** -- new path, uses Claude Code CLI with Claude subscription auth

The Claude Agent SDK (`claude-agent-sdk` Python library) is NOT needed -- it uses
the same API keys that already work with OpenCode, adding a dependency for no benefit.

```
adjutant.yaml:
  llm:
    backend: "claude-cli"     # "opencode" | "claude-cli"

src/adjutant/
  core/
    backend.py                # Abstract protocol + factory + LLMResult
    backend_opencode.py       # OpenCode CLI backend (renamed from opencode.py)
    backend_claude_cli.py     # Claude Code CLI backend (claude -p)
  lib/
    ndjson.py                 # OpenCode NDJSON parser (unchanged)
    claude_json.py            # Claude Code --output-format json parser
```

### Why Two Backends (Not Three)

| Backend | Auth | Billing | Best For |
|---------|------|---------|----------|
| `opencode` | Anthropic API key (or other providers) | Pay-per-token via API | Users with API keys, non-Anthropic models |
| `claude-cli` | Claude subscription (Pro/Team/Enterprise) | Included in subscription | Users with Claude subscription |
| ~~`claude-sdk`~~ | ~~API key~~ | ~~Pay-per-token~~ | ~~Unnecessary -- same auth as opencode~~ |

### Backend Selection Logic

```python
def get_backend(config: AdjutantConfig) -> LLMBackend:
    name = config.llm.backend
    if name == "opencode":
        return OpenCodeBackend()
    elif name == "claude-cli":
        return ClaudeCLIBackend()
    raise ValueError(f"Unknown LLM backend: {name}")
```

---

## 3. Separation of Concerns: Python vs Backend

The split is clean and consistent. Python owns orchestration; the backend owns LLM execution.

```
PYTHON LAYER (adjutant)                 BACKEND LAYER (opencode / claude)
------------------------------          --------------------------------
Registry management (CRUD)              Agent definition loading
Name -> path resolution                 LLM conversation loop
Model tier resolution                   Tool execution (Read/Glob/Grep/Edit/Write)
CLI arg assembly                        Permission enforcement (sandbox)
Subprocess lifecycle                    Output stream (NDJSON / JSON)
Output parsing                          Session state (internal to backend)
Session file management                 Model routing to provider API
Timeout / error handling
Fire-and-forget dispatch
Telegram message delivery
Cron scheduling
```

**The boundary is a subprocess call.** Python builds the invocation, the backend
executes an autonomous LLM conversation with tool use, Python parses the output.
Python never enters the LLM loop. The backend never touches Telegram, registries,
or scheduling.

**KB scheduled operations (`kb_run`) do NOT use the backend.** They invoke the KB's
own Python CLI or bash scripts directly. Backend migration has zero impact on
portfolio fetch/analyze/news/reconcile cron jobs.

**Portfolio-kb has a NESTED backend dependency.** Its own Python code (`src/cli.py`
analyze pipeline) internally calls `opencode run` for LLM signal generation. This
is a secondary migration target -- decision deferred to implementation phase. It
currently works fine on API keys.

---

## 4. Detailed Coupling Analysis

### 4.1 Invocation Patterns (3 distinct patterns)

**Pattern A: Async `opencode_run()` with NDJSON parsing (primary path)**
Used by: `chat.py`, `commands.py`, `query.py` (reads), `vision.py`, `analyze.py`, `identity.py`

```python
result = await opencode_run(args, timeout=240)
parsed = parse_ndjson(result.stdout)
reply = parsed.text
session_id = parsed.session_id
```

**Pattern B: Synchronous `subprocess.run` (cron path)**
Used by: `cron.py`

```python
result = subprocess.run([opencode, "run", "--dir", str(adj_dir), prompt_text])
sys.exit(result.returncode)
```

**Pattern C: Detached `subprocess.Popen` (fire-and-forget)**
Used by: `query.py` (writes), `control.py` (web server)

```python
subprocess.Popen(["bash", "-c", shell_script], start_new_session=True)
```

### 4.2 Exact CLI Arguments Constructed Per Call Site

| Call Site | OpenCode Command |
|-----------|-----------------|
| `chat.py` | `opencode run --agent adjutant --dir <adj_dir> --format json --model <model> [--session <id>] "<message>"` |
| `commands.py` (pulse/reflect) | `opencode run --agent adjutant --dir <adj_dir> --format json --model <model> "<prompt_text>"` |
| `commands.py` (model list) | `opencode models` |
| `query.py` (read) | `opencode run --agent kb --dir <kb_path> --format json --model <model> "<query>"` |
| `query.py` (write) | `opencode run --agent kb --dir <kb_path> --format json --model <model> "<instruction>"` (detached) |
| `vision.py` | `opencode run --model <model> --format json -f <image_path> [-- "<prompt>"]` |
| `analyze.py` | `opencode run "<prompt>" --model <model> --format json` |
| `cron.py` | `opencode run --dir <adj_dir> "<prompt_text>"` |
| `identity.py` | `opencode --model anthropic/claude-haiku-4-5 --format json "<prompt>"` |
| `control.py` | `opencode web --mdns` (detached) |

### 4.3 Session Management Details (chat.py only)

- Session file: `state/telegram_session.json` with `{session_id, epoch, model}`
- Session reused within 2-hour timeout via `--session <id>` flag
- Model mismatch invalidates session (OpenCode hangs on cross-model resume)
- Session cleared on `/model` switch

**Claude Code equivalent:**
- CLI: `--resume <session_id>` (UUID format required)
- Session ID captured from JSON output: `result_json["session_id"]`

### 4.4 NDJSON Format vs Claude Code JSON Format

**OpenCode NDJSON (current):**
```json
{"type": "session.create", "properties": {"sessionID": "abc123"}}
{"type": "text", "part": {"text": "Hello "}}
{"type": "text", "part": {"text": "world"}}
{"type": "error", "error": {"name": "ModelNotFound", "data": {"message": "..."}}}
```

**Claude Code `--output-format json` (non-streaming, simpler):**
```json
{
  "result": "The assembled text response",
  "session_id": "uuid-string",
  "is_error": false,
  "cost_usd": 0.0042,
  "usage": {"input_tokens": 1234, "output_tokens": 567}
}
```

**Recommendation:** Use `--output-format json` for the CLI backend (simplest
parsing -- single JSON object with `result` field).

---

## 5. Phase 1: Backend Abstraction Layer

### 5.1 `src/adjutant/core/backend.py`

```python
"""LLM backend abstraction -- protocol, result types, factory."""

from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass
class LLMResult:
    """Unified result from any LLM backend invocation."""
    text: str
    session_id: str | None = None
    error_type: str | None = None
    returncode: int = 0
    timed_out: bool = False
    cost_usd: float | None = None


@dataclass(frozen=True)
class BackendCapabilities:
    """Declares which optional features a backend supports.

    Call sites MUST check capabilities before calling optional methods.
    This prevents silent no-ops and makes capability gaps explicit.
    """
    vision: bool = False          # Native image input (not via tool-use Read)
    model_listing: bool = False   # Dynamic model list from backend
    reaping: bool = False         # Orphan process cleanup
    web_server: bool = False      # Built-in web server (opencode web)
    streaming: bool = False       # Incremental output (NDJSON streaming)
    cost_tracking: bool = False   # Per-request cost_usd in LLMResult


class LLMBackend(Protocol):
    """Protocol all LLM backends must implement."""

    @property
    def name(self) -> str: ...

    @property
    def capabilities(self) -> BackendCapabilities: ...

    async def run(
        self, prompt: str, *,
        agent: str | None = None, workdir: Path | None = None,
        model: str | None = None, session_id: str | None = None,
        timeout: float | None = None, env: dict[str, str] | None = None,
        files: list[Path] | None = None,
    ) -> LLMResult: ...

    def run_detached(
        self, prompt: str, *,
        agent: str | None = None, workdir: Path | None = None,
        model: str | None = None, log_path: Path | None = None,
    ) -> None: ...

    def run_sync(
        self, prompt: str, *,
        workdir: Path | None = None, timeout: float | None = None,
    ) -> int: ...

    async def reap(self, adj_dir: Path) -> int: ...
    async def health_check(self, adj_dir: Path) -> bool: ...
    async def list_models(self) -> str: ...
    def find_binary(self) -> str | None: ...
    def resolve_alias(self, alias: str) -> str: ...
    def translate_model_id(self, model_id: str) -> str: ...


class BackendNotFoundError(Exception):
    """Raised when the backend binary is not available."""


def get_backend(backend_name: str | None = None) -> LLMBackend:
    """Factory: return the configured LLM backend."""
    if backend_name is None:
        from adjutant.core.config import get_config
        backend_name = get_config().llm.backend
    if backend_name == "opencode":
        from adjutant.core.backend_opencode import OpenCodeBackend
        return OpenCodeBackend()
    elif backend_name == "claude-cli":
        from adjutant.core.backend_claude_cli import ClaudeCLIBackend
        return ClaudeCLIBackend()
    raise ValueError(f"Unknown LLM backend: {backend_name!r}")
```

### 5.2 Key Design Decisions

1. **Three run methods** to cover all invocation patterns:
   - `run()` -- async, returns LLMResult (chat, commands, KB queries, vision, analyze)
   - `run_detached()` -- fire-and-forget for KB writes
   - `run_sync()` -- blocking for cron jobs

2. **`LLMResult` is the universal contract** -- all backends return the same
   dataclass. No more `OpenCodeResult` + `NDJSONResult` at call sites.

3. **Model resolution has two distinct operations:**
   - `resolve_alias(alias)` -- maps config shorthand to the backend's model ID.
     Used at call sites: `"sonnet"` → `"anthropic/claude-sonnet-4-6"` (OpenCode)
     or `"sonnet"` → `"sonnet"` (Claude CLI). If the input is not a known alias,
     it's passed through unchanged.
   - `translate_model_id(model_id)` -- converts a model ID from another backend's
     format to this backend's format. Used ONLY during backend switch (Section 16):
     `"anthropic/claude-sonnet-4-6"` → `"sonnet"` (Claude CLI) or vice versa.
     This is a cross-backend operation; `resolve_alias` is a within-backend
     operation. Keeping them separate prevents bugs where a full model ID stored
     in `state/telegram_model.txt` is misinterpreted as an alias.

4. **Agent/prompt handling is backend-specific** -- OpenCode uses `--agent`,
   Claude CLI uses `--system-prompt-file`.

5. **Backend capabilities are declared, not discovered.** Each backend exposes a
   `capabilities` property returning a `BackendCapabilities` dataclass. Call sites
   check capabilities before calling optional methods:

   ```python
   # In commands.py (model listing)
   backend = get_backend()
   if backend.capabilities.model_listing:
       models = await backend.list_models()
   else:
       await msg_send("Model listing is not available on the current backend.")

   # In listener.py (reaping)
   if backend.capabilities.reaping:
       count = await backend.reap(adj_dir)

   # In vision.py (native image input)
   if not backend.capabilities.vision and _has_image_files(files):
       return LLMResult(text="Vision not supported...", error_type="vision_unsupported")
   ```

   **Per-backend capability declarations:**

   | Capability | `opencode` | `claude-cli` |
   |---|---|---|
   | `vision` | Yes (`-f` flag) | No (no native image input) |
   | `model_listing` | Yes (`opencode models`) | No (hardcoded list) |
   | `reaping` | Yes (orphan language-server cleanup) | No (no orphan leak) |
   | `web_server` | Yes (`opencode web --mdns`) | No |
   | `streaming` | Yes (NDJSON incremental) | No (`--output-format json` blocks) |
   | `cost_tracking` | No (NDJSON has no cost data) | Yes (`cost_usd` in JSON output) |

   Methods like `reap()` and `list_models()` remain on the protocol -- they are
   still callable on all backends. But the implementation is a documented no-op
   when the capability is absent (`reap()` returns 0, `list_models()` returns a
   static string). The `capabilities` property lets call sites make informed
   decisions rather than calling a no-op and wondering why nothing happened.

6. **Backends are stateless.** `get_backend()` creates a new instance per call.
   Backends are lightweight subprocess launchers with no mutable state. If caching
   is needed in the future (e.g., binary path resolution), use a module-level
   `@functools.cache`.

---

## 6. Phase 2: Claude Code CLI Backend

### 6.1 `src/adjutant/core/backend_claude_cli.py`

**Binary:** `claude` (resolved via `CLAUDE_CODE_BIN` env var or `shutil.which("claude")`)

**Run method:** Spawns `claude -p` with `--output-format json`:
```python
args = [
    claude_bin, "-p",
    "--output-format", "json",
    "--model", self.resolve_alias(model),
    "--system-prompt-file", str(agent_prompt_file),
    "--dangerously-skip-permissions",
]
if session_id:
    args += ["--resume", session_id]
```

**`--dangerously-skip-permissions` security note:**

This flag is required for non-interactive subprocess mode -- without it, Claude
Code prompts for permission on each tool use, which blocks the subprocess
indefinitely. However, it has a critical security implication: **it bypasses
Claude Code's built-in permission deny rules entirely**. The `.claude/settings.json`
deny rules (Layer 1 of the three-layer defense, Section 19) become inert when
this flag is active.

This means the effective defense for `.env` protection on the Claude CLI backend is:
- ~~Layer 1: Permission deny rules~~ (bypassed by `--dangerously-skip-permissions`)
- **Layer 2: PreToolUse hooks** (still active -- hooks fire regardless of the flag)
- **Layer 3: System prompt** (still active)

The hooks in `.claude/hooks/` are therefore the **primary technical defense**,
not belt-and-suspenders redundancy. They MUST be present, executable, and tested.
`adjutant doctor` must verify hook script presence and permissions as a critical
check, not an informational one.

If Claude Code adds a non-interactive mode that respects deny rules (e.g.,
`--non-interactive` without bypassing permissions), migrate to that flag
immediately and restore the three-layer defense.

**Workspace scoping:** Uses `cwd=workdir` parameter on subprocess instead of `--dir`.

**Session management:**
- Session ID captured from JSON output: `result_json["session_id"]`
- Resume via `--resume <session_id>` (must be a UUID)
- OpenCode uses arbitrary string IDs; Claude Code requires UUIDs

**Agent/system prompt:**
- Uses `--system-prompt-file` to pass the agent definition's markdown body
- Frontmatter stripped; only the markdown body is passed
- This avoids CLAUDE.md auto-loading conflicts entirely

**File attachment (vision):**

Claude Code has no `-f` flag for direct file attachment. The strategy depends on
the file type and what Claude Code supports at invocation time:

1. **Primary: image path in prompt.** Claude Code's `-p` mode operates in the
   working directory. If the image file is accessible from `cwd`, include its path
   in the prompt text: `"Analyze the image at ./photos/image.jpg: <user prompt>"`.
   Claude Code's agent loop will use the Read tool to access the file. This works
   for images the LLM can process via tool use.

2. **Fallback: copy to workdir.** If the image is outside the workspace (e.g.,
   Telegram downloads to a temp directory), copy it into `workdir` before
   invocation. The backend's `run()` method handles this when `files` is provided:
   ```python
   if files:
       for f in files:
           dest = workdir / f.name
           shutil.copy2(f, dest)
       file_refs = ", ".join(f.name for f in files)
       prompt = f"[Attached files: {file_refs}]\n\n{prompt}"
   ```

3. **Known limitation: no native vision input.** OpenCode's `-f` flag sends the
   file as a vision content block (the image pixels are seen by the model directly).
   Claude Code's `-p` mode does not support this. When `files` is passed to the
   Claude CLI backend, the model sees the file via tool-use Read, NOT as a vision
   content block. For photographic images this is a **functional regression** --
   the model cannot "see" the image, only read text/binary content.

   **Handling:** When `files` contains image types (`.jpg`, `.png`, `.gif`, `.webp`)
   and the backend is `claude-cli`, `run()` should return an `LLMResult` with
   `error_type="vision_unsupported"` and `text` containing a user-facing message:
   `"Vision (image analysis) is not supported on the Claude CLI backend. Switch to the opencode backend for image analysis."`.

   Call sites (`vision.py`) should check for this error type and surface the
   limitation clearly rather than silently degrading to a text-only analysis.

4. **Future: monitor Claude CLI releases.** If `claude -p` gains stdin image
   piping or a `-f` equivalent, update the backend to use native vision input.
   Track at: https://docs.anthropic.com/en/docs/claude-code

**Model listing:**
- No direct equivalent to `opencode models`. Return hardcoded list of known models.

**Orphan cleanup:**
- Claude Code doesn't leak `bash-language-server` processes. Reaper is a no-op.

**Streaming / latency:**

OpenCode produces NDJSON events incrementally (text chunks arrive as they're
generated). Claude Code's `--output-format json` blocks until the entire
response is complete, then emits a single JSON object.

Adjutant currently waits for the full `opencode_run()` subprocess to complete
before parsing (`proc.communicate()` collects all stdout), so both backends
have the same wall-clock latency at the call site level. However, this is a
**UX-visible difference for long responses**: OpenCode's streaming means the
subprocess appears "alive" throughout, while Claude CLI is silent until done.

This matters if Adjutant ever adds:
- Typing indicators based on output activity (the Telegram "typing..." indicator
  would go stale during Claude CLI's silent processing)
- Partial response delivery (sending chunks to the user as they arrive)
- Progress tracking / cancellation based on output activity

**Current impact:** None -- all call sites wait for completion. But this should
be documented as a known behavioral difference in the user-facing backend guide
(`docs/guides/backends.md`) so users understand why Claude CLI responses may
*feel* slower even if wall-clock time is similar.

**Future:** If `claude -p` gains a streaming JSON output mode (e.g.,
`--output-format stream-json`), update the backend to use it and set
`capabilities.streaming = True`.

### 6.2 `src/adjutant/lib/claude_json.py`

```python
@dataclass
class ClaudeJSONResult:
    text: str = ""
    session_id: str | None = None
    error_type: str | None = None
    is_error: bool = False
    cost_usd: float | None = None

def parse_claude_json(output: str) -> ClaudeJSONResult:
    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        return ClaudeJSONResult(error_type="parse_error")

    is_error = data.get("is_error", False)
    error_type = None
    if is_error:
        error_type = _classify_claude_error(data.get("result", ""))

    return ClaudeJSONResult(
        text=data.get("result", ""),
        session_id=data.get("session_id"),
        is_error=is_error,
        cost_usd=data.get("cost_usd"),
        error_type=error_type,
    )


def _classify_claude_error(result_text: str) -> str:
    """Map Claude Code error text to the common error taxonomy.

    Claude Code's --output-format json sets is_error=true and puts the error
    description in the result field. We pattern-match on known error messages
    to classify into actionable error types.
    """
    text = result_text.lower()

    # Model errors
    if "model not found" in text or "invalid model" in text:
        return "model_not_found"

    # Auth / subscription errors
    if any(s in text for s in [
        "not authenticated", "authentication", "login required",
        "unauthorized", "forbidden", "subscription",
        "please log in", "session expired",
    ]):
        return "auth_failure"

    # Rate limiting (Claude subscription 5-hour rolling window)
    if any(s in text for s in [
        "rate limit", "too many requests", "throttl", "capacity",
    ]):
        return "rate_limited"

    # Context overflow
    if any(s in text for s in [
        "context length", "too long", "max tokens", "context window",
        "token limit",
    ]):
        return "context_overflow"

    # Permission / sandbox errors
    if any(s in text for s in [
        "permission denied", "not allowed", "permission",
    ]):
        return "permission_denied"

    return "error"
```

### 6.3 Common Error Taxonomy

All backends must map their errors to this shared taxonomy. Call sites use these
`error_type` values to decide how to respond. This ensures consistent behavior
regardless of which backend is active.

| `error_type` | Meaning | Call Site Action |
|---|---|---|
| `None` | Success | Use `result.text` normally |
| `"model_not_found"` | Requested model does not exist | Tell user to check model name; do NOT retry |
| `"auth_failure"` | API key invalid / subscription expired / not logged in | Tell user to check credentials; do NOT retry |
| `"rate_limited"` | Backend-specific rate limit hit | Exponential backoff; tell user to wait |
| `"context_overflow"` | Conversation too long for context window | Clear session; retry with fresh conversation |
| `"permission_denied"` | Sandbox or permission system blocked the operation | Log; tell user to check backend permissions |
| `"vision_unsupported"` | Backend does not support native vision input | Tell user to switch backends; do NOT retry |
| `"timeout"` | Subprocess exceeded timeout | Set via `LLMResult.timed_out`; tell user to retry |
| `"parse_error"` | Backend output could not be parsed | Log raw output; tell user to retry |
| `"error"` | Unclassified error | Log; surface `result.text` to user for diagnosis |

**OpenCode parity:** `parse_ndjson` currently only detects `model_not_found`.
As part of migration, extend `parse_ndjson` to classify OpenCode errors into the
same taxonomy. OpenCode errors appear in NDJSON `error` events with
`error.data.message` and `error.name` fields, and in stderr. At minimum, match
the same patterns above against those fields. This ensures call sites get
consistent `error_type` values from both backends.

**Backend `run()` responsibility:** Each backend's `run()` method must:
1. Parse the output using its format-specific parser
2. Map `returncode` to `error_type` when the parser can't classify (e.g.,
   non-zero exit with no JSON output → `"error"`)
3. Populate `LLMResult.error_type` from the parser result
4. Set `LLMResult.timed_out = True` (and `error_type = "timeout"`) on timeout

**Retry guidance:** Call sites should NOT implement their own retry logic. If
retry/backoff is needed (for `rate_limited` errors), it should be handled inside
the backend's `run()` method with a configurable max-retries, so retry behavior
is consistent. Initial implementation: zero retries (fail immediately). Retry
logic is a follow-up enhancement.

### 6.4 Per-Request Observability

Every backend `run()` / `run_sync()` call must log which backend handled the
request and how long it took. Without this, debugging production issues and
comparing backend performance after a switch is guesswork.

**Implementation in each backend's `run()` method:**

```python
async def run(self, prompt: str, **kwargs) -> LLMResult:
    start = time.monotonic()
    try:
        result = await self._execute(prompt, **kwargs)
        elapsed = time.monotonic() - start
        adj_log("backend", f"[{self.name}] run completed in {elapsed:.1f}s"
                f" | model={kwargs.get('model')} agent={kwargs.get('agent')}"
                f" | error_type={result.error_type}")
        return result
    except Exception as exc:
        elapsed = time.monotonic() - start
        adj_log("backend", f"[{self.name}] run FAILED in {elapsed:.1f}s"
                f" | model={kwargs.get('model')} error={exc!r}")
        raise
```

**What gets logged:**
- Backend name (`opencode` / `claude-cli`) -- tags every request
- Wall-clock duration -- enables latency comparison between backends
- Model and agent -- for request identification
- Error type -- for error rate tracking
- Exception details on failure -- for debugging

**Where it logs:** Uses `adj_log("backend", ...)` consistent with existing
Adjutant logging conventions. This writes to `journal/adjutant.log`.

**Cost tracking (claude-cli only):** When `result.cost_usd` is populated,
include it in the log line: `cost=$0.0042`. OpenCode does not provide cost
data (NDJSON has no cost field), so this field is omitted for the opencode backend.

---

## 7. Phase 3: Call Site Migration

### 7.1 Migration Table (Every File That Changes)

| File | Current Code | New Code | Complexity |
|------|-------------|----------|------------|
| `messaging/telegram/chat.py` | `opencode_run(args)` + `parse_ndjson()` | `backend.run(message, agent="adjutant", model=model, session_id=sid)` | Medium |
| `messaging/telegram/commands.py` | `opencode_run(args)` + `opencode models` | `backend.run(prompt, agent="adjutant", model=model)` + `backend.list_models()` | Medium |
| `capabilities/kb/query.py` (reads) | `opencode_run(args)` + `parse_ndjson()` | `backend.run(query, agent="kb", workdir=kb_path, model=model)` | Low |
| `capabilities/kb/query.py` (writes) | `subprocess.Popen` shell wrapper | `backend.run_detached(instruction, agent="kb", workdir=kb_path)` | Medium |
| `capabilities/vision/vision.py` | `opencode_run(args)` with `-f` flag | `backend.run(prompt, model=model, files=[image_path])` | Medium |
| `news/analyze.py` | `asyncio.run(opencode_run(args))` | `asyncio.run(backend.run(prompt, model=model))` | Low |
| `lifecycle/cron.py` | `subprocess.run([opencode, ...])` | `backend.run_sync(prompt, workdir=adj_dir)` | Low |
| `lifecycle/control.py` | `subprocess.Popen(["opencode", "web"])` | Conditional: skip for non-opencode backends | Low |
| `messaging/telegram/listener.py` | `opencode_reap()` + web watchdog | `backend.reap(adj_dir)` + conditional watchdog | Low |
| `setup/steps/identity.py` | `asyncio.run(opencode_run(...))` | `asyncio.run(backend.run(prompt, model="haiku"))` | Low |
| `setup/steps/prerequisites.py` | `shutil.which("opencode")` | `backend.find_binary()` | Low |
| `setup/install.py` | `shutil.which("opencode")` | `backend.find_binary()` | Low |
| `setup/repair.py` | `shutil.which("opencode")` | `backend.find_binary()` | Low |
| `setup/steps/features.py` | `shutil.which("opencode")` | `backend.find_binary()` | Low |
| `setup/uninstall.py` | `_pkill("opencode web")` | Conditional on backend | Low |
| `cli.py` | `OpenCodeNotFoundError` | `BackendNotFoundError` + backend-aware doctor | Low |
| `core/config.py` | `backend: str = "opencode"` | Add validation for `"claude-cli"` | Low |

### 7.2 Before/After Example (chat.py)

**BEFORE:**
```python
from adjutant.core.opencode import OpenCodeNotFoundError, opencode_run
from adjutant.lib.ndjson import parse_ndjson

args = ["run", "--agent", "adjutant", "--dir", str(adj_dir),
        "--format", "json", "--model", model]
if existing_session:
    args += ["--session", existing_session]
args.append(message)

result = await opencode_run(args, timeout=chat_timeout)
parsed = parse_ndjson(result.stdout)
reply = parsed.text
new_sid = parsed.session_id
```

**AFTER:**
```python
from adjutant.core.backend import BackendNotFoundError, get_backend

backend = get_backend()
result = await backend.run(
    message, agent="adjutant", workdir=adj_dir,
    model=model, session_id=existing_session, timeout=chat_timeout,
)
reply = result.text
new_sid = result.session_id
```

---

## 8. Phase 4: Agent Definitions & Permissions

### 8.1 Agent Prompt Strategy: `--system-prompt-file`

For Claude Code backend, we use `--system-prompt-file` instead of `--agent`. This:
- Avoids CLAUDE.md auto-loading conflicts
- Gives full control over what the model sees
- Reuses the same prompt markdown body from the OpenCode agent definition

**Implementation:** The backend reads the agent file, strips YAML frontmatter,
passes the markdown body via `--system-prompt-file`.

### 8.2 Agent Prompt Files (Single Source of Truth)

**Problem:** Having separate prompt files for each backend (`.opencode/agents/adjutant.md`
with frontmatter and `prompts/agents/adjutant.md` body-only) creates two copies of
the same prompt content that will inevitably drift. When the prompt is updated in
one file but not the other, the two backends silently diverge in behavior.

**Solution:** `.opencode/agents/adjutant.md` remains the **single source of truth**.
Both backends read from this file. The backend is responsible for extracting what
it needs:

- **OpenCode backend:** passes the file path via `--agent adjutant` (unchanged --
  OpenCode reads the frontmatter + body natively).
- **Claude CLI backend:** reads the file at runtime, strips the YAML frontmatter,
  writes the markdown body to a temp file, and passes it via `--system-prompt-file`.

```python
# In ClaudeCLIBackend.run():
def _extract_prompt_body(agent_file: Path) -> str:
    """Strip YAML frontmatter, return markdown body."""
    content = agent_file.read_text()
    if content.startswith("---"):
        _, _, body = content.split("---", 2)
        return body.strip()
    return content
```

**No `prompts/agents/` directory is needed.** The original plan's extraction step
is eliminated. There is exactly one file per agent, and both backends use it.

**KB agent prompts follow the same pattern:** `.opencode/agents/kb.md` in each KB
directory is the source of truth. The Claude CLI backend strips frontmatter at
runtime. For KBs like hopen that already have `.claude/agents/kb.md`, that file
should be removed during migration -- the single source is `.opencode/agents/kb.md`.

### 8.3 Permission Mapping

**For Claude CLI backend**, create `.claude/settings.json`:
```json
{
  "permissions": {
    "allow": ["Read", "Glob", "Grep", "Bash(*)", "Edit", "Write"],
    "deny": [
      "Read(.env)", "Read(**/.env)", "Read(**/.env.*)",
      "Read(**/*secret*)", "Read(**/*credential*)",
      "Bash(cat .env*)", "Bash(cat **/.env)",
      "Bash(head .env*)", "Bash(tail .env*)",
      "Bash(grep* .env*)", "Bash(less .env*)",
      "Bash(source .env*)", "Bash(env)", "Bash(printenv*)",
      "Bash(*export -p*)", "Bash(*declare -p*)", "Bash(set)"
    ]
  }
}
```

**For OpenCode backend**, `opencode.json` remains unchanged.

---

## 9. Phase 5: KB Review & Migration

### 9.1 Existing KB Inventory

All 6 KBs are registered in `knowledge_bases/registry.yaml`. All live on
`/Volumes/Mandalor/JottaSync/AI_knowledge_bases/`. All are `read-write`.

| KB | opencode.json | .opencode/agents/kb.md | .claude/ | Model (registry) | Model (kb.yaml) |
|---|---|---|---|---|---|
| ixda | Yes (no `external_directory: deny`) | Yes (custom) | None | `anthropic/claude-sonnet-4-6` | `inherit` **(DRIFT)** |
| fagkomite | **MISSING** | Yes (custom, 5 extra agents) | Yes (`settings.local.json`) | `anthropic/claude-sonnet-4-6` | **MISSING** |
| portfolio | Yes (bash ALLOWED, Playwright MCP, NO .env deny) | Yes (complex, 188-line) | None | `cheap` | `medium` **(DRIFT)** |
| munich-summer2026 | Yes (standard) | Yes (standard) | None | `inherit` | `inherit` |
| hopen | Yes (standard) | Yes (custom, Norwegian) | Yes (`.claude/agents/kb.md`) | `inherit` | `inherit` |
| smaabruksbryggeri | Yes (standard) | Yes (standard) | None | `inherit` | `inherit` |

### 9.2 KB Categories for Migration

**Category A: Standard scaffold** (munich-summer2026, smaabruksbryggeri)
- Clean template-generated structure
- Migration: generate `.claude/settings.json` + hooks from templates

**Category B: Custom KBs** (ixda, fagkomite, hopen)
- Hand-edited agent prompts with KB-specific content
- Migration: generate `.claude/settings.json` but preserve custom agent prompts
- hopen already has dual-backend files -- validates the approach

**Category C: Full project KB** (portfolio-kb)
- Own Python CLI, git repo, test suite, Playwright MCP
- `opencode.json` allows everything (bash, write, edit)
- **No `.env` deny rules** -- hooks become the ONLY protection
- Migration: most complex; careful permission + MCP translation needed

### 9.3 Pre-Migration Remediation

**Fix fagkomite** (missing kb.yaml + opencode.json):
- Generate `kb.yaml` from registry entry values
- Generate `opencode.json` with standard read-write sandbox rules

**Fix model drift** (registry is source of truth):
- `ixda/kb.yaml`: model to match registry
- `portfolio-kb/kb.yaml`: model to match registry

**Fix ixda opencode.json**: add `"external_directory": "deny"`

### 9.4 Per-KB Claude Code Migration

For each KB, the claude-cli backend needs `.claude/settings.json` + `.claude/hooks/`.

Standard KB (bash denied, read-write):
```json
{
  "permissions": {
    "allow": ["Read", "Edit", "Write", "Glob", "Grep"],
    "deny": ["Bash(*)", "Read(.env)", "Read(**/.env)", "Read(**/.env.*)",
             "Read(**/*secret*)", "Read(**/*credential*)"]
  },
  "hooks": {
    "PreToolUse": [
      {"matcher":"Read","hooks":[{"type":"command","command":"\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/block-env-read.sh"}]}
    ]
  }
}
```

Portfolio-kb (bash ALLOWED, Playwright MCP):
```json
{
  "permissions": {
    "allow": ["Read", "Edit", "Write", "Glob", "Grep", "Bash(*)"]
  },
  "mcpServers": {
    "playwright": {
      "command": "playwright-mcp",
      "args": ["--user-agent", "Mozilla/5.0 ...", "--init-script", "scripts/playwright-stealth.js"]
    }
  },
  "hooks": {
    "PreToolUse": [
      {"matcher":"Bash","hooks":[{"type":"command","command":"\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/block-env-access.sh"}]},
      {"matcher":"Read","hooks":[{"type":"command","command":"\"$CLAUDE_PROJECT_DIR\"/.claude/hooks/block-env-read.sh"}]}
    ]
  }
}
```

### 9.5 KB Scheduled Operations: Zero Impact

`kb_run()` does NOT use the LLM backend. It invokes the KB's own Python CLI or
bash scripts directly. Backend migration has zero impact on cron-triggered operations.

**Exception**: Portfolio-kb's `analyze` pipeline internally calls `opencode run`.
This nested dependency is deferred -- it works on API keys today.

---

## 10. Phase 6: KB Template System

### 10.1 Updated KB Scaffold (Backend-aware)

```python
def kb_scaffold(adj_dir, name, kb_path, description, model, access):
    # Always write OpenCode scaffold (baseline)
    _write_kb_opencode_json(kb_path, access)
    _render_template("templates/kb/agents/kb.md",
                     kb_path / ".opencode" / "agents" / "kb.md", vars)

    # ALSO write Claude scaffold
    _write_kb_claude_settings(kb_path, access)
    _write_kb_claude_hooks(kb_path)
```

Both scaffolds are written so the KB works regardless of which backend is active.
This matches the dual-backend pattern already proven by hopen.

### 10.2 New Template Files

- `templates/kb/claude/settings.json` -- read-only KB permissions
- `templates/kb/claude/settings-rw.json` -- read-write KB permissions
- Both include hooks for `.env` protection

---

## 11. Phase 7: Config, Setup & Model Resolution

### 11.1 adjutant.yaml Changes

```yaml
llm:
  backend: "claude-cli"           # "opencode" | "claude-cli"
  models:
    cheap: "haiku"
    medium: "sonnet"
    expensive: "opus"
```

### 11.2 Model ID Translation

| Alias | OpenCode | Claude CLI |
|-------|----------|------------|
| `haiku` | `anthropic/claude-haiku-4-5` | `haiku` |
| `sonnet` | `anthropic/claude-sonnet-4-6` | `sonnet` |
| `opus` | `anthropic/claude-opus-4-6` | `opus` |

If the config value is not an alias, it's passed through unchanged.

### 11.3 Setup Wizard

**`setup/steps/prerequisites.py`:**
- `opencode`: `shutil.which("opencode")`
- `claude-cli`: `shutil.which("claude")`

**New step: `setup/steps/backend.py`:**
```
Which LLM backend would you like to use?

  1. OpenCode (default)
     -> Uses `opencode` CLI, requires API key

  2. Claude Code CLI
     -> Uses `claude` CLI, works with Claude subscription
```

### 11.4 Config Validation

```python
class LLMConfig(BaseModel):
    backend: str = "opencode"

    @field_validator("backend")
    @classmethod
    def validate_backend(cls, v):
        valid = {"opencode", "claude-cli"}
        if v not in valid:
            raise ValueError(f"llm.backend must be one of {valid}, got {v!r}")
        return v
```

---

## 12. Phase 8: Backend-Aware Test Organization

### 12.1 Problem

After the migration, the test suite has three categories:

| Category | Examples | When to run |
|---|---|---|
| **Backend-neutral** | `test_backend.py`, all consumer tests (chat, kb_query, vision, etc.) | Always |
| **OpenCode-specific** | `test_opencode.py`, `test_ndjson.py`, `test_backend_opencode.py` | Only when opencode is active |
| **Claude CLI-specific** | `test_backend_claude_cli.py`, `test_claude_json.py`, `test_security_hooks.py` | Only when claude-cli is active |

Running OpenCode-specific tests when `claude-cli` is selected wastes time and
may fail if the `opencode` binary is not installed. Vice versa for Claude tests.

### 12.2 Solution: pytest Markers + Auto-Skip

**New markers in `pyproject.toml`:**
```toml
[tool.pytest.ini_options]
markers = [
    "unit: Unit tests (no external calls, fast)",
    "integration: Integration tests (mocked external calls)",
    "slow: Slow tests (skip with -m 'not slow')",
    "bash: Tests that invoke bash scripts",
    "backend_opencode: Tests specific to the OpenCode backend",
    "backend_claude_cli: Tests specific to the Claude CLI backend",
]
```

**Mark backend-specific test files:**
```python
# test_opencode.py, test_ndjson.py, test_backend_opencode.py
import pytest
pytestmark = pytest.mark.backend_opencode

# test_backend_claude_cli.py, test_claude_json.py, test_security_hooks.py
import pytest
pytestmark = pytest.mark.backend_claude_cli
```

**Auto-skip logic in `tests/conftest.py`:**
```python
def pytest_addoption(parser):
    parser.addoption(
        "--run-all-backends", action="store_true", default=False,
        help="Run tests for ALL backends, not just the active one",
    )

def _get_active_backend() -> str:
    """Read active backend from adjutant.yaml if it exists.

    Uses AdjutantConfig.load() for correct nested YAML parsing rather than
    line-scanning (which would incorrectly match messaging.backend or other
    nested 'backend:' keys).
    """
    for candidate in [
        Path.home() / ".adjutant" / "adjutant.yaml",
        Path(__file__).parent.parent / "adjutant.yaml",
    ]:
        if candidate.exists():
            try:
                from adjutant.core.config import AdjutantConfig
                config = AdjutantConfig.load(candidate)
                return config.llm.backend
            except Exception:
                pass  # Fall through to default on parse failure
    return "opencode"

def pytest_collection_modifyitems(config, items):
    """Auto-skip backend-specific tests when that backend is not active."""
    if config.getoption("--run-all-backends", default=False):
        return
    markexpr = config.getoption("-m", default="")
    if "backend_opencode" in markexpr or "backend_claude_cli" in markexpr:
        return

    active = _get_active_backend()
    skip_oc = pytest.mark.skip(reason="opencode backend not active")
    skip_cc = pytest.mark.skip(reason="claude-cli backend not active")

    for item in items:
        if "backend_opencode" in item.keywords and active != "opencode":
            item.add_marker(skip_oc)
        if "backend_claude_cli" in item.keywords and active != "claude-cli":
            item.add_marker(skip_cc)
```

### 12.3 Usage Patterns

```bash
# Normal run: only tests for the active backend + neutral tests
.venv/bin/pytest tests/ -q

# Force all backends (e.g., before a release)
.venv/bin/pytest tests/ -q --run-all-backends

# Run only opencode tests
.venv/bin/pytest tests/ -q -m backend_opencode

# Run only claude-cli tests
.venv/bin/pytest tests/ -q -m backend_claude_cli

# Run only backend-neutral tests
.venv/bin/pytest tests/ -q -m "not backend_opencode and not backend_claude_cli"
```

### 12.4 Test File Classification

| File | Marker | Rationale |
|------|--------|-----------|
| `test_opencode.py` | `backend_opencode` | Tests OpenCode internals |
| `test_ndjson.py` | `backend_opencode` | Tests OpenCode NDJSON parser |
| `test_backend_opencode.py` (new) | `backend_opencode` | Tests `OpenCodeBackend` wrapper |
| `test_backend_claude_cli.py` (new) | `backend_claude_cli` | Tests `ClaudeCLIBackend` |
| `test_claude_json.py` (new) | `backend_claude_cli` | Tests Claude JSON parser |
| `test_security_hooks.py` (new) | `backend_claude_cli` | Tests hook scripts |
| `test_backend.py` (new) | *(none)* | Factory, LLMResult, BackendCapabilities -- neutral |
| `test_backend_switch.py` (new) | *(none)* | Switch detection + nested dependency warning -- neutral |
| `test_backend_contract.py` (new) | `slow` | Cross-backend equivalence (requires both binaries) |
| `test_telegram_chat.py` | *(none)* | Mocks `backend.run()` -- neutral |
| `test_kb_query.py` | *(none)* | Mocks `backend.run()` -- neutral |
| `test_vision.py` | *(none)* | Mocks `backend.run()` -- neutral |
| `test_news_analyze.py` | *(none)* | Mocks `backend.run()` -- neutral |
| `test_cron.py` | *(none)* | Mocks `backend.run_sync()` -- neutral |
| `test_telegram_commands.py` | *(none)* | Mocks `backend.run()` -- neutral |

### 12.5 New Fixtures

```python
@pytest.fixture()
def mock_claude(tmp_path, monkeypatch):
    """Fake claude binary that returns a valid JSON response."""
    script = tmp_path / "claude"
    script.write_text(
        '#!/bin/bash\n'
        'echo \'{"result":"OK","session_id":"test-uuid-123","is_error":false}\'\n'
    )
    script.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path) + ":" + os.environ.get("PATH", ""))
    return script
```

### 12.6 Consumer Test Migration

Consumer tests replace `_oc_result()`/`_nd_result()` helpers with:

```python
def _llm_result(text="OK", session_id=None, error_type=None, returncode=0, timed_out=False):
    return LLMResult(text=text, session_id=session_id, error_type=error_type,
                     returncode=returncode, timed_out=timed_out)
```

Mock target changes from `adjutant.core.opencode.opencode_run` to
`adjutant.core.backend.get_backend`.

### 12.7 Backend Contract Tests

Backend-neutral consumer tests mock `backend.run()` and verify call site logic.
But nothing verifies that both backends produce structurally equivalent `LLMResult`
values for the same input. Without this, the abstraction is "correct by coincidence"
-- it works because both backends happen to populate the same fields today, but
there's no test that would catch a drift.

**`test_backend_contract.py`** -- parametrized tests that run the same prompt
through both backends and assert structural equivalence of the result:

```python
import pytest
from adjutant.core.backend import get_backend, LLMResult

BACKENDS = ["opencode", "claude-cli"]

def _backend_available(name: str) -> bool:
    try:
        b = get_backend(name)
        return b.find_binary() is not None
    except Exception:
        return False

@pytest.mark.slow
@pytest.mark.parametrize("backend_name", BACKENDS)
def test_simple_prompt_returns_valid_result(backend_name, adj_dir):
    """Both backends return a well-formed LLMResult for a trivial prompt."""
    if not _backend_available(backend_name):
        pytest.skip(f"{backend_name} binary not available")

    backend = get_backend(backend_name)
    import asyncio
    result = asyncio.run(backend.run(
        "Reply with exactly: hello",
        model="haiku", timeout=30,
    ))
    assert isinstance(result, LLMResult)
    assert result.text  # Non-empty
    assert result.returncode == 0
    assert result.timed_out is False
    assert result.error_type is None

@pytest.mark.slow
@pytest.mark.parametrize("backend_name", BACKENDS)
def test_session_id_returned(backend_name, adj_dir):
    """Both backends return a session_id that can be used for resume."""
    if not _backend_available(backend_name):
        pytest.skip(f"{backend_name} binary not available")

    backend = get_backend(backend_name)
    import asyncio
    result = asyncio.run(backend.run(
        "Reply with exactly: hi",
        agent="adjutant", workdir=adj_dir, model="haiku", timeout=30,
    ))
    assert result.session_id is not None
    assert len(result.session_id) > 0
```

**Marker:** *(none)* -- these are backend-neutral (they parametrize over both).
They require both binaries to be installed and are marked `@pytest.mark.slow`.
Run with `--run-all-backends` or `-m slow`.

**Test file classification update:**

| File | Marker | Rationale |
|------|--------|-----------|
| `test_backend_contract.py` (new) | `slow` | Runs real prompts through both backends |

---

## 13. CLAUDE.md Conflict Resolution

**Problem:** Claude Code auto-loads `CLAUDE.md` from the working directory.

**Solution:** Use `--system-prompt-file` for the CLI backend. This **replaces the
entire system prompt**, including CLAUDE.md loading.

**Result:** No CLAUDE.md files needed for programmatic use. Complete prompt control.

**Note:** A `CLAUDE.md` file IS created for interactive developer use (see Section 20).

---

## 14. Billing & Rate Limiting

| Backend | Auth Method | Billing | Rate Limits |
|---------|-------------|---------|-------------|
| `opencode` | Anthropic API key (or other) | Pay-per-token via API | Provider-specific |
| `claude-cli` | Claude subscription | Included in subscription | 5-hour rolling window |

**Recommendation:**
- API key users: stay on `opencode`
- Subscription users: switch to `claude-cli`
- Non-Anthropic models: stay on `opencode`

---

## 15. Process Lifecycle & Orphan Management

### 15.1 OpenCode Backend (unchanged)
- `opencode_reap()` kills orphaned `bash-language-server` processes
- `opencode web --mdns` web server management via PID files

### 15.2 Claude CLI Backend
- No language-server leak. Reaper is a no-op.
- No web server to manage.
- `health_check()` verifies `claude` binary exists

### 15.3 Lifecycle Control Changes

```python
def start_opencode_web(adj_dir):
    if get_config(adj_dir).llm.backend != "opencode":
        return "opencode web: skipped (not using opencode backend)"

def emergency_kill(adj_dir):
    backend_name = get_config(adj_dir).llm.backend
    if backend_name == "opencode":
        _kill_by_pattern(f"opencode.*{adj_dir}", signal.SIGTERM)
    elif backend_name == "claude-cli":
        _kill_by_pattern(f"claude.*{adj_dir}", signal.SIGTERM)
```

---

## 16. Backend Switch Detection & Side Effects

### 16.1 Detection Mechanism

At startup, `lifecycle/control.py` compares `adjutant.yaml llm.backend` against
`state/backend.txt` (single-line file recording the last-known backend). If they
differ, `_handle_backend_switch()` fires.

```python
def _detect_backend_change(adj_dir: Path) -> str | None:
    state_file = adj_dir / "state" / "backend.txt"
    current = get_config(adj_dir).llm.backend
    if state_file.exists():
        previous = state_file.read_text().strip()
        if previous != current:
            return previous
    state_file.write_text(current)
    return None
```

Detection happens ONLY at startup -- not hot-reloaded. User must restart after
changing `adjutant.yaml`.

### 16.2 Side Effects Handled

| # | Side Effect | Action | Why |
|---|---|---|---|
| 1 | Session IDs are backend-specific | Delete `state/telegram_session.json` | OpenCode uses strings; Claude uses UUIDs |
| 2 | Model ID format differs | Translate via `backend.translate_model_id()` | `anthropic/claude-sonnet-4-6` vs `sonnet` |
| 3 | Orphaned opencode web server | Kill `opencode web --mdns` if switching away | Leaves zombie process |
| 4 | Binary not installed | Validate `backend.find_binary()` | Fail fast with install instructions |
| 5 | KBs missing scaffold files | Auto-generate `.claude/` or `opencode.json` for all KBs | KB queries would fail |
| 6 | Crontab references wrong binary | Re-sync crontab via `schedule sync` | Entries baked at install time |
| 7 | Record new backend | Write `state/backend.txt` | Prevent re-triggering |
| 8 | Log the switch | `adj_log("backend", f"Switched from {old} to {new}")` | Audit trail |
| 9 | Warn about nested backend dependencies | Log + notify if portfolio-kb uses OpenCode internally | User may not realize API key is still required |

### 16.3 Implementation

```python
def _handle_backend_switch(adj_dir: Path, old_backend: str, new_backend: str) -> None:
    # 1. Clear active session
    session_file = adj_dir / "state" / "telegram_session.json"
    if session_file.exists():
        session_file.unlink()

    # 2. Translate model ID (cross-backend format conversion)
    model_file = adj_dir / "state" / "telegram_model.txt"
    if model_file.exists():
        current_model = model_file.read_text().strip()
        backend = get_backend(new_backend)
        new_model = backend.translate_model_id(current_model)
        if new_model != current_model:
            model_file.write_text(new_model)

    # 3. Stop old backend services
    if old_backend == "opencode":
        _stop_opencode_web(adj_dir)

    # 4. Validate new backend binary
    backend = get_backend(new_backend)
    if not backend.find_binary():
        raise BackendNotFoundError(...)

    # 5. Auto-generate missing KB scaffold files
    for kb in kb_list(adj_dir):
        _ensure_kb_scaffold(Path(kb.path), new_backend, kb.access)

    # 6. Re-sync crontab
    from adjutant.capabilities.schedule.install import schedule_sync
    schedule_sync(adj_dir)

    # 7. Record new backend
    (adj_dir / "state" / "backend.txt").write_text(new_backend)

    # 8. Log
    adj_log("backend", f"Switched from {old_backend} to {new_backend}")

    # 9. Warn about nested backend dependencies
    if new_backend == "claude-cli":
        _warn_nested_opencode_dependencies(adj_dir)


def _warn_nested_opencode_dependencies(adj_dir: Path) -> None:
    """Warn about KBs that internally call opencode, which still need an API key.

    Portfolio-kb's analyze pipeline (`src/cli.py`) internally calls `opencode run`
    for LLM signal generation. Switching to claude-cli does NOT affect this nested
    dependency -- it will still require a working OpenCode installation and API key.
    Users who switch to claude-cli to avoid needing an API key will find portfolio
    analysis broken with no obvious error unless we warn them.
    """
    # Check if portfolio-kb is registered
    known_nested = []
    for kb in kb_list(adj_dir):
        if kb.name == "portfolio" or "portfolio" in str(getattr(kb, "path", "")):
            known_nested.append(kb.name)

    if known_nested:
        msg = (
            f"Warning: KB(s) {known_nested} internally use OpenCode for LLM calls. "
            f"These still require a working `opencode` binary and API key even though "
            f"the main backend is now claude-cli. Their analyze pipelines will fail if "
            f"OpenCode is not installed or the API key is missing."
        )
        adj_log("backend", msg)
        # Also surface via doctor check (see 16.4)
```

### 16.4 Doctor Integration

`adjutant doctor` gains a backend health check:

```
LLM Backend
  Backend:     claude-cli
  Binary:      /usr/local/bin/claude (found)
  State file:  state/backend.txt (claude-cli)
  Session:     state/telegram_session.json (none -- clean)
  Model:       claude-sonnet-4-6 (valid for claude-cli)
  Hooks:       .claude/hooks/block-env-access.sh (OK, executable)
               .claude/hooks/block-env-read.sh (OK, executable)
  KBs:
    ixda:              .claude/settings.json OK, hooks OK
    fagkomite:         .claude/settings.json OK, hooks OK
    portfolio:         .claude/settings.json OK, hooks OK (bash allowed)
                       WARNING: uses opencode internally (API key required)
    munich-summer2026: .claude/settings.json OK, hooks OK
    hopen:             .claude/settings.json OK, hooks OK
    smaabruksbryggeri: .claude/settings.json OK, hooks OK
```

**Hook checks are errors, not warnings.** Since `--dangerously-skip-permissions`
bypasses deny rules (see Section 6.1), hooks are the primary technical defense.
Missing or non-executable hook scripts should cause `adjutant doctor` to exit
with a non-zero status and a clear error message.

---

## 17. Migration Checklist

### New Files to Create (11 source files)

| File | Purpose |
|------|---------|
| `src/adjutant/core/backend.py` | Abstract protocol + factory |
| `src/adjutant/core/backend_opencode.py` | OpenCode backend (wraps existing opencode.py) |
| `src/adjutant/core/backend_claude_cli.py` | Claude Code CLI backend |
| `src/adjutant/lib/claude_json.py` | Claude Code JSON output parser |
| `src/adjutant/setup/steps/backend.py` | Setup wizard backend selection step |
| `.claude/hooks/block-env-access.sh` | Bash env-file access hook |
| `.claude/hooks/block-env-read.sh` | Read env-file access hook |
| `.claude/settings.json` | Claude Code permissions + hooks config |
| `templates/kb/claude/settings.json` | KB permissions for Claude (read-only) |
| `templates/kb/claude/settings-rw.json` | KB permissions for Claude (read-write) |
| `templates/kb/claude/hooks/block-env-read.sh` | KB-level Read env hook template |

### KB Remediation Files (pre-migration fixes)

| File | Action |
|------|--------|
| `fagkomite/kb.yaml` | **Create** -- from registry entry |
| `fagkomite/opencode.json` | **Create** -- standard read-write sandbox |
| `ixda/opencode.json` | **Fix** -- add `external_directory: deny` |
| `ixda/kb.yaml` | **Fix** -- model to match registry |
| `portfolio-kb/kb.yaml` | **Fix** -- model to match registry |

### Per-KB Claude Code Files (6 KBs)

| KB | Files to Create |
|---|---|
| ixda | `.claude/settings.json`, `.claude/hooks/block-env-read.sh` |
| fagkomite | `.claude/settings.json`, `.claude/hooks/block-env-read.sh` |
| portfolio-kb | `.claude/settings.json` (Playwright MCP + bash), `.claude/hooks/block-env-access.sh`, `.claude/hooks/block-env-read.sh` |
| munich-summer2026 | `.claude/settings.json`, `.claude/hooks/block-env-read.sh` |
| hopen | `.claude/settings.json`, `.claude/hooks/block-env-read.sh` |
| smaabruksbryggeri | `.claude/settings.json`, `.claude/hooks/block-env-read.sh` |

### Existing Files to Modify (17 files)

| File | Change |
|------|--------|
| `core/opencode.py` | Rename to `core/backend_opencode.py` or keep as internal |
| `core/config.py` | Add backend validation |
| `messaging/telegram/chat.py` | Use `backend.run()` |
| `messaging/telegram/commands.py` | Use `backend.run()`, `backend.list_models()` |
| `messaging/telegram/listener.py` | Use `backend.reap()`, conditional watchdog |
| `capabilities/kb/query.py` | Use `backend.run()`, `backend.run_detached()` |
| `capabilities/kb/manage.py` | Backend-aware scaffold |
| `capabilities/vision/vision.py` | Use `backend.run()` with files param |
| `news/analyze.py` | Use `backend.run()` |
| `lifecycle/cron.py` | Use `backend.run_sync()` |
| `lifecycle/control.py` | Conditional web server + switch detection |
| `setup/steps/identity.py` | Use `backend.run()` |
| `setup/steps/prerequisites.py` | Use `backend.find_binary()` |
| `setup/install.py` | Use `backend.find_binary()` |
| `setup/repair.py` | Use `backend.find_binary()` |
| `setup/uninstall.py` | Conditional process cleanup |
| `cli.py` | `BackendNotFoundError`, backend-aware doctor |

### Test Files to Modify/Create (15 files)

| File | Action | Marker |
|------|--------|--------|
| `test_opencode.py` | Keep as-is | `backend_opencode` |
| `test_ndjson.py` | Keep as-is | `backend_opencode` |
| `test_backend.py` | **Create** -- factory, LLMResult, BackendCapabilities | *(none)* |
| `test_backend_opencode.py` | **Create** -- OpenCodeBackend | `backend_opencode` |
| `test_backend_claude_cli.py` | **Create** -- ClaudeCLIBackend | `backend_claude_cli` |
| `test_claude_json.py` | **Create** -- JSON parser + `_classify_claude_error()` | `backend_claude_cli` |
| `test_security_hooks.py` | **Create** -- env bypass vectors | `backend_claude_cli` |
| `test_backend_switch.py` | **Create** -- switch detection + nested dependency warning | *(none)* |
| `test_backend_contract.py` | **Create** -- parametrized cross-backend equivalence | `slow` |
| `test_telegram_chat.py` | **Update** -- mock backend.run | *(none)* |
| `test_telegram_commands.py` | **Update** -- mock backend.run + capabilities check | *(none)* |
| `test_kb_query.py` | **Update** -- mock backend.run | *(none)* |
| `test_vision.py` | **Update** -- mock backend.run + vision_unsupported error | *(none)* |
| `test_news_analyze.py` | **Update** -- mock backend.run | *(none)* |
| `test_cron.py` | **Update** -- mock backend.run_sync | *(none)* |

---

## 18. Risk Register

| Risk | Impact | Mitigation |
|------|--------|------------|
| Claude Code `--output-format json` schema changes | Parser breaks | Pin version; defensive parsing |
| `--system-prompt-file` doesn't fully suppress CLAUDE.md | Prompt conflict | Test empirically; fall back to inline `--system-prompt` |
| Session ID format incompatibility | Resume fails | Session storage detects format; generate UUIDs for Claude |
| Claude subscription rate limits hit during heavy use | Throttled | Exponential backoff; surface errors clearly |
| Vision file attachment via piped stdin unreliable | Image analysis broken | Test piping; fall back to temp file in workdir |
| `--dangerously-skip-permissions` disabled by org policy | Runs fail | Detect permission prompts; fall back to `.claude/settings.json` allow rules |
| KB writes via `run_detached()` lose output | No confirmation | Log to adjutant.log; monitor for completion |
| Existing tests break during migration | CI failure | Migrate incrementally; keep OpenCode tests passing |
| `.env` bypass via creative Bash | Credential leak | Three-layer defense + bypass vector testing |
| Hook scripts not executable at deploy | Hooks silently fail | `adjutant doctor` checks; setup wizard `chmod +x` |
| portfolio-kb has NO .env deny in opencode.json | Leak on opencode | Add deny rules in pre-migration remediation |
| fagkomite missing kb.yaml + opencode.json | Wrong model/no sandbox | Generate from registry in remediation |
| Registry vs kb.yaml model drift | Wrong model used | Fix drift: registry is source of truth |
| Portfolio-kb nested opencode dependency | Analysis unaffected by switch | Deferred -- works on API keys today; warn on switch (Section 16.3 step 9) |
| Vision not supported on Claude CLI backend | Image analysis broken for claude-cli users | Return `error_type="vision_unsupported"` with clear message; document limitation |
| `--dangerously-skip-permissions` bypasses deny rules | `.env` deny rules in `.claude/settings.json` are inert | Hooks are primary defense; doctor checks hooks as errors not warnings (Section 6.1, 19.2) |
| Claude CLI error messages unclassified | Generic "error" instead of actionable error types | Pattern-match on error text in `_classify_claude_error()`; extend as new patterns discovered |
| No streaming on Claude CLI backend | Perceived latency regression for long responses | Document as known limitation; monitor for `--output-format stream-json` support |
| Agent prompt drift between backends | Backends silently diverge in behavior | Single source of truth: `.opencode/agents/` files; Claude CLI strips frontmatter at runtime (Section 8.2) |

---

## 19. Environment File Security (Hooks & Defense-in-Depth)

### 19.1 The Problem

Claude Code's permission system has a critical gap:

> "Read and Edit deny rules apply to Claude's built-in file tools, not to Bash
> subprocesses. A `Read(./.env)` deny rule blocks the Read tool but does not
> prevent `cat .env` in Bash."

Static deny rules are a first line of defense only. `PreToolUse` hooks provide
the second defense layer.

### 19.2 Three-Layer Defense Strategy

| Layer | What It Catches | Implementation | Status with `--dangerously-skip-permissions` |
|-------|----------------|----------------|----------------------------------------------|
| **1. Permission deny rules** | Direct Read/Glob tool access | `.claude/settings.json` deny rules | **BYPASSED** -- flag disables all deny rules |
| **2. PreToolUse hooks** | Bash commands that read env files | Hook scripts in `.claude/hooks/` | **ACTIVE** -- hooks fire regardless of flag |
| **3. System prompt** | LLM-level instruction | "Don't read `.env`" in `adjutant.md` | **ACTIVE** -- prompt is always sent |

**Important:** Because `--dangerously-skip-permissions` is required for
non-interactive subprocess mode (see Section 6.1), the Claude CLI backend
effectively operates with a **two-layer defense**. Layer 1 deny rules are
written to `.claude/settings.json` for completeness (they protect interactive
developer sessions, and will become active if a non-interactive mode that
respects deny rules becomes available), but they do NOT protect programmatic
invocations.

This makes the PreToolUse hooks the **primary technical defense** against `.env`
exfiltration on the Claude CLI backend. Hook scripts must be treated as
security-critical code:
- `adjutant doctor` must flag missing or non-executable hooks as **errors**, not warnings
- `test_security_hooks.py` must cover bypass vectors (symlinks, path traversal,
  encoding tricks, indirect reads via `source`, `eval`, `xargs`, etc.)
- Hook failures (exit code != 0 and != 2) should be logged and investigated

### 19.3 Hook Scripts

**`.claude/hooks/block-env-access.sh`** -- blocks Bash env access:
- Matches `.env` patterns (excluding `.env.example`)
- Blocks `printenv`, `env`, `export -p`, `declare -p`
- Blocks sourcing `.env` files
- Blocks reading credential/secret files via Bash
- Returns `exit 2` to deny the tool call

**`.claude/hooks/block-env-read.sh`** -- blocks Read tool env access:
- Matches `.env` file paths (excluding `.env.example`)
- Blocks credential/secret file paths
- Belt-and-suspenders redundancy with permission deny rules

### 19.4 KB Sub-agents

- **OpenCode backend**: `opencode.json` denies `.env` (except portfolio-kb -- needs fix)
- **Claude CLI backend**: KB `.claude/settings.json` includes deny rules + hooks

---

## 20. Documentation Plan

### 20.1 New Documents (5 files)

#### `docs/guides/backends.md` -- User-Facing Backend Guide (HIGH)

Covers: overview, prerequisites, initial setup step-by-step, switching backends
step-by-step (what to change, what happens automatically, what to verify),
model configuration, KB compatibility, permission and security model, troubleshooting.

#### `docs/architecture/backends.md` -- Architecture Deep Dive (HIGH)

Covers: separation of concerns, backend protocol, OpenCode internals, Claude CLI
internals, switch detection, agent prompt handling, KB sub-agent invocation.

#### `docs/development/backend-guide.md` -- Developer Guide (HIGH)

Covers: rules (dual-backend parity, never import impls directly, register switch
state), adding a feature that uses the LLM (5-step checklist), adding a third
backend (10-step checklist), testing backends, backend-specific state files.

#### `CLAUDE.md` -- Claude Code Developer Instructions (MEDIUM)

For developers using Claude Code interactively on the adjutant repo:

```markdown
# CLAUDE.md

Read AGENTS.md for the full builder guide.

## Critical Rules

1. Never read .env files. Use `get_credential()` from `core/env.py`.
2. Never read KB directories directly. Use `kb query` CLI.
3. All LLM features must support both backends (opencode + claude-cli).
   Use `core/backend.py` -- never import backend implementations directly.
4. When adding backend-dependent state, register cleanup in
   `_handle_backend_switch()` so it's handled on backend changes.
5. Run the full test suite before committing: `.venv/bin/pytest tests/ -q`
```

Note: `--system-prompt-file` suppresses CLAUDE.md for programmatic use. This
file only applies to interactive developer sessions.

#### `docs/reference/backend-migration-log.md` -- Migration Reference (LOW)

Historical record: why, what changed, pre-migration remediation, known limitations.

### 20.2 Existing Documents to Update (8 files)

#### `AGENTS.md` (HIGH)

**Hard Rules** -- add:

```markdown
2. **Dual-backend parity.** Any feature that touches the LLM backend MUST work
   on both `opencode` and `claude-cli`. Never import from `backend_opencode.py`
   or `backend_claude_cli.py` directly -- always use `core/backend.py`.

3. **Backend switch side effects.** When adding state files, crontab entries,
   or any artifact that depends on the active backend, register it in
   `_handle_backend_switch()` so it gets cleaned up on backend changes.
```

**Repo Map** -- update core/ and lib/ listings.

**Adding a Capability** -- add steps 8-9:

```markdown
8. **If the feature invokes the LLM backend**: use `backend.run()` /
   `backend.run_detached()` / `backend.run_sync()` from `core/backend.py`.
   Never call `opencode` or `claude` CLI directly. Test with both backends.
9. **If the feature creates backend-dependent state**: register cleanup
   in `_handle_backend_switch()`.
```

**New section: "LLM Backend Architecture"** -- protocol, factory, switching, file table.

**Gotchas** -- update:
- Replace NDJSONResult/OpenCodeResult gotcha with LLMResult guidance
- Add "never use opencode_run() directly" gotcha
- Add hook scripts chmod gotcha

#### `docs/guides/configuration.md` (HIGH)

- New section: "LLM Backend" (`llm.backend` setting, how to switch)
- Update `opencode.json` section (note: opencode backend only)
- New section: `.claude/settings.json` (deny rules, hooks, MCP)
- New section: `.claude/hooks/` (what scripts do, `.env` protection)

#### `docs/guides/knowledge-bases.md` (MEDIUM)

- Update "Required files" (both opencode.json and .claude/settings.json)
- New section: "Backend Compatibility" (dual support, auto-generation on switch)

#### `docs/architecture/overview.md` (MEDIUM)

- Rename "OpenCode" layer to "LLM Backend (opencode | claude-cli)"
- Update core/ module list

#### `docs/architecture/identity.md` (MEDIUM)

- Rename "OpenCode integration" to "LLM Backend integration"
- Update security model for dual permission systems

#### `docs/architecture/design-decisions.md` (LOW)

- Add ADR: "Dual LLM backend support" -- why, tradeoffs, rejected alternative

#### `docs/development/plugin-guide.md` (MEDIUM)

- Update checklist: step 8 (use backend.run()), step 9 (register switch state)

#### `docs/README.md` (MEDIUM)

- Add new docs to the index table

### 20.3 Total Documentation Scope

| Action | Count |
|--------|-------|
| Create | 5 new docs |
| Update | 8 existing docs |
| Mirror to adjutant-docs/ | 13 files |
| **Total** | **13 source + 13 mirrors** |

---

## 21. Implementation Order

### Step 0: Pre-migration remediation
- Fix fagkomite: generate missing `kb.yaml` + `opencode.json`
- Fix model drift: update `ixda/kb.yaml` and `portfolio-kb/kb.yaml` to match registry
- Fix ixda `opencode.json`: add `external_directory: deny`
- Fix portfolio-kb `opencode.json`: add `.env` deny rules

### Step 1: Backend abstraction (zero behavior change)
- Create `backend.py` (protocol + factory + LLMResult + BackendCapabilities)
- Include `resolve_alias()` and `translate_model_id()` as separate protocol methods
- Include `name` property and `capabilities` property on the protocol
- Create `backend_opencode.py` (wraps existing `opencode.py`)
- Declare OpenCode capabilities: `vision=True, model_listing=True, reaping=True, web_server=True, streaming=True`
- Add per-request observability logging in `run()` / `run_sync()` (Section 6.4)
- All existing tests must continue passing unchanged

### Step 2: First call site migration
- Migrate `analyze.py` (simplest call site) to use `backend.run()`
- Update `test_news_analyze.py`
- Run full test suite -- confirm zero regressions

### Step 3: Claude CLI backend
- Create `backend_claude_cli.py` + `claude_json.py` (including `_classify_claude_error()` error taxonomy)
- Declare Claude CLI capabilities: `cost_tracking=True` (all others False)
- Implement vision `files` param: copy-to-workdir for non-images, `vision_unsupported` error for images
- Implement agent prompt handling: read `.opencode/agents/*.md`, strip frontmatter, pass via `--system-prompt-file`
- Create `.claude/settings.json` for adjutant root
- Create `.claude/hooks/block-env-access.sh` + `block-env-read.sh`
- Create `test_backend_claude_cli.py` + `test_claude_json.py` (including error classification tests)
- Document `--dangerously-skip-permissions` implications in code comments

### Step 4: Migrate remaining call sites
- chat.py, commands.py, query.py, vision.py, cron.py, control.py, listener.py, identity.py, prerequisites.py
- `commands.py`: check `backend.capabilities.model_listing` before calling `list_models()`
- `vision.py`: check `backend.capabilities.vision`; handle `vision_unsupported` error type
- `listener.py`: check `backend.capabilities.reaping` before calling `reap()`
- Extend `parse_ndjson` to classify errors into the common taxonomy (Section 6.3)
- Update corresponding tests (including vision_unsupported and capabilities checks)

### Step 5: KB migration
- Generate `.claude/settings.json` + hooks for all 6 KBs
- Special handling for portfolio-kb (bash allowed, Playwright MCP, env hooks)
- Remove hopen's `.claude/agents/kb.md` -- single source of truth is `.opencode/agents/kb.md`
- Verify Claude CLI backend correctly strips frontmatter from each KB's agent prompt
- Update `manage.py` scaffold to generate both OpenCode + Claude files
- Update KB templates

### Step 6: Config + setup wizard + switch detection
- Update `adjutant.yaml` schema + validation
- Backend selection in setup wizard
- Implement `_detect_backend_change()` + `_handle_backend_switch()` in `lifecycle/control.py`
- Include `translate_model_id()` call (not `resolve_alias()`) for model file conversion
- Include `_warn_nested_opencode_dependencies()` for portfolio-kb (step 9 in Section 16.3)
- Add `state/backend.txt` state file
- `adjutant doctor` checks: backend binary, hook script permissions (**errors** for missing/non-executable hooks), KB scaffolds, nested dependency warnings

### Step 7: Backend-aware test infrastructure
- Add `backend_opencode` / `backend_claude_cli` / `slow` markers to pyproject.toml
- Add auto-skip logic to `tests/conftest.py` with `--run-all-backends` flag
  - Use `AdjutantConfig.load()` for YAML parsing (not line-scanning)
- Mark existing test files (`test_opencode.py`, `test_ndjson.py`)
- Add `mock_claude` fixture
- Create `test_backend.py` (factory, LLMResult, BackendCapabilities)
- Create `test_backend_switch.py` (switch detection + nested dependency warning)
- Create `test_security_hooks.py` (env bypass vectors)
- Create `test_backend_contract.py` (parametrized cross-backend equivalence, `@pytest.mark.slow`)
- Migrate consumer test helpers (`_oc_result` -> `_llm_result`)
- Run full suite with `--run-all-backends` to verify

### Step 8: Documentation
- Create `docs/guides/backends.md` (user guide)
- Create `docs/architecture/backends.md` (architecture)
- Create `docs/development/backend-guide.md` (developer guide)
- Create `CLAUDE.md` (interactive dev instructions)
- Update AGENTS.md (hard rules, repo map, capability checklist, backend section, gotchas)
- Update `docs/guides/configuration.md` (backend config, .claude/settings.json, hooks)
- Update `docs/guides/knowledge-bases.md` (backend compatibility)
- Update `docs/architecture/overview.md`, `identity.md`, `design-decisions.md`
- Update `docs/development/plugin-guide.md`
- Update `docs/README.md` (index)
- Mirror all changes to `adjutant-docs/`
- Create `docs/reference/backend-migration-log.md`

### Step 9: Final verification
- End-to-end testing with each backend
- Run `test_backend_contract.py` with both binaries installed
- Security audit: attempt `.env` bypass vectors against Claude CLI backend
- Verify `--dangerously-skip-permissions` does NOT make hooks ineffective
- Test vision on claude-cli backend: confirm `vision_unsupported` error, not silent failure
- Test error taxonomy: trigger rate limit, auth failure, model-not-found on Claude CLI
- Run full test suite with `--run-all-backends`
- Verify `adjutant doctor` passes for both backends (hooks flagged as errors when missing)
- Document known behavioral differences (streaming, vision) in `docs/guides/backends.md`
