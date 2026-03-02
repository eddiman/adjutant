# Changelog

All notable changes to this project will be documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
