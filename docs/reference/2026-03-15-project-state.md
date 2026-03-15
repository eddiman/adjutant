# Project State — 2026-03-15

This is the canonical "where are we" document. It captures the full state of Adjutant as of the end of the codebase audit and architecture hardening session. Read this first in any new session.

---

## What Adjutant Is

A Python-based persistent agent framework. A Claude-powered LLM agent receives messages via Telegram, queries sandboxed knowledge base sub-agents, and orchestrates lifecycle/heartbeat logic. The CLI entrypoint (`adjutant`) is a thin bash shim that delegates to `python -m adjutant`.

**Repo**: `github.com/eddiman/adjutant`  
**Language**: Python 3.9+ (all source under `src/adjutant/`)  
**Tests**: 1139 unit tests via pytest (`tests/unit/`)  
**Version**: 2.0.0 (`pyproject.toml`, `cli.py`, `VERSION`)

---

## Architecture (Current)

```
src/adjutant/
├── cli.py                      # Click CLI — 27 commands, 933 lines
├── __main__.py                 # python -m adjutant entrypoint
├── core/                       # config, env, lockfiles, logging, model, opencode, paths, platform, process
├── lib/                        # http (HttpClient with get/get_text/post), ndjson
├── lifecycle/                  # control (start/stop/kill), cron, update (self-update with SHA256)
├── observability/              # status, usage_estimate, journal_rotate
├── capabilities/
│   ├── kb/                     # manage (registry CRUD), query (sub-agent), run (KB operations)
│   ├── schedule/               # manage, install (crontab), notify_wrap
│   ├── screenshot/             # screenshot.py + playwright_screenshot.mjs
│   ├── search/                 # Brave Search API
│   └── vision/                 # single + multi-image vision via opencode
├── news/                       # fetch → analyze → briefing pipeline
├── setup/                      # install, repair, uninstall, wizard (WizardContext dataclass)
│   └── steps/                  # autonomy, features, identity, install_path, kb_wizard,
│                               #   messaging, prerequisites, schedule_wizard, service
└── messaging/
    ├── adaptor.py              # messaging interface contract
    ├── dispatch.py             # command routing, rate limiting, auth
    └── telegram/               # chat, commands, listener, notify, photos, send, service
```

### Key Design Patterns

- **KB isolation**: KBs are sandboxed opencode workspaces. Main agent never reads KB files — queries via sub-agent process. Enforced in AGENTS.md Hard Rules.
- **Registry-driven**: KBs discovered from `knowledge_bases/registry.yaml`. Schedules from `adjutant.yaml schedules:`.
- **Config**: `adjutant.yaml` + Pydantic models in `core/config.py`. Secrets in `.env` via `get_credential()`.
- **Logging**: `adj_log("component", "message")` — never `print()`.
- **Paths**: `get_adj_dir()` — never hardcode `~/.adjutant`.

---

## What Was Built (Completed Phases)

| Phase | Name | Key Deliverables |
|-------|------|-----------------|
| 1–3 | Shared utilities, paths, config | `scripts/common/`, `adjutant.yaml`, path resolution |
| 4 | KB system | Registry, query pipeline, sub-agent isolation, KB wizard |
| 5 | Generalization | Curl installer, self-update, optional Telegram, `.adjutant-root` marker |
| 6 | Python rewrite | Full replacement of bash with Python (`src/adjutant/`), Click CLI, pytest suite |
| 7 | Codebase audit | 23 issues fixed, prompt injection guards, SHA256 verification, deduplication |
| 8 | Scheduling | `adjutant schedule add/list/enable/disable/remove/sync/run`, KB-backed jobs |
| KB hardening | Runtime contract | Generic KB operations, schedule decoupling, reflect safety policy |

---

## What Was Fixed Today (2026-03-15)

### Codebase Audit — 23 Issues (commits `c9c8bec`, `85eef60`)

**Critical bugs fixed:**
- `update.py`: entire self-update was broken (wrong `HttpClient` API usage)
- `reply.py`: wrong kwarg for `HttpClient.post()` (then removed as dead code)
- `search.py`: double-encoded query parameters
- Prompts referenced non-existent bash scripts

**Security:**
- Prompt injection guard added to `pulse.md` and `review.md`
- SHA256 checksum verification for update tarballs
- `emergency_kill` scoped to this Adjutant instance

**Architecture hardening:**
- Listener processes ALL updates per poll batch (was dropping all but last)
- Deduplication: `sanitize_message()` canonical in `send.py`, registry parser in `manage.py`, colour helpers in `wizard.py`, `_read_env_cred` delegates to `core/env.py`
- `WizardContext` dataclass replaces scattered `WIZARD_*` globals
- Configurable timeouts: `chat_timeout_seconds`, `rate_limit.window_seconds`
- CLI test coverage: 35 tests via Click `CliRunner`

