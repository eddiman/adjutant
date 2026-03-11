# AGENTS.md — Builder Guide

For AI coding agents working on Adjutant. Not read at runtime — zero token cost to the Adjutant agent itself.

---

## What This Is

Adjutant is a Python-based persistent agent framework. An OpenCode-powered LLM agent receives messages via Telegram, queries sandboxed knowledge base sub-agents, and orchestrates lifecycle/heartbeat logic. The CLI entrypoint (`adjutant`) is a thin bash shim that delegates to `python -m adjutant`.

---

## Repo Map

```
adjutant/
├── adjutant                        # CLI shim — finds .venv/bin/python, exec python -m adjutant
├── adjutant.yaml.example           # Config template (adjutant.yaml is gitignored)
├── .env.example                    # Secrets template (.env is gitignored)
├── .opencode/agents/adjutant.md    # Main agent definition (tracked)
├── identity/                       # Soul/heart/registry — gitignored, personal
├── knowledge_bases/                # registry.yaml (gitignored) + nothing else tracked
├── templates/kb/                   # KB scaffold templates — tracked
├── prompts/                        # pulse.md, review.md, escalation.md — tracked
├── src/adjutant/
│   ├── cli.py                      # Click CLI — all commands live here
│   ├── __main__.py                 # python -m adjutant entrypoint
│   ├── core/                       # config, env, lockfiles, logging, model, opencode, paths, platform, process
│   ├── lib/                        # http, ndjson — shared utilities
│   ├── lifecycle/                  # control, cron, update
│   ├── observability/              # status, usage_estimate, journal_rotate
│   ├── capabilities/
│   │   ├── kb/                     # manage, query, run
│   │   ├── schedule/               # install, manage, notify_wrap
│   │   ├── screenshot/             # screenshot.py + playwright_screenshot.mjs
│   │   ├── search/                 # search.py
│   │   └── vision/                 # vision.py
│   ├── news/                       # fetch → analyze → briefing pipeline
│   ├── setup/                      # install, repair, uninstall, wizard
│   │   └── steps/                  # autonomy, features, identity, install_path, kb_wizard,
│   │                               #   messaging, prerequisites, schedule_wizard, service
│   └── messaging/
│       ├── adaptor.py, dispatch.py
│       └── telegram/               # chat, commands, listener, notify, photos, reply, send, service
├── tests/
│   └── unit/                       # ~52 test files, 1055 tests — pytest only
└── docs/
    ├── development/                # plugin-guide, adaptor-guide, testing, setup-wizard
    ├── architecture/               # overview, messaging, identity, state, design-decisions, autonomy
    └── guides/                     # getting-started, commands, knowledge-bases, configuration,
                                    #   schedules, autonomy, lifecycle
```

---

## Never Commit

These are gitignored and contain personal or runtime data:

- `identity/` — soul.md, heart.md, registry.md (personal; `.example` files are tracked)
- `state/` — all runtime mutable state
- `journal/`, `insights/`, `photos/`, `screenshots/`
- `.env` — secrets only (`.env.example` is tracked)
- `adjutant.yaml` — live config (`adjutant.yaml.example` is tracked)
- `knowledge_bases/registry.yaml` — live KB routing table

---

## Python Conventions

1. All source lives under `src/adjutant/` — no top-level modules
2. Imports: stdlib → third-party → local, each group alphabetical
3. Credentials: never read `.env` directly — use `get_credential(key)` from `core/env.py`
4. Paths: use `get_adj_dir()` from `core/paths.py`; never hardcode `~/.adjutant`
5. Logging: `adj_log("component", "message")` from `core/logging.py` — not `print()`
6. Return types: capability functions return a result string or raise; never print to stdout inside library code
7. Temp files: `tempfile.NamedTemporaryFile(delete=False)` + `finally: os.unlink(tmp)`
8. All new modules need a corresponding `tests/unit/test_<module>.py`

---

## Module Naming

| Module | Location | Purpose |
|--------|----------|---------|
| `cmd_*` | `messaging/telegram/commands.py` | Slash command handlers |
| `msg_*` | `messaging/adaptor.py` + telegram/ | Messaging interface (send, react, typing) |
| `adj_log` | `core/logging.py` | Structured log appender |
| `kb_*` | `capabilities/kb/manage.py` | Knowledge base CRUD |
| `wiz_*` | `setup/wizard.py` | Wizard UI helpers |
| `step_*` | `setup/steps/*.py` | Wizard setup steps |
| `_*` | anywhere | Private/internal — not part of public API |

---

## Adding a Capability

1. Create `src/adjutant/capabilities/<name>/<name>.py` — return a result string or raise
2. Add `cmd_<name>()` handler in `src/adjutant/messaging/telegram/commands.py`
3. Register in the dispatch table in `src/adjutant/messaging/dispatch.py`
4. Add the CLI command in `src/adjutant/cli.py`
5. Document in `.opencode/agents/adjutant.md` so the agent knows it exists
6. Add unit test at `tests/unit/test_<name>.py`
7. Add to `docs/guides/commands.md`

