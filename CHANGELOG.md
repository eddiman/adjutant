# Changelog

All notable changes to this project will be documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [2.0.2] — 2026-03-15 — Architecture Hardening

Addresses all 7 remaining issues from the codebase audit.

### Fixed

- **listener.py**: now processes ALL updates in each poll batch sequentially instead of only the last one — no more silently dropped messages
- **emergency_kill** pattern match scoped to this Adjutant instance (from previous round)

### Security

- **update.py**: SHA256 checksum verification for downloaded release tarballs; gracefully skips when no `.sha256` file is published
- **release.yml**: generates and publishes `adjutant-{version}.tar.gz.sha256` alongside tarball

### Changed

- **reply.py**: removed — dead code superseded by `send.py`'s `msg_send_text()`
- **send.py**: extracted `sanitize_message(msg, max_len)` as the canonical sanitisation function; `notify.py` now imports it instead of maintaining a duplicate
- **kb/run.py**: `_get_kb()` now delegates to `manage.py`'s `kb_info()` instead of maintaining a duplicate registry parser; `_load_registry()` removed from run.py
- **install.py**: colour/TTY helpers (`_IS_TTY`, `_c()`, `_BOLD`, etc.) replaced with imports from `wizard.py` for NO_COLOR compliance
- **repair.py** and **messaging.py**: `_read_env_cred()` now delegates to `core/env.py`'s `get_credential()` instead of maintaining inline parsers
- **wizard.py**: added `WizardContext` dataclass for shared state; orchestrator now passes `dry_run` to all steps (was missing before); syncs step globals into context
- **config.py**: added `window_seconds` to `TelegramRateLimitConfig` and `chat_timeout_seconds` to `TelegramConfig`
- **chat.py**: chat timeout now reads from `adjutant.yaml` (`messaging.telegram.chat_timeout_seconds`)
- **dispatch.py**: rate limit window now reads from config (`messaging.telegram.rate_limit.window_seconds`)

### Added

- **test_cli.py**: smoke tests for all 22 CLI commands and 13 subcommands via Click's `CliRunner`

---

## [2.0.1] — 2026-03-15 — Codebase Audit & Bug Fixes

Full codebase audit identifying and fixing 16 issues across bugs, security,
technical debt, and documentation.

### Fixed

- **update.py**: `get_latest_version()` called `follow_redirects`, `.raise_for_status()`, and `.json()` on a dict return from `HttpClient.get()` — entire self-update mechanism was broken
- **update.py**: `download_and_apply()` used `client.stream()` which does not exist on `HttpClient` — replaced with direct `httpx.Client` streaming
- **update.py**: `_warn_if_listener_running()` and `_run_doctor()` referenced legacy bash scripts — now use Python service module and `sys.executable`
- **search.py**: manual `quote(query)` combined with httpx's automatic param encoding caused double-encoding (`%2520` for spaces)
- **reply.py**: used `json=` instead of `json_data=` for `HttpClient.post()`, then called `.raise_for_status()` on the dict return
- **notify.py**: daily notification budget counter incremented even when Telegram API returned `{"ok": false}` — now verifies response before counting
- **commands.py**: `/schedule run` only handled script-based jobs, ignoring KB-operation-backed jobs — now delegates to `install.run_now()` which handles both
- **control.py**: `emergency_kill` killed ALL processes matching "opencode" system-wide — now scoped to this Adjutant instance's ADJ_DIR
- **chat.py**: session timeout was hardcoded to 7200s despite config field existing — now reads `messaging.telegram.session_timeout_seconds` from config
- **http.py**: `get()` did not catch `json.JSONDecodeError` for non-JSON responses — now raises `HttpClientError` with response preview
- **lifecycle.md**: contradicted itself about `adjutant start` behaviour with KILLED lockfile
- **configuration.md**: YAML indentation error made `llm:` appear nested under `messaging:`
- **VERSION**: was `0.0.2`, now `2.0.0` to match `pyproject.toml` and `cli.py`

### Security

- Added prompt injection guard to `pulse.md` and `review.md` (was only in `escalation.md`)

### Changed

- **prompts**: all bash script references (`scripts/capabilities/kb/query.sh`, `scripts/messaging/telegram/notify.sh`) updated to Python CLI equivalents (`.venv/bin/python -m adjutant kb query`, `.venv/bin/python -m adjutant notify`)
- **install.py**: `_resolve_command()` and `_resolve_path()` now delegate to `manage.py` canonical implementations instead of maintaining duplicates
- **http.py**: removed unused `import json` and false urllib-fallback docstring
- **docs**: corrected `.Claude/agents/adjutant.md` references to `.opencode/agents/adjutant.md` in README, overview, identity, and plugin-guide docs

---

## [0.1.0] — Autonomy & Self-Agency

### Added

- Scheduled autonomous pulse checks query all registered KBs on a configurable cron schedule (`autonomy.pulse_schedule`)
- Daily review synthesizes pulse findings and sends Telegram notifications for significant insights (`autonomy.review_schedule`)
- Machine-readable action ledger (`state/actions.jsonl`) — one JSONL record per autonomous cycle or notification sent
- Hard notification budget counter in `notify.sh` — date-scoped counter file enforces `notifications.max_per_day` at script layer, independent of LLM
- Dry-run mode enforced in all three autonomous prompts: `pulse.md`, `review.md`, `escalation.md` — no side effects, `[DRY RUN]` journal prefix, `actions.jsonl` records `"dry_run":true`
- `autonomy:` section added to `adjutant.yaml.example` with `enabled`, `pulse_schedule`, `review_schedule`
- Wizard Step 7: guided autonomy configuration (pulse cadence, review schedule, notification budget, quiet hours, cron install)
- Wizard completion now offers to create a knowledge base immediately after setup
- Wizard step counter updated to 7 across all step files (was 6)
- `/status` now surfaces last heartbeat type/timestamp, today's notification count vs. budget, and last 5 action ledger entries
- `/status` cron job detection now recognizes `prompts/pulse.md` and `prompts/review.md` job types
- News briefing cron schedule now read from `adjutant.yaml features.news.schedule` instead of hardcoded `"0 8 * * 1-5"`
- `docs/guides/autonomy.md` — user guide covering enabling, cadence, budget, ledger, pause/resume, dry-run, status output
- `docs/architecture/autonomy.md` — architecture reference covering control flow, kill-switch hierarchy, data flow, isolation guarantees, budget enforcement, ledger schema