### Same-Day Features

- **Typing indicator fix** (`1399151`): 240s vision timeout, `try/finally` guards, `max_duration` safety ceiling on typing thread
- **Multi-image vision** (`75c254f`): `run_vision_multi()` passes multiple images to one LLM call
- **`HttpClient.get_text()`** (`75c254f`): raw text fetches for RSS/XML (was trying to JSON-parse)

---

## Current Health

- **Tests**: 1139 passing, 0 failures, 1 warning (unawaited coroutine in test — cosmetic)
- **Working tree**: Clean (no uncommitted changes)
- **Services**: Listener running, opencode web running, 5 cron jobs synced
- **Version**: 2.0.0 everywhere (VERSION, pyproject.toml, cli.py)

---

## What's Left to Build

### Priority 1: LaunchAgent Plist Hardening (Medium)

The wizard generates a macOS LaunchAgent plist. Needs verification:

- [ ] `KeepAlive: true` is set (unconditional — listener must always restart)
- [ ] `ThrottleInterval >= 30` (limit crash loop blast radius)
- [ ] Listener does NOT send startup notification (only `control.py` sends "I'm online" — prevents notification spam on launchd restarts)

**Where**: `src/adjutant/setup/steps/service.py` (plist generation), `src/adjutant/messaging/telegram/listener.py` (startup message)

### Priority 2: Integration/System Tests (Low)

Only unit tests exist. No process-level tests for:

- Listener start/stop lifecycle
- PID lock acquisition/release under race conditions
- LaunchAgent install/uninstall roundtrip
- End-to-end message flow with mock Telegram API
- Schedule crontab install/remove/sync

**Where**: Would need `tests/integration/` directory, pytest fixtures for process management with proper cleanup.

### Priority 3: Multi-Instance Support (Low)

`adjutant.yaml` `instance.name` exists but no CLI support. Would need:

- `adjutant --instance <name>` global flag or `ADJUTANT_INSTANCE` env var
- Instance-scoped ADJ_DIR resolution in `core/paths.py`
- Per-instance LaunchAgent/systemd service in `setup/steps/service.py`
- Per-instance PID locks in `core/lockfiles.py`

### Priority 4: Additional Messaging Backends (Low)

`adaptor.py` defines the interface. Only Telegram implemented. To add Slack/Discord:

- New `src/adjutant/messaging/slack/` directory
- Implement `msg_send_text`, `msg_send_photo`, `msg_typing_start/stop`
- Backend-specific auth (OAuth for Slack vs bot token for Telegram)
- Webhook vs polling model per backend

### Priority 5: Plugin/Capability Discovery (Low)

Capabilities exist as Python modules but no formal discovery. Framework plan proposed `capability.yaml` per capability for:

- `adjutant capabilities list`
- Wizard auto-discovery
- Runtime enable/disable

Current approach (imports + feature flags in config) works fine. This is a "nice to have."

---

## Known Technical Debt

These are acceptable for now but worth noting:

| Item | Location | Notes |
|------|----------|-------|
| `_TYPING_MAX_DURATION = 300` hardcoded | `send.py:189` | Not configurable, but 5 min is a sane ceiling |
| `_POLL_TIMEOUT = 10` hardcoded | `listener.py:30` | Telegram long-poll interval; 10s is standard |
| Photo dedup window `60.0` inline | `photos.py:31` | Could be a constant but rarely needs changing |
| Wizard globals still exist | `steps/messaging.py` etc. | `WizardContext` exists but steps still write to module globals for test compat |
| `_features_update_config` in `features.py` | `setup/steps/features.py` | Inline YAML manipulation — fragile but works |
| No `capability.yaml` discovery | `capabilities/` | Modules are imported directly, not discovered |

---

## File Quick Reference

| Need to... | Look at... |
|------------|-----------|
| Add a Telegram command | `messaging/dispatch.py` (routing) + `messaging/telegram/commands.py` (handler) |
| Add a capability | `capabilities/<name>/`, `dispatch.py`, `cli.py`, `AGENTS.md` — see `docs/development/plugin-guide.md` |
| Change config schema | `core/config.py` (Pydantic models) + `adjutant.yaml.example` |
| Fix a KB issue | `capabilities/kb/manage.py` (registry), `query.py` (sub-agent), `run.py` (operations) |
| Fix scheduling | `capabilities/schedule/manage.py` (CRUD), `install.py` (crontab) |
| Fix the listener | `messaging/telegram/listener.py` (poll loop), `dispatch.py` (routing) |
| Fix the wizard | `setup/wizard.py` (orchestrator), `setup/steps/` (individual steps) |
| Run tests | `.venv/bin/pytest tests/unit/ -q` |
| Check KB data | `.venv/bin/python -m adjutant kb query <name> "<question>"` — NEVER read KB files directly |
