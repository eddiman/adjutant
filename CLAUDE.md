# CLAUDE.md

## Hard Rules
1. **NEVER read KB files directly.** Query via CLI: `.venv/bin/python -m adjutant kb query <name> "<question>"`.
2. **NEVER read `.env` directly.** Use `get_credential()` from `core/env.py`.
3. **NEVER commit** gitignored files: `identity/`, `state/`, `journal/`, `insights/`, `photos/`, `screenshots/`, `.env`, `adjutant.yaml`, `knowledge_bases/registry.yaml`.

## Dev Commands
```bash
.venv/bin/pytest tests/ -q              # tests
.venv/bin/mypy src/adjutant/ --strict   # type check
.venv/bin/ruff check src/ tests/        # lint
```

## Key Patterns
- LLM calls: `get_backend().run()` — never call backends directly.
- Imports: stdlib → third-party → local, alphabetical.
- Logging: `adj_log("component", "msg")` — no `print()`.
- Paths: `get_adj_dir()` — never hardcode.
- Capabilities: return string or raise, no stdout.
- Tests: every module gets `tests/unit/test_<module>.py`.
