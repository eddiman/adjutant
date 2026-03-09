# Python Rewrite — Progress Notes

**Branch:** `python-rewrite`  
**Started:** 2026-03-08  
**Last updated:** 2026-03-09  

This document is the single authoritative record of what has been migrated,
what decisions were made, and what remains to do. The old plan documents
(`python-rewrite-plan.md`, `python-rewrite-plan-complete.md`) are superseded
by this file.

---

## Strategy

**Full rewrite (Option A).** Bash scripts are replaced one-to-one by Python
equivalents under `src/adjutant/`. Once a Python module is written and tested,
the bash original is deleted. No bridging layer.

The migration follows a bottom-up order: shared library modules first, then
leaf capability scripts, then orchestrators, then the live Telegram messaging
core last.

---

## Current state (as of 2026-03-09)

### Migrated and deleted ✅

| Bash original | Python replacement | Tests |
|---|---|---|
| `scripts/common/paths.sh` | `src/adjutant/core/paths.py` | `test_paths.py` |
| `scripts/common/env.sh` | `src/adjutant/core/env.py` | `test_env.py` |
| `scripts/common/logging.sh` | `src/adjutant/core/logging.py` | `test_logging.py` |
| `scripts/common/lockfiles.sh` | `src/adjutant/core/lockfiles.py` | `test_lockfiles.py` |
| `scripts/common/platform.sh` | `src/adjutant/core/platform.py` | `test_platform.py` |
| `scripts/common/opencode.sh` | `src/adjutant/core/opencode.py` | `test_opencode.py` |
| `scripts/lifecycle/pulse_cron.sh` | `src/adjutant/lifecycle/cron.py` | `test_cron.py` |
| `scripts/lifecycle/review_cron.sh` | `src/adjutant/lifecycle/cron.py` | `test_cron.py` |
| `scripts/lifecycle/update.sh` | `src/adjutant/lifecycle/update.py` | `test_update.py` |
| `scripts/messaging/telegram/reply.sh` | `src/adjutant/messaging/telegram/reply.py` | `test_reply.py` |
| `scripts/messaging/telegram/notify.sh` | `src/adjutant/messaging/telegram/notify.py` | `test_notify.py` |
| `scripts/capabilities/kb/run.sh` | `src/adjutant/capabilities/kb/run.py` | `test_kb_run.py` |
| `scripts/capabilities/kb/query.sh` | `src/adjutant/capabilities/kb/query.py` | `test_kb_query.py` |
| `scripts/observability/journal_rotate.sh` | `src/adjutant/observability/journal_rotate.py` | `test_journal_rotate.py` |
| `scripts/setup/wizard.sh` + `helpers.sh` | `src/adjutant/setup/wizard.py` | `test_wizard.py` |
| `scripts/setup/uninstall.sh` | `src/adjutant/setup/uninstall.py` | `test_uninstall.py` |
| `scripts/setup/steps/schedule_wizard.sh` | `src/adjutant/setup/steps/schedule_wizard.py` | `test_schedule_wizard.py` |
| `scripts/setup/steps/kb_wizard.sh` | `src/adjutant/setup/steps/kb_wizard.py` | `test_kb_wizard.py` |

### Supporting Python modules (no bash original)

| Module | Purpose |
|---|---|
| `src/adjutant/core/config.py` | Typed `AdjutantConfig` + dict API |
| `src/adjutant/core/model.py` | `resolve_kb_model()` |
| `src/adjutant/core/process.py` | Process management helpers |
| `src/adjutant/lib/http.py` | `get_client()` singleton (httpx) |
| `src/adjutant/lib/ndjson.py` | `parse_ndjson()` |
| `src/adjutant/cli.py` | Click-based CLI entrypoint |

### Test suite

**456 tests, all passing** as of 2026-03-09.

```
tests/unit/
  test_config.py         test_cron.py           test_env.py
  test_http.py           test_journal_rotate.py  test_kb_query.py
  test_kb_run.py         test_kb_wizard.py       test_lockfiles.py
  test_logging.py        test_model.py           test_ndjson.py
  test_notify.py         test_opencode.py        test_paths.py
  test_platform.py       test_process.py         test_reply.py
  test_schedule_wizard.py  test_uninstall.py     test_update.py
  test_wizard.py
```

Run with: `.venv/bin/pytest tests/unit/ -q`

---

## Remaining bash scripts (35 total)

### Observability (2)
- `scripts/observability/status.sh` — formatted status report (state, jobs, heartbeat, notify count)
- `scripts/observability/usage_estimate.sh` — JSONL usage log + session/weekly cap display

### Lifecycle (5)
- `scripts/lifecycle/pause.sh` — write PAUSED lockfile
- `scripts/lifecycle/resume.sh` — clear PAUSED lockfile
- `scripts/lifecycle/restart.sh` — stop + start all services
- `scripts/lifecycle/emergency_kill.sh` — nuclear shutdown, write KILLED, disable crontab
- `scripts/lifecycle/startup.sh` — start listener + opencode web, recover from KILLED

### News pipeline (3)
- `scripts/news/fetch.sh` — fetch from HN, Reddit, blogs → `state/news_raw/<date>.json`
- `scripts/news/analyze.sh` — deduplicate + keyword filter + Haiku LLM ranking
- `scripts/news/briefing.sh` — orchestrator: fetch → analyze → format → deliver → cleanup

