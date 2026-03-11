# Adjutant Python Rewrite Plan — Complete Coverage

**Version:** 2.5  
**Date:** 2026-03-09  
**Status:** Phase 1 Complete — Phase 2 Not Started

**Changelog:**
- **v2.5:** Updated plan to reflect Phase 1 implementation reality. Module structure corrected to `src/adjutant/` layout (avoids conflict with bash `adjutant` entrypoint at repo root). `process.py` uses standalone functions (not `ProcessManager` class) — plan code samples updated. `ndjson.py` returns `NDJSONResult` dataclass (not `tuple[str, str | None, str | None]`) — plan code samples updated. Phase 1 test count updated from ~148 to 198 (actual), with per-file breakdowns. Added `test_logging.py` (22 tests) and `test_config.py` (15 tests) which were missing from the Phase 1 test table. Removed `tests/fixtures/` directory from tree (Phase 1 uses `conftest.py` fixtures instead). Added phase annotations to module tree. Updated pyproject.toml section to match actual (entrypoint is `adjutant.cli:main` via src layout). All `ProcessManager.*` references in plan code samples updated to standalone function calls.
- **v2.4:** Expanded Phases 2, 4, 5, 6 to full behavioral contract parity with Phases 1 & 3 (plan grew from 2,148 → 4,864 lines). Phase 2: registry CRUD with 3 code paths, name validation regex, scaffold template rendering with conditional overwrite rules, query model resolution chain, run.py stderr merge. Phase 4: schedule YAML storage + crontab sync + notify wrapper (always exit 0), screenshot Playwright + two-stage send + caption truncation, vision model chain + `-f` flag + ModelNotFoundError handling, search Brave API + count clamping. Phase 5: 4-state machine (2 lockfiles), startup recovery mode + 3-branch OpenCode web detection, emergency_kill 4-phase sequence + KILLED-first ordering, pause/resume flag-only ops, cron handler PAUSED/KILLED fix, update semver + backup + rsync, wizard 7-step fatal/non-fatal, repair 10 checks, uninstall "yes" confirm. Phase 6: news fetch HN/Reddit/RSS with timeout fix + null fix + regex escape fix, analyze dedup + keyword pre-filter + proper JSON extraction (not greedy grep), briefing operational check + notification-failure isolation fix + URL-based dedup fix, status dashboard + cron_to_human, usage JSONL tracker, journal gzip + truncate-not-delete rotation. Phase 7: added crontab migration procedure + agent definition audit checklist. Updated module tree with all new files. Updated test file list.
- **v2.3:** Final completeness audit — fixed 3 blockers (route_command, opencode.py module location, NDJSON naming), 15 gaps (photo dedup, session injection, notification budget, quiet hours, pending_reflect persistence, cmd_kb parsing, inline orphan cleanup, timeout convention, sync/async KB query, service PID tiers, Phase 2+ tests), 10 nitpicks (sanitize tab char, length limit note, dispatch_message signature, inventory count, etc.).
- **v2.2:** Fixed 26 issues found during deep review against bash source code. Fixed reaper rule (b), subprocess timeout pattern, health check endpoint/restart logic, in-flight task cancellation, dispatch_photo, rate limiter behavioral parity, session format, single-instance lock, message sanitization. Added dev tooling spec. Deferred pydantic to Phase 3. Detailed Phase 1 test groups. Added conftest.py config fixture. Detailed Phase 7 integration points.
- **v2.1:** Added Security & Authorization, Concurrency Model, Process Management, Chat Session Management, Error Handling. Updated module structure, dependencies, effort estimates.
- **v2.0:** Initial complete coverage plan.
- **v1.0:** Targeted plan (superseded).

---

## Executive Summary

This document provides a **comprehensive migration plan** to rewrite the entire Adjutant codebase from bash to Python, covering all 54 scripts, 518 tests, and ensuring full compatibility with existing knowledge bases.

**Recommendation:** A **phased migration** with a hybrid architecture during transition. Python becomes the orchestration layer; bash scripts are replaced incrementally. Existing KBs continue working unchanged throughout.

---

## Current Codebase Inventory

### Scripts (54 files, 9,602 lines)

