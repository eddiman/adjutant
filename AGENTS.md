# AGENTS.md — Builder Guide

For AI coding agents working on Adjutant. Not read at runtime.

---

## Hard Rules

1. **NEVER read KB files directly.** Always query via CLI: `.venv/bin/python -m adjutant kb query <name> "<question>"`. No Read, Glob, Grep, `cat`, or `ls` on any KB path.

---

## What This Is

Python-based persistent agent framework. An LLM agent receives messages via Telegram, queries sandboxed KB sub-agents, and orchestrates lifecycle/heartbeat logic. CLI entrypoint: `adjutant` (bash shim → `python -m adjutant`).

---

## Repo Map

```
adjutant/                                 # Monorepo
├── adjutant                              # CLI shim
├── adjutant.yaml.example                 # Config template (adjutant.yaml gitignored)
├── .env.example                          # Secrets template (.env gitignored)
├── .opencode/agents/adjutant.md          # Main agent definition (tracked)
├── identity/                             # Soul/heart/registry (gitignored)
├── knowledge_bases/                      # registry.yaml (gitignored)
├── templates/kb/                         # KB scaffold templates
├── prompts/                              # pulse.md, review.md, escalation.md
├── src/adjutant/                         # Python framework
│   ├── cli.py                            # Click CLI
│   ├── __main__.py
│   ├── core/                             # backend, backend_opencode, backend_claude_cli, config, env, lockfiles, logging, model, opencode, paths, platform, process
│   ├── lib/                              # http, ndjson, claude_json
│   ├── lifecycle/                        # control, cron, update
│   ├── observability/                    # status, usage_estimate, journal_rotate
│   ├── capabilities/
│   │   ├── kb/                           # manage, query, run
│   │   ├── schedule/                     # install, manage, notify_wrap
│   │   ├── screenshot/                   # screenshot.py + playwright_screenshot.mjs
│   │   ├── search/                       # search.py
│   │   └── vision/                       # vision.py
│   ├── news/                             # fetch → analyze → briefing pipeline
│   ├── setup/                            # install, repair, uninstall, wizard + steps/
│   └── messaging/
│       ├── adaptor.py, dispatch.py
│       └── telegram/                     # chat, commands, listener, notify, photos, send, service
├── tests/unit/                           # ~56 files, ~1139 tests
├── tests/integration/                    # lifecycle, feature gating, plist tests
│
├── web/                                  # Adjutant Web (KB explorer dashboard)
│   ├── package.json                      # npm workspace root
│   ├── api/                              # Express REST API (port 3020)
│   │   ├── src/
│   │   │   ├── index.ts                  # Express app setup, createApp(), server start
│   │   │   ├── config.ts                 # Static config (port, host, ~/.adjutant-web paths)
│   │   │   ├── routes/                   # config, kbs, folders, notes, assets, adjutant
│   │   │   ├── services/                 # configService, kbService, folderService, fileNoteService, imageService, registryService
│   │   │   ├── middleware/               # auth (session token), accessControl (read-only KBs)
│   │   │   └── types/                    # config, kb, folder (WebSidecar), note
│   │   ├── vitest.config.ts
│   │   └── package.json
│   └── app/                              # React 19 frontend (port 3021)
│       ├── src/
│       │   ├── App.tsx                    # Main app: routing, state orchestration
│       │   ├── types/                    # Shared TypeScript types
│       │   ├── hooks/                    # useKbs, useFolder, useNotes, useImages, useSettings, useAdjutant, useCanvas*
│       │   ├── contexts/                 # EditorContext, PlacementContext
│       │   └── components/               # Canvas, Home, Sidebar, NoteEditor, nodes/, Toolbar, etc.
│       ├── index.html
│       ├── vite.config.ts
│       └── package.json
│
├── site/                                 # Docusaurus documentation site
│   ├── (reads ../docs via config)         # path: '../docs' in docusaurus.config.ts
│   ├── docusaurus.config.ts
│   ├── sidebars.ts
│   └── package.json
│
├── integrations/
│   └── openwebui/                        # Open WebUI filter/pipe integration
│       ├── adjutant_web_filter.py
│       ├── adjutant_web_pipe.py
│       └── README.md
│
├── docs/                                 # Source-of-truth documentation
│   ├── architecture/
│   ├── development/
│   ├── guides/
│   ├── plans/
│   ├── reference/
│   └── web/                              # Web dashboard docs
└── pyproject.toml                        # Python build (hatchling)
```

---

## Never Commit

Gitignored: `identity/`, `state/`, `journal/`, `insights/`, `photos/`, `screenshots/`, `.env`, `adjutant.yaml`, `knowledge_bases/registry.yaml`, `web/*/node_modules/`, `site/node_modules/`, `site/build/`.

---

## Python Conventions

1. All source under `src/adjutant/` — no top-level modules
2. Imports: stdlib → third-party → local, alphabetical within groups
3. Credentials: `get_credential(key)` from `core/env.py` — never read `.env` directly
4. Paths: `get_adj_dir()` from `core/paths.py` — never hardcode `~/.adjutant`
5. Logging: `adj_log("component", "message")` — not `print()`
6. Capability functions return a result string or raise — no stdout
7. Temp files: `NamedTemporaryFile(delete=False)` + `finally: os.unlink(tmp)`
8. New modules need `tests/unit/test_<module>.py`