### Capabilities (7)
- `scripts/capabilities/kb/manage.sh` — KB CRUD: create, register, scaffold, list, info, remove
- `scripts/capabilities/schedule/manage.sh` — scheduled job CRUD from adjutant.yaml
- `scripts/capabilities/schedule/install.sh` — crontab reconciler
- `scripts/capabilities/schedule/notify_wrap.sh` — run job + send Telegram notification
- `scripts/capabilities/screenshot/screenshot.sh` — Playwright screenshot → sendPhoto/sendDocument
- `scripts/capabilities/vision/vision.sh` — opencode `--file` image analysis
- `scripts/capabilities/search/search.sh` — Brave Search API → formatted results

### Messaging core (8) — most complex
- `scripts/messaging/adaptor.sh` — interface contract (no-op stubs)
- `scripts/messaging/dispatch.sh` — command router + rate limiter + chat fallback
- `scripts/messaging/telegram/listener.sh` — Telegram long-poll loop
- `scripts/messaging/telegram/commands.sh` — all `/command` handlers
- `scripts/messaging/telegram/chat.sh` — opencode session + conversation handler
- `scripts/messaging/telegram/send.sh` — msg_send_text, msg_send_photo, msg_react, msg_typing
- `scripts/messaging/telegram/photos.sh` — photo download + vision routing
- `scripts/messaging/telegram/service.sh` — start/stop/restart/status for the listener

### Setup (10)
- `scripts/setup/install.sh` — curl installer: prereq check + download + wizard
- `scripts/setup/repair.sh` — health check + auto-fix for existing installations
- `scripts/setup/helpers.sh` — (already replaced by `wizard.py` UI primitives — **delete only**)
- `scripts/setup/steps/prerequisites.sh` — Step 1: dependency check
- `scripts/setup/steps/install_path.sh` — Step 2: confirm/choose install directory
- `scripts/setup/steps/identity.sh` — Step 3: LLM-generated soul.md + heart.md
- `scripts/setup/steps/messaging.sh` — Step 4: Telegram bot token + chat ID
- `scripts/setup/steps/features.sh` — Step 5: enable/disable news, screenshot, vision, search
- `scripts/setup/steps/service.sh` — Step 6: launchd/systemd + crontab + PATH alias
- `scripts/setup/steps/autonomy.sh` — Step 7: autonomous pulse/review enable + quiet hours

---

## Inconsistencies found

Documented in `docs/reference/inconsistencies.md`.

| Date | Finding |
|---|---|
| 2026-03-09 | `reply.sh` clamps messages at 4000 chars; `notify.sh` at 4096. Both carried forward faithfully. |
| 2026-03-09 | `wizard.sh` default YAML had stale `claude-sonnet-4-5`; Python wizard uses `claude-sonnet-4-6`. |
| 2026-03-09 | `notify.sh` does not set `parse_mode`; `reply.sh` does. Faithfully preserved. |

---

## Key decisions

**No pydantic fallback.** The early `scripts_py/lib/config.py` had a metaclass-based pydantic
fallback for Python < 3.11 compatibility. The current `src/adjutant/core/config.py` requires
pydantic ≥ 2.0 (declared in `pyproject.toml`). Python ≥ 3.11 is required.

**Local imports for http client in `update.py`.** `get_client()` is imported inside
`get_latest_version()` and `download_and_apply()` rather than at module level. Tests
therefore patch `adjutant.lib.http.get_client`, not `adjutant.lifecycle.update.get_client`.

**`kb_wizard.py` catches `TypeError` from missing `--name`.** When `--quick` is given
without `--name`, `kb_quick_create()` receives a missing positional arg → `TypeError`.
The `main()` except block now catches `TypeError` alongside `ValueError` and `RuntimeError`.

**`_kb_create_simple()` over bash `kb_create`.** `kb_wizard.py` cannot call `manage.sh`
(bash). The pure-Python scaffold + registry-write path (`_kb_create_simple`) is used instead
of a bridge call.

**Messaging core migrated last.** The Telegram listener is the live runtime — migrating it
last minimises disruption risk. All other scripts can be migrated and tested independently.

---

## Migration order (remaining)

1. Observability: `status.py`, `usage_estimate.py`
2. Lifecycle: `pause.py`, `resume.py`, `restart.py`, `emergency_kill.py`, `startup.py`
3. Capabilities: `kb/manage.py`, `schedule/manage.py`, `schedule/install.py`,
   `schedule/notify_wrap.py`, `screenshot/screenshot.py`, `vision/vision.py`,
   `search/search.py`
4. News: `fetch.py`, `analyze.py`, `briefing.py`
5. Setup steps: `prerequisites.py`, `install_path.py`, `identity.py`, `messaging.py`,
   `features.py`, `service.py`, `autonomy.py`; plus `install.py`, `repair.py`
6. Messaging core: `send.py`, `photos.py`, `commands.py`, `dispatch.py`,
   `chat.py`, `service.py` (listener service), `listener.py`

---

## Git history

| Commit | Description |
|---|---|
| `6958207` | Phase 1: foundation modules + tests |
| `5cbb97e` | Migrate 5 bash leaf scripts to Python; drop `tests_py/` |
| `305f7cf` | Add Python ignores to `.gitignore`; untrack `__pycache__` |
| `34fdd01` | Migrate 7 more bash scripts; add 162 tests; update CLI; drop 18 bash scripts |