| Directory | Files | Lines | Purpose |
|-----------|-------|-------|---------|
| `scripts/common/` | 6 | 864 | Core libraries (paths, env, logging, platform, opencode, lockfiles) |
| `scripts/messaging/` | 8 | 1,529 | Telegram backend + adaptor + dispatch |
| `scripts/messaging/telegram/` | 8 | 1,451 | send, chat, photos, reply, notify, listener, commands, service |
| `scripts/capabilities/kb/` | 3 | 759 | KB manage, query, run |
| `scripts/capabilities/schedule/` | 3 | 596 | Schedule manage, install, notify_wrap |
| `scripts/capabilities/screenshot/` | 1 | 147 | Screenshot capability |
| `scripts/capabilities/vision/` | 1 | 118 | Vision capability |
| `scripts/capabilities/search/` | 1 | 97 | Search capability |
| `scripts/lifecycle/` | 8 | 1,252 | start, stop, restart, pause, resume, kill, update, startup, cron jobs |
| `scripts/setup/` | 13 | 2,636 | wizard, install, uninstall, repair, steps/* |
| `scripts/news/` | 3 | 486 | fetch, analyze, briefing |
| `scripts/observability/` | 3 | 564 | status, usage_estimate, journal_rotate |
| `adjutant` (CLI) | 1 | 384 | Main entrypoint dispatcher |

### Tests (518 tests, ~7,100 lines)

| Directory | Count | Purpose |
|-----------|-------|---------|
| `tests/unit/` | ~350 | Pure logic tests |
| `tests/integration/` | ~168 | Mock curl/opencode via PATH |

### Knowledge Bases (Existing)

KBs are **OpenCode sub-agent workspaces** with this structure:
```
<kb-path>/
├── kb.yaml                 # Metadata (name, model, access, description)
├── .opencode/agents/kb.md  # Sub-agent definition
├── opencode.json           # Sandboxed permissions
├── data/current.md         # Live status (sub-agent reads this first)
├── knowledge/              # Stable reference docs
├── history/                # Archived records
└── templates/              # Reusable formats
```

**KBs are NOT rewritten.** They remain as-is. The Python code only:
1. Reads the KB registry (`knowledge_bases/registry.yaml`)
2. Invokes `opencode run --agent kb --dir <kb-path>`
3. Parses NDJSON output from OpenCode

---

## Architecture: Python + OpenCode

```
┌─────────────────────────────────────────────────────────────────┐
│                         adjutant CLI                             │
│                    (Python entrypoint)                           │
└──────────────────────────┬──────────────────────────────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
        ▼                  ▼                  ▼
┌───────────────┐  ┌───────────────┐  ┌───────────────┐
│   messaging/  │  │  capabilities/│  │   lifecycle/  │
│   (Python)    │  │   (Python)    │  │   (Python)    │
└───────┬───────┘  └───────┬───────┘  └───────┬───────┘
        │                  │                  │
        │                  │                  │
        ▼                  ▼                  ▼
┌───────────────┐  ┌───────────────┐  ┌───────────────┐
│Telegram API   │  │  KB Query     │  │  OpenCode     │
│(httpx)        │  │  (opencode)   │  │  (opencode)   │
└───────────────┘  └───────┬───────┘  └───────────────┘
                           │
                           ▼
                   ┌───────────────┐
                   │  KB Workspace │
                   │  (unchanged)  │
                   │  - kb.yaml    │
                   │  - knowledge/ │
                   │  - data/      │
                   └───────────────┘
```

---

## Module Structure

> **Note:** The Python package uses a `src/` layout (`src/adjutant/`) because the repo root
> contains a bash file named `adjutant` that would conflict with a top-level `adjutant/` package.

```
adjutant/                            # Repository root
├── src/
│   └── adjutant/                    # Python package
│       ├── __init__.py
│       ├── __main__.py              # python -m adjutant entrypoint
│       ├── cli.py                   # Click CLI commands
│       │
│       ├── core/                    # Core libraries (Phase 1 ✓)
│       │   ├── __init__.py
│       │   ├── paths.py             # ADJ_DIR resolution
│       │   ├── env.py               # Credential loading
│       │   ├── logging.py           # Structured logging
│       │   ├── platform.py          # OS detection
│       │   ├── lockfiles.py         # State management (paused/killed)
│       │   ├── config.py            # YAML config loading (PyYAML)
│       │   ├── model.py             # Model tier resolution
│       │   ├── process.py           # Process management (psutil, PidLock)
│       │   └── opencode.py          # opencode_run(), opencode_reap(), opencode_health_check()
│       │
│       ├── messaging/               # Messaging layer (Phase 3)
│       │   ├── __init__.py
│       │   ├── adaptor.py           # Backend-agnostic interface
│       │   ├── telegram/            # Telegram backend
│       │   │   ├── __init__.py
│       │   │   ├── api.py           # HTTP client (httpx)
│       │   │   ├── listener.py      # Long polling loop (asyncio)
│       │   │   ├── commands.py      # /command handlers
│       │   │   ├── send.py          # Send text/photos
│       │   │   ├── photos.py        # Photo download, dedup, vision routing, session injection
│       │   │   ├── reply.py         # Reply markup
│       │   │   ├── notify.py        # Push notifications
│       │   │   ├── session.py       # OpenCode session management (2h timeout)
│       │   │   ├── auth.py          # Single-user authorization
│       │   │   └── service.py       # start/stop/status (daemon management)
│       │   └── dispatch.py          # Message router (auth → rate limit → reflect → route)
│       │
│       ├── capabilities/            # Capabilities (Phases 2 & 4)
│       │   ├── __init__.py
│       │   ├── kb/                  # Knowledge base management
│       │   │   ├── __init__.py
│       │   │   ├── registry.py      # KB CRUD (registry.yaml)
│       │   │   ├── query.py         # KB query via OpenCode
│       │   │   ├── scaffold.py      # KB creation from templates
│       │   │   └── run.py           # KB-local operations
│       │   ├── schedule/            # Scheduled jobs
│       │   │   ├── __init__.py
│       │   │   ├── registry.py      # Job CRUD
│       │   │   ├── crontab.py       # Crontab sync
│       │   │   └── runner.py        # Job execution
│       │   ├── screenshot/          # Screenshot capability
│       │   │   ├── __init__.py
│       │   │   └── capture.py       # Playwright wrapper
│       │   ├── vision/              # Vision capability
│       │   │   ├── __init__.py
│       │   │   └── analyze.py       # Image analysis
│       │   └── search/              # Search capability
│       │       ├── __init__.py
│       │       └── brave.py         # Brave Search API
│       │
│       ├── lifecycle/               # Lifecycle management (Phase 5)
│       │   ├── __init__.py
│       │   ├── state.py             # State helpers (is_paused, is_killed, get_state)
│       │   ├── start.py             # Start services
│       │   ├── stop.py              # Stop services
│       │   ├── restart.py           # Restart services
│       │   ├── pause.py             # Soft pause (flag only)
│       │   ├── resume.py            # Resume from pause (flag only)
│       │   ├── kill.py              # Emergency shutdown (4-phase kill)
│       │   ├── update.py            # Self-update from GitHub releases
│       │   ├── startup.py           # Full startup/recovery orchestration
│       │   └── cron.py              # Cron job handlers (pulse, review)
│       │
│       ├── setup/                   # Setup/installation (Phase 5)
│       │   ├── __init__.py
│       │   ├── wizard.py            # Interactive 7-step setup
│       │   ├── install.py           # Installer
│       │   ├── uninstall.py         # Uninstaller
│       │   ├── repair.py            # Health check/repair (10 checks)
│       │   └── steps/               # Wizard steps
│       │       ├── __init__.py
│       │       ├── prerequisites.py  # Dependency checking
│       │       ├── install_path.py   # Directory creation
│       │       ├── identity.py       # LLM-generated soul.md/heart.md
│       │       ├── messaging.py      # Telegram token + chat ID
│       │       ├── features.py       # 5 feature toggles
│       │       ├── service.py        # Platform service install + CLI alias
│       │       ├── autonomy.py       # Pulse/review schedule enable
│       │       ├── kb_wizard.py      # KB creation wizard
│       │       └── schedule_wizard.py # Schedule creation wizard
│       │
│       ├── news/                    # News pipeline (Phase 6)
│       │   ├── __init__.py
│       │   ├── fetch.py             # Multi-source fetching (HN, Reddit, blogs/RSS)
│       │   ├── analyze.py           # Dedup + Haiku-powered ranking
│       │   └── briefing.py          # Pipeline orchestrator
│       │
│       ├── observability/           # Observability (Phase 6)
│       │   ├── __init__.py
│       │   ├── status.py            # System status dashboard
│       │   ├── usage.py             # Token usage estimation (JSONL)
│       │   └── journal.py           # Journal/log rotation
│       │
│       └── lib/                     # Shared utilities (Phase 1 ✓)
│           ├── __init__.py
│           └── ndjson.py            # NDJSON parser (parse_ndjson → NDJSONResult)
│
├── tests/                           # pytest suite
│   ├── conftest.py
│   ├── unit/
│   │   ├── test_paths.py            # Phase 1 ✓ (14 tests)
│   │   ├── test_env.py              # Phase 1 ✓ (20 tests)
│   │   ├── test_logging.py          # Phase 1 ✓ (22 tests)
│   │   ├── test_platform.py         # Phase 1 ✓ (14 tests)
│   │   ├── test_lockfiles.py        # Phase 1 ✓ (24 tests)
│   │   ├── test_config.py           # Phase 1 ✓ (15 tests)
│   │   ├── test_model.py            # Phase 1 ✓ (14 tests)
│   │   ├── test_process.py          # Phase 1 ✓ (15 tests)
│   │   ├── test_opencode.py         # Phase 1 ✓ (12 tests)
│   │   ├── test_ndjson.py           # Phase 1 ✓ (21 tests)
│   │   ├── test_kb_registry.py      # Phase 2
│   │   ├── test_kb_scaffold.py      # Phase 2
│   │   ├── test_kb_query.py         # Phase 2
│   │   ├── test_schedule_registry.py # Phase 4
│   │   ├── test_schedule_crontab.py # Phase 4
│   │   ├── test_screenshot.py       # Phase 4
│   │   ├── test_vision.py           # Phase 4
│   │   ├── test_search.py           # Phase 4
│   │   ├── test_lifecycle_state.py  # Phase 5
│   │   ├── test_startup.py          # Phase 5
│   │   ├── test_kill.py             # Phase 5
│   │   ├── test_update.py           # Phase 5
│   │   ├── test_cron.py             # Phase 5
│   │   ├── test_wizard.py           # Phase 5
│   │   ├── test_repair.py           # Phase 5
│   │   ├── test_news_fetch.py       # Phase 6
│   │   ├── test_news_analyze.py     # Phase 6
│   │   ├── test_news_briefing.py    # Phase 6
│   │   ├── test_status.py           # Phase 6
│   │   ├── test_usage.py            # Phase 6
│   │   └── test_journal_rotate.py   # Phase 6
│   └── integration/
│       ├── test_dispatch.py         # Phase 3
│       ├── test_kb_query.py         # Phase 2
│       ├── test_kb_endtoend.py      # Phase 2
│       ├── test_telegram_api.py     # Phase 3
│       ├── test_schedule_crontab.py # Phase 4
│       ├── test_news_pipeline.py    # Phase 6
│       ├── test_lifecycle_endtoend.py # Phase 5
│       └── ...
│
├── templates/kb/                    # KB templates (unchanged)
├── knowledge_bases/                 # KB workspaces (unchanged)
├── identity/                        # Personal identity (unchanged)
├── state/                           # Runtime state (unchanged)
├── adjutant                         # Bash CLI entrypoint (kept during transition)
├── pyproject.toml                   # Python project config (src layout, hatchling)
└── adjutant.yaml.example            # Config template (unchanged)
```

---

## KB Compatibility Guarantee

### What Changes

| Component | Current (bash) | New (Python) |
|-----------|----------------|--------------|
| KB registry CRUD | `kb_*()` functions in manage.sh | `adjutant.capabilities.kb.registry` module |
| KB query | `opencode run` + `jq` parsing | `opencode run` + Python NDJSON parsing |
| KB scaffold | `kb_scaffold()` in manage.sh | `adjutant.capabilities.kb.scaffold` module |
| Model resolution | grep/sed on adjutant.yaml | PyYAML + dataclasses (Phase 1); pydantic added Phase 3 for API validation |

### What Does NOT Change

| Component | Status |
|-----------|--------|
| KB directory structure | **Unchanged** |
| kb.yaml format | **Unchanged** |
| .opencode/agents/kb.md | **Unchanged** |
| opencode.json permissions | **Unchanged** |
| data/, knowledge/, history/ | **Unchanged** |
| OpenCode invocation | **Unchanged** (same CLI args) |
| Existing portfolio_kb | **Unchanged** (works as-is) |

### Migration Path for KBs

1. **No action required** for existing KBs
2. Python `kb_query()` produces identical output to bash version
3. Registry format (`knowledge_bases/registry.yaml`) unchanged
4. CLI commands (`adjutant kb list`, `adjutant kb query`, etc.) unchanged

### KB-Internal Scripts (Out of Scope)

Some KBs contain their own scripts (e.g., portfolio_kb has `fetch.sh`, `trade.sh`, `analyze.sh`, and nordnet/yfinance libs). These are **out of scope** for this rewrite:

- KB-internal scripts live in external paths (e.g., `/Volumes/.../portfolio-kb/`), not in this repository
- They are invoked via `opencode run --agent kb` or `adjutant kb run <name> <operation>` — the invocation interface is unchanged
- Rewriting KB-internal scripts is a separate project per KB owner
- The two integration test files that reference external KB paths (`portfolio_fetch.bats`, `portfolio_trade.bats`) are ported as **skip-if-absent** pytest tests using `@pytest.mark.skipif(not Path("...").exists(), reason="External KB not present")`
- The `yfinance` and `nordnet` dependencies from the old plan are **removed** from this plan's core dependencies (they belong to the portfolio KB, not the framework)

---

## Security & Authorization

### Current Implementation

The dispatch pipeline enforces a strict security model that the Python port must replicate exactly:

1. **Single-user authorization** (`send.sh:137-139`): `msg_authorize(from_id)` does a strict string comparison `[ "${from_id}" = "${TELEGRAM_CHAT_ID}" ]`. Only the configured owner can interact. All other senders are **silently dropped** — no response is sent, preventing information leakage. The only trace is `adj_log messaging "Rejected unauthorized sender: ${from_id}"`.

2. **Rate limiting** (`dispatch.sh:26-60`): A sliding-window rate limiter allows `_RATE_LIMIT_MAX` messages per 60 seconds (default: 10, overridable via `ADJUTANT_RATE_LIMIT_MAX`). State is stored in `state/rate_limit_window` (one epoch timestamp per line). When exceeded, a polite error message is sent and the command is not dispatched.

3. **Dispatch order** (security-critical — `AGENTS.md` warns against refactoring without the full test suite):
   ```
   authorize(from_id)          → silent drop if unauthorized
   rate_limit()                → polite error if exceeded
   pending_reflect_intercept() → consumes message if reflect awaiting /confirm
   case dispatch               → route to command handler
   ```

4. **Pending reflect state machine** (`dispatch.sh:110-119`): When `/reflect` is requested, a `PENDING_REFLECT_FILE` sentinel is created. The **entire dispatch is hijacked** — all subsequent messages are intercepted before reaching the `case` block. Only `/confirm` proceeds with the reflect; any other message (including other slash commands) cancels the reflect **and is consumed** (not re-dispatched). This is a two-state modal system.

   **Python change (intentional):** The Python port stores `pending_reflect` as an in-memory
   boolean on `DispatchState`, not as a file sentinel. This means if the listener restarts
   between `/reflect` and `/confirm`, the pending state is lost. This is acceptable — the
   reflect flow is interactive and the user would simply re-issue `/reflect`.

### Python Implementation

```python
# adjutant/messaging/telegram/auth.py
from adjutant.core.env import get_credential
from adjutant.core.logging import adj_log

def authorize(from_id: str | int) -> bool:
    """Single-user authorization. Returns True if allowed."""
    allowed_id = get_credential("TELEGRAM_CHAT_ID")
    return str(from_id) == str(allowed_id)
```

```python
# adjutant/messaging/dispatch.py
import os
import time
from collections import deque
from adjutant.messaging.telegram.auth import authorize
from adjutant.core.logging import adj_log

class RateLimiter:
    """In-memory sliding window rate limiter.
    
    Behavioral contract (matches bash dispatch.sh:33-60):
    - Timestamp is appended BEFORE checking count (rejected messages still
      consume window slots, matching bash behavior where the epoch is written
      to the file before the count check)
    - Default 10/minute, overridable via ADJUTANT_RATE_LIMIT_MAX env var
    - Note: adjutant.yaml has messaging.telegram.rate_limit.messages_per_minute
      but bash only reads the env var, not the YAML. Python preserves this behavior.
      Future enhancement: read from config with env var override.
    """
    
    def __init__(self, max_per_minute: int | None = None):
        self.max_per_minute = max_per_minute or int(
            os.environ.get("ADJUTANT_RATE_LIMIT_MAX", "10")
        )
        self.timestamps: deque[float] = deque()
    
    def check(self) -> bool:
        """Returns True if request is allowed."""
        now = time.time()
        # Append FIRST (bash appends epoch before counting — dispatch.sh:41)
        self.timestamps.append(now)
        # Prune entries outside window
        cutoff = now - 60
        while self.timestamps and self.timestamps[0] <= cutoff:
            self.timestamps.popleft()
        # Check threshold (bash uses > not >=, but since we append first, the
        # semantics are: 11th message within window triggers the limit)
        if len(self.timestamps) > self.max_per_minute:
            return False
        return True

class DispatchState:
    """Tracks modal dispatch state (e.g., pending reflect)."""
    
    def __init__(self):
        self.pending_reflect: bool = False

async def dispatch_message(update: dict, state: DispatchState, rate_limiter: RateLimiter, adaptor) -> None:
    from_id = update["message"]["from"]["id"]
    message_id = update["message"]["message_id"]
    
    # 1. Authorization — silent drop (no response to prevent info leakage)
    if not authorize(from_id):
        adj_log("messaging", f"Rejected unauthorized sender: {from_id}")
        return
    
    # 2. Rate limiting — polite error
    if not rate_limiter.check():
        await adaptor.send_text(
            "I'm receiving messages too quickly. Please wait a moment before sending another.",
            message_id,
        )
        return
    
    text = update["message"].get("text", "")
    adj_log("messaging", f"Received msg={message_id}: {text}")
    
    # 3. Pending reflect interception — consumes message
    if state.pending_reflect:
        if text == "/confirm":
            await cmd_reflect_confirm(message_id)
        else:
            state.pending_reflect = False
            await adaptor.send_text("No problem — I've cancelled the reflection.", message_id)
            adj_log("messaging", "Reflect cancelled.")
            # Message is consumed — NOT re-dispatched
        return
    
    # 4. Command dispatch
    if text.startswith("/"):
        await route_command(text, message_id, adaptor)
    else:
        # Natural language conversation
        adj_log("messaging", f"Chat msg={message_id}: {text}")
        await adaptor.react(message_id)  # Eyes emoji acknowledgment (dispatch.sh:146)
        await dispatch_chat(text, message_id, adaptor)

async def dispatch_photo(update: dict, adaptor) -> None:
    """Dispatch photo messages (matches bash dispatch.sh:176-197).
    
    Authorization is checked. Photo handling is delegated to the adaptor.
    """
    from_id = update["message"]["from"]["id"]
    message_id = update["message"]["message_id"]
    
    if not authorize(from_id):
        adj_log("messaging", f"Rejected photo from unauthorized sender: {from_id}")
        return
    
    photos = update["message"].get("photo", [])
    if not photos:
        return
    
    # Telegram sends multiple resolutions — take the highest (last in array)
    file_id = photos[-1]["file_id"]
    caption = update["message"].get("caption", "")
    
    await adaptor.handle_photo(from_id, message_id, file_id, caption)
```

### Command Routing

`route_command()` maps slash commands to handler functions. This replaces the bash `case` block
in `dispatch.sh:122-168`:

```python
# adjutant/messaging/dispatch.py (continued)

async def route_command(text: str, message_id: str, adaptor) -> None:
    """Route slash commands to handlers (matches dispatch.sh case block).
    
    Note: word-splitting for multi-argument commands (e.g., /kb query portfolio "question")
    uses shlex.split() rather than bash's unquoted variable splitting. This correctly handles
    quoted arguments that bash would mangle.
    """
    import shlex
    parts = shlex.split(text)
    cmd = parts[0].lower()
    args = parts[1:]
    
    # Simple commands (no arguments)
    simple = {
        "/status":  lambda: cmd_status(message_id, adaptor),
        "/pause":   lambda: cmd_pause(message_id, adaptor),
        "/resume":  lambda: cmd_resume(message_id, adaptor),
        "/kill":    lambda: cmd_kill(message_id, adaptor),
        "/pulse":   lambda: cmd_pulse(message_id, adaptor),
        "/restart": lambda: cmd_restart(message_id, adaptor),
        "/reflect": lambda: cmd_reflect_request(message_id, adaptor, state),  # sets state.pending_reflect = True
        "/help":    lambda: cmd_help(message_id, adaptor),
        "/start":   lambda: cmd_help(message_id, adaptor),  # Telegram convention
    }
    
    if cmd in simple and not args:
        await simple[cmd]()
        return
    
    # Commands with arguments
    if cmd == "/model":
        await cmd_model(" ".join(args), message_id, adaptor)
    elif cmd == "/screenshot":
        if not args:
            await adaptor.send_text("Please provide a URL. Example: /screenshot https://example.com", message_id)
        else:
            await cmd_screenshot(args[0], message_id, adaptor)
    elif cmd == "/search":
        if not args:
            await adaptor.send_text("Please provide a search query. Example: /search latest AI news", message_id)
        else:
            await cmd_search(" ".join(args), message_id, adaptor)
    elif cmd == "/kb":
        # /kb → list, /kb query <name> <question> → query with multi-word question
        subcommand = args[0] if args else "list"
        remaining = args[1:] if args else []
        await cmd_kb(subcommand, remaining, message_id, adaptor)
    elif cmd == "/schedule":
        subcommand = args[0] if args else "list"
        remaining = args[1:] if args else []
        await cmd_schedule(subcommand, remaining, message_id, adaptor)
    else:
        # Unknown command — treat as natural language
        await adaptor.react(message_id)
        await dispatch_chat(text, message_id, adaptor)
```

### Photo Handling Behavioral Contract

`photos.py` (Phase 3) must replicate these bash patterns from `photos.sh`:

1. **Deduplication** (`photos.sh:20-37`): File IDs are hashed (MD5) and stored as marker files
   in `state/photo_dedup/` with a 60-second TTL. Duplicate photos within 60s are silently
   dropped. Python equivalent: `hashlib.md5(file_id.encode()).hexdigest()` marker files,
   cleaned up with `pathlib.Path.glob()` + `stat().st_mtime` check.

2. **Session context injection** (`photos.sh:141-143`): After successful vision analysis,
   a silent message is injected into the chat session so the agent has awareness of the photo:
   ```
   [PHOTO] User sent a photo with caption: "...". Vision analysis: <result>
   ```
   This is sent through `chat.sh` (Python equivalent: `handle_chat()`) with output suppressed.
   Without this, the agent loses conversational context about photos.

3. **Background execution** (`photos.sh:105-146`): The entire download→vision→reply flow runs
   in a background subshell (`( ... ) &; disown $!`). Python equivalent: `asyncio.create_task()`.

4. **Eyes emoji reaction** before processing (`photos.sh:103`): `msg_react "${message_id}"`.

### Notification Budget Guard

`notify.py` (Phase 3) must replicate the daily budget from `notify.sh:25-41`:

```python
# adjutant/messaging/telegram/notify.py
async def send_notification(message: str, adj_dir: Path, config: dict) -> str:
    """Send a notification with daily budget enforcement.
    
    Budget state: state/notify_count_YYYY-MM-DD.txt (integer count)
    Config: notifications.max_per_day (default: 3)
    Config: notifications.quiet_hours.enabled/start/end (not yet implemented in bash)
    
    Returns "OK:sent (N/max today)" or "ERROR:budget_exceeded (N/max today)"
    """
    today = datetime.date.today().isoformat()
    count_file = adj_dir / "state" / f"notify_count_{today}.txt"
    count = int(count_file.read_text().strip()) if count_file.exists() else 0
    max_per_day = config.get("notifications", {}).get("max_per_day", 3)
    
    if count >= max_per_day:
        return f"ERROR:budget_exceeded ({count}/{max_per_day} sent today)"
    
    # Sanitize (notify.sh uses 4096, NOT 4000 like send.sh — no parse_mode)
    message = sanitize_message(message)
    
    # Send WITHOUT parse_mode (notify.sh intentionally omits it — notifications
    # may contain characters that break Markdown parsing)
    await api.send_message(chat_id=chat_id, text=message)
    
    count_file.write_text(str(count + 1))
    return f"OK:sent ({count + 1}/{max_per_day} today)"
```

**Note on `parse_mode`:** `send_text()` uses `parse_mode=Markdown`. `send_notification()` does
NOT (matching bash `notify.sh:43-44` vs `send.sh:29`). This is intentional — notifications are
often generated programmatically and may contain characters that break Markdown.

**Note on quiet hours:** `adjutant.yaml.example` defines `notifications.quiet_hours.enabled/start/end`
(lines 101-104) but the bash code does not implement quiet hours yet. The Python port should add
this as a Phase 3 enhancement if desired, checking current time against the configured window.

**Note on `/kb query` argument parsing (GAP 13):** The bash version uses unquoted `${text#/kb }` 
which splits on whitespace, so `cmd_kb` receives `query portfolio what's my allocation?` as 
separate positional args, then reconstructs the query with `shift 3`. The Python version uses 
`shlex.split()` which handles quoting properly. The `cmd_kb` handler receives `subcommand="query"` 
and `remaining=["portfolio", "what's", "my", "allocation?"]`, then joins remaining[1:] for the 
query string.

---

## Concurrency Model

### Decision: asyncio Throughout

The Telegram listener must handle long-running commands (screenshot, KB query, chat — each taking 5-300 seconds) without blocking the polling loop. The chosen model is **asyncio throughout**.

### Architecture

```
┌─────────────────────────────────────────────────────┐
│               asyncio event loop                     │
│                                                     │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────┐  │
│  │  Listener    │  │  Background  │  │  Reaper   │  │
│  │  (polling)   │  │  Tasks       │  │  (60s)    │  │
│  │             │  │             │  │           │  │
│  │  getUpdates │  │ • kb_query  │  │ pgrep +   │  │
│  │  → dispatch │  │ • chat      │  │ kill      │  │
│  │  → repeat   │  │ • screenshot│  │ orphans   │  │
│  └─────────────┘  │ • search    │  └───────────┘  │
│                   └──────────────┘                  │
│                                                     │
│  ┌──────────────────────────────────────────────┐   │
│  │  Typing Indicator Tasks (per-command)         │   │
│  │  • send ChatAction every 3s until cancelled  │   │
│  └──────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

### Key Patterns

**Long-running commands as tasks:**
```python
# Instead of bash: ( ... ) </dev/null >/dev/null 2>&1 &; disown $!
async def handle_kb_query(message_id: str, kb_name: str, query: str):
    typing_task = asyncio.create_task(typing_indicator(message_id))
    try:
        result = await asyncio.create_subprocess_exec(
            "opencode", "run", "--agent", "kb", ...,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await asyncio.wait_for(result.communicate(), timeout=80)
        ndjson_result = parse_ndjson(stdout.decode())
        await send_text(ndjson_result.text or "No response.", message_id)
    except asyncio.TimeoutError:
        await send_text("KB query timed out.", message_id)
    finally:
        typing_task.cancel()

# Dispatched as a fire-and-forget task
asyncio.create_task(handle_kb_query(message_id, kb_name, query))
```

**Typing indicators as persistent tasks:**
```python
async def typing_indicator(message_id: str):
    """Send 'typing...' every 4s until cancelled (matches bash send.sh:108 sleep 4)."""
    try:
        while True:
            await api.send_chat_action("typing")
            await asyncio.sleep(4)
    except asyncio.CancelledError:
        pass
```

**In-flight chat job cancellation:**
```python
# Only one natural-language chat can run at a time.
# New messages cancel the previous one.
_current_chat_task: asyncio.Task | None = None

async def dispatch_chat(message: str, message_id: str, adaptor):
    global _current_chat_task
    if _current_chat_task and not _current_chat_task.done():
        _current_chat_task.cancel()
    _current_chat_task = asyncio.create_task(
        handle_chat(message, message_id, adaptor)
    )

async def handle_chat(message: str, message_id: str, adaptor):
    """Handle natural-language chat via OpenCode subprocess.
    
    CRITICAL: On cancellation (new message supersedes this one), the OpenCode
    subprocess must be explicitly terminated. asyncio.Task.cancel() only raises
    CancelledError at the next await — it does NOT kill child processes.
    The bash version uses `pkill -9 -P` for forceful tree kill (dispatch.sh:73-74).
    """
    typing_task = asyncio.create_task(typing_indicator(message_id))
    proc = None
    try:
        proc = await asyncio.create_subprocess_exec(
            "opencode", "run", "--agent", "adjutant", "--format", "json", message,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=240)
        ndjson_result = parse_ndjson(stdout.decode())
        if ndjson_result.error_type == "model_not_found":
            model = get_chat_model(state_dir)
            await adaptor.send_text(f"The model `{model}` is no longer available. Use /model to switch.", message_id)
        else:
            await adaptor.send_text(ndjson_result.text or "I ran into a problem getting a response.", message_id)
    except asyncio.CancelledError:
        # Subprocess must be explicitly killed on cancellation
        if proc and proc.returncode is None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=2.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                proc.kill()
        raise
    except asyncio.TimeoutError:
        if proc and proc.returncode is None:
            proc.terminate()
        await adaptor.send_text("Request timed out — try again shortly.", message_id)
    finally:
        typing_task.cancel()
```

**Process-only-last-update behavior:**

The current bash listener intentionally drops all but the most recent message in each poll batch to prevent replay storms. Most Python Telegram libraries process ALL updates. This must be explicitly preserved:

```python
async def poll_loop():
    offset = load_offset()
    last_processed_id = 0  # Track last processed update_id to prevent duplicates
    while not is_killed():
        updates = await api.get_updates(offset=offset, timeout=10)
        if not updates:
            continue
        
        # Advance offset for ALL updates (acknowledge receipt)
        offset = updates[-1]["update_id"] + 1
        save_offset(offset)
        
        # But only dispatch the LAST one
        last = updates[-1]
        if last["update_id"] > last_processed_id:
            last_processed_id = last["update_id"]
            await dispatch(last)
```

**Periodic reaper as background task:**
```python
async def reaper_loop():
    """Kill orphaned language-server processes every ~60s.
    
    Note: opencode_reap() uses psutil.process_iter() which is synchronous.
    The reaper implementation (see Process Management section) wraps the
    scanning in asyncio.to_thread() to avoid blocking the event loop.
    """
    while True:
        await asyncio.sleep(60)
        await opencode_reap()
```

---

## Process Management

### The Problem

The bash codebase contains sophisticated process management patterns that Python's `subprocess` module doesn't natively support:

- **4-layer listener kill** in `emergency_kill.sh` (PID file, lock dir PID, two `pkill -f` patterns)
- **Two-phase TERM→sleep→KILL** used in opencode.sh, startup.sh, emergency_kill.sh
- **Orphan detection** via PID snapshots (`pgrep` before/after, `comm -13` to diff)
- **Orphan language-server reaping** by parent PID and RSS thresholds
- **Portable timeout** (`timeout` → `gtimeout` → shell-native watchdog)
- **PID file management** (read, validate with `kill -0`, detect stale)
- **`mkdir`-based atomic locking** with stale-lock recovery

### Required Dependencies

`psutil` (process utilities) is required. `filelock` is **not needed** — the bash `mkdir`-based
locking pattern is replicated with a custom `PidLock` class (see below) which also stores the
PID for `emergency_kill` and handles stale lock recovery:

```toml
dependencies = [
    "psutil>=5.9",
    # ...existing deps
]
```

### Python Equivalents

```python
# adjutant/core/process.py (Phase 1 — IMPLEMENTED)
#
# NOTE: The original plan proposed a ProcessManager class with @staticmethod methods.
# The actual implementation uses standalone functions — simpler, since there is no
# shared state. PidLock remains a class (it has instance state).

import os
import shutil
from pathlib import Path
import psutil
from adjutant.core.logging import adj_log

def kill_graceful(pid: int, timeout: float = 2.0) -> bool:
    """Two-phase TERM→KILL. Returns True if process was killed."""
    try:
        proc = psutil.Process(pid)
        proc.terminate()  # SIGTERM
        try:
            proc.wait(timeout=timeout)
            return True
        except psutil.TimeoutExpired:
            proc.kill()  # SIGKILL
            proc.wait(timeout=1.0)
            return True
    except psutil.NoSuchProcess:
        return False

def kill_process_tree(pid: int, timeout: float = 2.0) -> None:
    """Kill a process and all its children (replaces pkill -P)."""
    try:
        parent = psutil.Process(pid)
        children = parent.children(recursive=True)
        # TERM parent + children
        for p in children + [parent]:
            try:
                p.terminate()
            except psutil.NoSuchProcess:
                pass
        # Wait, then KILL survivors
        _, alive = psutil.wait_procs(children + [parent], timeout=timeout)
        for p in alive:
            try:
                p.kill()
            except psutil.NoSuchProcess:
                pass
    except psutil.NoSuchProcess:
        pass

def find_by_cmdline(pattern: str) -> list[psutil.Process]:
    """Find processes by command-line pattern (replaces pgrep -f).
    Excludes current process."""
    results = []
    for proc in psutil.process_iter(['pid', 'cmdline']):
        try:
            if proc.pid == os.getpid():
                continue
            cmdline = ' '.join(proc.info['cmdline'] or [])
            if pattern in cmdline:
                results.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return results

def pid_is_alive(pid: int) -> bool:
    """Check if PID exists (replaces kill -0). PermissionError counts as alive."""
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # Process exists but we can't signal it

def read_pid_file(path: Path) -> int | None:
    """Read and validate a PID file. Returns PID if alive, else None."""
    try:
        content = path.read_text().strip()
        pid = int(content)
        if pid_is_alive(pid):
            return pid
        return None  # Stale PID
    except (FileNotFoundError, ValueError):
        return None
```

**Per-invocation orphan cleanup (`opencode_run` wrapper):**

In addition to the periodic reaper, the bash `opencode_run()` (opencode.sh:125-155) does
per-invocation cleanup: it snapshots `pgrep` before and after each OpenCode call, then kills
any new language-server processes that appeared during the invocation. The Python `opencode_run()`
must replicate this. Commands like `/pulse` and `/reflect` (commands.sh:114-125, 188-199) also
do their own inline cleanup. In Python, all of these should use the same `opencode_run()` wrapper,
which handles the PID-snapshot cleanup internally.

**Periodic orphan language-server reaper:**
```python
async def opencode_reap():
    """Kill orphaned language-server processes (replaces opencode_reap in opencode.sh).
    
    Three kill rules (must match bash opencode.sh:175-210):
      (a) Orphaned — parent is PID 1 or parent process is gone
      (b) Stranded — parent is the opencode web server PID (the ephemeral
          `opencode run` that spawned it has exited, reparenting to web server)
      (c) RSS runaway — exceeds memory threshold regardless of parentage
    """
    web_pid = read_pid_file(
        Path(os.environ.get("ADJ_DIR", "")) / "state" / "opencode_web.pid"
    )
    rss_limit_kb = int(os.environ.get("OPENCODE_LANGSERVER_RSS_LIMIT_KB", "524288"))
    rss_limit_mb = rss_limit_kb / 1024
    
    targets: list[psutil.Process] = []
    
    # Scanning is synchronous — run in executor to avoid blocking event loop
    def _scan():
        for proc in psutil.process_iter(['pid', 'ppid', 'name', 'cmdline', 'memory_info']):
            try:
                cmdline = ' '.join(proc.info['cmdline'] or [])
                if 'bash-language-server' not in cmdline and 'yaml-language-server' not in cmdline:
                    continue
                
                ppid = proc.info['ppid']
                rss_mb = (proc.info['memory_info'].rss if proc.info['memory_info'] else 0) / 1024 / 1024
                
                # Rule (a): Orphaned — parent is init or gone
                is_orphan = ppid <= 1 or not pid_is_alive(ppid)
                # Rule (b): Stranded under web server — parent is opencode web PID
                is_stranded = web_pid is not None and ppid == web_pid
                # Rule (c): RSS runaway — exceeds configured limit
                is_bloated = rss_mb > rss_limit_mb
                
                if is_orphan or is_stranded or is_bloated:
                    reason = "orphan" if is_orphan else ("stranded" if is_stranded else "rss")
                    adj_log("opencode", f"Reaping {reason}: pid={proc.pid} ppid={ppid} rss={rss_mb:.0f}MB")
                    targets.append(proc)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    
    await asyncio.to_thread(_scan)
    
    # Batch TERM, wait 1s, then KILL survivors (matches bash pattern)
    for p in targets:
        try:
            p.terminate()
        except psutil.NoSuchProcess:
            pass
    if targets:
        await asyncio.sleep(1.0)
        for p in targets:
            try:
                if p.is_running():
                    p.kill()
            except psutil.NoSuchProcess:
                pass
```

**Timeout convention:**

The bash code uses exit code 124 (GNU `timeout` convention) to signal timeouts. In Python:
- Async code: `asyncio.TimeoutError` (raised by `asyncio.wait_for()`)
- Sync code: `subprocess.TimeoutExpired` (raised by `subprocess.run(timeout=N)`)
- The `opencode_run()` wrapper should catch both and convert to a unified `OpenCodeTimeout`
  exception or return a result object with a `timed_out: bool` field.
- Phase 2's synchronous `kb_query()` uses `subprocess.TimeoutExpired`. When called from
  Phase 3's async listener, it must be wrapped in `asyncio.to_thread()` (see GAP 16 below).

**Portable timeout (replaces `_adj_timeout`):**
```python
# asyncio.wait_for replaces the entire 3-tier _adj_timeout wrapper.
# IMPORTANT: Wrap proc.communicate(), NOT create_subprocess_exec().
# create_subprocess_exec() returns almost instantly (just spawns the process).
proc = await asyncio.create_subprocess_exec(
    "opencode", "run", ...,
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE
)
try:
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=80)
except asyncio.TimeoutError:
    # Equivalent to bash exit code 124 — clean up the subprocess
    proc.terminate()
    try:
        await asyncio.wait_for(proc.wait(), timeout=2.0)
    except asyncio.TimeoutError:
        proc.kill()
    raise
```

**Single-instance lock (replaces `mkdir`-based lock):**

The bash listener uses `mkdir` for atomic locking with a PID file inside (`listener.lock/pid`).
`emergency_kill.sh` reads this PID file to find the listener. A `filelock.FileLock` does not
store PIDs and does not handle stale locks. Use a custom `PidLock` instead:

```python
import shutil

class PidLock:
    """mkdir-based atomic lock with PID storage and stale-lock recovery.
    
    Matches bash listener.sh:56-72:
    - mkdir for atomic acquire (no race conditions)
    - PID stored in lock_dir/pid (read by emergency_kill)
    - Stale lock detection: if PID is dead, remove and re-acquire
    """
    def __init__(self, lock_dir: Path):
        self.lock_dir = lock_dir
        self.pid_file = lock_dir / "pid"
    
    def acquire(self) -> bool:
        """Acquire the lock. Returns True on success, False if another instance is running."""
        try:
            self.lock_dir.mkdir(parents=False, exist_ok=False)
        except FileExistsError:
            # Check if holder is still alive (stale lock detection)
            existing_pid = self._read_pid()
            if existing_pid and pid_is_alive(existing_pid):
                return False  # Another instance is genuinely running
            # Stale lock — previous listener crashed without cleanup
            adj_log("listener", f"Removing stale lock (PID {existing_pid} no longer running)")
            shutil.rmtree(self.lock_dir, ignore_errors=True)
            try:
                self.lock_dir.mkdir(parents=False, exist_ok=False)
            except FileExistsError:
                return False  # Race condition — another instance beat us
        self.pid_file.write_text(str(os.getpid()))
        return True
    
    def release(self):
        """Release the lock (called in finally/atexit)."""
        shutil.rmtree(self.lock_dir, ignore_errors=True)
    
    def _read_pid(self) -> int | None:
        try:
            return int(self.pid_file.read_text().strip())
        except (FileNotFoundError, ValueError):
            return None

# Usage:
lock = PidLock(adj_dir / "state" / "listener.lock")
if not lock.acquire():
    adj_log("listener", "Another listener is already running. Exiting.")
    sys.exit(1)
try:
    await poll_loop()
finally:
    lock.release()
```

Note: `filelock` is removed from core dependencies. The `PidLock` preserves the
`listener.lock/pid` interface that `emergency_kill.sh` (and later `adjutant.lifecycle.kill`)
reads to find the listener PID.

**OpenCode health check (replaces `opencode_health_check`):**
```python
async def opencode_health_check(adj_dir: Path) -> bool:
    """Two-stage health probe with restart-and-retry on failure.
    
    Matches bash opencode.sh:230-293:
    - Stage 1: HTTP ping to opencode web server root path
    - Stage 2: Real API call with cheapest model (no --agent, minimal cost)
    - On failure: restart opencode web, wait up to 20s for recovery
    """
    port = int(os.environ.get("OPENCODE_WEB_PORT", "4096"))
    base_url = f"http://localhost:{port}/"
    
    async def _http_ping() -> bool:
         pid = read_pid_file(adj_dir / "state" / "opencode_web.pid")
        if not pid:
            return False
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(base_url)
                return resp.status_code == 200
        except httpx.RequestError:
            return False
    
    async def _api_probe() -> bool:
        """Probe with cheapest model. Accepts any JSON event as success
        (even error responses prove the server is processing requests)."""
        proc = await asyncio.create_subprocess_exec(
            "opencode", "run",
            "--model", "anthropic/claude-haiku-4-5",
            "--format", "json",
            "ping",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=8)
            output = stdout.decode()
            # Accept exit 0 OR any JSON with "type" key (matches bash behavior)
            return proc.returncode == 0 or '"type"' in output
        except asyncio.TimeoutError:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                proc.kill()
            return False
    
    # Try probe
    if await _http_ping() and await _api_probe():
        return True
    
    # Probe failed — restart and retry (matches bash opencode.sh:262-293)
    adj_log("opencode", "Health check failed — restarting opencode web server")
    restart_proc = await asyncio.create_subprocess_exec(
        "python", "-m", "adjutant.lifecycle.restart",
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    # Don't await restart — poll for recovery instead
    
    # Wait up to 20s for recovery via HTTP polling
    for _ in range(20):
        await asyncio.sleep(1.0)
        if await _http_ping():
            adj_log("opencode", "Health check recovered after restart")
            return True
    
    adj_log("opencode", "Health check failed — could not recover after restart")
    return False
```

---

## Chat Session Management

### Current Implementation

`chat.sh` maintains conversation continuity via `state/telegram_session.json`:

```json
{
    "session_id": "ses_abc123",
    "last_message_epoch": 1741456800,
    "last_message_at": "18:00 08.03.2026"
}
```

**Format change (intentional):** The Python port changes `last_message_at` from the bash
format (`HH:MM DD.MM.YYYY`, local timezone) to ISO-8601 UTC (`YYYY-MM-DDTHH:MM:SSZ`).
This is an intentional improvement — ISO-8601 is unambiguous and sortable. The field is
human-readable metadata only; `last_message_epoch` is the machine-authoritative timestamp
for all timeout calculations. The Python code reads both formats gracefully during migration.

**Session lifecycle:**
1. On first message: OpenCode creates a new session. `save_session()` writes the full JSON.
2. On subsequent messages within 2 hours: Session ID is reused (`--session SID` flag). `touch_session()` updates only the timestamps.
3. After 2 hours of inactivity: Session expires. Next message starts fresh.
4. Legacy handling: Old Python-era files may have decimal epoch values; `${last_epoch%.*}` truncation is applied.

**Model resolution — two distinct chains:**

The chat and KB paths have **different** resolution chains. The Python port must keep them separate:

*Chat model resolution* (`chat.sh:get_model()` — simpler, does NOT consult adjutant.yaml):
```
state/telegram_model.txt → "anthropic/claude-haiku-4-5" (hardcoded default)
```
Use `get_chat_model(state_dir)` — reads file or returns default. No config lookup.

*KB model resolution* (`query.sh:_resolve_model()` — full tier chain):
```
"inherit" → state/telegram_model.txt → adjutant.yaml llm.models.cheap → "anthropic/claude-haiku-4-5"
"cheap"   → adjutant.yaml llm.models.cheap  → "anthropic/claude-haiku-4-5"
"medium"  → adjutant.yaml llm.models.medium → "anthropic/claude-sonnet-4-6"
"expensive" → adjutant.yaml llm.models.expensive → "anthropic/claude-opus-4-5"
explicit  → used as-is
```
Use `resolve_kb_model(kb_model, state_dir, config)` — full resolution with config fallbacks.

**Model-not-found handling:** Both the NDJSON stream and stderr are checked for `"Model not found"` / `"ProviderModelNotFoundError"`. On detection, the user gets: `"The model \`X\` is no longer available. Use /model to switch."` — not a raw error.

### Python Implementation

```python
# adjutant/messaging/telegram/session.py
import json
import time
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

SESSION_TIMEOUT = 7200  # 2 hours (hardcoded — matches bash chat.sh:30 which has a TODO to read from config)

@dataclass
class Session:
    session_id: str
    last_message_epoch: int
    last_message_at: str

class SessionManager:
    def __init__(self, state_dir: Path):
        self.session_file = state_dir / "telegram_session.json"
    
    def get_active_session_id(self) -> Optional[str]:
        """Return session ID if active (within timeout), else None."""
        if not self.session_file.exists():
            return None
        try:
            data = json.loads(self.session_file.read_text())
            epoch = int(float(data.get("last_message_epoch", 0)))  # Handle legacy decimals
            if time.time() - epoch < SESSION_TIMEOUT:
                return data.get("session_id")
        except (json.JSONDecodeError, KeyError, ValueError):
            pass
        return None
    
    def save(self, session_id: str):
        """Save a new session (full write)."""
        now = time.time()
        data = {
            "session_id": session_id,
            "last_message_epoch": int(now),
            "last_message_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(now)),
        }
        self.session_file.write_text(json.dumps(data))
    
    def touch(self):
        """Update timestamps only (existing session)."""
        if not self.session_file.exists():
            return
        data = json.loads(self.session_file.read_text())
        now = time.time()
        data["last_message_epoch"] = int(now)
        data["last_message_at"] = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(now))
        self.session_file.write_text(json.dumps(data))
```

```python
# adjutant/core/model.py
from pathlib import Path
from typing import Optional

DEFAULT_MODEL = "anthropic/claude-haiku-4-5"

TIER_DEFAULTS = {
    "cheap": "anthropic/claude-haiku-4-5",
    "medium": "anthropic/claude-sonnet-4-6",
    "expensive": "anthropic/claude-opus-4-5",
}

def get_chat_model(state_dir: Path) -> str:
    """Get the current chat model (simpler chain — matches chat.sh:get_model).
    
    Resolution: state/telegram_model.txt → hardcoded default.
    Does NOT consult adjutant.yaml (that's only for KB tier resolution).
    """
    model_file = state_dir / "telegram_model.txt"
    if model_file.exists():
        model = model_file.read_text().strip()
        if model:
            return model
    return DEFAULT_MODEL

def resolve_kb_model(
    kb_model: str,
    state_dir: Path,
    config: Optional[dict] = None,
) -> str:
    """Resolve KB model tier to concrete model ID (matches query.sh:_resolve_model).
    
    Resolution chain:
      "inherit"/"" → state/telegram_model.txt → config cheap tier → hardcoded default
      "cheap"/"medium"/"expensive" → config tier → hardcoded default
      anything else → used verbatim (explicit model ID)
    """
    if kb_model in ("inherit", ""):
        model_file = state_dir / "telegram_model.txt"
        if model_file.exists():
            model = model_file.read_text().strip()
            if model:
                return model
        # Fall back to cheap tier
        kb_model = "cheap"
    
    if kb_model in TIER_DEFAULTS:
        # Check adjutant.yaml config first
        if config:
            llm = config.get("llm", {})
            models = llm.get("models", {})
            configured = models.get(kb_model)
            if configured:
                return configured
        return TIER_DEFAULTS[kb_model]
    
    return kb_model  # Explicit model ID
```

---

## Agent Definition & OpenCode Integration

### What Stays Unchanged

| File | Status | Reason |
|------|--------|--------|
| `.opencode/agents/adjutant.md` | **Unchanged** | Agent prompt is OpenCode-side, not framework-side |
| `identity/soul.md` | **Unchanged** | Personal, gitignored, read by agent at runtime |
| `identity/heart.md` | **Unchanged** | Personal, gitignored, read by agent at runtime |
| `identity/registry.md` | **Unchanged** | Personal, gitignored, read by agent at runtime |
| `templates/kb/agents/kb.md` | **Unchanged** | KB sub-agent template, rendered at scaffold time |
| `opencode.json` | **Unchanged** | Root permission config for OpenCode |

### OpenCode Invocation Contract

The Python code must invoke OpenCode with **identical arguments** to the bash version:

```python
# Main agent chat (chat.sh equivalent)
["opencode", "run", "--agent", "adjutant", "--dir", ADJ_DIR,
 "--format", "json", "--model", MODEL, "--session", SID, MESSAGE]

# KB query (query.sh equivalent)
["opencode", "run", "--agent", "kb", "--dir", KB_PATH,
 "--format", "json", "--model", MODEL, QUERY]
```

The `--format json` flag produces NDJSON output. The `--agent` flag selects the agent definition from the workspace's `.opencode/agents/` directory. Changing any of these arguments would break the agent/KB interaction.

### KB Routing Rules (Agent-Side)

The agent definition contains routing intelligence for KB queries:
- **Ambiguous query** → agent asks user which KB to query
- **Clear domain match** → agent queries silently
- **Named agent reference** → agent offers to query that KB

These rules live in `.opencode/agents/adjutant.md` and are enforced by the LLM, not by framework code. The Python port does not need to replicate this logic — it just needs to provide the `/kb query` command and let the agent use it.

---

## Error Handling Strategy

### Design Principle: Never Crash the Daemon

The current bash listener (`listener.sh`) deliberately does **not** use `set -euo pipefail`. This is intentional — `curl` failures, `jq` parse errors, and OpenCode timeouts must not crash the long-running daemon. Individual errors are logged and reported to the user; the loop continues.

`chat.sh` also disables strict mode for the same reason: OpenCode may return non-zero on warnings that are not fatal.

### Python Error Handling Rules

**1. Top-level poll loop — catch everything:**
```python
async def poll_loop():
    while not is_killed():
        try:
            updates = await api.get_updates(offset=offset, timeout=10)
            # ... process updates
        except httpx.RequestError as e:
            adj_log("listener", f"Poll failed: {e}")
            await asyncio.sleep(5)  # Back off on network errors
        except Exception as e:
            adj_log("listener", f"Unexpected error in poll loop: {e}")
            await asyncio.sleep(1)  # Never crash
```

**2. Individual command handlers — catch and report:**
```python
async def handle_command(text: str, message_id: str):
    try:
        await route_command(text, message_id)
    except asyncio.TimeoutError:
        model = get_model()
        if model.startswith("anthropic/"):
            await send_text(
                "Request timed out. You may have hit your Anthropic usage limit — "
                "check usage.anthropic.com. Otherwise try again shortly.",
                message_id
            )
        else:
            await send_text("Request timed out — try again shortly.", message_id)
    except Exception as e:
        adj_log("dispatch", f"Command error: {e}")
        await send_text("Something went wrong. Check /status for details.", message_id)
```

**3. NDJSON parsing — skip bad lines:**
```python
# adjutant/lib/ndjson.py (Phase 1 — IMPLEMENTED)
#
# NOTE: The original plan proposed parse_ndjson(lines: list[str]) -> tuple[str, str | None, str | None].
# The actual implementation uses a dataclass return type for readability and extensibility.

from dataclasses import dataclass, field

@dataclass
class NDJSONResult:
    text: str = ""
    session_id: str | None = None
    error_type: str | None = None
    events: list[dict] = field(default_factory=list)

def parse_ndjson(output: str) -> NDJSONResult:
    """Parse NDJSON output from opencode. Returns NDJSONResult dataclass.
    
    Skips unparseable lines. Accumulates text from {"type":"text"} events.
    Extracts session_id from session.create events.
    Detects model-not-found errors.
    """
    result = NDJSONResult()
    text_parts = []
    
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue  # Skip malformed lines
        
        result.events.append(record)
        
        # Extract session ID
        if not result.session_id:
            result.session_id = record.get("sessionID")
        
        # Check errors
        if record.get("type") == "error":
            msg = record.get("error", {}).get("data", {}).get("message", "")
            name = record.get("error", {}).get("name", "")
            if "Model not found" in msg or "ModelNotFound" in name:
                result.error_type = "model_not_found"
        
        # Accumulate text
        if record.get("type") == "text":
            text_parts.append(record.get("part", {}).get("text", ""))
    
    result.text = "".join(text_parts)
    return result

def check_model_not_found(output: str, stderr: str = "") -> bool:
    """Quick check for model-not-found errors in output or stderr."""
    result = parse_ndjson(output)
    if result.error_type == "model_not_found":
        return True
    return "Model not found" in stderr or "ProviderModelNotFoundError" in stderr
```

**4. Subprocess failures — never propagate raw errors:**

OpenCode and capability scripts may fail for many reasons (network, auth, timeout, model unavailable). Every subprocess call must:
- Catch `subprocess.TimeoutExpired` / `asyncio.TimeoutError` → user-friendly timeout message
- Catch non-zero exit codes → check stderr for known error patterns → user-friendly message
- Never expose raw tracebacks or error internals to the Telegram user

---

## Message Sanitization

All outgoing messages must pass through sanitization before hitting the Telegram API.
This matches bash `send.sh:23` which does `tr -d '\000-\010\013-\037\177' | cut -c1-4000`:

```python
# adjutant/messaging/telegram/send.py
import re

# Telegram Bot API maximum message length
TELEGRAM_MAX_MESSAGE_LENGTH = 4096

def sanitize_message(text: str) -> str:
    """Strip control characters and enforce Telegram length limit.
    
    Matches bash send.sh:23 — tr -d '\\000-\\010\\013-\\037\\177'
    Strips: 0x00-0x08, 0x0B-0x1F, 0x7F. Preserves 0x09 (tab) and 0x0A (newline).
    
    Length: bash send.sh uses 4000 (conservative), notify.sh uses 4096 (actual API limit).
    Python uses 4096 for all paths. This is a deliberate change from send.sh's 4000.
    """
    # Remove control chars: 0x00-0x08, 0x0B-0x1F, 0x7F
    # Preserves: 0x09 (tab) and 0x0A (newline) — matches bash \000-\010 (octal)
    text = re.sub(r'[\x00-\x08\x0b-\x1f\x7f]', '', text)
    if len(text) > TELEGRAM_MAX_MESSAGE_LENGTH:
        text = text[:TELEGRAM_MAX_MESSAGE_LENGTH - 3] + "..."
    return text
```

**Telegram send contract:**
- All `send_text()` calls pass through `sanitize_message()` before making the API request
- All messages are sent with `parse_mode=Markdown` (matches bash `send.sh:29`)
- Reactions (`msg_react`) are fire-and-forget — spawned as background tasks, not awaited (matches bash `send.sh:75` which uses `&`)

---

## Phase-by-Phase Migration

### Phase 1: Foundation (Week 1-2) — COMPLETE

**Goal:** Python test infrastructure + core libraries

**Status:** Implemented and passing. 198 unit tests, 0 failures. All 10 core modules,
CLI entrypoint, and test suite are in place. Uses `src/adjutant/` layout with hatchling
build system.

**Deliverables (implemented):**
```
src/adjutant/
├── __init__.py
├── __main__.py
├── cli.py                    # Click CLI (main group + status command)
├── core/
│   ├── __init__.py
│   ├── paths.py              # ADJ_DIR resolution
│   ├── env.py                # Credential loading
│   ├── logging.py            # Structured logging
│   ├── platform.py           # OS detection
│   ├── lockfiles.py          # State management
│   ├── config.py             # YAML config
│   ├── model.py              # Model tier resolution
│   ├── process.py            # Process management (standalone functions + PidLock)
│   └── opencode.py           # opencode_run, opencode_reap, health check (async)
└── lib/
    └── ndjson.py             # NDJSON parser (NDJSONResult dataclass)
tests/
├── conftest.py               # 5 fixtures: adj_dir, adj_env, adj_config, mock_opencode, sample_kb
└── unit/
    ├── test_paths.py          # 14 tests
    ├── test_env.py            # 20 tests
    ├── test_logging.py        # 22 tests
    ├── test_platform.py       # 14 tests
    ├── test_lockfiles.py      # 24 tests
    ├── test_config.py         # 15 tests
    ├── test_model.py          # 14 tests
    ├── test_process.py        # 15 tests
    ├── test_opencode.py       # 12 tests
    └── test_ndjson.py         # 21 tests (includes extras)
                                 ─────
                                 198 total
```

**Implementation notes:**
- `process.py` uses **standalone functions** (`kill_graceful`, `kill_process_tree`,
  `find_by_cmdline`, `pid_is_alive`, `read_pid_file`) rather than the `ProcessManager` class
  originally proposed. `PidLock` remains a class. This is a deliberate simplification — the
  functions have no shared state and don't benefit from class encapsulation.
- `ndjson.py` returns an `NDJSONResult` dataclass (fields: `text`, `session_id`, `error_type`,
  `events`) rather than the `tuple[str, str | None, str | None]` originally proposed. The
  dataclass is more readable and extensible.
- `opencode.py` functions (`opencode_run`, `opencode_reap`, `opencode_health_check`) are
  `async` as planned. `OpenCodeResult` dataclass wraps subprocess output.
- `cli.py` implements a Click group with `--version` and a `status` subcommand that reports
  KILLED/PAUSED/OPERATIONAL state.
- `config.py` imports `dataclass` and `field` but does not use them yet (reserved for Phase 3
  pydantic migration).

**Tests:** 198 unit tests for core libraries:

| Test File | Module | Actual Tests | Key Assertions |
|-----------|--------|:------------:|----------------|
| `test_paths.py` | `core/paths.py` | 14 | `ADJUTANT_HOME` override, walk-up tree for `.adjutant-root`, walk-up for `adjutant.yaml` (legacy), `~/.adjutant` fallback, error on nonexistent dir, spaces in paths, `ADJ_DIR` + `ADJUTANT_DIR` export |
| `test_env.py` | `core/env.py` | 20 | `load_env` success/failure, `get_credential` key extraction, single-quote stripping, double-quote stripping, missing key returns `None`/empty, `has_credential` boolean, `require_telegram_credentials` validates both present, guard clause on missing `ADJ_DIR`, never `source` (security) |
| `test_logging.py` | `core/logging.py` | 22 | `adj_log` format `[HH:MM DD.MM.YYYY] [context] message`, append-only, default context, control char stripping (tabs, CR), `fmt_ts` ISO→European conversion, empty input→empty output, unparseable→passthrough, `log_error` to file+stderr, `log_warn` file only, `log_debug` conditional on env var |
| `test_platform.py` | `core/platform.py` | 14 | OS detection (`macos`/`linux`/`unknown`), `date_subtract` returns UTC ISO-8601 for hours/days/minutes, unknown unit fails, `file_mtime` returns epoch or `0`+failure, `file_size` returns bytes or `0`+failure, `ensure_path` idempotent |
| `test_lockfiles.py` | `core/lockfiles.py` | 24 | `set_paused`/`clear_paused` create/remove `PAUSED`, `set_killed`/`clear_killed` for `KILLED`, `is_paused`/`is_killed` silent boolean, `is_operational` composite (neither), `check_killed`/`check_paused`/`check_operational` verbose stderr messages, killed checked before paused, full lifecycle, guard clause |
| `test_config.py` | `core/config.py` | 15 | Load valid YAML, missing file returns defaults, missing keys return `None`, nested access (`llm.models.cheap`), type validation, invalid YAML handled gracefully, `is_feature_enabled` boolean, bonus edge cases |
| `test_model.py` | `core/model.py` | 14 | `get_chat_model`: reads file, fallback to default. `resolve_kb_model`: tier resolution (cheap/medium/expensive), inherit chain (file→config→default), explicit model passthrough, missing config fallbacks, empty string treated as inherit |
| `test_process.py` | `core/process.py` | 15 | `kill_graceful` (TERM→wait→KILL), `kill_process_tree`, `find_by_cmdline`, `pid_is_alive` (live/dead/permission), `read_pid_file` (valid/stale/missing/corrupt), `PidLock` (acquire/release/stale recovery/race condition) |
| `test_ndjson.py` | `lib/ndjson.py` | 21 | Text accumulation from multiple `{"type":"text"}` events, session ID extraction from `session.create`, `ModelNotFound` error detection (both `.error.name` and `.error.data.message`), malformed lines skipped, empty input, mixed event types, stderr fallback via `check_model_not_found`, NDJSONResult dataclass fields |
| `test_opencode.py` | `core/opencode.py` | 12 | `opencode_run` subprocess spawning, timeout handling, PID snapshot orphan cleanup after run, `opencode_reap` 3 rules (orphan/stranded/RSS), health check 2-stage probe, health check restart-and-retry, `OPENCODE_WEB_PORT` config |
| **Total** | | **198** | |

**Bash scripts replaced:** None (parallel implementation)

**Validation:**
```bash
pytest tests/unit/ -v
python -m adjutant.cli --help
```

---

### Phase 2: KB System (Week 3-4)

**Goal:** Full KB management in Python

**Deliverables:**
```
adjutant/capabilities/kb/
├── __init__.py
├── registry.py               # kb_count, kb_exists, kb_list, kb_info, kb_register, kb_remove
├── query.py                  # kb_query with NDJSON parsing
├── scaffold.py               # kb_scaffold from templates
└── run.py                    # KB-local operations
tests/
├── unit/
│   ├── test_kb_registry.py
│   ├── test_kb_scaffold.py
│   └── test_kb_query.py
└── integration/
    └── test_kb_endtoend.py
```

#### Registry (`registry.py`) — Behavioral Contract

The registry manages `knowledge_bases/registry.yaml`. This file has a rigid format that must be preserved for backward compatibility with any tooling that reads it directly.

**Registry YAML format** (preserved exactly):
```yaml
knowledge_bases:
  - name: "portfolio"
    description: "Investment portfolio tracker"
    path: "/absolute/path/to/portfolio_kb"
    model: "inherit"
    access: "read-write"
    created: "2025-01-15"
```

Format rules: 2-space indent for `- name:`, 4-space indent for continuation fields, all values double-quoted.

```python
# adjutant/capabilities/kb/registry.py
import re
from pathlib import Path
from typing import Optional

# Matches bash: '^[a-z0-9][a-z0-9-]*[a-z0-9]$' OR '^[a-z0-9]$'
# No underscores allowed (unlike schedule names)
KB_NAME_RE = re.compile(r'^[a-z0-9]([a-z0-9-]*[a-z0-9])?$')

# Operation names: must start with letter, allow letters/digits/underscore/hyphen
KB_OPERATION_RE = re.compile(r'^[a-z][a-z0-9_-]*$')

REGISTRY_HEADER = "knowledge_bases:\n"

def _registry_path() -> Path:
    """Return path to knowledge_bases/registry.yaml."""
    from adjutant.core.paths import get_adj_dir
    return get_adj_dir() / "knowledge_bases" / "registry.yaml"

def kb_validate_name(name: str) -> bool:
    """Validate KB name. No underscores, lowercase alphanumeric + hyphens only."""
    return bool(KB_NAME_RE.match(name))

def kb_validate_operation(name: str) -> bool:
    """Validate operation name. Must start with letter."""
    return bool(KB_OPERATION_RE.match(name))

def kb_exists(name: str) -> bool:
    """Check if KB exists in registry.
    
    Matches bash: grep '^  - name: "<name>"' (literal quotes, 2-space indent).
    """
    path = _registry_path()
    if not path.exists():
        return False
    target = f'  - name: "{name}"'
    for line in path.read_text().splitlines():
        if line == target:
            return True
    return False

def kb_count() -> int:
    """Count registered KBs.
    
    Matches bash: grep -c '^  - name:' (2-space indent assumption).
    """
    path = _registry_path()
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text().splitlines()
               if line.startswith('  - name:'))

def kb_get_field(name: str, field: str) -> Optional[str]:
    """Get a field value for a named KB.
    
    Pure line-by-line parsing (no YAML library) to match bash behavior.
    Scans for the matching '  - name: "<name>"' line, then reads subsequent
    4-space-indented lines until the next entry or EOF.
    Returns the unquoted value, or None if not found.
    """
    path = _registry_path()
    if not path.exists():
        return None
    
    lines = path.read_text().splitlines()
    in_entry = False
    for line in lines:
        if line == f'  - name: "{name}"':
            if field == "name":
                return name
            in_entry = True
            continue
        if in_entry:
            if line.startswith('  - name:'):
                break  # Next entry
            if line.startswith('    ') and ':' in line:
                key, _, val = line.strip().partition(':')
                val = val.strip().strip('"')
                if key == field:
                    return val
    return None

def kb_list() -> list[dict[str, str]]:
    """List all registered KBs with all fields."""
    path = _registry_path()
    if not path.exists():
        return []
    
    entries = []
    current: dict[str, str] = {}
    for line in path.read_text().splitlines():
        if line.startswith('  - name:'):
            if current:
                entries.append(current)
            val = line.split(':', 1)[1].strip().strip('"')
            current = {"name": val}
        elif line.startswith('    ') and ':' in line and current:
            key, _, val = line.strip().partition(':')
            current[key.strip()] = val.strip().strip('"')
    if current:
        entries.append(current)
    return entries

def kb_register(name: str, description: str, path: str,
                model: str = "inherit", access: str = "read-only",
                created: str = "") -> None:
    """Register a KB in registry.yaml.
    
    Behavioral contract from bash (THREE code paths):
    (A) No file or no header → write header + entry (cat >)
    (B) File contains empty '[]' list → write header + entry (cat >)
    (C) Existing entries → append entry (cat >>)
    
    WARNING: The bash version has NO atomicity for the append case (C).
    The Python version uses atomic write (tmpfile + rename) for ALL cases.
    This is an intentional improvement over bash.
    
    No file locking — matches bash behavior. Concurrent writes to the
    registry are not expected (single-user system, wizard-only creation).
    """
    import tempfile
    from datetime import date
    
    if not created:
        created = date.today().isoformat()
    
    reg_path = _registry_path()
    reg_path.parent.mkdir(parents=True, exist_ok=True)
    
    entry = (
        f'  - name: "{name}"\n'
        f'    description: "{description}"\n'
        f'    path: "{path}"\n'
        f'    model: "{model}"\n'
        f'    access: "{access}"\n'
        f'    created: "{created}"\n'
    )
    
    if reg_path.exists():
        content = reg_path.read_text()
        # Case B: empty list
        if content.strip() == "knowledge_bases: []" or content.strip() == "knowledge_bases:":
            content = REGISTRY_HEADER + entry
        else:
            # Case C: append
            content = content.rstrip('\n') + '\n' + entry
    else:
        # Case A: new file
        content = REGISTRY_HEADER + entry
    
    # Atomic write
    fd, tmp = tempfile.mkstemp(dir=str(reg_path.parent))
    try:
        import os
        os.write(fd, content.encode())
        os.close(fd)
        os.rename(tmp, str(reg_path))
    except Exception:
        os.close(fd) if not os.get_inheritable(fd) else None
        os.unlink(tmp)
        raise

def kb_unregister(name: str) -> bool:
    """Remove a KB from registry.yaml.
    
    Matches bash: tmpfile + mv (atomic rename).
    Removes the '  - name: "<name>"' line and all subsequent 4-space lines
    until the next entry or EOF.
    Returns True if found and removed, False if not found.
    """
    import tempfile, os
    
    reg_path = _registry_path()
    if not reg_path.exists():
        return False
    
    lines = reg_path.read_text().splitlines()
    output = []
    skip = False
    found = False
    
    for line in lines:
        if line == f'  - name: "{name}"':
            skip = True
            found = True
            continue
        if skip and line.startswith('    '):
            continue  # Skip continuation fields
        if skip and (line.startswith('  - name:') or not line.strip()):
            skip = False
        if not skip:
            output.append(line)
    
    if not found:
        return False
    
    fd, tmp = tempfile.mkstemp(dir=str(reg_path.parent))
    try:
        os.write(fd, ('\n'.join(output) + '\n').encode())
        os.close(fd)
        os.rename(tmp, str(reg_path))
    except Exception:
        os.unlink(tmp)
        raise
    return True
```

#### Scaffold (`scaffold.py`) — Behavioral Contract

```python
# adjutant/capabilities/kb/scaffold.py
from pathlib import Path

# Template variables replaced during scaffold
TEMPLATE_VARS = {
    "{{KB_NAME}}": "",
    "{{KB_DESCRIPTION}}": "",
    "{{KB_MODEL}}": "",
    "{{KB_ACCESS}}": "",
    "{{KB_WRITE_ENABLED}}": "",  # "true" or "false" — derived from access level
    "{{KB_CREATED}}": "",
}

def kb_scaffold(name: str, description: str, kb_path: Path,
                model: str = "inherit", access: str = "read-only") -> None:
    """Create KB directory structure from templates.
    
    Behavioral contract from bash:
    - kb.yaml, opencode.json, .opencode/agents/kb.md are ALWAYS written
      (overwritten on re-scaffold — intentional)
    - docs/README.md has conditional creation guard (won't overwrite existing)
    - data/current.md stub created only if not already present
    - opencode.json is COPIED not rendered (no template variables in it)
    - Access level enforcement is in kb.md agent definition, NOT opencode.json
      (write: {{KB_WRITE_ENABLED}}, edit: {{KB_WRITE_ENABLED}},
       bash: {{KB_WRITE_ENABLED}})
    
    Template source: templates/kb/ directory
    """
    from datetime import date
    from adjutant.core.paths import get_adj_dir
    
    templates_dir = get_adj_dir() / "templates" / "kb"
    write_enabled = "true" if access == "read-write" else "false"
    created = date.today().isoformat()
    
    replacements = {
        "{{KB_NAME}}": name,
        "{{KB_DESCRIPTION}}": description,
        "{{KB_MODEL}}": model,
        "{{KB_ACCESS}}": access,
        "{{KB_WRITE_ENABLED}}": write_enabled,
        "{{KB_CREATED}}": created,
    }
    
    # Create directory structure
    kb_path.mkdir(parents=True, exist_ok=True)
    (kb_path / "data").mkdir(exist_ok=True)
    (kb_path / "knowledge").mkdir(exist_ok=True)
    (kb_path / "history").mkdir(exist_ok=True)
    (kb_path / "templates").mkdir(exist_ok=True)
    (kb_path / "docs").mkdir(exist_ok=True)
    (kb_path / ".opencode" / "agents").mkdir(parents=True, exist_ok=True)
    
    def _render(template_text: str) -> str:
        result = template_text
        for var, val in replacements.items():
            result = result.replace(var, val)
        return result
    
    # Always overwrite: kb.yaml
    _write_rendered(templates_dir / "kb.yaml", kb_path / "kb.yaml", _render)
    
    # Always copy (not render): opencode.json
    import shutil
    shutil.copy2(templates_dir / "opencode.json", kb_path / "opencode.json")
    
    # Always overwrite: agent definition
    _write_rendered(
        templates_dir / "agents" / "kb.md",
        kb_path / ".opencode" / "agents" / "kb.md",
        _render,
    )
    
    # Conditional: docs/README.md (don't overwrite existing)
    readme_path = kb_path / "docs" / "README.md"
    if not readme_path.exists():
        _write_rendered(templates_dir / "docs" / "README.md", readme_path, _render)
    
    # Conditional: data/current.md stub (don't overwrite existing)
    current_path = kb_path / "data" / "current.md"
    if not current_path.exists():
        current_path.write_text(f"# {name} — Current Status\n\nNo data yet.\n")

def _write_rendered(template: Path, target: Path, render_fn) -> None:
    """Read template, render, write to target."""
    target.write_text(render_fn(template.read_text()))
```

#### Query (`query.py`) — Behavioral Contract

```python
# adjutant/capabilities/kb/query.py
import subprocess
import logging
from pathlib import Path
from typing import Optional
from adjutant.lib.ndjson import parse_ndjson

logger = logging.getLogger(__name__)

KB_QUERY_TIMEOUT = 80  # seconds — headroom under 120s tool ceiling

EMPTY_REPLY_FALLBACK = "The knowledge base did not return an answer. Try rephrasing your question."

def resolve_kb_model(kb_model: str, state_dir: Path, config: dict) -> str:
    """Resolve model for KB query.
    
    Resolution chain (distinct from get_chat_model):
    1. If kb_model is a concrete model name → use it
    2. If kb_model is "inherit" or "" → read state/telegram_model.txt
    3. If that file doesn't exist → resolve tier from adjutant.yaml
       (cheap/medium/expensive under llm.models)
    4. Fall through to hardcoded cheap tier default
    
    The bash version reads adjutant.yaml with naive grep for 'cheap:'/
    'medium:'/'expensive:' under llm.models. The Python version uses
    proper config loading from Phase 1.
    """
    from adjutant.core.model import resolve_model_tier
    
    if kb_model and kb_model not in ("inherit", ""):
        return kb_model
    
    # Try session model
    model_file = state_dir / "telegram_model.txt"
    if model_file.exists():
        session_model = model_file.read_text().strip()
        if session_model:
            return session_model
    
    # Fall through to cheap tier
    return resolve_model_tier("cheap", config)

def kb_query(kb_name: str, query: str, timeout: int = KB_QUERY_TIMEOUT) -> str:
    """Query a knowledge base via OpenCode sub-agent (synchronous).
    
    IMPORTANT: This is synchronous (subprocess.run). When called from the
    async listener (Phase 3), it MUST be wrapped in asyncio.to_thread():
    
        result = await asyncio.to_thread(kb_query, name, question)
    
    Calling subprocess.run() directly from an async event loop would block
    the entire loop for up to 80 seconds.
    
    Behavioral contract from bash query.sh:
    - Error events in NDJSON are logged to stderr but do NOT stop parsing
    - Text parts are concatenated without separator
    - Empty reply returns success with fallback message (NOT an error)
    - subprocess.TimeoutExpired is caught and returns error message
    """
    from adjutant.capabilities.kb.registry import kb_get_field
    from adjutant.core.paths import get_adj_dir
    from adjutant.core.config import load_config
    
    kb_path = kb_get_field(kb_name, "path")
    if kb_path is None:
        raise ValueError(f"KB '{kb_name}' not found in registry")
    
    kb_model = kb_get_field(kb_name, "model") or "inherit"
    state_dir = get_adj_dir() / "state"
    config = load_config()
    model = resolve_kb_model(kb_model, state_dir, config)
    
    args = [
        "opencode", "run",
        "--agent", "kb",
        "--dir", kb_path,
        "--format", "json",
        "--model", model,
        query,
    ]
    
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return f"KB query timed out after {timeout}s"
    
    # Parse NDJSON — error events logged but don't stop parsing
    ndjson_result = parse_ndjson(result.stdout)
    
    if ndjson_result.error_type:
        logger.warning("KB '%s' returned error: %s", kb_name, ndjson_result.error_type)
    
    if not text.strip():
        return EMPTY_REPLY_FALLBACK
    
    return text
```

#### Run (`run.py`) — Behavioral Contract

```python
# adjutant/capabilities/kb/run.py
import subprocess
from pathlib import Path
from adjutant.capabilities.kb.registry import kb_get_field, kb_validate_operation

def kb_run(kb_name: str, operation: str, *args: str) -> str:
    """Run a KB-local operation script.
    
    Behavioral contract from bash run.sh:
    - Merges stderr into stdout via 2>&1 capture
    - Does NOT add OK:/ERROR: prefixes — passes through operation output
    - Operation scripts live at <kb_path>/scripts/<operation>.sh
    - Validates operation name before execution
    
    Note: The bash dispatch uses UNQUOTED ${text#/kb } causing word-splitting.
    cmd_kb receives individual words as separate args. This function handles
    proper argument passing to the operation script.
    """
    if not kb_validate_operation(operation):
        return f"Invalid operation name: {operation}"
    
    kb_path = kb_get_field(kb_name, "path")
    if kb_path is None:
        return f"KB '{kb_name}' not found"
    
    script = Path(kb_path) / "scripts" / f"{operation}.sh"
    if not script.exists():
        return f"Operation '{operation}' not found for KB '{kb_name}'"
    
    result = subprocess.run(
        ["bash", str(script)] + list(args),
        capture_output=True,
        text=True,
        cwd=kb_path,
    )
    
    # Merge stdout + stderr (matches bash 2>&1)
    output = result.stdout
    if result.stderr:
        output += result.stderr
    
    return output.strip()
```

#### Phase 2 Test Specifications

```python
# tests/unit/test_kb_registry.py — Key test cases

class TestKBNameValidation:
    """KB names: lowercase alphanumeric + hyphens, no underscores."""
    # Valid: "a", "portfolio", "my-kb", "kb1"
    # Invalid: "A", "my_kb", "-start", "end-", "my kb", ""

class TestKBRegistryFormat:
    """Registry YAML must use exact format (2-space, 4-space, double-quoted)."""
    # Test: written registry can be read back
    # Test: format matches expected string exactly (byte-for-byte)

class TestKBRegister:
    """Three code paths for register."""
    # Test: register to nonexistent file (creates file with header)
    # Test: register to file with empty list "knowledge_bases: []"
    # Test: register to file with existing entries (appends)
    # Test: all cases use atomic write (no partial writes on crash)

class TestKBUnregister:
    """Atomic remove via tmpfile + rename."""
    # Test: remove existing entry
    # Test: remove nonexistent entry returns False
    # Test: remove from single-entry file leaves header only
    # Test: other entries preserved after removal

class TestKBCount:
    """Count based on '  - name:' line prefix."""
    # Test: empty file → 0
    # Test: multiple entries → correct count

class TestKBGetField:
    """Line-by-line field extraction."""
    # Test: get each field (name, description, path, model, access, created)
    # Test: nonexistent KB returns None
    # Test: nonexistent field returns None

# tests/unit/test_kb_scaffold.py — Key test cases

class TestKBScaffold:
    """Template rendering and conditional creation."""
    # Test: all template variables replaced
    # Test: opencode.json copied verbatim (no variable substitution)
    # Test: access level → write_enabled mapping (read-only→false, read-write→true)
    # Test: re-scaffold overwrites kb.yaml, opencode.json, kb.md
    # Test: re-scaffold does NOT overwrite existing docs/README.md
    # Test: re-scaffold does NOT overwrite existing data/current.md
    # Test: directory structure created (data/, knowledge/, history/, templates/, docs/)

# tests/unit/test_kb_query.py — Key test cases

class TestResolveKBModel:
    """Model resolution chain for KB queries."""
    # Test: concrete model name → used directly
    # Test: "inherit" → reads telegram_model.txt
    # Test: "" → reads telegram_model.txt
    # Test: no session model → falls to cheap tier from config
    # Test: no config → hardcoded default

class TestKBQuery:
    """Query via subprocess with NDJSON parsing."""
    # Test: successful query returns text
    # Test: empty reply returns EMPTY_REPLY_FALLBACK (not error)
    # Test: timeout returns timeout message (not exception)
    # Test: NDJSON error events logged but don't stop parsing
    # Test: nonexistent KB raises ValueError
```

**Bash scripts replaced:** 
- `scripts/capabilities/kb/manage.sh` → `adjutant/capabilities/kb/registry.py` + `scaffold.py`
- `scripts/capabilities/kb/query.sh` → `adjutant/capabilities/kb/query.py`
- `scripts/capabilities/kb/run.sh` → `adjutant/capabilities/kb/run.py`

**Validation:**
```bash
# Existing KBs must work unchanged
python -m adjutant.cli kb list
python -m adjutant.cli kb query portfolio "What's my current allocation?"
python -m adjutant.cli kb info portfolio
# Re-scaffold existing KB — verify no data loss
python -m adjutant.cli kb create test-kb  # wizard flow
```

---

### Phase 3: Messaging Layer (Week 5-6)

**Goal:** Complete Telegram messaging backend in Python — listener, dispatch, all send primitives,
photo handling, notifications, session management, service management, and all `/command` handlers.

**Deliverables:**
```
adjutant/messaging/
├── __init__.py
├── adaptor.py                # Backend-agnostic interface (msg_send_text, msg_react, msg_typing)
├── dispatch.py               # Message router (auth → rate limit → reflect → route)
└── telegram/
    ├── __init__.py
    ├── api.py                # Telegram HTTP client (httpx.AsyncClient)
    ├── listener.py           # Long polling loop (asyncio, process-only-last)
    ├── commands.py           # All /command handlers
    ├── send.py               # Send text/photos, react, typing, sanitize
    ├── photos.py             # Photo download, dedup, vision routing, session injection
    ├── notify.py             # Push notifications (budget guard, no parse_mode)
    ├── session.py            # OpenCode session management (2h timeout)
    ├── auth.py               # Single-user authorization
    └── service.py            # start/stop/restart/status (three-tier PID detection)
```

**Bash scripts replaced:**
- `scripts/messaging/adaptor.sh` → `adjutant/messaging/adaptor.py`
- `scripts/messaging/dispatch.sh` → `adjutant/messaging/dispatch.py`
- `scripts/messaging/telegram/send.sh` → `adjutant/messaging/telegram/send.py`
- `scripts/messaging/telegram/photos.sh` → `adjutant/messaging/telegram/photos.py`
- `scripts/messaging/telegram/reply.sh` → merged into `send.py` (reply.sh is just send.sh with `set -e`)
- `scripts/messaging/telegram/notify.sh` → `adjutant/messaging/telegram/notify.py`
- `scripts/messaging/telegram/chat.sh` → logic absorbed into `dispatch.py` + `session.py`
- `scripts/messaging/telegram/commands.sh` → `adjutant/messaging/telegram/commands.py`
- `scripts/messaging/telegram/listener.sh` → `adjutant/messaging/telegram/listener.py`
- `scripts/messaging/telegram/service.sh` → `adjutant/messaging/telegram/service.py`

---

#### 3.1 `api.py` — Telegram HTTP Client

The HTTP client wraps `httpx.AsyncClient` with a persistent connection pool. All Telegram API
calls go through this single class. Bash used raw `curl` per-call; Python reuses connections.

```python
# adjutant/messaging/telegram/api.py
import httpx
from pathlib import Path
from adjutant.core.env import get_credential
from adjutant.core.logging import adj_log

# Telegram API base URL
_BASE = "https://api.telegram.org"

class TelegramAPI:
    """Async Telegram Bot API client.
    
    Behavioral contract:
    - Single shared httpx.AsyncClient with connection pooling
    - All methods are async
    - Timeout: 30s for sends, 15s for get_updates (+ server-side long poll)
    - On HTTP error: log and return None (never raise to caller)
    - Bot token loaded once from .env via get_credential()
    """
    
    def __init__(self):
        self.token = get_credential("TELEGRAM_BOT_TOKEN")
        self.chat_id = get_credential("TELEGRAM_CHAT_ID")
        self._client: httpx.AsyncClient | None = None
    
    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client
    
    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()
    
    def _url(self, method: str) -> str:
        return f"{_BASE}/bot{self.token}/{method}"
    
    async def get_updates(
        self,
        offset: int = 0,
        timeout: int = 10,
        allowed_updates: list[str] | None = None,
    ) -> list[dict]:
        """Long-poll for updates (matches bash listener.sh:126).
        
        Returns list of update dicts, or empty list on error.
        The httpx timeout must exceed the Telegram server timeout to avoid
        premature client-side cancellation.
        """
        client = await self._ensure_client()
        params: dict = {"offset": offset, "timeout": timeout}
        if allowed_updates:
            params["allowed_updates"] = allowed_updates
        try:
            resp = await client.get(
                self._url("getUpdates"),
                params=params,
                timeout=timeout + 5,  # Extra margin over server long-poll
            )
            data = resp.json()
            if data.get("ok"):
                return data.get("result", [])
            return []
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            adj_log("telegram", f"getUpdates failed: {e}")
            return []
    
    async def send_message(
        self,
        text: str,
        reply_to_message_id: str | int | None = None,
        parse_mode: str | None = "Markdown",
        chat_id: str | int | None = None,
    ) -> dict | None:
        """Send a text message (matches bash send.sh:18-37).
        
        Returns API response dict on success, None on failure.
        """
        client = await self._ensure_client()
        payload: dict = {
            "chat_id": chat_id or self.chat_id,
            "text": text,
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode
        if reply_to_message_id:
            payload["reply_to_message_id"] = reply_to_message_id
        try:
            resp = await client.post(self._url("sendMessage"), data=payload)
            return resp.json()
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            adj_log("telegram", f"sendMessage failed: {e}")
            return None
    
    async def send_photo(
        self,
        photo_path: str | Path,
        caption: str | None = None,
        chat_id: str | int | None = None,
    ) -> dict | None:
        """Send a photo file (matches bash send.sh:41-61).
        
        Uses multipart form upload. Caption is optional.
        """
        client = await self._ensure_client()
        path = Path(photo_path)
        if not path.is_file():
            adj_log("telegram", f"send_photo: file not found: {photo_path}")
            return None
        try:
            files = {"photo": (path.name, path.read_bytes())}
            data: dict = {"chat_id": chat_id or self.chat_id}
            if caption:
                data["caption"] = caption
            resp = await client.post(self._url("sendPhoto"), data=data, files=files)
            return resp.json()
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            adj_log("telegram", f"sendPhoto failed: {e}")
            return None
    
    async def set_message_reaction(
        self,
        message_id: str | int,
        emoji: str = "\U0001f440",  # 👀
        chat_id: str | int | None = None,
    ) -> bool:
        """Add emoji reaction to a message (matches bash send.sh:65-76).
        
        Fire-and-forget semantics — failure is silently logged. Bash version
        runs this with `&` (background); Python callers should wrap in
        asyncio.create_task() and not await the result.
        """
        client = await self._ensure_client()
        payload = {
            "chat_id": chat_id or self.chat_id,
            "message_id": int(message_id),
            "reaction": [{"type": "emoji", "emoji": emoji}],
        }
        try:
            resp = await client.post(
                self._url("setMessageReaction"),
                json=payload,
            )
            return resp.json().get("ok", False)
        except (httpx.RequestError, httpx.HTTPStatusError):
            return False
    
    async def send_chat_action(
        self,
        action: str = "typing",
        chat_id: str | int | None = None,
    ) -> bool:
        """Send typing indicator (matches bash send.sh:104).
        
        Called in a loop every 4s by the typing indicator task.
        """
        client = await self._ensure_client()
        try:
            resp = await client.post(
                self._url("sendChatAction"),
                data={"chat_id": chat_id or self.chat_id, "action": action},
            )
            return resp.json().get("ok", False)
        except (httpx.RequestError, httpx.HTTPStatusError):
            return False
    
    async def get_file(self, file_id: str) -> str | None:
        """Get file path for download (matches bash photos.sh:47).
        
        Returns the Telegram file_path string, or None on failure.
        """
        client = await self._ensure_client()
        try:
            resp = await client.get(
                self._url("getFile"),
                params={"file_id": file_id},
            )
            data = resp.json()
            if data.get("ok"):
                return data["result"].get("file_path")
            return None
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            adj_log("telegram", f"getFile failed: {e}")
            return None
    
    async def download_file(self, file_path: str) -> bytes | None:
        """Download a file by its Telegram file_path (matches bash photos.sh:68).
        
        Returns raw bytes, or None on failure.
        """
        client = await self._ensure_client()
        url = f"{_BASE}/file/bot{self.token}/{file_path}"
        try:
            resp = await client.get(url)
            if resp.status_code == 200:
                return resp.content
            return None
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            adj_log("telegram", f"download_file failed: {e}")
            return None
```

---

#### 3.2 `send.py` — Send Primitives + Sanitization

Consolidates `send.sh` (145 lines) and `reply.sh` (31 lines) — reply.sh is just a standalone
script that duplicates send.sh's logic with `set -e`. In Python, `reply.sh` becomes a thin
CLI wrapper calling `send.py` (not a separate module).

```python
# adjutant/messaging/telegram/send.py
import re
import asyncio
from adjutant.messaging.telegram.api import TelegramAPI

# Telegram Bot API maximum message length
TELEGRAM_MAX_MESSAGE_LENGTH = 4096

def sanitize_message(text: str) -> str:
    """Strip control characters and enforce Telegram length limit.
    
    Matches bash send.sh:23 — tr -d '\\000-\\010\\013-\\037\\177'
    Strips: 0x00-0x08, 0x0B-0x1F, 0x7F. Preserves 0x09 (tab) and 0x0A (newline).
    
    Length: bash send.sh uses 4000 (conservative), notify.sh uses 4096 (API limit).
    Python uses 4096 for all paths — deliberate change from send.sh's 4000.
    
    Truncation is CHARACTER-based (not byte-based). This is intentional bug fix #8
    over bash, which used `cut -c1-4000` (byte-based on some locales).
    """
    # Remove control chars: 0x00-0x08, 0x0B-0x1F, 0x7F
    text = re.sub(r'[\x00-\x08\x0b-\x1f\x7f]', '', text)
    if len(text) > TELEGRAM_MAX_MESSAGE_LENGTH:
        text = text[:TELEGRAM_MAX_MESSAGE_LENGTH - 3] + "..."
    return text


async def send_text(
    api: TelegramAPI,
    message: str,
    reply_to_message_id: str | int | None = None,
) -> dict | None:
    """Send a sanitized text message with Markdown parse mode.
    
    Behavioral contract (matches bash send.sh:18-37):
    - ALL outgoing text passes through sanitize_message() before API call
    - parse_mode=Markdown is always set (matching send.sh:29)
    - reply_to_message_id is optional (matches send.sh:32-34)
    - Failures are silently logged (curl > /dev/null 2>&1 in bash)
    """
    message = sanitize_message(message)
    return await api.send_message(
        text=message,
        reply_to_message_id=reply_to_message_id,
        parse_mode="Markdown",
    )


async def send_photo(
    api: TelegramAPI,
    photo_path: str,
    caption: str | None = None,
) -> dict | None:
    """Send a photo with optional caption (matches bash send.sh:41-61).
    
    Caption is sanitized. Photo file must exist (api.py checks this).
    """
    if caption:
        caption = sanitize_message(caption)
    return await api.send_photo(photo_path=photo_path, caption=caption)


async def react(
    api: TelegramAPI,
    message_id: str | int,
    emoji: str = "\U0001f440",
) -> None:
    """Fire-and-forget emoji reaction (matches bash send.sh:65-76).
    
    Bash version: `curl ... &` (background, not waited on).
    Python version: spawned as asyncio.create_task(), not awaited by caller.
    Failure is silently ignored.
    """
    asyncio.create_task(api.set_message_reaction(message_id, emoji))


async def typing_indicator(api: TelegramAPI) -> None:
    """Send 'typing...' action every 4s until cancelled.
    
    Matches bash send.sh:102-110 — background loop with `sleep 4`.
    
    Usage: Create as a task, cancel when command completes.
        typing_task = asyncio.create_task(typing_indicator(api))
        try:
            # ... do work ...
        finally:
            typing_task.cancel()
    """
    try:
        while True:
            await api.send_chat_action("typing")
            await asyncio.sleep(4)
    except asyncio.CancelledError:
        pass
```

**Telegram send contract summary:**
- All `send_text()` calls pass through `sanitize_message()` before the API request
- All regular messages use `parse_mode=Markdown` (matches bash `send.sh:29`)
- Notifications do NOT use `parse_mode` (see `notify.py` below)
- Reactions are fire-and-forget — spawned as background tasks, not awaited (matches bash `send.sh:75` which uses `&`)

---

#### 3.3 `auth.py` — Single-User Authorization

```python
# adjutant/messaging/telegram/auth.py
from adjutant.core.env import get_credential
from adjutant.core.logging import adj_log

def authorize(from_id: str | int) -> bool:
    """Single-user authorization (matches bash send.sh:137-139).
    
    Behavioral contract:
    - Strict string comparison: str(from_id) == str(TELEGRAM_CHAT_ID)
    - Unauthorized senders are SILENTLY dropped — no response sent
    - Only trace is adj_log (prevents information leakage to unknown senders)
    - This is the FIRST check in the dispatch pipeline (security-critical order)
    """
    allowed_id = get_credential("TELEGRAM_CHAT_ID")
    return str(from_id) == str(allowed_id)
```

---

#### 3.4 `dispatch.py` — Message Router

The dispatch pipeline is the security-critical core. Order: authorize → rate limit → pending
reflect interception → command/chat dispatch. `AGENTS.md` explicitly warns against refactoring
this without the full test suite.

```python
# adjutant/messaging/dispatch.py
import os
import time
import shlex
import asyncio
from collections import deque
from adjutant.messaging.telegram.auth import authorize
from adjutant.messaging.telegram.send import send_text, react, typing_indicator
from adjutant.messaging.telegram.api import TelegramAPI
from adjutant.messaging.telegram.session import SessionManager
from adjutant.core.logging import adj_log
from adjutant.core.model import get_chat_model
from adjutant.core.opencode import opencode_run
from adjutant.lib.ndjson import parse_ndjson


class RateLimiter:
    """In-memory sliding window rate limiter.
    
    Behavioral contract (matches bash dispatch.sh:33-60):
    - Timestamp is appended BEFORE checking count (rejected messages still
      consume window slots, matching bash behavior where the epoch is written
      to the file before the count check)
    - Default 10/minute, overridable via ADJUTANT_RATE_LIMIT_MAX env var
    - Note: adjutant.yaml has messaging.telegram.rate_limit.messages_per_minute
      but bash only reads the env var, not the YAML. Python preserves this behavior.
    """
    
    def __init__(self, max_per_minute: int | None = None):
        self.max_per_minute = max_per_minute or int(
            os.environ.get("ADJUTANT_RATE_LIMIT_MAX", "10")
        )
        self.timestamps: deque[float] = deque()
    
    def check(self) -> bool:
        """Returns True if request is allowed."""
        now = time.time()
        # Append FIRST (bash appends epoch before counting — dispatch.sh:41)
        self.timestamps.append(now)
        # Prune entries outside window
        cutoff = now - 60
        while self.timestamps and self.timestamps[0] <= cutoff:
            self.timestamps.popleft()
        # Check threshold (bash uses > not >=; 11th message triggers limit)
        if len(self.timestamps) > self.max_per_minute:
            return False
        return True


class DispatchState:
    """Tracks modal dispatch state.
    
    Python change (intentional): pending_reflect is in-memory, not a file sentinel.
    If the listener restarts between /reflect and /confirm, the pending state is lost.
    This is acceptable — the flow is interactive and the user would re-issue /reflect.
    """
    
    def __init__(self):
        self.pending_reflect: bool = False


# --- In-flight chat job cancellation ---
# Only one natural-language chat can run at a time (matches bash dispatch.sh:62-86).
# New messages cancel the previous one. The subprocess must be explicitly terminated
# on cancellation — asyncio.Task.cancel() does NOT kill child processes.
_current_chat_task: asyncio.Task | None = None


async def dispatch_message(
    update: dict,
    state: DispatchState,
    rate_limiter: RateLimiter,
    api: TelegramAPI,
) -> None:
    """Main dispatch entry point (matches bash dispatch.sh:90-168).
    
    Security-critical order:
    1. authorize(from_id) → silent drop if unauthorized
    2. rate_limit() → polite error if exceeded
    3. pending_reflect_intercept() → consumes message if reflect awaiting /confirm
    4. command dispatch OR natural language chat
    """
    from_id = update["message"]["from"]["id"]
    message_id = update["message"]["message_id"]
    
    # 1. Authorization — silent drop (no response to prevent info leakage)
    if not authorize(from_id):
        adj_log("messaging", f"Rejected unauthorized sender: {from_id}")
        return
    
    # 2. Rate limiting — polite error
    if not rate_limiter.check():
        await send_text(
            api,
            "I'm receiving messages too quickly. Please wait a moment before sending another.",
            message_id,
        )
        return
    
    text = update["message"].get("text", "")
    adj_log("messaging", f"Received msg={message_id}: {text}")
    
    # 3. Pending reflect interception — consumes message
    if state.pending_reflect:
        if text == "/confirm":
            await cmd_reflect_confirm(message_id, api, state)
        else:
            state.pending_reflect = False
            await send_text(api, "No problem — I've cancelled the reflection.", message_id)
            adj_log("messaging", "Reflect cancelled.")
            # Message is consumed — NOT re-dispatched
        return
    
    # 4. Command dispatch
    if text.startswith("/"):
        await route_command(text, message_id, api, state)
    else:
        # Natural language conversation
        adj_log("messaging", f"Chat msg={message_id}: {text}")
        await react(api, message_id)  # Eyes emoji acknowledgment (dispatch.sh:146)
        await dispatch_chat(text, message_id, api)


async def dispatch_photo(
    update: dict,
    api: TelegramAPI,
) -> None:
    """Dispatch photo messages (matches bash dispatch.sh:176-197).
    
    Authorization is checked. Photo handling delegated to photos.py.
    """
    from_id = update["message"]["from"]["id"]
    message_id = update["message"]["message_id"]
    
    if not authorize(from_id):
        adj_log("messaging", f"Rejected photo from unauthorized sender: {from_id}")
        return
    
    photos = update["message"].get("photo", [])
    if not photos:
        return
    
    # Telegram sends multiple resolutions — take the highest (last in array)
    file_id = photos[-1]["file_id"]
    caption = update["message"].get("caption", "")
    
    # Import here to avoid circular imports
    from adjutant.messaging.telegram.photos import handle_photo
    asyncio.create_task(handle_photo(api, message_id, file_id, caption))


async def route_command(
    text: str,
    message_id: str | int,
    api: TelegramAPI,
    state: DispatchState,
) -> None:
    """Route slash commands to handlers (matches bash dispatch.sh:122-168).
    
    Uses shlex.split() for proper argument parsing (bash used unquoted variable
    splitting which mangles quoted arguments). This is a deliberate improvement.
    """
    parts = shlex.split(text)
    cmd = parts[0].lower()
    args = parts[1:]
    
    # Import command handlers
    from adjutant.messaging.telegram.commands import (
        cmd_status, cmd_pause, cmd_resume, cmd_kill, cmd_pulse,
        cmd_restart, cmd_reflect_request, cmd_help, cmd_model,
        cmd_screenshot, cmd_search, cmd_kb, cmd_schedule,
    )
    
    # Simple commands (no arguments)
    simple = {
        "/status":  lambda: cmd_status(message_id, api),
        "/pause":   lambda: cmd_pause(message_id, api),
        "/resume":  lambda: cmd_resume(message_id, api),
        "/kill":    lambda: cmd_kill(message_id, api),
        "/pulse":   lambda: cmd_pulse(message_id, api),
        "/restart": lambda: cmd_restart(message_id, api),
        "/reflect": lambda: cmd_reflect_request(message_id, api, state),
        "/help":    lambda: cmd_help(message_id, api),
        "/start":   lambda: cmd_help(message_id, api),  # Telegram convention
    }
    
    if cmd in simple and not args:
        await simple[cmd]()
        return
    
    # Commands with arguments
    if cmd == "/model":
        await cmd_model(" ".join(args), message_id, api)
    elif cmd == "/screenshot":
        if not args:
            await send_text(api, "Please provide a URL. Example: /screenshot https://example.com", message_id)
        else:
            await cmd_screenshot(args[0], message_id, api)
    elif cmd == "/search":
        if not args:
            await send_text(api, "Please provide a search query. Example: /search latest AI news", message_id)
        else:
            await cmd_search(" ".join(args), message_id, api)
    elif cmd == "/kb":
        # /kb → list, /kb query <name> <question> → query with multi-word question
        subcommand = args[0] if args else "list"
        remaining = args[1:] if args else []
        await cmd_kb(subcommand, remaining, message_id, api)
    elif cmd == "/schedule":
        subcommand = args[0] if args else "list"
        remaining = args[1:] if args else []
        await cmd_schedule(subcommand, remaining, message_id, api)
    else:
        # Unknown command — treat as natural language
        await react(api, message_id)
        await dispatch_chat(text, message_id, api)


async def dispatch_chat(
    message: str,
    message_id: str | int,
    api: TelegramAPI,
) -> None:
    """Dispatch natural-language chat (matches bash dispatch.sh:142-167).
    
    Only one chat task runs at a time. New messages cancel the previous one.
    The OpenCode subprocess must be explicitly terminated on cancellation.
    """
    global _current_chat_task
    if _current_chat_task and not _current_chat_task.done():
        _current_chat_task.cancel()
    _current_chat_task = asyncio.create_task(
        _handle_chat(message, message_id, api)
    )


async def _handle_chat(
    message: str,
    message_id: str | int,
    api: TelegramAPI,
) -> None:
    """Handle natural-language chat via OpenCode subprocess.
    
    Behavioral contract (matches bash dispatch.sh + chat.sh):
    - Start typing indicator before OpenCode call
    - Run opencode with --agent adjutant, --format json, --model, --session
    - Parse NDJSON output for text, session_id, error_type
    - On model_not_found: user-friendly message (not raw error)
    - On timeout: Anthropic-specific hint about usage limits
    - On cancellation: explicitly terminate the subprocess
    - On empty reply: fallback message
    - Update session on success (save new, touch existing)
    """
    from adjutant.core.paths import get_adj_dir
    adj_dir = get_adj_dir()
    state_dir = adj_dir / "state"
    session_mgr = SessionManager(state_dir)
    
    typing_task = asyncio.create_task(typing_indicator(api))
    proc = None
    try:
        model = get_chat_model(state_dir)
        session_id = session_mgr.get_active_session_id()
        
        args = ["opencode", "run", "--agent", "adjutant", "--dir", str(adj_dir),
                "--format", "json", "--model", model]
        if session_id:
            args.extend(["--session", session_id])
        args.append(message)
        
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=240)
        
        ndjson_result = parse_ndjson(stdout.decode())
        
        # Also check stderr for model errors (matches bash chat.sh:158-164)
        error_type = ndjson_result.error_type
        if not error_type and stderr:
            err_content = stderr.decode()
            if "Model not found" in err_content or "ProviderModelNotFoundError" in err_content:
                error_type = "model_not_found"
        
        if error_type == "model_not_found":
            await send_text(
                api,
                f"The model `{model}` is no longer available. Use /model to switch.",
                message_id,
            )
        else:
            reply = ndjson_result.text or "I ran into a problem getting a response. Try again in a moment."
            await send_text(api, reply, message_id)
        
        # Persist session (matches bash chat.sh:214-220)
        if new_sid:
            if not session_id:
                session_mgr.save(new_sid)
            else:
                session_mgr.touch()
        
    except asyncio.CancelledError:
        # Subprocess must be explicitly killed on cancellation (bash uses pkill -9 -P)
        if proc and proc.returncode is None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=2.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                proc.kill()
        raise
    except asyncio.TimeoutError:
        if proc and proc.returncode is None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                proc.kill()
        # Anthropic-specific hint (matches bash chat.sh:190-196)
        model = get_chat_model(state_dir)
        if model.startswith("anthropic/"):
            await send_text(
                api,
                "Request timed out after 240s. If this keeps happening, you may have hit "
                "your Anthropic 5-hour usage limit — check usage.anthropic.com. Otherwise "
                "the server may just be slow; try again in a moment.",
                message_id,
            )
        else:
            await send_text(
                api,
                "Request timed out — try again shortly.",
                message_id,
            )
    except Exception as e:
        adj_log("dispatch", f"Chat error: {e}")
        await send_text(api, "Something went wrong. Check /status for details.", message_id)
    finally:
        typing_task.cancel()
```

---

#### 3.5 `photos.py` — Photo Download, Dedup, Vision, Session Injection

```python
# adjutant/messaging/telegram/photos.py
import hashlib
import time
import asyncio
from pathlib import Path
from adjutant.messaging.telegram.api import TelegramAPI
from adjutant.messaging.telegram.send import send_text, react, typing_indicator
from adjutant.core.logging import adj_log
from adjutant.core.paths import get_adj_dir


async def handle_photo(
    api: TelegramAPI,
    message_id: str | int,
    file_id: str,
    caption: str = "",
) -> None:
    """Handle an incoming photo (matches bash photos.sh:86-147).
    
    Behavioral contract:
    1. Dedup check (60s TTL by file_id MD5 hash) — skip silently if duplicate
    2. React with 👀 emoji before processing
    3. Download photo from Telegram (getFile → download)
    4. Run vision analysis with caption as prompt (or default prompt)
    5. Send vision reply to user
    6. Inject "[PHOTO]" context into chat session (silent — output suppressed)
    7. Entire flow runs as asyncio.create_task() — matches bash `( ... ) &; disown $!`
    
    On failure at any step: send user-friendly error, don't crash the listener.
    """
    adj_dir = get_adj_dir()
    
    # 1. Deduplication (matches bash photos.sh:20-37)
    dedup_dir = adj_dir / "state" / "photo_dedup"
    dedup_dir.mkdir(parents=True, exist_ok=True)
    _cleanup_dedup(dedup_dir)
    
    marker = dedup_dir / hashlib.md5(file_id.encode()).hexdigest()
    if marker.exists():
        adj_log("telegram", f"Skipping duplicate photo file_id={file_id}")
        return
    marker.touch()
    
    # 2. React (matches bash photos.sh:103)
    await react(api, message_id)
    
    # 3. Download
    typing_task = asyncio.create_task(typing_indicator(api))
    try:
        local_path = await _download_photo(api, file_id, adj_dir)
        if not local_path:
            await send_text(api, "I couldn't retrieve the photo from Telegram. Try again.", message_id)
            return
        
        # 4. Vision analysis
        vision_prompt = caption or "Describe what you see in this image. Be concise and informative."
        
        from adjutant.capabilities.vision.analyze import analyze_image
        vision_reply = await analyze_image(str(local_path), vision_prompt)
        
        if not vision_reply:
            await send_text(
                api,
                f"Photo saved to `{local_path}` but vision analysis failed. Try again.",
                message_id,
            )
            adj_log("telegram", f"Vision analysis failed for {local_path}")
            return
        
        # 5. Send reply
        await send_text(api, vision_reply, message_id)
        adj_log("telegram", f"Vision reply sent for msg={message_id}")
        
        # 6. Inject into session context (silent — matches bash photos.sh:141-143)
        session_msg = f"[PHOTO] User sent a photo"
        if caption:
            session_msg += f' with caption: "{caption}"'
        session_msg += f". Vision analysis: {vision_reply}"
        
        from adjutant.messaging.dispatch import dispatch_chat
        # Fire-and-forget with output suppressed — matches bash `>/dev/null 2>&1 || true`
        try:
            await dispatch_chat(session_msg, message_id, api)
        except Exception:
            pass  # Session injection failure is non-fatal
    
    except Exception as e:
        adj_log("telegram", f"Photo handling error: {e}")
        await send_text(api, "Something went wrong processing the photo.", message_id)
    finally:
        typing_task.cancel()


def _cleanup_dedup(dedup_dir: Path) -> None:
    """Remove dedup markers older than 60s (matches bash photos.sh:21-23).
    
    Bash: `find "${PHOTO_DEDUP_DIR}" -type f -mmin +1 -delete`
    Python: stat each file, delete if mtime > 60s ago.
    """
    cutoff = time.time() - 60
    for marker in dedup_dir.iterdir():
        try:
            if marker.is_file() and marker.stat().st_mtime < cutoff:
                marker.unlink()
        except OSError:
            pass


async def _download_photo(
    api: TelegramAPI,
    file_id: str,
    adj_dir: Path,
) -> Path | None:
    """Download a photo from Telegram (matches bash photos.sh:42-82).
    
    Steps:
    1. getFile API → get file_path
    2. Determine extension from file_path (default: jpg)
    3. Download to photos/ directory with timestamp+random filename
    4. Verify non-empty file exists
    """
    import random
    from datetime import datetime
    
    photos_dir = adj_dir / "photos"
    photos_dir.mkdir(parents=True, exist_ok=True)
    
    # Step 1: Get file path
    file_path = await api.get_file(file_id)
    if not file_path:
        adj_log("telegram", f"getFile failed for file_id={file_id}")
        return None
    
    # Step 2: Extension
    ext = file_path.rsplit(".", 1)[-1] if "." in file_path else "jpg"
    
    # Step 3: Download
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    local_path = photos_dir / f"{timestamp}_{random.randint(1000,9999)}.{ext}"
    
    data = await api.download_file(file_path)
    if not data:
        adj_log("telegram", f"Download failed for {file_path}")
        return None
    
    local_path.write_bytes(data)
    
    # Step 4: Verify
    if not local_path.exists() or local_path.stat().st_size == 0:
        adj_log("telegram", f"Downloaded file empty: {local_path}")
        local_path.unlink(missing_ok=True)
        return None
    
    adj_log("telegram", f"Photo saved: {local_path} ({local_path.stat().st_size} bytes)")
    return local_path
```

---

#### 3.6 `notify.py` — Push Notifications with Budget Guard

```python
# adjutant/messaging/telegram/notify.py
import datetime
from pathlib import Path
from adjutant.messaging.telegram.api import TelegramAPI
from adjutant.messaging.telegram.send import sanitize_message
from adjutant.core.logging import adj_log


async def send_notification(
    api: TelegramAPI,
    message: str,
    adj_dir: Path,
    config: dict,
) -> str:
    """Send a notification with daily budget enforcement.
    
    Behavioral contract (matches bash notify.sh:25-54):
    - Budget state: state/notify_count_YYYY-MM-DD.txt (integer count)
    - Config: notifications.max_per_day (default: 3) from adjutant.yaml
    - Bash reads max_per_day with grep (notify.sh:33-35); Python reads from parsed config
    - Returns "OK:sent (N/max today)" or "ERROR:budget_exceeded (N/max today)"
    
    CRITICAL difference from send_text():
    - NO parse_mode (matches bash notify.sh:43-44 — omits parse_mode intentionally)
    - Notifications are generated programmatically and may contain characters
      that break Markdown parsing
    - Uses 4096 char limit (matches bash notify.sh:23) not 4000
    - Response is checked for "ok":true (matches bash notify.sh:48)
    - Count is incremented ONLY on successful send (matches bash notify.sh:49)
    """
    today = datetime.date.today().isoformat()
    count_file = adj_dir / "state" / f"notify_count_{today}.txt"
    count = 0
    if count_file.exists():
        try:
            count = int(count_file.read_text().strip())
        except (ValueError, OSError):
            count = 0
    
    max_per_day = config.get("notifications", {}).get("max_per_day", 3)
    
    if count >= max_per_day:
        return f"ERROR:budget_exceeded ({count}/{max_per_day} sent today)"
    
    # Sanitize (same function, but note: no parse_mode on send)
    message = sanitize_message(message)
    
    # Send WITHOUT parse_mode (intentional — matches bash notify.sh:43-44)
    result = await api.send_message(
        text=message,
        parse_mode=None,  # Explicitly no parse_mode
    )
    
    if result and result.get("ok"):
        count_file.write_text(str(count + 1))
        return f"OK:sent ({count + 1}/{max_per_day} today)"
    else:
        adj_log("telegram", f"Notification send failed: {result}")
        return f"ERROR:send_failed"
```

**Note on quiet hours:** `adjutant.yaml.example` defines `notifications.quiet_hours.enabled/start/end`
(lines 101-104) but bash does not implement quiet hours. The Python port adds this as an optional
check — if `quiet_hours.enabled` is true and current time is within the window, notifications are
deferred (not dropped). Implementation deferred to post-Phase 3 enhancement.

---

#### 3.7 `session.py` — OpenCode Session Management

```python
# adjutant/messaging/telegram/session.py
import json
import time
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

SESSION_TIMEOUT = 7200  # 2 hours (hardcoded — matches bash chat.sh:30)

@dataclass
class Session:
    session_id: str
    last_message_epoch: int
    last_message_at: str


class SessionManager:
    """OpenCode session continuity (matches bash chat.sh:53-99).
    
    Behavioral contract:
    - Session stored in state/telegram_session.json
    - Format: {"session_id": "ses_abc", "last_message_epoch": 1741456800, "last_message_at": "..."}
    - Sessions reused within 2h timeout window
    - After timeout: next message starts fresh session
    - get_active_session_id() returns session_id if within timeout, else None
    - save() writes full JSON (new session)
    - touch() updates only timestamps (existing session)
    
    Python format change (intentional):
    - last_message_at: ISO-8601 UTC ("YYYY-MM-DDTHH:MM:SS") instead of bash's "HH:MM DD.MM.YYYY"
    - last_message_epoch is machine-authoritative for all timeout calculations
    - Python reads both formats gracefully (legacy bash files have HH:MM format)
    - Legacy handling: int(float(...)) for decimal epoch values from old Python-era files
    """
    
    def __init__(self, state_dir: Path):
        self.session_file = state_dir / "telegram_session.json"
    
    def get_active_session_id(self) -> Optional[str]:
        """Return session ID if active (within timeout), else None."""
        if not self.session_file.exists():
            return None
        try:
            data = json.loads(self.session_file.read_text())
            epoch = int(float(data.get("last_message_epoch", 0)))  # Handle legacy decimals
            if time.time() - epoch < SESSION_TIMEOUT:
                return data.get("session_id")
        except (json.JSONDecodeError, KeyError, ValueError):
            pass
        return None
    
    def save(self, session_id: str):
        """Save a new session (full write — matches bash chat.sh:71-83)."""
        now = time.time()
        data = {
            "session_id": session_id,
            "last_message_epoch": int(now),
            "last_message_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(now)),
        }
        self.session_file.write_text(json.dumps(data))
    
    def touch(self):
        """Update timestamps only (matches bash chat.sh:85-99)."""
        if not self.session_file.exists():
            return
        try:
            data = json.loads(self.session_file.read_text())
            now = time.time()
            data["last_message_epoch"] = int(now)
            data["last_message_at"] = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(now))
            self.session_file.write_text(json.dumps(data))
        except (json.JSONDecodeError, OSError):
            pass  # Non-fatal — next message will create a new session
```

---

#### 3.8 `listener.py` — Telegram Polling Loop

```python
# adjutant/messaging/telegram/listener.py
import asyncio
from pathlib import Path
from adjutant.messaging.telegram.api import TelegramAPI
from adjutant.messaging.dispatch import dispatch_message, dispatch_photo, DispatchState, RateLimiter
from adjutant.messaging.telegram.send import send_text
from adjutant.core.lockfiles import is_killed
from adjutant.core.opencode import opencode_reap
from adjutant.core.process import PidLock
from adjutant.core.logging import adj_log
from adjutant.core.paths import get_adj_dir


def load_offset(state_dir: Path) -> int:
    """Load poll offset from state file (matches bash listener.sh:78-88).
    
    Returns 0 if file missing, empty, or corrupted (non-integer).
    Corrupted files are logged and reset to 0.
    """
    offset_file = state_dir / "telegram_offset"
    if not offset_file.exists():
        return 0
    try:
        raw = offset_file.read_text().strip()
        if raw.isdigit():
            return int(raw)
        adj_log("telegram", f"WARNING: corrupt offset file (value: '{raw}'), resetting to 0")
        offset_file.write_text("0")
        return 0
    except OSError:
        return 0


def save_offset(state_dir: Path, offset: int) -> None:
    """Persist poll offset (matches bash listener.sh:159)."""
    (state_dir / "telegram_offset").write_text(str(offset))


async def telegram_listener() -> None:
    """Main Telegram polling loop (matches bash listener.sh:110-198).
    
    Behavioral contract:
    - Long-poll with 10s timeout (idles in API call, not sleep)
    - Process ONLY the last update per batch (prevent replay storms)
    - Advance offset for ALL updates (acknowledge receipt to Telegram)
    - Background reaper task kills orphaned language servers every ~60s
    - Never crash — catch all exceptions per iteration
    - Check KILLED lockfile each iteration
    - Single-instance guard via PidLock (listener.lock/pid)
    
    Error handling (matches bash's intentional lack of `set -euo pipefail`):
    - Top-level: catch everything, log, sleep, continue
    - Network errors: 5s backoff
    - Other errors: 1s backoff
    - The daemon must never crash
    """
    adj_dir = get_adj_dir()
    state_dir = adj_dir / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    
    # Single-instance guard (matches bash listener.sh:56-72)
    lock = PidLock(state_dir / "listener.lock")
    if not lock.acquire():
        adj_log("telegram", "Another listener is already running. Exiting.")
        return
    
    api = TelegramAPI()
    state = DispatchState()
    rate_limiter = RateLimiter()
    offset = load_offset(state_dir)
    last_processed_id = 0
    
    # Background reaper (matches bash listener.sh:103-122)
    reaper_task = asyncio.create_task(_reaper_loop())
    
    adj_log("telegram", f"Listener started (offset={offset})")
    
    try:
        while not is_killed():
            try:
                updates = await api.get_updates(
                    offset=offset,
                    timeout=10,
                    allowed_updates=["message"],
                )
                
                if not updates:
                    continue
                
                # Advance offset for ALL updates (acknowledge receipt)
                last_update = updates[-1]
                update_id = last_update.get("update_id")
                if update_id:
                    offset = update_id + 1
                    save_offset(state_dir, offset)
                    
                    # Deduplication (matches bash listener.sh:162-167)
                    if update_id <= last_processed_id:
                        adj_log("telegram", f"Skipping duplicate update_id={update_id}")
                        continue
                    last_processed_id = update_id
                
                # Route: photo or text (matches bash listener.sh:176-197)
                message = last_update.get("message", {})
                if not message.get("chat", {}).get("id") or not message.get("message_id"):
                    continue
                
                if message.get("photo"):
                    await dispatch_photo(last_update, api)
                elif message.get("text"):
                    await dispatch_message(last_update, state, rate_limiter, api)
                
            except Exception as e:
                adj_log("telegram", f"Poll loop error: {e}")
                await asyncio.sleep(5)
    finally:
        reaper_task.cancel()
        await api.close()
        lock.release()
        adj_log("telegram", "Listener exited.")


async def _reaper_loop() -> None:
    """Kill orphaned language-server processes every ~60s.
    
    Matches bash listener.sh:103-122 (reap every ~6 poll cycles).
    Note: opencode_reap() uses psutil.process_iter() which is synchronous —
    the implementation wraps scanning in asyncio.to_thread().
    """
    while True:
        await asyncio.sleep(60)
        try:
            await opencode_reap()
        except Exception as e:
            adj_log("reaper", f"Reap failed: {e}")
```

---

#### 3.9 `commands.py` — Slash Command Handlers

All `/command` handlers. These are backend-agnostic — they use `send_text()`, `react()`,
`typing_indicator()` from `send.py`, not Telegram API directly.

```python
# adjutant/messaging/telegram/commands.py
import asyncio
from pathlib import Path
from adjutant.messaging.telegram.api import TelegramAPI
from adjutant.messaging.telegram.send import send_text, send_photo, react, typing_indicator
from adjutant.messaging.dispatch import DispatchState
from adjutant.core.logging import adj_log, fmt_ts
from adjutant.core.lockfiles import set_paused, clear_paused
from adjutant.core.paths import get_adj_dir
from adjutant.core.model import get_chat_model
from adjutant.core.opencode import opencode_run
from adjutant.lib.ndjson import parse_ndjson


async def cmd_status(message_id: str | int, api: TelegramAPI) -> None:
    """Run status dashboard and send result (matches bash commands.sh:25-32)."""
    from adjutant.observability.status import get_status
    try:
        status_output = await get_status()
    except Exception:
        status_output = "Could not retrieve status."
    await send_text(api, status_output, message_id)


async def cmd_pause(message_id: str | int, api: TelegramAPI) -> None:
    """Pause adjutant (matches bash commands.sh:35-44).
    
    Sets PAUSED lockfile and appends to journal.
    """
    from datetime import datetime
    adj_dir = get_adj_dir()
    set_paused()
    ts = datetime.now().strftime("%H:%M %d.%m.%Y")
    journal_file = adj_dir / "journal" / f"{datetime.now().strftime('%Y-%m-%d')}.md"
    journal_file.parent.mkdir(parents=True, exist_ok=True)
    with open(journal_file, "a") as f:
        f.write(f"{ts} — Paused via Telegram command.\n")
    await send_text(api, "Got it, I've paused. Send /resume whenever you want me back.", message_id)
    adj_log("telegram", "Adjutant paused via Telegram.")


async def cmd_resume(message_id: str | int, api: TelegramAPI) -> None:
    """Resume adjutant (matches bash commands.sh:47-56)."""
    from datetime import datetime
    adj_dir = get_adj_dir()
    clear_paused()
    ts = datetime.now().strftime("%H:%M %d.%m.%Y")
    journal_file = adj_dir / "journal" / f"{datetime.now().strftime('%Y-%m-%d')}.md"
    journal_file.parent.mkdir(parents=True, exist_ok=True)
    with open(journal_file, "a") as f:
        f.write(f"{ts} — Resumed via Telegram command.\n")
    await send_text(api, "I'm back online and keeping an eye on things.", message_id)
    adj_log("telegram", "Adjutant resumed via Telegram.")


async def cmd_kill(message_id: str | int, api: TelegramAPI) -> None:
    """Emergency kill (matches bash commands.sh:59-68).
    
    Background the kill script so we can send reply before listener dies.
    """
    adj_log("telegram", "EMERGENCY KILL SWITCH activated via Telegram.")
    # Send reply BEFORE kill (bash sends reply then backgrounds the kill script)
    await send_text(api, "Emergency kill switch activated. Shutting down all systems...", message_id)
    from adjutant.lifecycle.kill import emergency_kill
    asyncio.create_task(emergency_kill())


async def cmd_pulse(message_id: str | int, api: TelegramAPI) -> None:
    """Run a pulse check (matches bash commands.sh:71-135).
    
    Behavioral contract:
    - If opencode not available: show last heartbeat from state file
    - If available: run pulse prompt through OpenCode with 240s timeout
    - PID-snapshot orphan cleanup before/after (via opencode_run wrapper)
    - On timeout (exit 124): "timed out after 4 minutes"
    - On error with no output: "ran into an error (exit N)"
    """
    await send_text(api, "On it — running a pulse check now. Give me a moment.", message_id)
    adj_log("telegram", "Pulse triggered via Telegram.")
    
    typing_task = asyncio.create_task(typing_indicator(api))
    try:
        adj_dir = get_adj_dir()
        pulse_prompt = adj_dir / "prompts" / "pulse.md"
        
        if not pulse_prompt.exists():
            await send_text(api, f"I can't find the pulse prompt — expected it at {pulse_prompt}.", message_id)
            return
        
        prompt_text = pulse_prompt.read_text()
        result = await opencode_run(
            args=["run", "--dir", str(adj_dir), "--format", "json", prompt_text],
            timeout=240,
        )
        
        ndjson_result = parse_ndjson(result.stdout)
        text = ndjson_result.text
        
        if result.timed_out:
            text = "The pulse check timed out after 4 minutes."
        elif result.exit_code != 0 and not text:
            text = f"The pulse check ran into an error (exit {result.exit_code}). Check adjutant.log for details."
        
        await send_text(api, text or "Pulse complete — nothing to report.", message_id)
        adj_log("telegram", f"Pulse completed via Telegram")
    except Exception as e:
        adj_log("telegram", f"Pulse failed: {e}")
        await send_text(api, "The pulse check failed. Check /status for details.", message_id)
    finally:
        typing_task.cancel()


async def cmd_restart(message_id: str | int, api: TelegramAPI) -> None:
    """Restart services (matches bash commands.sh:138-152)."""
    await send_text(api, "Restarting all services...", message_id)
    adj_log("telegram", "Restart triggered via Telegram.")
    from adjutant.lifecycle.restart import restart
    asyncio.create_task(restart())
    await asyncio.sleep(2)
    await send_text(
        api,
        "Services restarted. If I don't respond, I'm still restarting — try again in 10 seconds.",
        message_id,
    )


async def cmd_reflect_request(
    message_id: str | int,
    api: TelegramAPI,
    state: DispatchState,
) -> None:
    """Request reflection confirmation (matches bash commands.sh:155-161)."""
    state.pending_reflect = True
    await send_text(
        api,
        "Starting a full reflection — this goes deeper than a pulse and may take a couple "
        "of minutes. Reply */confirm* if you'd like me to go ahead, or send anything else to cancel.",
        message_id,
    )
    adj_log("telegram", "Reflect requested via Telegram — awaiting confirmation.")