### Fixed

- `scripts/capabilities/kb/manage.sh`: `kb_scaffold` used `ls *.md` glob in a `set -e` context, causing silent exit 1 when `docs/` was empty; replaced with `find -name '*.md'` (fixes integration tests `kb quick-create scaffolds and registers` and `kb quick-create with custom model and access`)

---

## [0.0.2] — 2026-03-02

### Fixed

- `install.sh`: refactored `resolve_version()` and `prompt_install_dir()` to use global variables instead of subshell capture, eliminating stdout pollution that corrupted the download URL
- `install.sh` / `update.sh`: corrected download URL from `api.github.com` to `github.com` releases endpoint
- Wizard: added top-level Telegram skip prompt in Step 4; answering `n` disables messaging setup entirely and sets `WIZARD_TELEGRAM_ENABLED=false`
- Wizard: screenshot and vision features now auto-disabled (with explanation) when Telegram setup is skipped
- Wizard: added inline loading indicator before slow `npx playwright --version` check in Step 1
- Wizard dry-run: all prompt helpers (`wiz_confirm`, `wiz_input`, `wiz_choose`, `wiz_multiline`, `wiz_secret`) now accept real user input in dry-run mode (previously auto-accepted defaults)
- Wizard: added news source configuration instructions shown immediately after enabling the news briefing feature
- `startup.sh`: added post-startup PID sync block to recover missing lock/PID files after listener restarts

---

## [1.0.0] — 2026-03-01

Initial public release.

### Framework

- Listener → dispatch → adaptor pipeline with full backend abstraction
- `scripts/messaging/adaptor.sh` — 8-function interface contract (4 required, 4 optional)
- `scripts/messaging/dispatch.sh` — backend-agnostic command dispatcher with sliding-window rate limiting
- Telegram adaptor: `send.sh`, `listener.sh`, `photos.sh`, `commands.sh`, `chat.sh`, `notify.sh`
- Slash commands: `/status`, `/pause`, `/resume`, `/kill`, `/restart`, `/pulse`, `/reflect`, `/screenshot`, `/kb`, `/model`, `/help`
- Natural language chat via OpenCode agent with in-flight job supersession

### Common Utilities (`scripts/common/`)

- `paths.sh` — `ADJ_DIR` resolution with `.adjutant-root` marker; walk-up with legacy `adjutant.yaml` fallback
- `env.sh` — credential loading via grep-based extraction (never sources `.env` directly)
- `lockfiles.sh` — `KILLED`/`PAUSED` state machine with boolean query functions
- `logging.sh` — structured log writer to `state/adjutant.log`
- `opencode.sh` — `opencode_run` wrapper that cleans up orphaned `bash-language-server` children; periodic `opencode_reap`
- `platform.sh` — OS/architecture detection helpers

### Capabilities

- `scripts/capabilities/screenshot/` — Playwright screenshot with auto cookie-banner dismissal + vision caption
- `scripts/capabilities/vision/` — LLM vision analysis of image files
- `scripts/capabilities/kb/` — Knowledge base sub-agent system (create, list, remove, info, query)
- `scripts/news/` — Scheduled news briefing with configurable feeds

### Lifecycle

- `scripts/lifecycle/startup.sh` — full startup / KILLED recovery
- `scripts/lifecycle/restart.sh` — graceful restart
- `scripts/lifecycle/pause.sh` / `resume.sh` — soft pause without killing listener
- `scripts/lifecycle/emergency_kill.sh` — hard stop via KILLED lockfile
- `scripts/lifecycle/update.sh` — self-update from GitHub release with semver compare and backup

### Setup

- `scripts/setup/wizard.sh` — interactive first-run setup (identity, credentials, KB)
- `scripts/setup/steps/` — modular wizard steps

### CLI

- `adjutant` entrypoint dispatching all subcommands: `start`, `stop`, `restart`, `update`, `status`, `pause`, `resume`, `kill`, `startup`, `notify`, `screenshot`, `news`, `rotate`, `kb`, `logs`, `doctor`, `setup`, `help`

### Identity Model

- Three-layer identity: `soul.md` (stable values), `heart.md` (personality), `registry.md` (operational facts)
- All identity files are user-specific and gitignored; example templates provided

### Release Infrastructure

- `scripts/setup/install.sh` — curl installer (prereq check → prompt install dir → download → extract → wizard)
- `VERSION` — `1.0.0`
- `.github/workflows/release.yml` — tag-triggered release workflow; tarball excludes personal files

### Security

- Prompt injection guard in agent system prompt
- Sender authorization via `msg_authorize()` hook
- Rate limiting: sliding-window counter (default 10 msg/min), configurable via `adjutant.yaml`
- Credential isolation: `.env` never sourced directly; credentials extracted by key
- `SECURITY_ASSESSMENT.md` documents threat model and open items
