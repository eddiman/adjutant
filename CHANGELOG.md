# Changelog

All notable changes to this project will be documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased] — Post-0.1.0 Hardening

Comprehensive code quality, type safety, and security hardening pass driven by full deployment readiness audit.

### Added

- **Active operation tracking** — pulse and review write `state/active_operation.json` while running, allowing external clients to observe operation state without holding open connections. Staleness detection auto-cleans markers older than 30 minutes with dead PIDs. (`core/lockfiles.py`, `lifecycle/cron.py`)
- **Post-completion notifications** — after a successful pulse or review, a Telegram notification is sent with a summary of KBs checked, issues found, and escalation status. Budget-guarded, best-effort. (`lifecycle/cron.py`)
- Active operation markers for Telegram `/pulse` and `/reflect` → `/confirm` paths (`messaging/telegram/commands.py`)

### Changed

- `lifecycle/cron.py`: replaced `os.execvp` with `subprocess.run` so Python keeps control for marker management and notification dispatch. Exit code propagated via `sys.exit()`. New `action` and `source` kwargs on `run_cron_prompt()`, `pulse_cron()`, `review_cron()`.

### Security

- Feature gate in dispatch now fails closed — rejects gated commands when config is unparseable
- Installer Python version check corrected from `>=3.9` to `>=3.11` to match `pyproject.toml`

### Fixed

- 4 real type bugs: `Path` passed as `int` in search command, `str`/`int` mismatch in listener watchdog, `Path`/`str` variable shadow in self-updater, nonexistent `cwd` kwarg in identity setup
- Wrong function names in repair module (`get_status` → `listener_status`, `start_service` → `listener_start`)
- Wrong argument types in KB wizard (`str` where `Path` expected)

### Improved

- **mypy --strict: 51 → 0 errors** — full type annotations across all 72 source files
- **ruff: 0 critical errors** — 24 unused imports removed, 23 line-length violations fixed, import sorting, `Optional[X]` → `X | None` modernization
- Removed dead `feedparser` optional dependency (declared but never imported)
- Removed 5 vestigial `main_*` CLI wrappers from `lifecycle/control.py`
- Renamed `_resolve_command` → `resolve_command` (was private but imported publicly in CLI)
- Refactored `control.py` to delegate PID/process operations to `core/process.py` (eliminated `pgrep` subprocess duplication)
- Annotated 36 silent exception swallows with `# noqa: BLE001` and rationale comments
- Added stderr fallback to `_adj_log` when logging infrastructure itself fails
- Fixed ambiguous variable names (`l` → `line`/`entry` in list comprehensions)

### Tests

- 1,289 tests passing (up from 1,257)
- 3 new tests for fail-closed feature gate behavior
- 12 new tests for active operation tracking (`test_lockfiles.py`)
- 12 new tests for cron notification and marker lifecycle (`test_cron.py`)

### Docs

- Updated deployment readiness evaluation prompt to reflect Python architecture
- Generated full deployment readiness assessment (`docs/reference/2026-03-16-deployment-readiness.md`)

---

## [0.1.0] — 2026-03-16 — Python Rewrite

Complete rewrite from bash to Python. New architecture, new capabilities, comprehensive test suite.

### Framework

- Full Python rewrite — all bash scripts replaced with `src/adjutant/` Python modules
- Hatchling build system, Python >=3.11, CLI via Click (`adjutant` entrypoint)
- Listener → dispatch → adaptor pipeline with full backend abstraction
- Pydantic-based configuration with typed models
- Structured logging via `adj_log()`
- `HttpClient` wrapper around httpx for all HTTP calls
- NDJSON result parsing for Claude sub-agent output

### Messaging

- Telegram adaptor: `send.py`, `listener.py`, `photos.py`, `commands.py`, `chat.py`, `notify.py`
- Backend-agnostic command dispatcher with sliding-window rate limiting
- Feature-gated commands (`/screenshot`, `/search`) rejected at dispatch if disabled in config
- Listener processes all updates in each poll batch sequentially — no dropped messages
- Natural language chat via Claude agent with in-flight job supersession