async def cmd_reflect_confirm(
    message_id: str | int,
    api: TelegramAPI,
    state: DispatchState,
) -> None:
    """Execute reflection (matches bash commands.sh:164-209).
    
    Same pattern as cmd_pulse but with review.md prompt and 300s timeout.
    """
    state.pending_reflect = False
    await send_text(api, "Great, I'm starting the reflection now — this usually takes a minute or two.", message_id)
    adj_log("telegram", "Reflect confirmed via Telegram.")
    
    typing_task = asyncio.create_task(typing_indicator(api))
    try:
        adj_dir = get_adj_dir()
        reflect_prompt = adj_dir / "prompts" / "review.md"
        
        if not reflect_prompt.exists():
            await send_text(api, "I can't find the reflection prompt — something may be misconfigured.", message_id)
            return
        
        prompt_text = reflect_prompt.read_text()
        result = await opencode_run(
            args=["run", "--dir", str(adj_dir), "--format", "json", prompt_text],
            timeout=300,
        )
        
        ndjson_result = parse_ndjson(result.stdout)
        text = ndjson_result.text
        
        if result.timed_out:
            text = "The reflection timed out after 5 minutes. Try again from inside OpenCode."
        elif result.exit_code != 0 and not text:
            text = f"The reflection ran into an error (exit {result.exit_code}). Check adjutant.log for details."
        
        await send_text(api, text or "Reflection complete.", message_id)
    except Exception as e:
        adj_log("telegram", f"Reflect failed: {e}")
        await send_text(api, "The reflection failed. Check /status for details.", message_id)
    finally:
        typing_task.cancel()