---

## Module Naming

- `cmd_*` — slash command handlers (`messaging/telegram/commands.py`)
- `msg_*` — messaging interface (`adaptor.py` + telegram/)
- `kb_*` — KB CRUD (`capabilities/kb/manage.py`)
- `wiz_*` / `step_*` — wizard UI / setup steps
- `_*` — private/internal

---

## Adding a Capability

1. Create `src/adjutant/capabilities/<name>/<name>.py` — return string or raise
2. Add `cmd_<name>()` in `messaging/telegram/commands.py`
3. Register in `messaging/dispatch.py`
4. Add CLI command in `cli.py`
5. Document in `.opencode/agents/adjutant.md`
6. Add `tests/unit/test_<name>.py`
7. Add to `docs/guides/commands.md`

8. Use `backend.run()` for LLM calls — never import backend implementations directly

Full guide: `docs/development/plugin-guide.md`

---

## LLM Backend

Adjutant supports two LLM backends: **OpenCode** (`opencode`) and **Claude Code CLI** (`claude-cli`). The active backend is set in `adjutant.yaml` under `llm.backend`.

**All LLM calls go through the backend abstraction.** Import `get_backend` from `core/backend.py`:

```python
from adjutant.core.backend import get_backend

backend = get_backend()
result = await backend.run(prompt, agent="adjutant", model=model)
```

Never import `backend_opencode` or `backend_claude_cli` directly. Never call `opencode_run()` from call sites.

**Web server services:** The native `opencode web --mdns` and `cloudcli --port` web servers used to be spawned by `lifecycle/control.py` for remote access. They have been **retired** — adjutant's own `web/app` (served from `web/api`) is the remote UI now, and the Python daemon no longer manages any backend-side web server. `BackendCapabilities.web_server` is `False` on both backends for the same reason.

**Check capabilities before optional features:**

```python
if backend.capabilities.vision:
    result = await backend.run(prompt, files=[image_path])

if backend.capabilities.model_listing:
    models = await backend.list_models()
```

**Error handling:** Check `result.error_type` against the shared taxonomy (`model_not_found`, `auth_failure`, `rate_limited`, `context_overflow`, `permission_denied`, `vision_unsupported`, `timeout`, `parse_error`, `error`).

Full guide: `docs/development/backend-guide.md`

---

## Adding a Slash Command

Register in `dispatch.py` (exact match + prefix match). Handler signature:

```python
async def cmd_mycommand(arg: str, message_id: int, adj_dir: Path, *, bot_token: str, chat_id: str) -> None:
```

For long-running commands, use `msg_typing_start()`/`msg_typing_stop()` and run in a background task.

---

## Knowledge Bases

KBs are sandboxed workspaces. The main agent **never reads KB files** — it queries via sub-agent.

```python
result = await kb_query("mybase", "What is the status?", adj_dir)
```

- Scaffold generated from `templates/kb/` by `kb_scaffold()` in `manage.py`
- Registry at `knowledge_bases/registry.yaml` — pure-Python YAML parsing (no `pyyaml`)
- `read-only` KBs deny bash/edit/write; `read-write` KBs only deny external_directory

Full guide: `docs/guides/knowledge-bases.md`

---

## Documentation

The documentation site lives at `site/` (Docusaurus, deployed to GitHub Pages). Its `docs/` directory is a symlink to the repo's `docs/` — single source of truth, no manual mirroring.

### Workflow for docs changes

1. Edit the file in `docs/` (source of truth)
2. The `site/` build picks it up automatically via symlink
3. To test the site locally: `cd site && npm start`
4. To build: `cd site && npm run build`

### Changes that require docs updates

- New or modified CLI commands → `docs/guides/commands.md`
- New capabilities → `docs/guides/` (dedicated guide) + `docs/development/plugin-guide.md`
- Config changes → `docs/guides/configuration.md`
- Architecture changes → `docs/architecture/`
- New slash commands → `docs/guides/commands.md`
- Web dashboard changes → `docs/web/`

---

## Agent Prompt

`.opencode/agents/adjutant.md` is tracked — edit when capabilities, routing, or tool patterns change.
`identity/soul.md`, `heart.md`, `registry.md` are **gitignored** — never edit programmatically.

---

## Web Dashboard (`web/`)

Adjutant Web is the local-first KB explorer dashboard. It discovers Adjutant-format KBs and presents them on an infinite spatial canvas.

### Tech Stack

- **API** (`web/api/`): Express 4.x, TypeScript ~5.3, Zod, Sharp, Vitest
- **Frontend** (`web/app/`): React 19, React Flow (`@xyflow/react`), TipTap, Vite 7.x, CSS Modules

### Commands

