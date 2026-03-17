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
adjutant/
├── adjutant                        # CLI shim
├── adjutant.yaml.example           # Config template (adjutant.yaml gitignored)
├── .env.example                    # Secrets template (.env gitignored)
├── .opencode/agents/adjutant.md    # Main agent definition (tracked)
├── identity/                       # Soul/heart/registry (gitignored)
├── knowledge_bases/                # registry.yaml (gitignored)
├── templates/kb/                   # KB scaffold templates
├── prompts/                        # pulse.md, review.md, escalation.md
├── src/adjutant/
│   ├── cli.py                      # Click CLI
│   ├── __main__.py
│   ├── core/                       # config, env, lockfiles, logging, model, opencode, paths, platform, process
│   ├── lib/                        # http, ndjson
│   ├── lifecycle/                  # control, cron, update
│   ├── observability/              # status, usage_estimate, journal_rotate
│   ├── capabilities/
│   │   ├── kb/                     # manage, query, run
│   │   ├── schedule/               # install, manage, notify_wrap
│   │   ├── screenshot/             # screenshot.py + playwright_screenshot.mjs
│   │   ├── search/                 # search.py
│   │   └── vision/                 # vision.py
│   ├── news/                       # fetch → analyze → briefing pipeline
│   ├── setup/                      # install, repair, uninstall, wizard + steps/
│   └── messaging/
│       ├── adaptor.py, dispatch.py
│       └── telegram/               # chat, commands, listener, notify, photos, send, service
├── tests/unit/                     # ~54 files, ~1139 tests
├── tests/integration/              # lifecycle, feature gating, plist tests
└── docs/                           # development/, architecture/, guides/
```

---

## Never Commit

Gitignored: `identity/`, `state/`, `journal/`, `insights/`, `photos/`, `screenshots/`, `.env`, `adjutant.yaml`, `knowledge_bases/registry.yaml`.

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

Full guide: `docs/development/plugin-guide.md`

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

Adjutant has a **separate documentation site repository**: `eddiman/adjutant-docs` (Docusaurus, deployed to GitHub Pages).

A clone of the docs site repo lives at **`adjutant-docs/`** in this project root (gitignored). This allows you to update both repos in the same session without external directory permission issues.

When making changes that affect user-facing behavior, **update docs in both places**:

1. **This repo** (`docs/`) — the source-of-truth markdown files
2. **`adjutant-docs/`** (local clone) — the published documentation site

The docs site clone mirrors the same structure: `adjutant-docs/docs/guides/`, `adjutant-docs/docs/architecture/`, `adjutant-docs/docs/development/`, etc.

### Workflow for docs changes

1. Edit the file in `docs/` (source of truth)
2. Apply the same change to `adjutant-docs/docs/` (the site repo clone)
3. Commit and push the adjutant-docs changes separately:
   ```bash
   cd adjutant-docs && git add -A && git commit -m "docs: ..." && git push
   ```

### If the clone is missing

```bash
git clone git@github.com:eddiman/adjutant-docs.git adjutant-docs
```

### Changes that require docs updates

- New or modified CLI commands → `docs/guides/commands.md`
- New capabilities → `docs/guides/` (dedicated guide) + `docs/development/plugin-guide.md`
- Config changes → `docs/guides/configuration.md`
- Architecture changes → `docs/architecture/`
- New slash commands → `docs/guides/commands.md`

The docs site plan is at `docs/reference/documentation-site-plan.md`.

---

## Agent Prompt

`.opencode/agents/adjutant.md` is tracked — edit when capabilities, routing, or tool patterns change.
`identity/soul.md`, `heart.md`, `registry.md` are **gitignored** — never edit programmatically.

---

## Testing

```bash
.venv/bin/pytest tests/ -q                          # full suite (~80s, ~1160 tests)
.venv/bin/pytest tests/unit/ -q                     # unit tests only (~75s, ~1139 tests)
.venv/bin/pytest tests/integration/ -q              # integration tests only (~5s)
.venv/bin/pytest tests/unit/test_kb_manage.py -q    # single file
```

All tests must pass before release. No CI. Full guide: `docs/development/testing.md`

---

## Gotchas

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