async def cmd_help(message_id: str | int, api: TelegramAPI) -> None:
    """Show help text (matches bash commands.sh:212-234)."""
    await send_text(api, """Here's what I can do for you:

You can just talk to me naturally — ask about your projects, priorities, upcoming events, or anything in your files and I'll look it up and answer.

Or use a command:
/status — I'll tell you if I'm running or paused, show registered scheduled jobs, and when I last checked in.
/pulse — I'll run a quick check across your projects and summarise what I find.
/restart — Restart all services (listener, opencode web).
/reflect — I'll do a deeper Opus reflection (I'll ask you to confirm first).
/screenshot <url> — Take a full-page screenshot of any website and send it here.
/search <query> — Search the web via Brave Search and return top results.
/kb — List knowledge bases or query one (/kb query <name> <question>).
/schedule — List scheduled jobs or manage them (/schedule run <name>, /schedule enable <name>, /schedule disable <name>).
/pause — I'll stop monitoring until you're ready for me to resume.
/resume — I'll pick back up where I left off.
/model — Show current model, or switch with /model <name>.
/kill — Emergency shutdown. Terminates all Adjutant processes and locks system. Use `adjutant start` to recover.
/help — Shows this message.

You can also send me a photo — I'll store it locally and tell you what I see.""", message_id)