### Capabilities

- **Knowledge bases** — sandboxed sub-agent workspaces (create, list, remove, info, query, write, run)
- **Screenshots** — Playwright screenshot with auto cookie-banner dismissal + vision caption
- **Vision** — LLM vision analysis of image files
- **Search** — web search via SearXNG
- **Scheduling** — cron-based job scheduling with KB operation support
- **News** — fetch → analyze → briefing pipeline with configurable feeds

### Autonomy

- Scheduled autonomous pulse checks query all registered KBs on a configurable cron schedule
- Daily review synthesizes pulse findings and sends Telegram notifications for significant insights
- Machine-readable action ledger (`state/actions.jsonl`)
- Hard notification budget counter — date-scoped, independent of LLM
- Dry-run mode in all autonomous prompts

### Memory

- Persistent long-term memory system — remember, recall, forget, digest
- Auto-classification of facts and patterns
- Memory digest for periodic consolidation

### Lifecycle

- Start, stop, restart, pause, resume, kill — full process lifecycle
- Self-update from GitHub releases with semver compare, backup, and SHA256 checksum verification
- Detached restart with proper `ADJUTANT_HOME` and cwd propagation
- Symlink-safe CLI shim

### Setup

- Interactive setup wizard with modular steps (identity, credentials, features, autonomy, service)
- Curl-style installer (`src/adjutant/setup/install.py`) — prereq check, download, extract, wizard
- Repair command for fixing broken installations
- macOS launchd service integration

### CLI

- `adjutant` entrypoint with subcommands: `start`, `stop`, `restart`, `update`, `status`, `pause`, `resume`, `kill`, `notify`, `screenshot`, `search`, `news`, `rotate`, `kb`, `schedule`, `logs`, `doctor`, `setup`, `repair`, `uninstall`, `help`

### Identity

- Three-layer identity: `soul.md` (stable values), `heart.md` (personality), `registry.md` (operational facts)
- All identity files are user-specific and gitignored; example templates provided

### Testing

- ~1160 tests across ~54 unit test files and integration tests
- Covers CLI, dispatch, all capabilities, lifecycle, setup, messaging, and config

### Security

- Prompt injection guard in agent system prompt, pulse, review, and escalation prompts
- Sender authorization via `msg_authorize()` hook
- Rate limiting: sliding-window counter, configurable via `adjutant.yaml`
- Credential isolation: `.env` never sourced directly; credentials extracted by key
- SHA256 checksum verification for downloaded release tarballs

### Release Infrastructure

- `.github/workflows/release.yml` — tag-triggered release workflow with tarball + checksum
- `VERSION` file as source of truth
- Docusaurus documentation site (`adjutant-docs`)

---

## [0.0.2] — 2026-03-02

### Fixed

- `install.sh`: refactored `resolve_version()` and `prompt_install_dir()` to use global variables instead of subshell capture, eliminating stdout pollution that corrupted the download URL
- `install.sh` / `update.sh`: corrected download URL from `api.github.com` to `github.com` releases endpoint
- Wizard: added top-level Telegram skip prompt in Step 4; answering `n` disables messaging setup entirely and sets `WIZARD_TELEGRAM_ENABLED=false`
- Wizard: screenshot and vision features now auto-disabled (with explanation) when Telegram setup is skipped
- Wizard: added inline loading indicator before slow `npx playwright --version` check in Step 1
- Wizard dry-run: all prompt helpers now accept real user input in dry-run mode (previously auto-accepted defaults)
- Wizard: added news source configuration instructions shown immediately after enabling the news briefing feature
- `startup.sh`: added post-startup PID sync block to recover missing lock/PID files after listener restarts

---

## [0.0.1] — 2026-02-28

Initial release. Bash-based framework with Telegram messaging, knowledge base sub-agents, and basic lifecycle management.