```bash
cd web && npm install           # Install both api + app deps (npm workspaces)
cd web/api && npm run dev       # API on :3020 (hot reload)
cd web/app && npm run dev       # Vite on :3021 (hot reload)
cd web/api && npm test          # API tests (~87 tests)
cd web/app && npx tsc -b --noEmit  # TypeScript check
```

### Data Format

- `.adjutant-web.json` — sidecar files in each KB folder storing canvas positions, sections, stickies
- `<kb>/.adjutant-web/assets/` — uploaded images (WebP + thumbnails)
- `~/.adjutant-web/config.json` — app config (kbRoot path)
- Notes are pure `.md` files — no frontmatter

### Key Types

- `WebSidecar` / `WebSidecarSchema` — the `.adjutant-web.json` root schema (items, sections, stickies, images)
- `NoteFile` / `NoteMeta` — note data structures
- `KbMeta` — KB metadata from `kb.yaml`

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ADJUTANT_WEB_PORT` | `3020` | API server port |
| `ADJUTANT_WEB_HOST` | `0.0.0.0` | API server host |
| `ADJUTANT_WEB_SESSION_TOKEN` | (none) | Session token for auth (set by Adjutant on startup) |
| `ADJUTANT_DIR` | (auto-detected) | Adjutant root directory. In monorepo, defaults to repo root. |

### Canvas Node Types

| Type | Component | Description |
|------|-----------|-------------|
| `note` | `NoteNode` | Note card with title + TipTap preview. Double-click opens editor. |
| `image` | `ImageNode` | Image with upload/error/ready states. Corner resize. |
| `section` | `SectionNode` | Grouping rectangle with editable label. Resize handles. |
| `sticky` | `StickyNode` | Colored sticky with inline text editing. 9 color variants. |

### TypeScript Patterns

- **Strict mode** — avoid `any` types
- **`.js` extension** for all local imports in the API (ESM requirement)
- **`import type`** for type-only imports
- **CSS Modules** for all component styling
- **Custom hooks** for data fetching — components stay presentational
- **Optimistic updates** with debounced saves (300ms)
- **Barrel exports** (`index.ts`) in each component directory

### Adjutant Integration

The web dashboard reads Adjutant's state via `registryService.ts` (resolves `ADJUTANT_DIR` → reads `knowledge_bases/registry.yaml`). The `/api/adjutant/*` routes provide lifecycle control, health checks, schedule management, and journal access — all via Adjutant's CLI or filesystem state.

The `source` field in `active_operation.json` uses `"adjutant-web"` when operations are triggered from the dashboard.

---

## Testing

```bash
# Python tests
.venv/bin/pytest tests/ -q                          # full suite (~80s, ~1160 tests)
.venv/bin/pytest tests/unit/ -q                     # unit tests only (~75s, ~1139 tests)
.venv/bin/pytest tests/integration/ -q              # integration tests only (~5s)
.venv/bin/pytest tests/unit/test_kb_manage.py -q    # single file

# Web dashboard tests
cd web/api && npm test                              # API tests (~87 tests)
cd web/app && npx tsc -b --noEmit                   # TypeScript type check

# Documentation site
cd site && npm run build                            # Docusaurus build
```

All tests must pass before release. No CI. Full guide: `docs/development/testing.md`

---

## Gotchas

- **Backend abstraction**: Never call `opencode_run()` from call sites — always use `get_backend().run()`. The old function still exists in `core/opencode.py` but is only used internally by `backend_opencode.py`.
- **Claude CLI `--dangerously-skip-permissions`**: Required for non-interactive subprocess mode. Bypasses `.claude/settings.json` deny rules — hooks in `.claude/hooks/` are the primary defense.
- **Backend capabilities**: Always check `backend.capabilities.*` before calling optional methods like `list_models()`, `reap()`, or passing `files=` for vision. Not all backends support all features.
- **Model ID formats differ**: OpenCode uses `anthropic/claude-sonnet-4-6`, Claude CLI uses `sonnet`. The backend's `resolve_alias()` handles this transparently, but raw model IDs in state files may need translation during backend switches.
- `kb_list()` returns `KBEntry` objects, not dicts — use `.name`, `.description`, `.access`
- `kb_info()` / `kb_remove()` raise `ValueError`, not `KBNotFoundError`
- `kb_quick_create()` takes `kb_path` as `str`, not `Path`
- `schedule_get()` returns `None` when not found — does not raise
- `resolve_command()` is public in `schedule/manage.py` (was `_resolve_command` before v0.2.0)
- `dispatch_photo` arg order differs from `dispatch_message` — check signature
- `NDJSONResult` vs `OpenCodeResult` — don't mix at call sites
- `dispatch.py` auth + rate-limit + feature-gate block is security-critical — run full tests before refactoring
- Feature-gated commands (`/screenshot`, `/search`) are rejected at dispatch if disabled in config — add new gates to `_FEATURE_GATES` in `dispatch.py`
- **Cron line length**: macOS cron silently skips lines over ~1,024 chars. `_snapshot_path()` in `schedule/install.py` must build a minimal PATH — never dump the full `$PATH` from the shell. After `schedule sync`, verify with `crontab -l | wc -c` per line.