async def cmd_model(arg: str, message_id: str | int, api: TelegramAPI) -> None:
    """Show/switch model (matches bash commands.sh:238-273).
    
    - No arg: show current model + available models (first 30)
    - With arg: validate against `opencode models` and switch
    """
    adj_dir = get_adj_dir()
    state_dir = adj_dir / "state"
    model_file = state_dir / "telegram_model.txt"
    current_model = get_chat_model(state_dir)
    
    if not arg:
        # List models (matches bash commands.sh:251-261)
        import asyncio
        proc = await asyncio.create_subprocess_exec(
            "opencode", "models",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await proc.communicate()
        model_list = "\n".join(stdout.decode().strip().splitlines()[:30])
        
        await send_text(api, f"""Current model: *{current_model}*

Available models (first 30 — full list at `opencode models`):
```
{model_list}
```

Switch with: /model <name>""", message_id)
        return
    
    # Validate model exists (matches bash commands.sh:265-268)
    proc = await asyncio.create_subprocess_exec(
        "opencode", "models",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    stdout, _ = await proc.communicate()
    available = stdout.decode().strip().splitlines()
    
    if arg not in available:
        await send_text(api, "I don't recognise that model. Run /model to see available options.", message_id)
        return
    
    model_file.write_text(arg)
    await send_text(api, f"Switched to *{arg}*.", message_id)
    adj_log("telegram", f"Model switched to {arg}")


async def cmd_screenshot(url: str, message_id: str | int, api: TelegramAPI) -> None:
    """Take screenshot (matches bash commands.sh:276-316).
    
    Runs screenshot capability, sends photo + vision result, injects into session.
    """
    adj_log("telegram", f"Screenshot requested: {url}")
    await react(api, message_id)
    
    typing_task = asyncio.create_task(typing_indicator(api))
    try:
        from adjutant.capabilities.screenshot.capture import take_screenshot
        result = await take_screenshot(url)
        
        if result.error:
            await send_text(api, f"Screenshot failed: {result.error}", message_id)
            return
        
        # Two-stage send: photo first, then vision caption (matches bash pattern)
        await send_photo(api, result.filepath, caption=result.vision_caption)
        
        # Session injection (matches bash commands.sh:311-312)
        if result.vision_caption:
            from adjutant.messaging.dispatch import dispatch_chat
            session_msg = f"[SCREENSHOT] User requested screenshot of {url}. Vision analysis: {result.vision_caption}"
            try:
                await dispatch_chat(session_msg, message_id, api)
            except Exception:
                pass
    except Exception as e:
        adj_log("telegram", f"Screenshot failed for {url}: {e}")
        await send_text(api, f"Screenshot failed: {e}", message_id)
    finally:
        typing_task.cancel()


async def cmd_search(query: str, message_id: str | int, api: TelegramAPI) -> None:
    """Web search (matches bash commands.sh:319-350)."""
    adj_log("telegram", f"Search requested: {query}")
    await react(api, message_id)
    
    typing_task = asyncio.create_task(typing_indicator(api))
    try:
        from adjutant.capabilities.search.brave import search
        result = await search(query)
        
        if result.startswith("ERROR:"):
            await send_text(api, f"Search failed: {result[6:]}", message_id)
        else:
            await send_text(api, result, message_id)
            adj_log("telegram", f"Search results sent for: {query}")
    except Exception as e:
        adj_log("telegram", f"Search failed for '{query}': {e}")
        await send_text(api, f"Search failed: {e}", message_id)
    finally:
        typing_task.cancel()


async def cmd_kb(
    subcommand: str,
    remaining: list[str],
    message_id: str | int,
    api: TelegramAPI,
) -> None:
    """KB management (matches bash commands.sh:353-421).
    
    /kb → list all KBs
    /kb query <name> <question> → query a KB
    
    Note on argument parsing: bash uses unquoted ${text#/kb } which splits on
    whitespace. Python uses shlex.split() via route_command(), so remaining is
    already properly split. remaining[0] is kb_name, remaining[1:] joined is query.
    """
    from adjutant.capabilities.kb.registry import kb_count, kb_list, kb_exists
    
    if subcommand == "list" or not subcommand:
        count = kb_count()
        if count == 0:
            await send_text(api, "No knowledge bases registered yet. Create one with `adjutant kb create`.", message_id)
            return
        
        entries = kb_list()
        text = f"*Knowledge Bases* ({count}):\n"
        for entry in entries:
            text += f"\n• *{entry.name}* ({entry.access}) — {entry.description}"
        text += "\n\nQuery with: /kb query <name> <question>"
        await send_text(api, text, message_id)
        return
    
    if subcommand == "query":
        if len(remaining) < 2:
            await send_text(api, "Usage: /kb query <name> <your question>", message_id)
            return
        
        kb_name = remaining[0]
        query = " ".join(remaining[1:])
        
        if not kb_exists(kb_name):
            await send_text(api, f"Knowledge base '{kb_name}' not found. Run /kb list to see available KBs.", message_id)
            return
        
        await react(api, message_id)
        
        typing_task = asyncio.create_task(typing_indicator(api))
        try:
            from adjutant.capabilities.kb.query import kb_query
            result = await asyncio.to_thread(kb_query, kb_name, query)
            
            if not result:
                await send_text(api, "KB query failed or returned empty. Check the KB has content.", message_id)
            else:
                await send_text(api, f"[{kb_name}] {result}", message_id)
                adj_log("telegram", f"KB query answered from {kb_name}")
        except Exception as e:
            adj_log("telegram", f"KB query failed for {kb_name}: {e}")
            await send_text(api, f"KB query failed: {e}", message_id)
        finally:
            typing_task.cancel()
        return
    
    await send_text(api, """Usage: /kb list — show knowledge bases
/kb query <name> <question> — ask a KB""", message_id)


async def cmd_schedule(
    subcommand: str,
    remaining: list[str],
    message_id: str | int,
    api: TelegramAPI,
) -> None:
    """Schedule management (matches bash commands.sh:424-534).
    
    /schedule → list all jobs
    /schedule run <name> → run a job immediately
    /schedule enable <name> → enable a job
    /schedule disable <name> → disable a job
    """
    from adjutant.capabilities.schedule.registry import (
        schedule_count, schedule_list, schedule_exists,
        schedule_get_field, schedule_set_enabled,
    )
    
    name = remaining[0] if remaining else ""
    
    if subcommand == "list" or not subcommand:
        count = schedule_count()
        if count == 0:
            await send_text(api, "No scheduled jobs registered yet. Add one with `adjutant schedule add`.", message_id)
            return
        
        entries = schedule_list()
        text = f"*Scheduled Jobs* ({count}):\n"
        for entry in entries:
            flag = " _(disabled)_" if not entry.enabled else ""
            text += f"\n• *{entry.name}*{flag} — {entry.schedule}\n  {entry.description}"
        text += "\n\nManage: /schedule run <name> | /schedule enable <name> | /schedule disable <name>"
        await send_text(api, text, message_id)
        return
    
    if subcommand == "run":
        if not name:
            await send_text(api, "Usage: /schedule run <name>", message_id)
            return
        if not schedule_exists(name):
            await send_text(api, f"Job '{name}' not found. Use /schedule list to see registered jobs.", message_id)
            return
        
        await react(api, message_id)
        typing_task = asyncio.create_task(typing_indicator(api))
        try:
            from adjutant.capabilities.schedule.runner import run_schedule
            result = await run_schedule(name)
            await send_text(api, f"[{name}] {result}", message_id)
            adj_log("telegram", f"Schedule job '{name}' run via Telegram")
        except Exception as e:
            adj_log("telegram", f"Schedule run failed for '{name}': {e}")
            await send_text(api, f"Job '{name}' failed: {e}", message_id)
        finally:
            typing_task.cancel()
        return
    
    if subcommand == "enable":
        if not name:
            await send_text(api, "Usage: /schedule enable <name>", message_id)
            return
        if not schedule_exists(name):
            await send_text(api, f"Job '{name}' not found. Use /schedule list to see registered jobs.", message_id)
            return
        schedule_set_enabled(name, True)
        await send_text(api, f"Job *{name}* enabled — crontab entry installed.", message_id)
        adj_log("telegram", f"Schedule job '{name}' enabled via Telegram")
        return
    
    if subcommand == "disable":
        if not name:
            await send_text(api, "Usage: /schedule disable <name>", message_id)
            return
        if not schedule_exists(name):
            await send_text(api, f"Job '{name}' not found. Use /schedule list to see registered jobs.", message_id)
            return
        schedule_set_enabled(name, False)
        await send_text(api, f"Job *{name}* disabled — crontab entry removed.", message_id)
        adj_log("telegram", f"Schedule job '{name}' disabled via Telegram")
        return
    
    await send_text(api, """Usage:
/schedule list — show all scheduled jobs
/schedule run <name> — run a job immediately
/schedule enable <name> — enable a job
/schedule disable <name> — disable a job""", message_id)
```

---

#### 3.10 `service.py` — Listener Start/Stop/Status

```python
# adjutant/messaging/telegram/service.py
import asyncio
import time
from pathlib import Path
from adjutant.core.process import read_pid_file, pid_is_alive, kill_graceful, find_by_cmdline
from adjutant.core.lockfiles import check_killed
from adjutant.core.logging import adj_log
from adjutant.core.paths import get_adj_dir


class TelegramService:
    """Manage the Telegram listener process (matches bash service.sh).
    
    Behavioral contract:
    - Three-tier listener detection (matches bash service.sh:21-53):
      1. listener.lock/pid (PidLock — authoritative, written by listener itself)
      2. state/telegram.pid (nohup wrapper PID — fallback)
      3. find_by_cmdline (pgrep — last resort for orphans)
    
    - start: check KILLED, check already running, clean stale files, launch,
      wait up to 5s for listener.lock/pid to appear (confirms real startup)
    - stop: kill via detected PID, pkill orphans, clean all tracking files
    - restart: stop + sleep 1 + start
    - status: detect + sync telegram.pid + clean stale files
    """
    
    def __init__(self):
        self.adj_dir = get_adj_dir()
        self.state_dir = self.adj_dir / "state"
        self.pidfile = self.state_dir / "telegram.pid"
        self.lockdir = self.state_dir / "listener.lock"
        self.lockpid = self.lockdir / "pid"
        self.logfile = self.state_dir / "telegram_listener.log"
    
    def find_listener_pid(self) -> int | None:
        """Three-tier PID detection (matches bash service.sh:21-53).
        
        Priority order:
        1. listener.lock/pid — the listener writes its own PID here
        2. telegram.pid — the nohup wrapper PID recorded at launch
        3. pgrep — catches orphans that lost both tracking files
        """
        # Tier 1: listener.lock/pid
        pid = read_pid_file(self.lockpid)
        if pid:
            return pid
        
        # Tier 2: telegram.pid
        pid = read_pid_file(self.pidfile)
        if pid:
            return pid
        
        # Tier 3: pgrep (matches bash: pgrep -f "messaging/telegram/listener")
        procs = find_by_cmdline("adjutant.messaging.telegram.listener")
        if procs:
            return procs[0].pid
        
        return None
    
    def is_running(self) -> bool:
        return self.find_listener_pid() is not None
    
    async def start(self) -> str:
        """Start the listener (matches bash service.sh:71-117).
        
        Returns status message string.
        """
        # Check KILLED lockfile
        if not check_killed():
            return "Cannot start — system is in KILLED state. Use `adjutant start` to recover."
        
        existing = self.find_listener_pid()
        if existing:
            # Sync telegram.pid if it drifted (matches bash service.sh:78)
            self.pidfile.write_text(str(existing))
            return f"Already running (PID {existing})"
        
        # Clean stale tracking files (matches bash service.sh:83-84)
        self.pidfile.unlink(missing_ok=True)
        if self.lockdir.exists():
            import shutil
            shutil.rmtree(self.lockdir, ignore_errors=True)
        
        # Launch listener as subprocess (matches bash: nohup listener.sh >> log 2>&1 &)
        proc = await asyncio.create_subprocess_exec(
            "python", "-m", "adjutant.messaging.telegram.listener",
            stdout=open(self.logfile, "a"),
            stderr=asyncio.subprocess.STDOUT,
        )
        self.pidfile.write_text(str(proc.pid))
        
        # Wait up to 5s for listener.lock/pid (matches bash service.sh:91-104)
        for _ in range(5):
            await asyncio.sleep(1)
            if self.lockpid.exists():
                real_pid = read_pid_file(self.lockpid)
                if real_pid:
                    self.pidfile.write_text(str(real_pid))
                    return f"Started (PID {real_pid})"
        
        # Fallback: check if nohup child is alive (matches bash service.sh:106-116)
        if pid_is_alive(proc.pid):
            return f"Started (PID {proc.pid}) — but listener.lock not yet created"
        
        self.pidfile.unlink(missing_ok=True)
        return f"Failed to start (check {self.logfile})"
    
    async def stop(self) -> str:
        """Stop the listener (matches bash service.sh:118-130)."""
        pid = self.find_listener_pid()
        if pid:
            kill_graceful(pid, timeout=5.0)
            msg = f"Stopped (was PID {pid})"
        else:
            msg = "Not running"
        
        # Kill orphans (matches bash: pkill -TERM -f "messaging/telegram/listener")
        for proc in find_by_cmdline("adjutant.messaging.telegram.listener"):
            try:
                proc.terminate()
            except Exception:
                pass
        
        # Clean all tracking files (matches bash service.sh:128-129)
        self.pidfile.unlink(missing_ok=True)
        if self.lockdir.exists():
            import shutil
            shutil.rmtree(self.lockdir, ignore_errors=True)
        
        return msg
    
    async def restart(self) -> str:
        """Restart (matches bash service.sh:131-135)."""
        stop_msg = await self.stop()
        await asyncio.sleep(1)
        start_msg = await self.start()
        return f"{stop_msg}\n{start_msg}"
    
    def status(self) -> str:
        """Status check (matches bash service.sh:136-147)."""
        pid = self.find_listener_pid()
        if pid:
            # Sync telegram.pid (matches bash service.sh:140)
            self.pidfile.write_text(str(pid))
            return f"Running (PID {pid})"
        
        # Clean stale files (matches bash service.sh:143-145)
        self.pidfile.unlink(missing_ok=True)
        if self.lockdir.exists():
            import shutil
            shutil.rmtree(self.lockdir, ignore_errors=True)
        return "Stopped"
```

---

#### 3.11 `adaptor.py` — Backend-Agnostic Interface

```python
# adjutant/messaging/adaptor.py
"""Backend-agnostic messaging interface (matches bash adaptor.sh).

This module defines the abstract contract. The Telegram implementation provides
the concrete backend. Future backends (Slack, Discord, CLI) would implement
the same interface.

In bash, adaptor.sh defines no-op stubs that telegram/send.sh overrides.
In Python, adaptor.py defines the Protocol/abstract class.
"""
from typing import Protocol, runtime_checkable


@runtime_checkable
class MessagingAdaptor(Protocol):
    """Interface contract for messaging backends."""
    
    async def send_text(self, message: str, reply_to: str | int | None = None) -> None:
        """Send a text message."""
        ...
    
    async def send_photo(self, path: str, caption: str | None = None) -> None:
        """Send a photo."""
        ...
    
    async def react(self, message_id: str | int, emoji: str = "\U0001f440") -> None:
        """Add reaction to a message (fire-and-forget)."""
        ...
    
    async def start_listener(self) -> None:
        """Start the polling/listening loop."""
        ...
    
    async def stop_listener(self) -> None:
        """Stop the listener."""
        ...
```

---

#### 3.12 Phase 3 Test Specifications

**Tests:** ~185 tests for the messaging layer, broken down by module:

| Test File | Module | Expected Tests | Key Assertions |
|-----------|--------|---------------|----------------|
| `test_api.py` | `telegram/api.py` | ~20 | Connection pooling, get_updates returns list, get_updates empty on error, send_message with/without reply_to, send_message with/without parse_mode, send_photo file existence check, set_message_reaction fire-and-forget, send_chat_action, get_file success/failure, download_file success/failure, timeout handling, HTTP error logging, client reuse across calls |
| `test_send.py` | `telegram/send.py` | ~18 | sanitize_message strips 0x00-0x08/0x0B-0x1F/0x7F, sanitize preserves tab+newline, sanitize truncates at 4096 chars (character-based), truncation adds "...", send_text calls sanitize before API, send_text passes parse_mode=Markdown, send_photo sanitizes caption, react spawns task (not awaited), typing_indicator sends every 4s, typing_indicator handles cancellation cleanly |
| `test_auth.py` | `telegram/auth.py` | ~8 | authorize matches int-to-string, authorize matches string-to-string, authorize rejects wrong ID, authorize silent (no side effects on rejection), authorize handles None/empty |
| `test_dispatch.py` | `dispatch.py` | ~30 | RateLimiter allows 10/min, RateLimiter rejects 11th, RateLimiter appends before checking, RateLimiter prunes old entries, RateLimiter env var override, DispatchState starts with pending_reflect=False, dispatch_message rejects unauthorized (silent), dispatch_message rate limits (polite error), dispatch_message pending_reflect consumes /confirm, dispatch_message pending_reflect cancels on other text, dispatch_message pending_reflect consumed message NOT re-dispatched, dispatch_message routes /commands, dispatch_message routes natural language to chat, dispatch_photo rejects unauthorized, dispatch_photo extracts highest-res file_id, route_command simple commands (all 9), route_command with args, route_command unknown → chat, dispatch_chat cancels previous task, _handle_chat subprocess explicit kill on cancel, _handle_chat timeout → anthropic hint, _handle_chat model_not_found from stdout, _handle_chat model_not_found from stderr, _handle_chat empty reply → fallback, _handle_chat session save/touch |
| `test_photos.py` | `telegram/photos.py` | ~16 | Dedup rejects duplicate within 60s, dedup allows after 60s, dedup cleanup removes old markers, dedup uses MD5 hash of file_id, download_photo success path, download_photo getFile failure, download_photo download failure, download_photo empty file cleanup, handle_photo full flow (dedup→download→vision→reply→session), handle_photo vision failure → error message, handle_photo session injection is non-fatal, handle_photo react before processing |
| `test_notify.py` | `telegram/notify.py` | ~12 | Budget allows under limit, budget rejects at limit, budget count file created on send, budget count incremented only on success, no parse_mode on notification, sanitize applied, max_per_day from config, max_per_day default 3, count file per-day isolation, send failure doesn't increment count, ERROR:budget_exceeded format, OK:sent format |
| `test_session.py` | `telegram/session.py` | ~14 | get_active_session_id within timeout, get_active_session_id expired → None, get_active_session_id missing file → None, get_active_session_id corrupted JSON → None, get_active_session_id legacy decimal epoch, save writes full JSON, save ISO-8601 format, touch updates only timestamps, touch missing file is no-op, touch corrupted file is no-op, SESSION_TIMEOUT is 7200 |
| `test_listener.py` | `telegram/listener.py` | ~18 | load_offset from file, load_offset missing file → 0, load_offset corrupted → 0 + reset, save_offset writes, poll loop processes only last update, poll loop advances offset for all, poll loop deduplication, poll loop checks KILLED each iteration, poll loop catches network errors + 5s sleep, poll loop catches other errors + 1s sleep, single-instance guard via PidLock, reaper task runs every 60s, cleanup on exit (api.close, lock.release), photo routing, text routing |
| `test_commands.py` | `telegram/commands.py` | ~25 | cmd_status calls get_status, cmd_pause sets lockfile + journal, cmd_resume clears lockfile + journal, cmd_kill backgrounds kill + sends reply first, cmd_pulse with prompt, cmd_pulse timeout, cmd_pulse missing prompt, cmd_restart backgrounds restart, cmd_reflect_request sets pending_reflect, cmd_reflect_confirm clears pending_reflect, cmd_help text content, cmd_model no arg → list, cmd_model valid → switch, cmd_model invalid → error, cmd_screenshot success, cmd_screenshot session injection, cmd_search success, cmd_search failure, cmd_kb list, cmd_kb query success, cmd_kb query empty → error, cmd_kb nonexistent KB, cmd_schedule list, cmd_schedule run, cmd_schedule enable/disable |
| `test_service.py` | `telegram/service.py` | ~15 | find_listener_pid tier 1 (lockpid), find_listener_pid tier 2 (pidfile), find_listener_pid tier 3 (pgrep), find_listener_pid none → None, start success flow, start already running, start KILLED state, start stale cleanup, stop running, stop not running, stop kills orphans, restart stop+start, status running syncs pidfile, status stopped cleans stale |
| `test_adaptor.py` | `adaptor.py` | ~5 | Protocol definition, Telegram backend satisfies protocol |
| **Total** | | **~181** | |

**Validation:**
```bash
pytest tests/unit/test_api.py tests/unit/test_send.py tests/unit/test_auth.py \
       tests/unit/test_dispatch.py tests/unit/test_photos.py tests/unit/test_notify.py \
       tests/unit/test_session.py tests/unit/test_listener.py tests/unit/test_commands.py \
       tests/unit/test_service.py tests/unit/test_adaptor.py -v

# Integration test: full dispatch pipeline
pytest tests/integration/test_dispatch.py tests/integration/test_telegram_api.py -v

# End-to-end: start listener, send test message via Telegram API
python -m adjutant.cli start
# /status, /pause, /resume, /kb query portfolio "test"
```

---

### Phase 4: Capabilities (Week 7-8)

**Goal:** All capabilities in Python

**Deliverables:**
```
adjutant/capabilities/
├── schedule/
│   ├── __init__.py
│   ├── registry.py           # Job CRUD (adjutant.yaml schedules: block)
│   ├── crontab.py            # Crontab sync (install/uninstall/sync)
│   └── runner.py             # Job execution + notify wrapper
├── screenshot/
│   ├── __init__.py
│   └── capture.py            # Playwright wrapper + Telegram send
├── vision/
│   ├── __init__.py
│   └── analyze.py            # Image analysis via OpenCode
└── search/
    ├── __init__.py
    └── brave.py              # Brave Search API
tests/
├── unit/
│   ├── test_schedule_registry.py
│   ├── test_schedule_crontab.py
│   ├── test_screenshot.py
│   ├── test_vision.py
│   └── test_search.py
└── integration/
    └── test_schedule_crontab.py
```

#### Schedule Registry (`registry.py`) — Behavioral Contract

Schedules are stored directly in `adjutant.yaml` under a `schedules:` block (NOT a separate file). The bash version parses this with pure awk/grep/sed — no yq dependency. The Python version uses the config system from Phase 1.

```python
# adjutant/capabilities/schedule/registry.py
import re
from typing import Optional
from adjutant.core.config import load_config, save_config

# Schedule name: allows underscores (unlike KB names)
# Must start with alphanumeric, then alphanumeric + underscore + hyphen
SCHEDULE_NAME_RE = re.compile(r'^[a-z0-9][a-z0-9_-]*$')

def schedule_validate_name(name: str) -> bool:
    """Validate schedule name. Allows underscores (unlike KB names)."""
    return bool(SCHEDULE_NAME_RE.match(name))

def schedule_list() -> list[dict]:
    """List all registered schedules from adjutant.yaml."""
    config = load_config()
    return config.get("schedules", []) or []

def schedule_get(name: str) -> Optional[dict]:
    """Get a schedule by name."""
    for s in schedule_list():
        if s.get("name") == name:
            return s
    return None

def schedule_add(name: str, schedule: str, *,
                 kb: Optional[str] = None,
                 script: Optional[str] = None,
                 description: str = "",
                 enabled: bool = True) -> None:
    """Add a schedule to adjutant.yaml.
    
    Behavioral contract from bash manage.sh:
    - _schedule_resolve_command() priority: KB command > script path
      (if both present, KB wins)
    - schedule_add() always sets notify=false — no way to set notify=true
      via this function (must edit YAML manually)
    - After adding, syncs crontab (install if enabled)
    """
    config = load_config()
    schedules = config.setdefault("schedules", [])
    
    entry = {
        "name": name,
        "schedule": schedule,
        "description": description,
        "enabled": enabled,
        "notify": False,  # Always false — matches bash behavior
    }
    if kb:
        entry["kb"] = kb
    if script:
        entry["script"] = script
    
    schedules.append(entry)
    save_config(config)

def schedule_remove(name: str) -> bool:
    """Remove a schedule.
    
    Behavioral contract from bash: uninstalls crontab FIRST, then removes
    from YAML. This order prevents orphaned cron entries.
    """
    from adjutant.capabilities.schedule.crontab import crontab_uninstall_one
    
    # Uninstall from crontab FIRST
    crontab_uninstall_one(name)
    
    config = load_config()
    schedules = config.get("schedules", [])
    original_len = len(schedules)
    config["schedules"] = [s for s in schedules if s.get("name") != name]
    save_config(config)
    return len(config["schedules"]) < original_len

def schedule_set_enabled(name: str, enabled: bool) -> bool:
    """Enable or disable a schedule.
    
    Behavioral contract from bash: updates YAML then syncs crontab
    (install or uninstall based on new value).
    """
    from adjutant.capabilities.schedule.crontab import (
        crontab_install_one, crontab_uninstall_one
    )
    
    config = load_config()
    for s in config.get("schedules", []):
        if s.get("name") == name:
            s["enabled"] = enabled
            save_config(config)
            if enabled:
                crontab_install_one(s)
            else:
                crontab_uninstall_one(name)
            return True
    return False
```

#### Crontab Sync (`crontab.py`) — Behavioral Contract

```python
# adjutant/capabilities/schedule/crontab.py
import subprocess
from pathlib import Path
from adjutant.core.paths import get_adj_dir

# Marker format for crontab identity: # adjutant:<name>
MARKER_PREFIX = "# adjutant:"

def _resolve_command(schedule: dict) -> str:
    """Resolve the command to run for a schedule.
    
    Priority from bash _schedule_resolve_command():
    1. KB command (if 'kb' field present) → constructs query command
    2. Script path (if 'script' field present) → uses directly
    
    If both present, KB wins.
    """
    adj_dir = get_adj_dir()
    if "kb" in schedule:
        kb_name = schedule["kb"]
        kb_query = schedule.get("kb_query", "")
        return f'python -m adjutant.cli kb query {kb_name} "{kb_query}"'
    elif "script" in schedule:
        return schedule["script"]
    else:
        raise ValueError(f"Schedule '{schedule['name']}' has no kb or script")

def crontab_install_one(schedule: dict) -> None:
    """Install a single schedule into crontab.
    
    Behavioral contract from bash install.sh:
    - Crontab entry format: <schedule> <command> >> <log> 2>&1  # adjutant:<name>
    - Marker '# adjutant:<name>' is the identity key for CRUD
    - Replace-or-append: filters out old entry then appends new one
    - When notify=true, wraps command in notify runner
    """
    name = schedule["name"]
    cron_schedule = schedule["schedule"]
    command = _resolve_command(schedule)
    adj_dir = get_adj_dir()
    log_path = adj_dir / "state" / "adjutant.log"
    
    if schedule.get("notify"):
        # Wrap in notify runner (Python equivalent of notify_wrap.sh)
        command = f'python -m adjutant.capabilities.schedule.runner --notify {name} {command}'
    
    entry = f'{cron_schedule} {command} >> {log_path} 2>&1  {MARKER_PREFIX}{name}'
    
    # Read existing crontab
    result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    existing = result.stdout if result.returncode == 0 else ""
    
    # Filter out old entry (fixed-string match — safe against regex)
    marker = f"{MARKER_PREFIX}{name}"
    lines = [l for l in existing.splitlines() if marker not in l]
    lines.append(entry)
    
    # Write back
    subprocess.run(
        ["crontab", "-"],
        input='\n'.join(lines) + '\n',
        check=True,
        text=True,
    )

def crontab_uninstall_one(name: str) -> None:
    """Remove a single schedule from crontab.
    
    Uses fixed-string match (grep -vF equivalent) — safe against regex
    metacharacters in names.
    """
    result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    if result.returncode != 0:
        return  # No crontab
    
    marker = f"{MARKER_PREFIX}{name}"
    lines = [l for l in result.stdout.splitlines() if marker not in l]
    
    if lines:
        subprocess.run(
            ["crontab", "-"],
            input='\n'.join(lines) + '\n',
            check=True,
            text=True,
        )
    else:
        # Empty crontab — remove it entirely
        subprocess.run(["crontab", "-r"], check=True)

def crontab_sync_all() -> None:
    """Sync all enabled schedules to crontab.
    
    Called during startup and after schedule changes.
    Installs all enabled, uninstalls all disabled.
    """
    from adjutant.capabilities.schedule.registry import schedule_list
    
    for schedule in schedule_list():
        if schedule.get("enabled"):
            crontab_install_one(schedule)
        else:
            crontab_uninstall_one(schedule["name"])

def crontab_backup() -> str:
    """Backup current crontab to state dir. Returns backup path."""
    from datetime import datetime
    adj_dir = get_adj_dir()
    result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    if result.returncode != 0:
        return ""
    backup_path = adj_dir / "state" / f"crontab_backup_{datetime.now():%Y%m%d_%H%M%S}"
    backup_path.write_text(result.stdout)
    return str(backup_path)
```

#### Job Runner (`runner.py`) — Behavioral Contract

```python
# adjutant/capabilities/schedule/runner.py
import subprocess
import logging

logger = logging.getLogger(__name__)

def run_schedule(name: str, command: str) -> tuple[int, str]:
    """Run a scheduled command.
    
    Behavioral contract from bash schedule_run_now():
    - Uses eval for KB commands that need word splitting
    - In Python, we use shell=True for the same effect
    
    Returns (exit_code, first_non_empty_output_line).
    """
    result = subprocess.run(
        command,
        shell=True,
        capture_output=True,
        text=True,
    )
    
    output_lines = (result.stdout + result.stderr).strip().splitlines()
    first_line = next((l for l in output_lines if l.strip()), "")
    
    return result.returncode, first_line

def run_with_notify(name: str, command: str) -> None:
    """Run a command and send notification with result.
    
    Behavioral contract from bash notify_wrap.sh (63 lines):
    - ALWAYS exits 0 (cron safety — prevents cron mail on failure)
    - Captures first non-empty line of output for notification summary
    - Failure format: '[job_name] ERROR (rc=N): <first_line>'
    - Success format: '[job_name] <first_line>' (OK: prefix NOT stripped)
    - Notification failure silently swallowed
    """
    try:
        rc, first_line = run_schedule(name, command)
        
        if rc != 0:
            msg = f"[{name}] ERROR (rc={rc}): {first_line}" if first_line else f"[{name}] ERROR (rc={rc})"
        else:
            msg = f"[{name}] {first_line}" if first_line else f"[{name}] completed"
        
        try:
            from adjutant.messaging.adaptor import msg_send_notification
            msg_send_notification(msg)
        except Exception:
            pass  # Notification failure silently swallowed — matches bash || true
            
    except Exception:
        pass  # ALWAYS exit 0 — cron safety
```

#### Screenshot (`capture.py`) — Behavioral Contract

```python
# adjutant/capabilities/screenshot/capture.py
import subprocess
import logging
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Playwright viewport matches bash: 1280x900
VIEWPORT_WIDTH = 1280
VIEWPORT_HEIGHT = 900
NAV_TIMEOUT_MS = 30_000
CAPTION_MAX_BYTES = 1024  # Telegram caption limit

def capture_screenshot(url: str, output_dir: Path) -> tuple[Path, str]:
    """Capture a screenshot of a URL using Playwright.
    
    Behavioral contract from bash screenshot.sh (147 lines):
    - Custom output format: OK:<filepath>:::<caption> (triple-colon separator)
    - In Python, we return a tuple instead of formatting a string
    - Domain extraction uses urllib.parse (bash used inline python3)
    - Viewport: 1280x900, cookie banner dismissal, 30s nav timeout
    - Uses Playwright via Node.js script (playwright_screenshot.mjs)
    
    The Python version uses playwright directly (pip install playwright)
    instead of the Node.js wrapper.
    """
    domain = urlparse(url).netloc or url
    
    # Sanitize domain for filename
    safe_domain = domain.replace(".", "_").replace(":", "_")
    filepath = output_dir / f"screenshot_{safe_domain}.png"
    
    try:
        from playwright.sync_api import sync_playwright
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(
                viewport={"width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT}
            )
            page.goto(url, timeout=NAV_TIMEOUT_MS, wait_until="networkidle")
            
            # Attempt cookie banner dismissal (best effort)
            _dismiss_cookie_banners(page)
            
            page.screenshot(path=str(filepath), full_page=False)
            browser.close()
    except Exception as e:
        raise RuntimeError(f"Screenshot failed for {url}: {e}")
    
    caption = f"Screenshot of {domain}"
    return filepath, caption

def _dismiss_cookie_banners(page) -> None:
    """Best-effort cookie banner dismissal."""
    selectors = [
        'button:has-text("Accept")',
        'button:has-text("Accept all")',
        'button:has-text("I agree")',
        '[id*="cookie"] button',
        '[class*="cookie"] button',
    ]
    for sel in selectors:
        try:
            el = page.query_selector(sel)
            if el and el.is_visible():
                el.click()
                break
        except Exception:
            continue

def send_screenshot(filepath: Path, caption: str,
                    message_id: Optional[int] = None) -> None:
    """Send screenshot via Telegram.
    
    Behavioral contract from bash:
    - Two-stage Telegram send: sendPhoto first, sendDocument fallback
    - Caption truncated to 1024 bytes (can split UTF-8 — bash uses cut -c1-1024)
    - Vision auto-captioning if no manual caption provided
    
    The Python version truncates at character boundaries (not byte boundaries)
    to avoid splitting UTF-8. This is an intentional improvement.
    """
    from adjutant.messaging.adaptor import msg_send_photo, msg_send_document
    
    # Truncate caption at character boundary (improvement over bash byte-based cut)
    if len(caption) > CAPTION_MAX_BYTES:
        caption = caption[:CAPTION_MAX_BYTES - 3] + "..."
    
    try:
        msg_send_photo(filepath, caption, reply_to=message_id)
    except Exception:
        # Fallback: send as document
        logger.warning("sendPhoto failed, falling back to sendDocument")
        msg_send_document(filepath, caption, reply_to=message_id)
```

#### Vision (`analyze.py`) — Behavioral Contract

```python
# adjutant/capabilities/vision/analyze.py
import subprocess
import logging
from pathlib import Path
from typing import Optional
from adjutant.lib.ndjson import parse_ndjson

logger = logging.getLogger(__name__)

def resolve_vision_model(config: dict, state_dir: Path) -> str:
    """Resolve model for vision analysis.
    
    Behavioral contract from bash vision.sh:
    1. vision.model from config
    2. Session model (state/telegram_model.txt)
    3. Hardcoded haiku fallback
    
    Note: The bash config parser uses hardcoded sibling section names as
    exit patterns (fragile). The Python version uses proper config loading.
    """
    # 1. Vision-specific model from config
    vision_model = (config.get("features", {})
                         .get("vision", {})
                         .get("model"))
    if vision_model:
        return vision_model
    
    # 2. Session model
    model_file = state_dir / "telegram_model.txt"
    if model_file.exists():
        session_model = model_file.read_text().strip()
        if session_model:
            return session_model
    
    # 3. Hardcoded fallback
    return "anthropic/claude-haiku-4-5"

def analyze_image(image_path: Path, prompt: str = "Describe this image",
                  config: Optional[dict] = None) -> str:
    """Analyze an image via OpenCode.
    
    Behavioral contract from bash vision.sh (118 lines):
    - Does NOT follow OK:/ERROR: contract — outputs raw text
    - OpenCode invocation: opencode run --model <MODEL> --format json -f <IMAGE_PATH> -- <PROMPT>
    - Note the -f flag for image file and -- separator before prompt
    - ModelNotFoundError: exits 0 with user-actionable suggestion (not hard error)
    - Empty reply: exits 1 (error)
    - Temp files cleaned inline (no trap) — minor leak risk in bash version
    
    The Python version raises exceptions instead of exit codes.
    """
    from adjutant.core.paths import get_adj_dir
    from adjutant.core.config import load_config
    
    if config is None:
        config = load_config()
    
    state_dir = get_adj_dir() / "state"
    model = resolve_vision_model(config, state_dir)
    
    args = [
        "opencode", "run",
        "--model", model,
        "--format", "json",
        "-f", str(image_path),
        "--", prompt,
    ]
    
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        return "Vision analysis timed out"
    
    # Check for ModelNotFoundError (user-actionable, not hard error)
    if "ModelNotFoundError" in result.stderr:
        return f"Model '{model}' not available. Try changing vision.model in config."
    
    ndjson_result = parse_ndjson(result.stdout)
    
    if not ndjson_result.text.strip():
        raise RuntimeError("Vision analysis returned empty response")
    
    return ndjson_result.text.strip()
```

#### Search (`brave.py`) — Behavioral Contract

```python
# adjutant/capabilities/search/brave.py
import logging
from typing import Optional
from urllib.parse import quote_plus

logger = logging.getLogger(__name__)

BRAVE_API_URL = "https://api.search.brave.com/res/v1/web/search"
DEFAULT_COUNT = 5
MIN_COUNT = 1
MAX_COUNT = 10
SEARCH_TIMEOUT = 15  # seconds

def search(query: str, count: int = DEFAULT_COUNT) -> str:
    """Search the web using Brave Search API.
    
    Behavioral contract from bash search.sh (97 lines):
    - Result count clamped to 1-10, default 5
    - URL encoding: python3 primary → curl fallback → space-to-plus fallback
      (In Python, we always have urllib — no fallback chain needed)
    - 15-second timeout
    - Result format: numbered list with title, URL, description
    - Empty results = success (exit 0) with "No results found"
    - Follows OK:/ERROR: entry script contract
    
    Returns formatted result string (not raw API response).
    """
    import httpx
    from adjutant.core.env import get_credential
    
    api_key = get_credential("BRAVE_API_KEY")
    if not api_key:
        return "ERROR: BRAVE_API_KEY not configured"
    
    # Clamp count
    count = max(MIN_COUNT, min(MAX_COUNT, count))
    
    try:
        response = httpx.get(
            BRAVE_API_URL,
            params={"q": query, "count": count},
            headers={
                "Accept": "application/json",
                "Accept-Encoding": "gzip",
                "X-Subscription-Token": api_key,
            },
            timeout=SEARCH_TIMEOUT,
        )
        response.raise_for_status()
    except httpx.TimeoutException:
        return "Search timed out"
    except httpx.HTTPError as e:
        return f"Search failed: {e}"
    
    data = response.json()
    results = data.get("web", {}).get("results", [])
    
    if not results:
        return "No results found"
    
    # Format: numbered list with title, URL, description
    lines = []
    for i, r in enumerate(results, 1):
        title = r.get("title", "Untitled")
        url = r.get("url", "")
        desc = r.get("description", "No description")
        lines.append(f"{i}. {title}\n   {url}\n   {desc}")
    
    return '\n\n'.join(lines)
```

#### Phase 4 Test Specifications

```python
# tests/unit/test_schedule_registry.py — Key test cases

class TestScheduleNameValidation:
    """Schedule names: allows underscores (unlike KB names)."""
    # Valid: "news_briefing", "pulse", "my-job1"
    # Invalid: "-start", "My Job", "", "123"
    # Contrast with KB: "my_kb" is INVALID for KB but VALID for schedule

class TestScheduleAdd:
    """Adding schedules to adjutant.yaml."""
    # Test: adds to empty schedules list
    # Test: appends to existing schedules
    # Test: notify always set to false
    # Test: KB field takes priority over script in command resolution

class TestScheduleRemove:
    """Remove order: crontab first, then YAML."""
    # Test: removes from crontab before YAML
    # Test: nonexistent schedule returns False

class TestScheduleSetEnabled:
    """Enable/disable with crontab sync."""
    # Test: enable → installs crontab entry
    # Test: disable → uninstalls crontab entry

# tests/unit/test_schedule_crontab.py — Key test cases

class TestCrontabInstallOne:
    """Crontab entry format and identity."""
    # Test: entry format matches '<schedule> <command> >> <log> 2>&1  # adjutant:<name>'
    # Test: marker '# adjutant:<name>' present
    # Test: replace-or-append (old entry filtered, new appended)
    # Test: notify=true wraps command in notify runner

class TestCrontabUninstallOne:
    """Fixed-string removal."""
    # Test: removes by marker (not regex — safe against metacharacters)
    # Test: other entries preserved
    # Test: empty crontab after removal → crontab -r

# tests/unit/test_screenshot.py — Key test cases

class TestScreenshotCapture:
    """Playwright-based screenshot."""
    # Test: viewport 1280x900
    # Test: cookie banner dismissal attempted
    # Test: timeout handling (30s nav timeout)

class TestScreenshotSend:
    """Two-stage send with caption truncation."""
    # Test: sendPhoto first, sendDocument fallback
    # Test: caption truncated at character boundary (not byte)
    # Test: max 1024 chars

# tests/unit/test_vision.py — Key test cases

class TestVisionModelResolution:
    """Three-tier model resolution."""
    # Test: vision.model from config → used
    # Test: session model fallback
    # Test: hardcoded haiku default

class TestVisionAnalyze:
    """Image analysis via OpenCode."""
    # Test: OpenCode invocation uses -f flag and -- separator
    # Test: ModelNotFoundError → user-friendly message (not exception)
    # Test: empty reply → RuntimeError
    # Test: timeout → graceful message

# tests/unit/test_search.py — Key test cases

class TestBraveSearch:
    """Brave Search API integration."""
    # Test: count clamped to 1-10
    # Test: default count is 5
    # Test: empty results → "No results found" (success, not error)
    # Test: result format: numbered, title/URL/description
    # Test: 15s timeout
    # Test: missing API key → error message
```

**Bash scripts replaced:**
- `scripts/capabilities/schedule/*` → `adjutant/capabilities/schedule/*`
- `scripts/capabilities/screenshot/*` → `adjutant/capabilities/screenshot/*`
- `scripts/capabilities/vision/*` → `adjutant/capabilities/vision/*`
- `scripts/capabilities/search/*` → `adjutant/capabilities/search/*`

---

### Phase 5: Lifecycle & Setup (Week 9-10)

**Goal:** Lifecycle and setup scripts in Python

**Deliverables:**
```
adjutant/lifecycle/
├── __init__.py
├── start.py                  # Start services (with recovery mode)
├── stop.py                   # Stop services
├── restart.py                # Stop → sleep → start
├── pause.py                  # Soft pause (flag only)
├── resume.py                 # Resume from pause (flag only)
├── kill.py                   # Emergency shutdown (4-phase kill)
├── update.py                 # Self-update from GitHub releases
├── startup.py                # Full startup/recovery orchestration
└── cron.py                   # Cron job handlers (pulse, review)

adjutant/setup/
├── __init__.py
├── wizard.py                 # Interactive 7-step setup
├── install.py                # Installer
├── uninstall.py              # Uninstaller
├── repair.py                 # Health check/repair (10 checks)
└── steps/
    ├── __init__.py
    ├── prerequisites.py      # Dependency checking
    ├── install_path.py       # Directory creation
    ├── identity.py           # LLM-generated soul.md/heart.md
    ├── messaging.py          # Telegram token + chat ID
    ├── features.py           # 5 feature toggles
    ├── service.py            # Platform service install + CLI alias
    ├── autonomy.py           # Pulse/review schedule enable
    ├── kb_wizard.py          # KB creation wizard
    └── schedule_wizard.py    # Schedule creation wizard
tests/
├── unit/
│   ├── test_lifecycle_state.py
│   ├── test_startup.py
│   ├── test_kill.py
│   ├── test_update.py
│   ├── test_cron.py
│   ├── test_wizard.py
│   └── test_repair.py
└── integration/
    └── test_lifecycle_endtoend.py
```

#### State Machine — Two Lockfiles, Four States

```
                    ┌─────────────┐
                    │ OPERATIONAL │  (no lockfiles)
                    └──────┬──────┘
                     ┌─────┴─────┐
              pause/│            │kill
                    ▼            ▼
             ┌──────────┐  ┌──────────┐
             │  PAUSED   │  │  KILLED   │
             └──────┬────┘  └──────┬───┘
                    │pause          │
                    ▼              ▼
             ┌──────────────────────┐
             │   KILLED + PAUSED    │
             └──────────────────────┘

Transitions:
- pause.py:  touch state/paused (does NOT stop services)
- resume.py: rm state/paused (does NOT clear killed, does NOT restart services)
- kill.py:   touch state/killed (BEFORE killing processes)
- start.py:  rm state/killed (interactive confirm in recovery mode)
```

```python
# adjutant/lifecycle/state.py (shared state helpers)
from pathlib import Path
from adjutant.core.paths import get_adj_dir

def is_paused() -> bool:
    return (get_adj_dir() / "state" / "paused").exists()

def is_killed() -> bool:
    return (get_adj_dir() / "state" / "killed").exists()

def get_state() -> str:
    """Return current state: operational, paused, killed, killed+paused."""
    killed = is_killed()
    paused = is_paused()
    if killed and paused:
        return "killed+paused"
    if killed:
        return "killed"
    if paused:
        return "paused"
    return "operational"
```

#### Startup (`startup.py`) — Behavioral Contract

```python
# adjutant/lifecycle/startup.py
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

def startup(*, interactive: bool = True) -> None:
    """Full startup with recovery mode.
    
    Behavioral contract from bash startup.sh (224 lines):
    
    1. Recovery mode detection:
       - If KILLED lockfile exists → recovery mode
       - If interactive: prompt y/N confirm to clear
       - Restores crontab from backup (if exists)
       - Re-syncs schedule registry
    
    2. Service start sequence (order matters):
       a. Telegram listener via service.py
       b. OpenCode web server with 3-branch orphan detection:
          - Match existing PID → reuse
          - Orphan found → kill then fresh start
          - No process → fresh start
       c. Cron schedule sync
    
    3. Post-startup PID sync safety net:
       - Recreates tracking PID files if processes running but files missing
    
    4. Final PAUSED check:
       - Warns but does NOT prevent startup (services start even if paused)
    
    OpenCode web started with: nohup opencode web --mdns
    Python equivalent: asyncio subprocess with stdout→log redirect
    """
    from adjutant.core.paths import get_adj_dir
    from adjutant.lifecycle.state import is_killed, is_paused
    from adjutant.messaging.telegram.service import start_listener
    from adjutant.capabilities.schedule.crontab import crontab_sync_all
    
    adj_dir = get_adj_dir()
    
    # 1. Recovery mode
    if is_killed():
        if interactive:
            confirm = input("System was killed. Recover? [y/N] ").strip().lower()
            if confirm != 'y':
                print("Startup aborted.")
                return
        # Clear killed state
        (adj_dir / "state" / "killed").unlink(missing_ok=True)
        # Restore crontab from backup if available
        _restore_crontab_backup(adj_dir)
        # Re-sync schedules
        crontab_sync_all()
        logger.info("Recovery mode: cleared killed state, restored crontab")
    
    # 2a. Start Telegram listener
    start_listener()
    
    # 2b. Start OpenCode web server
    _start_opencode_web(adj_dir)
    
    # 2c. Sync cron schedules
    crontab_sync_all()
    
    # 3. PID sync safety net
    _sync_pid_files(adj_dir)
    
    # 4. PAUSED warning
    if is_paused():
        logger.warning("System is PAUSED — services started but dispatch is paused")

def _start_opencode_web(adj_dir: Path) -> None:
    """Start OpenCode web server with 3-branch orphan detection.
    
    Branch 1: PID file exists and process running → reuse (do nothing)
    Branch 2: PID file exists but process dead → orphan, kill and fresh start
    Branch 3: No PID file → fresh start
    """
    import subprocess
    import os
    
    pid_file = adj_dir / "state" / "opencode_web.pid"
    log_file = adj_dir / "state" / "opencode_web.log"
    
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
            os.kill(pid, 0)  # Check if alive
            logger.info("OpenCode web already running (PID %d)", pid)
            return  # Branch 1: reuse
        except (ProcessLookupError, ValueError):
            # Branch 2: stale PID
            logger.info("Stale OpenCode web PID, restarting")
            pid_file.unlink(missing_ok=True)
    
    # Branch 3 (or 2 after cleanup): fresh start
    proc = subprocess.Popen(
        ["opencode", "web", "--mdns"],
        stdout=open(log_file, "a"),
        stderr=subprocess.STDOUT,
        start_new_session=True,  # Equivalent of nohup
    )
    pid_file.write_text(str(proc.pid))
    logger.info("Started OpenCode web (PID %d)", proc.pid)

def _restore_crontab_backup(adj_dir: Path) -> None:
    """Restore crontab from most recent backup."""
    import subprocess, glob
    
    backups = sorted(adj_dir.glob("state/crontab_backup_*"), reverse=True)
    if backups:
        backup = backups[0]
        subprocess.run(
            ["crontab", str(backup)],
            check=True,
        )
        logger.info("Restored crontab from %s", backup.name)

def _sync_pid_files(adj_dir: Path) -> None:
    """Recreate tracking files if processes running but files missing."""
    # Implementation: check for running processes via pgrep,
    # create PID files if found. Safety net only.
    pass
```

#### Emergency Kill (`kill.py`) — Behavioral Contract

```python
# adjutant/lifecycle/kill.py
import logging
import subprocess
import os
import signal
from pathlib import Path

logger = logging.getLogger(__name__)

def emergency_kill() -> None:
    """Nuclear shutdown — kill everything.
    
    Behavioral contract from bash emergency_kill.sh (165 lines):
    
    CRITICAL: Creates KILLED lockfile BEFORE any process killing begins.
    This ensures the system knows it was killed even if the kill script
    itself is interrupted.
    
    4-phase kill sequence:
    1. OpenCode processes: pkill -f "opencode" (broader than "opencode web")
    2. Telegram listener: 3-layer (PID files + orphan sweep)
    3. Scheduled jobs: per-script pkill -TERM
    4. Entire crontab: backed up then crontab -r
       WARNING: This removes ALL user cron jobs, not just adjutant entries
    
    Sends Telegram notifications before AND after kill (|| true — never blocks).
    ALWAYS exits 0 (all operations wrapped in || true equivalent).
    """
    from adjutant.core.paths import get_adj_dir
    
    adj_dir = get_adj_dir()
    
    # Create KILLED lockfile FIRST — before any killing
    (adj_dir / "state" / "killed").touch()
    
    # Notification: "shutting down" (best effort)
    _notify_best_effort("Emergency shutdown initiated")
    
    try:
        # Phase 1: Kill OpenCode processes (broad match)
        _kill_opencode_processes()
        
        # Phase 2: Kill Telegram listener (3-layer)
        _kill_telegram_listener(adj_dir)
        
        # Phase 3: Kill scheduled jobs
        _kill_scheduled_jobs(adj_dir)
        
        # Phase 4: Backup and remove entire crontab
        _backup_and_remove_crontab(adj_dir)
        
    except Exception as e:
        logger.error("Error during emergency kill: %s", e)
    
    # Notification: "shutdown complete" (best effort)
    _notify_best_effort("Emergency shutdown complete")

def _kill_opencode_processes() -> None:
    """Kill all opencode processes (broader than just 'opencode web')."""
    try:
        subprocess.run(["pkill", "-f", "opencode"], check=False)
    except Exception:
        pass

def _kill_telegram_listener(adj_dir: Path) -> None:
    """3-layer listener kill: PID files → orphan sweep.
    
    Layer 1: Read listener.lock/pid
    Layer 2: Read telegram.pid
    Layer 3: pgrep sweep for telegram_listener
    """
    # Layer 1: PidLock
    pid_file = adj_dir / "state" / "listener.lock" / "pid"
    _kill_from_pid_file(pid_file)
    
    # Layer 2: telegram.pid
    pid_file = adj_dir / "state" / "telegram.pid"
    _kill_from_pid_file(pid_file)
    
    # Layer 3: pgrep sweep
    try:
        result = subprocess.run(
            ["pgrep", "-f", "telegram_listener"],
            capture_output=True, text=True
        )
        for pid_str in result.stdout.strip().splitlines():
            try:
                os.kill(int(pid_str), signal.SIGTERM)
            except (ProcessLookupError, ValueError):
                pass
    except Exception:
        pass

def _kill_from_pid_file(pid_file: Path) -> None:
    """Kill process from PID file, then remove file."""
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
            os.kill(pid, signal.SIGTERM)
        except (ProcessLookupError, ValueError):
            pass
        pid_file.unlink(missing_ok=True)

def _kill_scheduled_jobs(adj_dir: Path) -> None:
    """Kill running scheduled job processes."""
    from adjutant.capabilities.schedule.registry import schedule_list
    for schedule in schedule_list():
        script = schedule.get("script", "")
        if script:
            try:
                subprocess.run(["pkill", "-TERM", "-f", script], check=False)
            except Exception:
                pass

def _backup_and_remove_crontab(adj_dir: Path) -> None:
    """Backup entire crontab then remove it.
    
    WARNING: crontab -r removes ALL user cron jobs, not just adjutant entries.
    This matches the bash behavior exactly.
    """
    from adjutant.capabilities.schedule.crontab import crontab_backup
    crontab_backup()
    try:
        subprocess.run(["crontab", "-r"], check=False)
    except Exception:
        pass

def _notify_best_effort(message: str) -> None:
    """Send notification, never fail."""
    try:
        from adjutant.messaging.adaptor import msg_send_notification
        msg_send_notification(message)
    except Exception:
        pass  # Matches bash || true
```

#### Simple Lifecycle Operations

```python
# adjutant/lifecycle/pause.py
from adjutant.core.paths import get_adj_dir

def pause() -> None:
    """Soft pause. Flag-only — does NOT stop any services.
    
    Behavioral contract: Just touch state/paused.
    Cron jobs and dispatch must check this flag.
    """
    (get_adj_dir() / "state" / "paused").touch()

# adjutant/lifecycle/resume.py
from adjutant.core.paths import get_adj_dir

def resume() -> None:
    """Resume from pause. Flag-only — does NOT clear KILLED, no service restart.
    
    Behavioral contract: Just rm state/paused.
    """
    (get_adj_dir() / "state" / "paused").unlink(missing_ok=True)

# adjutant/lifecycle/restart.py
import time

def restart() -> None:
    """Restart: stop → sleep 2 → start.
    
    Behavioral contract from bash restart.sh (64 lines):
    - Does NOT check KILLED/PAUSED state
    - Delegates to startup.py after stopping
    """
    from adjutant.lifecycle.stop import stop
    from adjutant.lifecycle.startup import startup
    
    stop()
    time.sleep(2)
    startup(interactive=False)
```

#### Cron Handlers — Bug Fix

```python
# adjutant/lifecycle/cron.py
import subprocess
import sys
from pathlib import Path

def pulse() -> None:
    """Run pulse prompt via OpenCode.
    
    Behavioral contract from bash pulse_cron.sh (29 lines):
    - Uses: exec opencode run --dir <ADJ_DIR> "<pulse.md contents>"
    - BUG IN BASH: Does NOT check PAUSED/KILLED state
    - PYTHON FIX: Add state checks (intentional improvement)
    - No timeout mechanism in bash (relies on OpenCode's own timeout)
    """
    from adjutant.core.paths import get_adj_dir
    from adjutant.lifecycle.state import is_killed, is_paused
    
    if is_killed() or is_paused():
        return  # Intentional fix: bash version doesn't check
    
    adj_dir = get_adj_dir()
    prompt = (adj_dir / "prompts" / "pulse.md").read_text()
    
    subprocess.run(
        ["opencode", "run", "--dir", str(adj_dir), prompt],
        check=False,
    )

def review() -> None:
    """Run review prompt via OpenCode. Same structure as pulse()."""
    from adjutant.core.paths import get_adj_dir
    from adjutant.lifecycle.state import is_killed, is_paused
    
    if is_killed() or is_paused():
        return  # Intentional fix
    
    adj_dir = get_adj_dir()
    prompt = (adj_dir / "prompts" / "review.md").read_text()
    
    subprocess.run(
        ["opencode", "run", "--dir", str(adj_dir), prompt],
        check=False,
    )
```

#### Update (`update.py`) — Behavioral Contract

```python
# adjutant/lifecycle/update.py
import logging
import subprocess
import shutil
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Directories backed up before update
BACKUP_DIRS = ["scripts", "templates", "tests"]
BACKUP_FILES = ["adjutant", "VERSION", ".adjutant-root"]

# rsync excludes (never overwrite user data)
RSYNC_EXCLUDES = [
    "adjutant.yaml", "identity/", ".env",
    "state/", "journal/", "insights/", "photos/", "screenshots/",
    "knowledge_bases/",
]

def check_for_update() -> Optional[str]:
    """Check GitHub releases for newer version.
    
    Returns new version string if available, None if current.
    Uses semver comparison — no pre-release support.
    """
    # Read current version
    # Compare against latest GitHub release tag
    # Return new version or None
    pass

def update(target_version: Optional[str] = None) -> None:
    """Self-update from GitHub releases.
    
    Behavioral contract from bash update.sh (262 lines):
    - set -euo pipefail (strictest safety)
    - Semver comparison via _semver_lt() — no pre-release support
    - Backup: timestamped dir in .backup/pre-update_TIMESTAMP/
    - Backs up: scripts/, templates/, tests/, adjutant, VERSION, .adjutant-root
    - Download: GitHub releases tarball via curl
    - Apply with rsync, excluding user data
    - Does NOT stop/restart services — warns user
    - No automated rollback mechanism
    """
    from adjutant.core.paths import get_adj_dir
    from datetime import datetime
    
    adj_dir = get_adj_dir()
    
    # 1. Backup
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = adj_dir / ".backup" / f"pre-update_{timestamp}"
    backup_dir.mkdir(parents=True)
    
    for d in BACKUP_DIRS:
        src = adj_dir / d
        if src.exists():
            shutil.copytree(src, backup_dir / d)
    for f in BACKUP_FILES:
        src = adj_dir / f
        if src.exists():
            shutil.copy2(src, backup_dir / f)
    
    logger.info("Backup created at %s", backup_dir)
    
    # 2. Download tarball
    # 3. Extract and apply with rsync (excluding user data)
    # 4. Warn user to restart services
    
    logger.warning("Update applied. Please restart services: adjutant restart")
```

#### Setup Wizard (`wizard.py`) — Behavioral Contract

```python
# adjutant/setup/wizard.py
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# 7-step sequence — steps 1-2 fatal on failure, steps 3-7 continue with warning
WIZARD_STEPS = [
    ("prerequisites", "Check dependencies", True),    # fatal
    ("install_path",  "Set install path", True),       # fatal
    ("identity",      "Configure identity", False),    # non-fatal
    ("messaging",     "Configure messaging", False),   # non-fatal
    ("features",      "Configure features", False),    # non-fatal
    ("service",       "Install service", False),       # non-fatal
    ("autonomy",      "Configure autonomy", False),    # non-fatal
]

DEFAULT_CONFIG_LINES = 67  # _ensure_config() writes a 67-line default adjutant.yaml

def run_wizard(*, dry_run: bool = False) -> None:
    """Interactive 7-step setup wizard.
    
    Behavioral contract from bash wizard.sh (289 lines):
    - Steps 1-2 are fatal on failure (abort wizard)
    - Steps 3-7 continue on failure with warning
    - _ensure_config() writes default adjutant.yaml if missing
    - Post-completion offers KB creation wizard
    
    Migration from bash:
    - All wiz_* functions (write to /dev/tty) → Rich prompts
    - wiz_confirm() → rich.prompt.Confirm.ask()
    - wiz_choose() → rich.prompt.Prompt.ask(choices=...)
    - wiz_input() → rich.prompt.Prompt.ask()
    - wiz_multiline() → rich.prompt.Prompt.ask() with multiline hint
    - wiz_secret() → rich.prompt.Prompt.ask(password=True)
    
    The /dev/tty pattern in bash was needed because wizard functions are
    often called inside $() subshells. Rich handles this natively.
    """
    from rich.console import Console
    from rich.prompt import Confirm
    
    console = Console()
    
    _ensure_config()
    
    for step_name, description, fatal in WIZARD_STEPS:
        console.print(f"\n[bold]Step: {description}[/bold]")
        try:
            step_fn = _get_step_function(step_name)
            step_fn(dry_run=dry_run)
        except Exception as e:
            if fatal:
                console.print(f"[red]FATAL: {e}[/red]")
                return
            else:
                console.print(f"[yellow]WARNING: {e} — continuing[/yellow]")
    
    # Post-completion: offer KB creation
    if Confirm.ask("Create a knowledge base?", default=False):
        from adjutant.setup.steps.kb_wizard import kb_wizard_step
        kb_wizard_step(dry_run=dry_run)

def _ensure_config() -> None:
    """Write default adjutant.yaml if missing (67-line template)."""
    from adjutant.core.paths import get_adj_dir
    config_path = get_adj_dir() / "adjutant.yaml"
    if not config_path.exists():
        # Write default config matching adjutant.yaml.example structure
        pass

def _get_step_function(name: str):
    """Import and return the step function."""
    import importlib
    mod = importlib.import_module(f"adjutant.setup.steps.{name}")
    return getattr(mod, f"{name}_step")
```

#### Repair (`repair.py`) — Behavioral Contract

```python
# adjutant/setup/repair.py
import logging
from typing import list

logger = logging.getLogger(__name__)

# 10 health checks from bash repair.sh (322 lines)
HEALTH_CHECKS = [
    "config_file",      # adjutant.yaml exists and is valid YAML
    "credentials",      # .env has required keys (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
    "cli_executable",   # 'adjutant' command on PATH
    "path_config",      # PATH includes adjutant bin directory
    "script_perms",     # All scripts have execute permission
    "env_perms",        # .env has restricted permissions (600)
    "required_dirs",    # state/, knowledge_bases/, identity/ exist
    "dependencies",     # Required binaries available (opencode, curl, etc.)
    "listener_status",  # Telegram listener running if not killed/paused
    "scheduled_jobs",   # Crontab entries match adjutant.yaml schedules
]

def repair(*, dry_run: bool = False, interactive: bool = True) -> list[str]:
    """Run health checks and offer interactive fixes.
    
    Behavioral contract from bash repair.sh (322 lines):
    - Each check has interactive fix-offer with dry-run support
    - Returns list of issues found
    - Supports --dry-run (report only, no fixes)
    """
    issues = []
    for check_name in HEALTH_CHECKS:
        check_fn = _get_check_function(check_name)
        ok, message = check_fn()
        if not ok:
            issues.append(f"{check_name}: {message}")
            if interactive and not dry_run:
                _offer_fix(check_name, message)
    return issues
```

#### Uninstall (`uninstall.py`) — Behavioral Contract

```python
# adjutant/setup/uninstall.py
import subprocess
import logging
import sys

logger = logging.getLogger(__name__)

def uninstall() -> None:
    """Uninstall Adjutant.
    
    Behavioral contract from bash uninstall.sh (331 lines):
    - Requires typing "yes" (not just "y") — intentional friction
    - 3-tier process termination (graceful → forced → sweep)
    - Platform-specific service removal (launchd on macOS, systemd on Linux)
    - Shell alias removal from .bashrc/.zshrc
    - Crontab backup then file deletion
    """
    confirm = input('Type "yes" to uninstall Adjutant: ').strip()
    if confirm != "yes":
        print("Uninstall cancelled.")
        return
    
    # 1. Stop all processes (3-tier)
    from adjutant.lifecycle.kill import emergency_kill
    emergency_kill()
    
    # 2. Remove platform service
    _remove_platform_service()
    
    # 3. Remove shell aliases
    _remove_shell_aliases()
    
    # 4. Backup crontab, remove entries
    from adjutant.capabilities.schedule.crontab import crontab_backup
    crontab_backup()
    
    # 5. Delete files
    from adjutant.core.paths import get_adj_dir
    import shutil
    adj_dir = get_adj_dir()
    logger.info("Removing %s", adj_dir)
    shutil.rmtree(adj_dir)

def _remove_platform_service() -> None:
    """Remove launchd (macOS) or systemd (Linux) service."""
    from adjutant.core.platform import get_platform
    platform = get_platform()
    if platform == "macos":
        # Remove launchd plist
        pass
    elif platform == "linux":
        # systemctl disable + remove unit file
        pass

def _remove_shell_aliases() -> None:
    """Remove adjutant alias from .bashrc/.zshrc."""
    pass
```

#### Phase 5 Test Specifications

```python
# tests/unit/test_lifecycle_state.py — Key test cases

class TestStateModel:
    """Four states from two lockfiles."""
    # Test: no files → "operational"
    # Test: paused only → "paused"
    # Test: killed only → "killed"
    # Test: both → "killed+paused"

# tests/unit/test_startup.py — Key test cases

class TestStartupRecovery:
    """Recovery mode with KILLED lockfile."""
    # Test: KILLED lockfile detected → enters recovery mode
    # Test: interactive confirm required (y/N)
    # Test: decline → startup aborted
    # Test: accept → KILLED cleared, crontab restored
    # Test: PAUSED state → warning logged but startup continues

class TestOpenCodeWebStart:
    """3-branch orphan detection."""
    # Test: PID file exists + process running → reuse (no restart)
    # Test: PID file exists + process dead → kill orphan, fresh start
    # Test: No PID file → fresh start

# tests/unit/test_kill.py — Key test cases

class TestEmergencyKill:
    """4-phase kill sequence."""
    # Test: KILLED lockfile created FIRST (before any kills)
    # Test: Phase 1 — pkill -f "opencode" called
    # Test: Phase 2 — 3-layer listener kill attempted
    # Test: Phase 3 — scheduled job processes killed
    # Test: Phase 4 — crontab backed up then removed
    # Test: notifications sent before AND after (best effort)
    # Test: always succeeds (never raises)

# tests/unit/test_cron.py — Key test cases

class TestPulseReview:
    """Cron handlers with state checks (bash bug fix)."""
    # Test: KILLED state → skips execution (improvement over bash)
    # Test: PAUSED state → skips execution (improvement over bash)
    # Test: operational state → runs OpenCode
    # Test: prompt file read from prompts/ directory

# tests/unit/test_repair.py — Key test cases

class TestRepair:
    """10 health checks."""
    # Test: each check reports pass/fail correctly
    # Test: dry-run mode reports but doesn't fix
    # Test: interactive mode offers fixes
```

**Bash scripts replaced:**
- `scripts/lifecycle/*` → `adjutant/lifecycle/*`
- `scripts/setup/*` → `adjutant/setup/*`

---

### Phase 6: News & Observability (Week 11)

**Goal:** Remaining components in Python

**Deliverables:**
```
adjutant/news/
├── __init__.py
├── fetch.py                  # Multi-source fetching (HN, Reddit, blogs/RSS)
├── analyze.py                # Dedup + Haiku-powered ranking
└── briefing.py               # Pipeline orchestrator

adjutant/observability/
├── __init__.py
├── status.py                 # System status dashboard
├── usage.py                  # Token usage estimation
└── journal.py                # Journal/log rotation
tests/
├── unit/
│   ├── test_news_fetch.py
│   ├── test_news_analyze.py
│   ├── test_news_briefing.py
│   ├── test_status.py
│   ├── test_usage.py
│   └── test_journal_rotate.py
└── integration/
    └── test_news_pipeline.py
```

**Cross-cutting note:** None of the 6 bash files in this phase follow the OK:/ERROR: entry script contract. The news pipeline communicates via exit codes and file artifacts. The Python version uses return values and exceptions instead.

#### News Fetch (`fetch.py`) — Behavioral Contract

```python
# adjutant/news/fetch.py
import json
import logging
import subprocess
from pathlib import Path
from typing import Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# Source types and their APIs
SOURCES = {
    "hackernews": "https://hn.algolia.com/api/v1/search",
    "reddit": "https://www.reddit.com/r/{subreddit}/hot.json",
    # Blogs use HTML scraping + RSS via feedparser
}

def fetch_all(config_path: Path, output_dir: Path) -> list[dict]:
    """Fetch news from all configured sources.
    
    Behavioral contract from bash fetch.sh:
    - Config from news_config.json (not adjutant.yaml)
    - Sources: HN (Algolia API), Reddit (public JSON), blogs (HTML + RSS)
    - Blog RSS uses feedparser (Python) — replaces bash inline python3 + xml.etree
    - BUG IN BASH: No curl timeouts (can hang). Python fix: 30s timeout on all requests.
    - BUG IN BASH: jq -s 'add' on all-null inputs writes 'null' not '[]'.
      Python fix: use empty list fallback.
    - BUG IN BASH: Keywords with regex metacharacters can break jq test().
      Python fix: use re.escape() for keyword matching.
    
    IMPORTANT: Must create output directories before writing:
    state/news_raw/ and state/news_analyzed/ (bash version missing mkdir -p).
    """
    import httpx
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    config = json.loads(config_path.read_text())
    all_items: list[dict] = []
    
    for source in config.get("sources", []):
        try:
            items = _fetch_source(source)
            all_items.extend(items or [])  # Fix: null → empty list
        except Exception as e:
            logger.warning("Failed to fetch %s: %s", source.get("name"), e)
    
    # Write raw items
    raw_path = output_dir / f"raw_{datetime.now():%Y%m%d_%H%M%S}.json"
    raw_path.write_text(json.dumps(all_items, indent=2))
    
    return all_items

def _fetch_source(source: dict) -> list[dict]:
    """Fetch from a single source."""
    import httpx
    
    source_type = source.get("type", "")
    
    if source_type == "hackernews":
        return _fetch_hackernews(source)
    elif source_type == "reddit":
        return _fetch_reddit(source)
    elif source_type == "blog":
        return _fetch_blog_rss(source)
    else:
        logger.warning("Unknown source type: %s", source_type)
        return []

def _fetch_hackernews(source: dict) -> list[dict]:
    """Fetch from HN Algolia API."""
    import httpx
    
    keywords = source.get("keywords", [])
    query = " OR ".join(keywords) if keywords else ""
    
    resp = httpx.get(
        SOURCES["hackernews"],
        params={"query": query, "tags": "story"},
        timeout=30,  # Fix: bash has no timeout
    )
    resp.raise_for_status()
    
    hits = resp.json().get("hits", [])
    return [
        {
            "title": h.get("title", ""),
            "url": h.get("url", ""),
            "score": h.get("points", 0),
            "source": "hackernews",
        }
        for h in hits
    ]

def _fetch_reddit(source: dict) -> list[dict]:
    """Fetch from Reddit public JSON API."""
    import httpx
    
    subreddit = source.get("subreddit", "technology")
    resp = httpx.get(
        SOURCES["reddit"].format(subreddit=subreddit),
        headers={"User-Agent": "adjutant/2.0"},
        timeout=30,
    )
    resp.raise_for_status()
    
    posts = resp.json().get("data", {}).get("children", [])
    return [
        {
            "title": p["data"].get("title", ""),
            "url": p["data"].get("url", ""),
            "score": p["data"].get("score", 0),
            "source": "reddit",
        }
        for p in posts
    ]

def _fetch_blog_rss(source: dict) -> list[dict]:
    """Fetch from blog RSS feed.
    
    Bash version uses inline python3 with xml.etree.ElementTree.
    Python version uses feedparser (pip extra: [news]).
    """
    import feedparser
    
    feed_url = source.get("url", "")
    feed = feedparser.parse(feed_url)
    
    return [
        {
            "title": entry.get("title", ""),
            "url": entry.get("link", ""),
            "score": 0,  # RSS has no score
            "source": "blog",
        }
        for entry in feed.entries
    ]
```

#### News Analyze (`analyze.py`) — Behavioral Contract

```python
# adjutant/news/analyze.py
import json
import re
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

OPENCODE_TIMEOUT = 90  # seconds — matches bash

def analyze(raw_items: list[dict], seen_urls_path: Path,
            keywords: list[str], config: dict) -> list[dict]:
    """Deduplicate and rank news items via Claude Haiku.
    
    Behavioral contract from bash analyze.sh:
    - Step 1: Dedup against state/news_seen_urls.json
    - Step 2: Keyword pre-filter (with fallback to all items sorted by score)
    - Step 3: Claude Haiku ranking via opencode
    - OPENCODE_TIMEOUT=90 seconds
    - BUG IN BASH: JSON array extraction via greedy grep -o '\\[.*\\]' (fragile —
      matches first '[' to last ']', breaks if LLM outputs multiple arrays).
      Python fix: proper JSON parsing with fallback.
    - Entirely procedural in bash (no function definitions).
    
    Keywords: Use re.escape() to prevent regex metacharacter issues
    (bash uses jq test() which is regex-based).
    """
    # Step 1: Dedup
    seen_urls = set()
    if seen_urls_path.exists():
        seen_urls = set(json.loads(seen_urls_path.read_text()))
    
    new_items = [i for i in raw_items if i.get("url") not in seen_urls]
    
    if not new_items:
        return []
    
    # Step 2: Keyword pre-filter
    if keywords:
        # Escape regex metacharacters (bash bug fix)
        patterns = [re.compile(re.escape(kw), re.IGNORECASE) for kw in keywords]
        filtered = [
            i for i in new_items
            if any(p.search(i.get("title", "")) for p in patterns)
        ]
        if not filtered:
            # Fallback: all items sorted by score (matches bash behavior)
            filtered = sorted(new_items, key=lambda x: x.get("score", 0), reverse=True)
    else:
        filtered = new_items
    
    # Step 3: Haiku ranking
    ranked = _rank_with_haiku(filtered, config)
    
    return ranked

def _rank_with_haiku(items: list[dict], config: dict) -> list[dict]:
    """Rank items using Claude Haiku via OpenCode.
    
    Returns ranked list. On failure, returns items sorted by score.
    """
    from adjutant.core.model import resolve_model_tier
    
    model = resolve_model_tier("cheap", config)
    
    prompt = (
        "Rank these news items by relevance and importance. "
        "Return a JSON array of the top items with 'title', 'url', 'summary' fields.\n\n"
        + json.dumps(items[:20], indent=2)  # Limit to 20 items for context
    )
    
    try:
        result = subprocess.run(
            ["opencode", "run", "--model", model, "--format", "json", prompt],
            capture_output=True, text=True,
            timeout=OPENCODE_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        logger.warning("Haiku ranking timed out, falling back to score sort")
        return sorted(items, key=lambda x: x.get("score", 0), reverse=True)
    
    # Parse JSON from response (fix: proper parsing, not greedy grep)
    text = result.stdout
    try:
        from adjutant.lib.ndjson import parse_ndjson
        ndjson_result = parse_ndjson(text)
        response_text = ndjson_result.text
        
        # Extract JSON array from response text
        ranked = _extract_json_array(response_text)
        if ranked:
            return ranked
    except Exception:
        pass
    
    # Fallback
    return sorted(items, key=lambda x: x.get("score", 0), reverse=True)

def _extract_json_array(text: str) -> list[dict]:
    """Extract JSON array from text, handling nested brackets properly.
    
    Improvement over bash greedy grep -o '\\[.*\\]' which matches
    first '[' to last ']' regardless of nesting.
    """
    # Find first '[' and its matching ']'
    start = text.find('[')
    if start == -1:
        return []
    
    depth = 0
    for i, ch in enumerate(text[start:], start):
        if ch == '[':
            depth += 1
        elif ch == ']':
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i+1])
                except json.JSONDecodeError:
                    return []
    return []
```

#### News Briefing (`briefing.py`) — Behavioral Contract

```python
# adjutant/news/briefing.py
import json
import logging
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

def run_briefing() -> None:
    """Run the full news pipeline: fetch → analyze → briefing → notify.
    
    Behavioral contract from bash briefing.sh:
    - Checks operational state (both killed AND paused — unlike some other
      scripts that only check killed)
    - BUG IN BASH: If Telegram notification fails, dedup cache update and
      cleanup are skipped (set -e propagation). Python fix: separate
      try/except blocks for notification vs cache update.
    - BUG IN BASH: Dedup update uses title-based cross-reference between
      analyzed and raw items (fragile if Haiku reformulates titles).
      Python fix: use URL-based cross-reference instead.
    - Cleanup: delete files older than N days (configurable)
    
    IMPORTANT: Must create directories before writing:
    state/news_raw/, state/news_analyzed/, journal/news/
    (bash version missing mkdir -p for these).
    """
    from adjutant.core.paths import get_adj_dir
    from adjutant.core.config import load_config
    from adjutant.lifecycle.state import is_killed, is_paused
    
    if is_killed() or is_paused():
        logger.info("Skipping news briefing — system is %s",
                     "killed" if is_killed() else "paused")
        return
    
    adj_dir = get_adj_dir()
    config = load_config()
    
    # Ensure directories exist (bash bug fix)
    for d in ["state/news_raw", "state/news_analyzed", "journal/news"]:
        (adj_dir / d).mkdir(parents=True, exist_ok=True)
    
    config_path = adj_dir / "news_config.json"
    if not config_path.exists():
        logger.warning("news_config.json not found, skipping briefing")
        return
    
    # 1. Fetch
    from adjutant.news.fetch import fetch_all
    raw_items = fetch_all(config_path, adj_dir / "state" / "news_raw")
    
    if not raw_items:
        logger.info("No news items fetched")
        return
    
    # 2. Analyze
    from adjutant.news.analyze import analyze
    news_config = json.loads(config_path.read_text())
    keywords = news_config.get("keywords", [])
    seen_urls_path = adj_dir / "state" / "news_seen_urls.json"
    
    analyzed = analyze(raw_items, seen_urls_path, keywords, config)
    
    if not analyzed:
        logger.info("No new items after analysis")
        return
    
    # 3. Format briefing
    briefing_text = _format_briefing(analyzed)
    
    # Save to journal
    journal_path = (adj_dir / "journal" / "news" /
                    f"briefing_{datetime.now():%Y%m%d_%H%M%S}.md")
    journal_path.write_text(briefing_text)
    
    # 4. Send notification (isolated from cache update — bash bug fix)
    try:
        from adjutant.messaging.adaptor import msg_send_notification
        msg_send_notification(briefing_text)
    except Exception as e:
        logger.error("Failed to send briefing notification: %s", e)
        # Continue to cache update — do NOT skip (bash bug fix)
    
    # 5. Update dedup cache (URL-based, not title-based — bash bug fix)
    _update_seen_urls(seen_urls_path, analyzed)
    
    # 6. Cleanup old files
    _cleanup_old_files(adj_dir, config)

def _format_briefing(items: list[dict]) -> str:
    """Format analyzed items into briefing text."""
    lines = ["📰 *News Briefing*\n"]
    for i, item in enumerate(items, 1):
        title = item.get("title", "Untitled")
        url = item.get("url", "")
        summary = item.get("summary", "")
        lines.append(f"{i}. [{title}]({url})")
        if summary:
            lines.append(f"   {summary}")
    return '\n'.join(lines)

def _update_seen_urls(seen_path: Path, items: list[dict]) -> None:
    """Update dedup cache using URLs (not titles — bash bug fix)."""
    seen = set()
    if seen_path.exists():
        seen = set(json.loads(seen_path.read_text()))
    
    for item in items:
        url = item.get("url", "")
        if url:
            seen.add(url)
    
    seen_path.write_text(json.dumps(list(seen), indent=2))

def _cleanup_old_files(adj_dir: Path, config: dict) -> None:
    """Delete news files older than retention days.
    
    Matches bash: find -mtime +N -delete
    """
    from datetime import timedelta
    import os
    
    retention_days = config.get("news", {}).get("retention_days", 30)
    cutoff = datetime.now().timestamp() - (retention_days * 86400)
    
    for subdir in ["state/news_raw", "state/news_analyzed"]:
        d = adj_dir / subdir
        if not d.exists():
            continue
        for f in d.iterdir():
            if f.stat().st_mtime < cutoff:
                f.unlink()
```

#### Status Dashboard (`status.py`) — Behavioral Contract

```python
# adjutant/observability/status.py
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

def get_status() -> dict:
    """Generate system status dashboard.
    
    Behavioral contract from bash status.sh:
    - Read-only dashboard — no side effects
    - No jq dependency — bash uses grep/sed/cut for all JSON parsing.
      Python version uses proper json module.
    - Shows: state, scheduled jobs, last heartbeat, notification budget,
      recent actions
    - _cron_human() translates cron expressions to human-readable
    """
    from adjutant.core.paths import get_adj_dir
    from adjutant.lifecycle.state import get_state
    from adjutant.capabilities.schedule.registry import schedule_list
    
    adj_dir = get_adj_dir()
    
    return {
        "state": get_state(),
        "schedules": _get_schedule_status(),
        "last_heartbeat": _get_last_heartbeat(adj_dir),
        "notification_budget": _get_notification_budget(adj_dir),
        "recent_actions": _get_recent_actions(adj_dir),
    }

def _get_schedule_status() -> list[dict]:
    """Get schedule statuses with human-readable cron expressions."""
    from adjutant.capabilities.schedule.registry import schedule_list
    
    schedules = []
    for s in schedule_list():
        schedules.append({
            "name": s.get("name"),
            "schedule": s.get("schedule"),
            "human": cron_to_human(s.get("schedule", "")),
            "enabled": s.get("enabled", False),
        })
    return schedules

def cron_to_human(expr: str) -> str:
    """Translate cron expression to human-readable string.
    
    Matches bash _cron_human() — basic translation of common patterns.
    Not a full cron parser; handles the most common cases.
    """
    parts = expr.split()
    if len(parts) != 5:
        return expr
    
    minute, hour, dom, month, dow = parts
    
    if minute == "0" and hour == "*":
        return "Every hour"
    if minute == "0" and hour != "*" and dom == "*":
        return f"Daily at {hour}:00"
    if minute != "*" and hour != "*" and dom == "*":
        return f"Daily at {hour}:{minute.zfill(2)}"
    if dow != "*" and dom == "*":
        days = {"0": "Sun", "1": "Mon", "2": "Tue", "3": "Wed",
                "4": "Thu", "5": "Fri", "6": "Sat"}
        day_name = days.get(dow, dow)
        return f"Every {day_name} at {hour}:{minute.zfill(2)}"
    
    return expr  # Fallback: return raw expression

def _get_last_heartbeat(adj_dir: Path) -> Optional[str]:
    """Read last heartbeat timestamp from state."""
    hb_file = adj_dir / "state" / "last_heartbeat"
    if hb_file.exists():
        return hb_file.read_text().strip()
    return None

def _get_notification_budget(adj_dir: Path) -> dict:
    """Get notification budget status."""
    from adjutant.core.config import load_config
    from datetime import date
    
    config = load_config()
    max_per_day = config.get("notifications", {}).get("max_per_day", 3)
    
    count_file = adj_dir / "state" / f"notify_count_{date.today().isoformat()}.txt"
    current = 0
    if count_file.exists():
        try:
            current = int(count_file.read_text().strip())
        except ValueError:
            pass
    
    return {
        "used": current,
        "max": max_per_day,
        "remaining": max(0, max_per_day - current),
    }

def _get_recent_actions(adj_dir: Path) -> list[str]:
    """Get recent actions from log (last 10 lines)."""
    log_file = adj_dir / "state" / "adjutant.log"
    if not log_file.exists():
        return []
    lines = log_file.read_text().splitlines()
    return lines[-10:]  # Last 10
```

#### Usage Tracker (`usage.py`) — Behavioral Contract

```python
# adjutant/observability/usage.py
import json
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# Hardcoded caps matching bash
SESSION_WINDOW_HOURS = 5
WEEKLY_WINDOW_DAYS = 7
SESSION_CAP = 44_000
WEEKLY_CAP = 350_000

def log_usage(tokens: int, model: str, adj_dir: Path) -> None:
    """Append token usage to JSONL log.
    
    Behavioral contract from bash usage_estimate.sh:
    - Appends to state/usage_log.jsonl
    - Each line: {"timestamp": "<iso>", "tokens": N, "model": "<model>"}
    - BUG IN BASH: JSONL parsing via awk is fragile (depends on key order).
      Python fix: proper JSON parsing per line.
    """
    log_file = adj_dir / "state" / "usage_log.jsonl"
    entry = json.dumps({
        "timestamp": datetime.utcnow().isoformat(),
        "tokens": tokens,
        "model": model,
    })
    with open(log_file, "a") as f:
        f.write(entry + "\n")

def get_usage_estimate(adj_dir: Path) -> dict:
    """Calculate session and weekly token usage.
    
    Behavioral contract from bash:
    - Session window: 5 hours rolling
    - Weekly window: 7 days rolling
    - Caps: 44K session, 350K weekly (hardcoded — match Claude Pro limits)
    - BUG IN BASH: Requires bc for all math. Python: native arithmetic.
    """
    log_file = adj_dir / "state" / "usage_log.jsonl"
    if not log_file.exists():
        return {
            "session": {"used": 0, "cap": SESSION_CAP, "pct": 0},
            "weekly": {"used": 0, "cap": WEEKLY_CAP, "pct": 0},
        }
    
    now = datetime.utcnow()
    session_cutoff = now - timedelta(hours=SESSION_WINDOW_HOURS)
    weekly_cutoff = now - timedelta(days=WEEKLY_WINDOW_DAYS)
    
    session_tokens = 0
    weekly_tokens = 0
    
    for line in log_file.read_text().splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
            ts = datetime.fromisoformat(entry["timestamp"])
            tokens = entry["tokens"]
            
            if ts >= weekly_cutoff:
                weekly_tokens += tokens
            if ts >= session_cutoff:
                session_tokens += tokens
        except (json.JSONDecodeError, KeyError, ValueError):
            continue  # Skip malformed lines
    
    return {
        "session": {
            "used": session_tokens,
            "cap": SESSION_CAP,
            "pct": round(session_tokens / SESSION_CAP * 100, 1),
        },
        "weekly": {
            "used": weekly_tokens,
            "cap": WEEKLY_CAP,
            "pct": round(weekly_tokens / WEEKLY_CAP * 100, 1),
        },
    }
```

#### Journal Rotation (`journal.py`) — Behavioral Contract

```python
# adjutant/observability/journal.py
import gzip
import logging
import os
from pathlib import Path
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

DEFAULT_RETENTION_DAYS = 30
DEFAULT_LOG_MAX_BYTES = 10 * 1024 * 1024  # 10 MB

def rotate_journals(adj_dir: Path, *, retention_days: int = DEFAULT_RETENTION_DAYS,
                    dry_run: bool = False, quiet: bool = False) -> None:
    """Archive old journal/news markdown files and rotate logs.
    
    Behavioral contract from bash journal_rotate.sh:
    - Archives: gzip old journal/news markdown files, then rm originals
    - Log rotation: numbered rotation with truncation (NOT deletion —
      safe for concurrent writers)
    - BUG IN BASH: Platform-specific stat for file size duplicates
      platform.sh instead of using it. Python fix: use Path.stat().st_size.
    - Supports --dry-run and --quiet flags
    """
    _rotate_markdown_files(adj_dir, retention_days, dry_run, quiet)
    _rotate_log(adj_dir, dry_run, quiet)

def _rotate_markdown_files(adj_dir: Path, retention_days: int,
                           dry_run: bool, quiet: bool) -> None:
    """Gzip and remove old journal/news markdown files."""
    cutoff = datetime.now() - timedelta(days=retention_days)
    
    for subdir in ["journal", "journal/news"]:
        d = adj_dir / subdir
        if not d.exists():
            continue
        
        for f in d.glob("*.md"):
            if datetime.fromtimestamp(f.stat().st_mtime) < cutoff:
                if not quiet:
                    logger.info("Archiving %s", f.name)
                if not dry_run:
                    # Gzip
                    gz_path = f.with_suffix(f.suffix + ".gz")
                    with open(f, "rb") as fin, gzip.open(gz_path, "wb") as fout:
                        fout.write(fin.read())
                    f.unlink()

def _rotate_log(adj_dir: Path, dry_run: bool, quiet: bool) -> None:
    """Rotate adjutant.log when exceeding size limit.
    
    Behavioral contract from bash:
    - Numbered rotation: adjutant.log → adjutant.log.1, .1 → .2, etc.
    - After rotation: TRUNCATE the file (not delete) — safe for concurrent
      writers that still have the file handle open
    - Uses Path.stat().st_size (not platform-specific stat command)
    """
    log_file = adj_dir / "state" / "adjutant.log"
    if not log_file.exists():
        return
    
    size = log_file.stat().st_size
    if size < DEFAULT_LOG_MAX_BYTES:
        return
    
    if not quiet:
        logger.info("Rotating log (%d bytes)", size)
    
    if dry_run:
        return
    
    # Numbered rotation: shift existing rotated files
    for i in range(9, 0, -1):
        old = log_file.with_name(f"adjutant.log.{i}")
        new = log_file.with_name(f"adjutant.log.{i + 1}")
        if old.exists():
            old.rename(new)
    
    # Current → .1
    import shutil
    shutil.copy2(log_file, log_file.with_name("adjutant.log.1"))
    
    # Truncate (not delete) — safe for concurrent writers
    with open(log_file, "w") as f:
        f.truncate(0)
```

#### Phase 6 Test Specifications

```python
# tests/unit/test_news_fetch.py — Key test cases

class TestNewsFetch:
    """Multi-source news fetching."""
    # Test: HN Algolia API response parsing
    # Test: Reddit JSON response parsing
    # Test: Blog RSS feed parsing (feedparser)
    # Test: timeout on slow sources (30s — bash bug fix)
    # Test: null/empty source results → empty list (not None)
    # Test: output directory created if missing
    # Test: keywords with regex metacharacters don't break

class TestNewsAnalyze:
    """Dedup + Haiku ranking."""
    # Test: dedup against seen_urls.json
    # Test: keyword pre-filter with re.escape()
    # Test: fallback to score-sorted on empty filter
    # Test: Haiku timeout → fallback to score sort
    # Test: JSON array extraction handles nested brackets
    # Test: malformed Haiku response → graceful fallback

class TestNewsBriefing:
    """Pipeline orchestrator."""
    # Test: killed state → skipped
    # Test: paused state → skipped (unlike some lifecycle scripts)
    # Test: notification failure does NOT skip cache update (bash bug fix)
    # Test: URL-based dedup, not title-based (bash bug fix)
    # Test: old file cleanup based on retention days
    # Test: missing directories created (bash bug fix)

# tests/unit/test_status.py — Key test cases

class TestStatus:
    """Status dashboard."""
    # Test: all state combinations reported correctly
    # Test: schedule list with human-readable cron
    # Test: notification budget calculation
    # Test: cron_to_human() translations

class TestCronToHuman:
    """Cron expression translation."""
    # Test: "0 * * * *" → "Every hour"
    # Test: "0 9 * * *" → "Daily at 9:00"
    # Test: "30 14 * * *" → "Daily at 14:30"
    # Test: "0 9 * * 1" → "Every Mon at 9:00"
    # Test: unparseable → returns raw expression

# tests/unit/test_usage.py — Key test cases

class TestUsageTracker:
    """Token usage estimation."""
    # Test: JSONL append format
    # Test: session window (5h rolling)
    # Test: weekly window (7d rolling)
    # Test: percentage calculation
    # Test: malformed JSONL lines skipped
    # Test: empty/missing log file → zero usage

# tests/unit/test_journal_rotate.py — Key test cases

class TestJournalRotation:
    """Journal and log rotation."""
    # Test: old markdown files gzipped
    # Test: files within retention period kept
    # Test: log rotation: numbered shift (.1→.2, etc.)
    # Test: log truncation (not deletion) after rotation
    # Test: dry-run mode: no file changes
    # Test: quiet mode: no log output
```

**Bash scripts replaced:**
- `scripts/news/*` → `adjutant/news/*`
- `scripts/observability/*` → `adjutant/observability/*`

---

### Phase 7: CLI & Cleanup (Week 12)

**Goal:** Final CLI, remove bash scripts

**Deliverables:**
```
adjutant/
├── __main__.py               # python -m adjutant
├── cli.py                    # Full Click CLI

# Bash wrapper for backward compatibility
adjutant                       #!/bin/bash
                              exec python -m adjutant "$@"
```

**Bash scripts removed:**

Before removing `scripts/`, all integration points must be updated:

1. **Crontab entries** — all `schedules:` in `adjutant.yaml` reference `scripts/` paths (e.g., `scripts/news/briefing.sh`, `scripts/lifecycle/pulse_cron.sh`). Phase 5 (`crontab.py`) must rewrite these to Python entry points (e.g., `python -m adjutant.news.briefing`). The schedule registry must update the `script:` field format.

2. **LaunchD/systemd service files** — currently reference `scripts/lifecycle/startup.sh` as the service command. Phase 5 must generate new service definitions pointing to `python -m adjutant start`.

3. **External KB crontab entries** — KB-specific scheduled jobs (e.g., `portfolio_fetch`) reference external absolute paths and are **unaffected** by the removal of `scripts/`.

4. **The `adjutant` CLI wrapper** — rewritten from the bash `case` dispatcher to `exec python -m adjutant "$@"`. The full command routing is handled by Click.

5. **`.opencode/agents/adjutant.md`** — if the agent definition references `bash "${ADJ_DIR}/scripts/..."` tool invocations, these must be updated to Python entry points. Review the agent definition before deletion.

6. **Crontab migration procedure** — for existing installations upgrading from bash to Python:
   ```python
   def migrate_crontab_entries():
       """One-time migration: rewrite bash script paths to Python entry points.
       
       Mapping:
       - scripts/news/briefing.sh → python -m adjutant.news.briefing
       - scripts/lifecycle/pulse_cron.sh → python -m adjutant.lifecycle.cron pulse
       - scripts/lifecycle/review_cron.sh → python -m adjutant.lifecycle.cron review
       - scripts/capabilities/schedule/notify_wrap.sh → python -m adjutant.capabilities.schedule.runner --notify
       
       External KB scripts (absolute paths outside adjutant/) are NOT migrated.
       
       Steps:
       1. Read current crontab
       2. For each line with '# adjutant:' marker, replace script path
       3. Update adjutant.yaml schedules[].script fields
       4. Write new crontab atomically
       """
   ```

7. **Agent definition tool audit** — before `scripts/` deletion, grep `.opencode/agents/adjutant.md` for patterns like `bash "${ADJ_DIR}/scripts/`, `bash "$ADJ_DIR/scripts/`, and `scripts/capabilities/`. Replace with Python invocations: `python -m adjutant.<module>`.

**Removal order:** Delete `scripts/` only after:
- All pytest tests pass with Python-only paths (coverage ≥ bats parity)
- Full end-to-end cycle completes: `adjutant start → /status → /kb query → /pause → /resume → /kill`
- Crontab entries verified with `adjutant schedule list`
- Service manager verified with `adjutant start` (daemonized)

**Final validation:**
```bash
pytest tests/ -v --cov=adjutant
python -m adjutant.cli doctor
python -m adjutant.cli kb list
python -m adjutant.cli start
```

---

## Test Suite Migration

### Strategy

1. **Parallel implementation** — Write pytest tests while bats tests still exist
2. **Coverage parity** — pytest must cover ≥100% of bats coverage before deletion
3. **Integration tests mock the same things** — OpenCode, curl, npx

### Test Structure

```python
# tests/conftest.py
import pytest
from pathlib import Path
import tempfile
import os

@pytest.fixture
def adj_dir(tmp_path, monkeypatch):
    """Create isolated adjutant directory."""
    adj_dir = tmp_path / ".adjutant"
    adj_dir.mkdir()
    (adj_dir / "state").mkdir()
    (adj_dir / "knowledge_bases").mkdir()
    (adj_dir / "identity").mkdir()
    monkeypatch.setenv("ADJUTANT_HOME", str(adj_dir))
    return adj_dir

@pytest.fixture
def mock_opencode(tmp_path, monkeypatch):
    """Mock opencode binary returning NDJSON."""
    mock_bin = tmp_path / "bin"
    mock_bin.mkdir()
    script = mock_bin / "opencode"
    script.write_text('#!/bin/bash\necho \'{"type":"text","text":"OK"}\'')
    script.chmod(0o755)
    monkeypatch.setenv("PATH", f"{mock_bin}:{os.environ['PATH']}")

@pytest.fixture
def sample_kb(adj_dir):
    """Create a sample KB for testing."""
    kb_dir = adj_dir / "knowledge_bases" / "test_kb"
    kb_dir.mkdir()
    (kb_dir / "kb.yaml").write_text("""
name: "test_kb"
description: "Test KB"
model: "inherit"
access: "read-only"
""")
    return kb_dir

@pytest.fixture
def adj_config(adj_dir):
    """Create adjutant.yaml with standard config for testing.
    
    Mirrors adjutant.yaml.example structure. Used by test_model.py,
    test_config.py, and any test that needs config resolution.
    """
    import yaml
    config = {
        "instance": {"name": "test"},
        "messaging": {
            "backend": "telegram",
            "telegram": {
                "session_timeout_seconds": 7200,
                "default_model": "anthropic/claude-haiku-4-5",
                "rate_limit": {"messages_per_minute": 10},
            },
        },
        "llm": {
            "models": {
                "cheap": "anthropic/claude-haiku-4-5",
                "medium": "anthropic/claude-sonnet-4-6",
                "expensive": "anthropic/claude-opus-4-5",
            }
        },
        "features": {
            "news": {"enabled": False},
            "screenshot": {"enabled": False},
            "vision": {"enabled": False},
            "search": {"enabled": False},
        },
        "notifications": {"max_per_day": 3, "quiet_hours": {"enabled": False}},
        "debug": {"dry_run": False, "verbose_logging": False},
    }
    (adj_dir / "adjutant.yaml").write_text(yaml.dump(config))
    return config

@pytest.fixture
def adj_env(adj_dir):
    """Create .env file with test credentials."""
    (adj_dir / ".env").write_text(
        'TELEGRAM_BOT_TOKEN=test-token-123\n'
        'TELEGRAM_CHAT_ID=12345678\n'
        'BRAVE_API_KEY=test-brave-key\n'
    )
```

### Coverage Targets

| Module | Target Coverage |
|--------|-----------------|
| `adjutant.core.*` | 95% |
| `adjutant.capabilities.kb.*` | 90% |
| `adjutant.messaging.*` | 85% |
| `adjutant.lifecycle.*` | 80% |
| `adjutant.setup.*` | 75% |

---

## Dependencies

**Dependency decisions:**
- **pydantic** is deferred to Phase 3 (optional `[validation]` extra). Phase 1 uses `dataclasses` + `PyYAML` for config loading — simpler, zero external deps beyond PyYAML. Pydantic is added in Phase 3 for Telegram API response validation.
- **filelock** is removed. The bash `mkdir`-based locking with PID storage is replicated by the custom `PidLock` class (see Process Management section) which preserves the `listener.lock/pid` interface needed by `emergency_kill`.

```toml
# pyproject.toml

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "adjutant"
version = "2.0.0"
requires-python = ">=3.11"

dependencies = [
    "click>=8.0",
    "httpx>=0.24",
    "pyyaml>=6.0",
    "rich>=13.0",           # Pretty CLI output
    "psutil>=5.9",          # Process management (reaper, kill trees, orphan detection)
]

[project.scripts]
adjutant = "adjutant.cli:main"

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-asyncio>=0.21",
    "pytest-cov>=4.0",
    "pytest-xdist>=3.0",    # Parallel tests
    "pytest-timeout>=2.0",  # Prevent hung tests
    "ruff>=0.4",            # Linting + formatting
    "mypy>=1.10",           # Type checking
    "types-PyYAML",         # Type stubs
    "types-psutil",         # Type stubs
]
validation = [
    "pydantic>=2.0",        # Added in Phase 3 for API response validation
]
screenshot = [
    "playwright>=1.40",
]
news = [
    "feedparser>=6.0",
]

[tool.hatch.build.targets.wheel]
packages = ["src/adjutant"]

[tool.ruff]
target-version = "py311"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP", "B", "A", "SIM", "TCH"]

[tool.mypy]
python_version = "3.11"
strict = true
warn_return_any = true
warn_unused_configs = true

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
timeout = 30
addopts = "-x --tb=short"
```

---

## Backward Compatibility

### CLI Commands (Unchanged)

```bash
adjutant start
adjutant stop
adjutant status
adjutant kb list
adjutant kb query <name> "question"
adjutant schedule list
adjutant news
# ...all commands work identically
```

### Config Files (Unchanged)

- `adjutant.yaml` — Same format
- `.env` — Same format
- `knowledge_bases/registry.yaml` — Same format
- KB `kb.yaml` — Same format

### State Files (Unchanged)

- `state/paused` — Same format (sentinel file)
- `state/killed` — Same format (sentinel file)
- `state/telegram_model.txt` — Same format (plain text)
- `state/telegram_session.json` — Same format (JSON with session_id, epoch, timestamp)
- `state/telegram_offset` — Same format (integer)
- `state/rate_limit_window` — Replaced by in-memory deque (file no longer needed)
- `state/adjutant.log` — Same format
- `state/listener.lock/` — Same `mkdir`-based lock with `pid` file inside (custom `PidLock` class preserves the bash interface; `emergency_kill`/`lifecycle.kill` reads `listener.lock/pid` to find the listener)
- `state/opencode_web.pid` — Same format (PID file)

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Auth/rate-limit regression | Medium | **Critical** | Security-critical path; dedicated test suite with unauthorized sender, rate exceeded, and reflect-interception scenarios. Side-by-side bash/Python testing before cutover. |
| Process management bugs | High | High | Orphan processes, stale PIDs, zombie language servers. Requires extensive integration testing with real process spawning. `psutil` test fixtures. |
| Session state corruption | Medium | Medium | Race conditions on `telegram_session.json` reads/writes during concurrent requests. Use atomic write (write-to-temp + rename). |
| asyncio complexity | Medium | High | Deadlocks, task cancellation edge cases, unhandled exceptions in fire-and-forget tasks. Use `asyncio.TaskGroup` (3.11+) with proper exception propagation. |
| Listener behavioral change | Medium | High | "Process only last update" is unusual; easy to accidentally process all. Must have explicit integration test verifying message dropping. |
| KB query regression | Medium | High | Integration tests against real OpenCode; side-by-side testing |
| Telegram API change | Low | High | Use stable Bot API; mock in tests |
| Python dependency conflicts | Low | Medium | Use venv; pin versions |
| Test coverage gaps | Medium | High | Coverage >90% before deleting bash |
| Cron job breakage | Medium | Medium | Test on real crontab; document migration |
| Setup wizard UX change | Low | Low | Keep same prompts; use Rich for better output |
| External KB test portability | High | Low | `portfolio_fetch.bats` / `portfolio_trade.bats` reference machine-specific paths; ported as skip-if-absent tests. |

---

## Effort Estimation

| Phase | Hours | Dependencies | Notes |
|-------|-------|--------------|-------|
| Phase 1: Foundation | 80-100 | None | Now includes `process.py` (psutil wrappers), `model.py` (tier resolution), and their tests |
| Phase 2: KB System | 60-80 | Phase 1 | Unchanged — registry, query, scaffold, run |
| Phase 3: Messaging | 120-160 | Phase 1 | **Revised up** — auth/rate-limit pipeline, asyncio listener, session management, typing indicators, in-flight job cancellation, pending-reflect state machine. This is the highest-risk phase. |
| Phase 4: Capabilities | 60-80 | Phase 2 | Unchanged — schedule, screenshot, vision, search |
| Phase 5: Lifecycle/Setup | 80-100 | Phase 3 | **Revised up** — emergency_kill process-tree killing, startup orphan detection, update self-updater, wizard /dev/tty→Rich migration |
| Phase 6: News/Observability | 40-60 | Phase 1 | Unchanged |
| Phase 7: CLI/Cleanup | 40-60 | Phases 2-6 | Unchanged |
| **Total** | **480-640** | - | |

**Contingency:** Add 15-20% for process management edge cases and asyncio debugging that only surface under real load. Realistic range: **550-750 hours**.

---

## Success Metrics

| Metric | Current (bash) | Target (Python) |
|--------|----------------|-----------------|
| Test suite runtime | >2 min (timeouts) | <30 sec |
| NDJSON parsing (1000 lines) | 3-5 sec | <50 ms |
| KB query latency | ~100-500 ms overhead | ~5-20 ms overhead |
| RAM usage (idle) | ~5-10 MB | ~20-40 MB |
| Lines of code | 9,600 bash + 7,100 tests | ~8,000 Python + 5,000 tests |
| Test coverage | N/A (bats) | >90% |
| Type safety | None | Full (pyright/mypy) |

---

## Rollback Plan

1. **Each phase is independently deployable**
2. **Bash scripts remain in repo during transition**
3. **Feature flags** control Python vs bash execution (add to `adjutant.yaml` during transition — not in `.example` since they're temporary):
   ```yaml
   # adjutant.yaml (transitional — remove after Phase 7)
   experimental:
     use_python_kb: true
     use_python_messaging: false
   ```
4. **Git tags** for each phase completion

---

## Conclusion

This plan provides **complete coverage** of the Adjutant codebase:

**Functional coverage:**
- All 54 bash scripts mapped to Python modules
- All 518 tests migrated to pytest
- All capabilities (kb, schedule, screenshot, vision, search) covered
- All lifecycle scripts covered (including process-tree killing and orphan reaping)
- All setup scripts covered (wizard /dev/tty patterns → Rich prompts)
- All messaging scripts covered (including asyncio listener and typing indicators)

**Behavioral fidelity:**
- Security pipeline preserved (auth → rate limit → reflect interception → dispatch)
- Single-user authorization with silent rejection of unauthorized senders
- "Process only last update" listener behavior explicitly preserved
- OpenCode session management with 2-hour timeout reuse
- In-flight chat job cancellation on new messages (with subprocess termination)
- Periodic language-server orphan reaping (all 3 rules: orphan, stranded, RSS)
- Model tier resolution: separate chat chain (file→default) and KB chain (file→config→default)
- Error handling strategy: never crash the daemon, user-friendly error messages
- Message sanitization: control character stripping, Telegram 4096-char limit, Markdown parse mode
- Photo dispatch with authorization
- Reflect cancellation user feedback
- Rate limiter: env var override, append-before-check behavioral parity with bash
- Single-instance lock: PidLock with stale recovery, PID stored for emergency_kill
- Health check: correct endpoint, restart-and-retry, accepts any JSON event as success

**Intentional improvements over bash (10 bug fixes):**
- Cron handlers (pulse/review) now check PAUSED/KILLED state before execution
- News fetch: 30s curl timeout (bash had none — could hang indefinitely)
- News fetch: null source results → empty list (bash `jq -s 'add'` wrote `null`)
- News fetch: keyword regex metacharacters escaped (bash `jq test()` could break)
- News analyze: proper bracket-matching JSON extraction (bash greedy `grep -o` was fragile)
- News briefing: notification failure doesn't skip dedup cache update (bash `set -e` propagation)
- News briefing: URL-based dedup (bash title-based cross-reference was fragile if Haiku reformulated)
- Screenshot caption: truncated at character boundary (bash byte-based `cut -c` could split UTF-8)
- Usage tracker: native arithmetic (bash required `bc` binary)
- Journal rotation: `Path.stat()` for file size (bash duplicated platform detection)

**Compatibility guarantees:**
- Existing KBs work unchanged — no migration required
- KB-internal scripts (portfolio_kb) are out of scope — separate project
- CLI commands identical — zero user-facing changes
- Config files unchanged — seamless upgrade
- Agent definition (`.opencode/agents/adjutant.md`) unchanged
- OpenCode invocation arguments identical

**Estimated timeline:** 12-14 weeks  
**Estimated effort:** 550-750 hours  
**Risk level:** Medium-High (mitigated by phased approach, parallel testing, and feature flags for rollback). Highest-risk phase is Phase 3 (Messaging) due to security-critical dispatch, asyncio complexity, and behavioral edge cases.
