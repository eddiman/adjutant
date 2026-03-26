# Architecture Overview

Adjutant is a persistent autonomous agent framework that runs on your local machine. It listens for messages from a messaging backend, routes them through a backend-agnostic dispatcher, and responds via LLM-powered AI (OpenCode or Claude Code CLI) or built-in commands.

---

## High-Level Diagram

```
┌──────────────────────────────────────────────────────┐
│                    User Device                       │
│                                                      │
│   adjutant CLI ──► lifecycle modules                 │
│         │                                            │
│         ▼                                            │
│   Listener (telegram/listener.py)                    │
│         │  async polling loop                        │
│         ▼                                            │
│   dispatch.py  ──► rate limit check                  │
│         │          authorization check               │
│         ├──► /command handlers (commands.py)         │
│         └──► natural language ──► chat.py            │
│                                       │              │
│                                       ▼              │
│                               backend.run()           │
│                          (OpenCode or Claude CLI)     │
│         │                                            │
│         ▼                                            │
│   Adaptor send functions ──► Messaging Backend       │
└──────────────────────────────────────────────────────┘
```

Everything runs on your machine. There is no server, no cloud component, and no data leaving your device except the messages you explicitly send and receive.

---

## Layer Summary

| Layer | Location | Responsibility |
|-------|----------|---------------|
| CLI | `src/adjutant/cli.py` | Click-based CLI — all `adjutant` subcommands |
| Common utilities | `src/adjutant/core/` | Shared library: backend abstraction, paths, env, lockfiles, logging, model, platform |
| Messaging | `src/adjutant/messaging/` | Adaptor contract, dispatcher, backend implementations |
| Lifecycle | `src/adjutant/lifecycle/` | Start, stop, pause, kill, restart, update |
| Capabilities | `src/adjutant/capabilities/` | Screenshot, vision, knowledge base, schedule, search |
| Identity | `identity/` | Three-layer agent persona loaded at chat time |
| LLM Backend | `core/backend*.py` | Backend abstraction: OpenCode or Claude CLI |
| Agent config | `.opencode/`, `.claude/` | Agent definitions, workspace config, permissions, hooks |

---

## CLI Layer — `src/adjutant/cli.py`

The CLI is a Click application. The `adjutant` script in the repo root is a thin bash shim that resolves `.venv/bin/python` and delegates to `python -m adjutant`. All business logic lives in the Python modules.

| Command group | Module |
|---------------|--------|
| `start` / `stop` / `restart` | `messaging/telegram/service.py` |
| `status` | `observability/status.py` |
| `pause` / `resume` / `kill` | `lifecycle/control.py` |
| `startup` | `lifecycle/control.py` |
| `update` | `lifecycle/update.py` |
| `pulse` / `review` | `lifecycle/cron.py` |
| `kb` | `capabilities/kb/` |
| `schedule` | `capabilities/schedule/` |
| `setup` | `setup/wizard.py` |
| `news` | `news/` |
| `screenshot` | `capabilities/screenshot/` |
| `search` | `capabilities/search/` |
| `notify` / `reply` | `messaging/telegram/notify.py`, `reply.py` |
| `doctor` / `logs` / `rotate` | `observability/`, `lifecycle/` |

---

## Core Utilities — `src/adjutant/core/`

Shared library imported by every other module.

| Module | Responsibility |
|--------|---------------|
| `paths.py` | Resolves `ADJ_DIR` by walking up from the calling module until it finds `.adjutant-root`. Sets and exports `ADJ_DIR`. Provides `get_adj_dir()` / `init_adj_dir()`. |
| `env.py` | Extracts credential values from `.env` using line-by-line parsing — never `exec`s the file. Provides `get_credential(key)`, `has_credential(key)`. |
| `lockfiles.py` | Manages the `KILLED` and `PAUSED` state files. Provides check functions and state mutators. |
| `logging.py` | Appends structured log lines to `state/adjutant.log`. Provides `adj_log(component, message)`. |
| `backend.py` | LLM backend protocol, `LLMResult`, `BackendCapabilities`, `get_backend()` factory. |
| `backend_opencode.py` | OpenCode CLI backend implementation. |
| `backend_claude_cli.py` | Claude Code CLI backend implementation. |
| `opencode.py` | Low-level OpenCode CLI process management (used by `backend_opencode.py`). |
| `model.py` | Resolves model tier names (`cheap`/`medium`/`expensive`) to actual model slugs from `adjutant.yaml`. |
| `config.py` | Loads and validates `adjutant.yaml`. |
| `platform.py` | OS and architecture detection. |
| `process.py` | Process management helpers. |

---

## Capabilities Layer — `src/adjutant/capabilities/`

Each capability is an isolated subdirectory. Capability functions accept arguments and return a result string or raise.

| Capability | Entry Module | Description |
|-----------|-------------|-------------|
| `kb/` | `kb/query.py`, `kb/run.py`, `kb/manage.py` | KB query, KB-local operations, KB CRUD |
| `schedule/` | `schedule/install.py`, `schedule/manage.py` | Scheduled job management |
| `screenshot/` | `screenshot/screenshot.py` | Playwright screenshot + vision caption + Telegram send |
| `vision/` | `vision/vision.py` | LLM image analysis (OpenCode backend only) |
| `search/` | `search/search.py` | Brave Search API integration |
| `memory/` | `memory/memory.py`, `memory/classify.py` | Persistent long-term memory with auto-classification |

---

## Further Reading

- [Messaging](messaging.md) — adaptor contract, dispatcher, Telegram internals
- [Identity & Agent](identity.md) — three-layer identity model, LLM backend integration
- [Backends](backends.md) — backend protocol, factory, capability system, error taxonomy
- [State & Lifecycle](state.md) — lockfiles, state files, lifecycle state machine
- [Autonomy](autonomy.md) — pulse/review cycle, notification budget, action ledger
- [Design Decisions](design-decisions.md) — why things are the way they are
