# Architecture Overview

Adjutant is a persistent autonomous agent framework that runs on your local machine. It listens for messages from a messaging backend, routes them through a backend-agnostic dispatcher, and responds via OpenCode-powered AI or built-in commands.

---

## High-Level Diagram

```
┌──────────────────────────────────────────────────────┐
│                    User Device                       │
│                                                      │
│   adjutant CLI ──► lifecycle scripts                 │
│         │                                            │
│         ▼                                            │
│   Listener (e.g. telegram/listener.sh)               │
│         │  polls backend API in a tight loop         │
│         ▼                                            │
│   dispatch.sh  ──► rate limit check                  │
│         │          authorization check               │
│         ├──► /command handlers (commands.sh)         │
│         └──► natural language ──► chat.sh            │
│                                       │              │
│                                       ▼              │
│                               opencode_run           │
│                               (OpenCode agent)       │
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
| CLI | `adjutant` (root) | Thin dispatcher — resolves paths, delegates to scripts |
| Common utilities | `scripts/common/` | Shared library: paths, env, lockfiles, logging, platform |
| Messaging | `scripts/messaging/` | Adaptor contract, dispatcher, backend implementations |
| Lifecycle | `scripts/lifecycle/` | Start, stop, pause, kill, restart, update |
| Capabilities | `scripts/capabilities/` | Screenshot, vision, knowledge base query |
| Identity | `identity/` | Three-layer agent persona loaded at chat time |
| OpenCode | `.opencode/` | Agent definition, workspace config, permissions |

---

## CLI Layer — `adjutant`

The `adjutant` script in the repo root is a thin dispatcher. It resolves `ADJ_DIR` via `paths.sh` and delegates every subcommand to the appropriate script using a `case` statement. It never contains business logic.

| Command | Script |
|---------|--------|
| `start` / `stop` | `scripts/messaging/telegram/service.sh` |
| `restart` | `scripts/lifecycle/restart.sh` |
| `update` | `scripts/lifecycle/update.sh` |
| `status` | `scripts/observability/status.sh` |
| `pause` / `resume` | `scripts/lifecycle/pause.sh` / `resume.sh` |
| `kill` | `scripts/lifecycle/emergency_kill.sh` |
| `startup` | `scripts/lifecycle/startup.sh` |
| `doctor` | inline in `adjutant` |
| `kb` | `scripts/capabilities/kb/manage.sh` |
| `setup` | `scripts/setup/wizard.sh` |

---

## Common Utilities — `scripts/common/`

Shared library sourced by every other script. Load order matters: `paths.sh` must come first.

| File | Responsibility |
|------|---------------|
| `paths.sh` | Resolves `ADJ_DIR` by walking up from the calling script until it finds `.adjutant-root` (tracked) or `adjutant.yaml` (legacy fallback). Sets and exports `ADJ_DIR`. |
| `env.sh` | Extracts credential values from `.env` using grep/cut/tr — never `source`s the file. Provides `get_credential KEY`, `has_credential KEY`, `require_telegram_credentials`. |
| `lockfiles.sh` | Manages the `KILLED` and `PAUSED` state files. Provides check functions (`check_killed`, `check_paused`, `check_operational`), boolean queries (`is_killed`, `is_paused`), and state mutators. |
| `logging.sh` | Appends structured log lines to `state/adjutant.log`. Format: `[YYYY-MM-DD HH:MM:SS] [COMPONENT] message`. |
| `opencode.sh` | Wraps `opencode run` with timeout support (`OPENCODE_TIMEOUT` env var), before/after PID snapshots to kill orphaned language-server children, and a periodic reaper (`opencode_reap`) that also catches servers stranded under the web process. Provides `opencode_health_check` to probe and auto-restart a degraded `opencode web` server. |
| `platform.sh` | OS and architecture detection. Used by setup and install scripts for platform-specific behaviour. |

---

## Capabilities Layer — `scripts/capabilities/`

Each capability is an isolated subdirectory with its own entry script. Capabilities accept arguments, load common utils, and return `OK:<result>` or `ERROR:<reason>` on stdout.

| Capability | Entry Script | Description |
|-----------|-------------|-------------|
| `screenshot` | `screenshot/screenshot.sh URL [CAPTION]` | Playwright screenshot + vision caption + Telegram send |
| `vision` | `vision/vision.sh FILE PROMPT` | LLM image analysis via OpenCode |
| `kb` | `kb/query.sh NAME QUESTION` | Query a registered knowledge base |
| `kb` | `kb/manage.sh` | CRUD operations on the KB registry |

---

## Further Reading

- [Messaging](messaging.md) — adaptor contract, dispatcher, Telegram internals
- [Identity & Agent](identity.md) — three-layer identity model, OpenCode integration
- [State & Lifecycle](state.md) — lockfiles, state files, lifecycle state machine
- [Design Decisions](design-decisions.md) — why things are the way they are