Full guide: `docs/development/plugin-guide.md`

---

## Adding a Slash Command

Register in `src/adjutant/messaging/dispatch.py` using the `if/elif` chain:

```python
elif text == "/mycommand":
    await cmd_mycommand("", message_id, adj_dir, bot_token=bot_token, chat_id=chat_id)
elif text.startswith("/mycommand "):
    await cmd_mycommand(text[len("/mycommand "):], message_id, adj_dir, bot_token=bot_token, chat_id=chat_id)
```

Handler shape in `commands.py` — handlers are `async`, `message_id` is `int`:

```python
async def cmd_mycommand(arg: str, message_id: int, adj_dir: Path, *, bot_token: str, chat_id: str) -> None:
    try:
        result = run_myfeature(adj_dir, arg)
        msg_send_text(result, message_id)
    except Exception as e:
        msg_send_text(f"Error: {e}", message_id)
```

For long-running commands, use `msg_typing_start()`/`msg_typing_stop()` and run in a background task.

---

## Knowledge Bases

A KB is a sandboxed OpenCode workspace in its own directory. The main Adjutant agent never reads KB files directly — it queries them via a sub-agent process.

**Query a KB:**
```python
from adjutant.capabilities.kb.query import kb_query
result = await kb_query("mybase", "What is the status?", adj_dir)
```

**Create a KB** (interactive wizard):
```bash
adjutant setup   # runs full wizard, including KB step
```

Or call directly:
```python
from adjutant.setup.steps.kb_wizard import kb_wizard_interactive
kb_wizard_interactive(adj_dir)
```

**Scaffold structure** (generated from `templates/kb/`):
```
<kb-path>/
├── kb.yaml                       # Metadata (name, description, model, access, cli_module)
├── .claude/agents/kb.md        # Sub-agent definition (rendered from template)
├── opencode.json               # Sandboxed permissions (external_directory: deny)
├── data/current.md               # Live status — sub-agent reads this first
├── docs/README.md                # KB orientation doc — what questions it can answer
├── knowledge/                    # Stable reference docs
├── history/                      # Archived records
├── state/                        # Runtime state (gitignored)
└── templates/                    # Reusable formats
```

**Template variables** replaced by `kb_scaffold()` in `manage.py`: `{{KB_NAME}}`, `{{KB_DESCRIPTION}}`, `{{KB_MODEL}}`, `{{KB_ACCESS}}`, `{{KB_WRITE_ENABLED}}`, `{{KB_CREATED}}`.

**KB registry** (`knowledge_bases/registry.yaml`) is the routing table. `kb_register()` appends to it; `kb_exists()` / `kb_get_field()` query it via pure-Python line-by-line YAML parsing (no `pyyaml` dependency).

**Access levels:** `read-only` KBs have `bash`, `edit`, and `write` denied in their workspace. `read-write` KBs have only `external_directory` denied — they can update their own `data/` files during a `/reflect`.

Full guide: `docs/guides/knowledge-bases.md`

---

## Agent Prompt

`.opencode/agents/adjutant.md` is the only agent definition that is tracked. Edit it when:
- A new capability needs to be surfaced to the agent
- Startup/routing behavior changes
- A new tool invocation pattern is added

`identity/soul.md`, `identity/heart.md`, `identity/registry.md` are **personal and gitignored** — never edit them programmatically or stage them.

---

## Testing

pytest only — no bats, no shell test infrastructure.

```bash
.venv/bin/pytest tests/unit/ -q        # full suite (~67s, 1055 tests)
.venv/bin/pytest tests/unit/test_kb_manage.py -q   # single file
```

All 1055 tests must pass before release. No CI — discipline-enforced.

Full guide: `docs/development/testing.md`

---

## Gotchas

- **`kb_list()` returns `KBEntry` objects**, not dicts — access via `.name`, `.description`, `.access` attributes
- **`kb_info()` and `kb_remove()` raise `ValueError`**, not `KBNotFoundError` — `KBNotFoundError` is only in `capabilities/kb/run.py`
- **`kb_quick_create()` takes `kb_path` as a plain `str`**, not `Path`
- **`schedule_get()` returns `None`** when not found — does not raise
- **`_resolve_command()` is private** in `schedule/manage.py` — used directly in CLI for `schedule run`
- **Playwright files** live in `src/adjutant/capabilities/screenshot/` — `screenshot.py` resolves them via `Path(__file__).parent`
- **`dispatch_photo` arg order** — check the signature before calling; it differs from `dispatch_message`
- **NDJSONResult vs OpenCodeResult** — `ndjson.py` returns `NDJSONResult`; `opencode.py` wraps it into `OpenCodeResult`; don't mix them up at call sites
- **`dispatch.py` auth + rate-limit block** — security-critical; don't refactor without running the full test suite first
