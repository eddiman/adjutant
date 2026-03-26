# CLAUDE.md — Claude Code CLI Instructions

Instructions for Claude Code CLI when working interactively on this project.

---

## Project

Adjutant is a Python-based persistent personal agent framework. It receives messages via Telegram, queries sandboxed KB sub-agents, and orchestrates lifecycle/heartbeat logic.

**CLI entrypoint:** `adjutant` (bash shim -> `python -m adjutant`)

---

## Hard Rules

1. **NEVER read KB files directly.** Always query via CLI: `.venv/bin/python -m adjutant kb query <name> "<question>"`. No Read, Glob, Grep, `cat`, or `ls` on any KB path.
2. **NEVER read `.env` directly.** Credentials are loaded via `get_credential()` from `core/env.py`.
3. **NEVER commit** gitignored files: `identity/`, `state/`, `journal/`, `insights/`, `photos/`, `screenshots/`, `.env`, `adjutant.yaml`, `knowledge_bases/registry.yaml`.

---

## Development

```bash
# Run tests
.venv/bin/pytest tests/ -q

# Run a single test file
.venv/bin/pytest tests/unit/test_backend.py -q

# Type check
.venv/bin/mypy src/adjutant/ --strict

# Lint
.venv/bin/ruff check src/ tests/
```

---

## Architecture

```
src/adjutant/
├── cli.py                      # Click CLI (~40 subcommands)
├── core/
│   ├── backend.py              # LLMBackend protocol, LLMResult, get_backend()
│   ├── backend_opencode.py     # OpenCode backend implementation
│   ├── backend_claude_cli.py   # Claude CLI backend implementation
│   ├── config.py               # YAML config + typed models
│   ├── env.py                  # .env credential extraction
│   ├── opencode.py             # Low-level opencode process management
│   ├── model.py                # Model tier resolution
│   └── ...
├── lib/
│   ├── ndjson.py               # OpenCode NDJSON parser
│   └── claude_json.py          # Claude Code JSON parser
├── lifecycle/                  # control, cron, update
├── capabilities/               # kb, schedule, screenshot, search, vision, memory
├── news/                       # fetch, analyze, briefing
├── setup/                      # install, repair, uninstall, wizard
└── messaging/                  # adaptor, dispatch, telegram/
```

---

## Key Patterns

- **Backend abstraction:** All LLM calls go through `get_backend().run()`. Never call `opencode_run()` or `claude` directly from call sites.
- **Imports:** stdlib -> third-party -> local, alphabetical within groups.
- **Logging:** `adj_log("component", "message")` — not `print()`.
- **Paths:** `get_adj_dir()` from `core/paths.py` — never hardcode paths.
- **Capabilities:** Return a result string or raise. Never print to stdout.
- **Tests:** Every new module needs `tests/unit/test_<module>.py`.

---

## Backend-Specific Notes

When this project uses `claude-cli` as its backend, YOU are the LLM backend. The hooks in `.claude/hooks/` apply to your tool calls:

- `block-env-access.sh` — blocks Bash commands that read `.env`
- `block-env-read.sh` — blocks Read tool on `.env` files

These hooks are intentional security measures. Do not circumvent them.
