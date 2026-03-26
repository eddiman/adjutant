# Contributing

## Development setup

```bash
git clone https://github.com/eddiman/adjutant.git
cd adjutant
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

## Dev commands

```bash
.venv/bin/pytest tests/ -q              # run tests
.venv/bin/mypy src/adjutant/ --strict   # type check
.venv/bin/ruff check src/ tests/        # lint
```

## Code conventions

- **LLM calls**: `get_backend().run()` — never call backends directly.
- **Imports**: stdlib, then third-party, then local, alphabetical within each group.
- **Logging**: `adj_log("component", "msg")` — no `print()`.
- **Paths**: `get_adj_dir()` — never hardcode.
- **Capabilities**: return string or raise, no stdout.
- **Tests**: every module gets `tests/unit/test_<module>.py`.

## Project structure

```
src/adjutant/
├── cli.py                 # CLI dispatcher (Click)
├── core/                  # Backend protocol, config, env, logging, paths
├── lib/                   # HTTP client, NDJSON/JSON parsers
├── lifecycle/             # Pause/resume/restart, cron jobs, self-update
├── capabilities/          # KB, memory, schedule, screenshot, search, vision
├── messaging/             # Dispatch + Telegram adaptor
├── news/                  # News fetch, analyze, briefing pipeline
├── observability/         # Journal rotation, status, usage tracking
└── setup/                 # Setup wizard, install, repair, uninstall
```

See [Architecture Overview](../architecture/overview.md) for detailed diagrams and the [Backend Guide](backend-guide.md) for working with the LLM abstraction.

## Adding a new capability

Follow the [Plugin Guide](plugin-guide.md) for step-by-step instructions on adding capability modules.

## Adding a new messaging backend

Follow the [Adaptor Guide](adaptor-guide.md) to implement a new messaging channel (Slack, Discord, CLI, etc.).
