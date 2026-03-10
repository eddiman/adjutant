# Python Rewrite — Final Notes

**Branch:** `python-rewrite`  
**Started:** 2026-03-08  
**Completed:** 2026-03-10  
**Status: COMPLETE — all bash scripts migrated**

---

## Strategy

**Full rewrite (Option A).** Bash scripts are replaced one-to-one by Python
equivalents under `src/adjutant/`. Once a Python module is written and tested,
the bash original is deleted. No bridging layer. Migration followed a
bottom-up order: shared library modules first, then leaf capability scripts,
then orchestrators, then the live Telegram messaging core last.

---

## Final Architecture Map

### `src/adjutant/core/` — Shared library

| Module | Replaces | Purpose |
|---|---|---|
| `paths.py` | `scripts/common/paths.sh` | `ADJ_DIR` resolution; `setup_paths()` |
| `env.py` | `scripts/common/env.sh` | `get_credential()`, `require_telegram_credentials()`, `.env` parsing |
| `logging.py` | `scripts/common/logging.sh` | `adj_log(component, message)` — structured append to `adjutant.log` |
| `lockfiles.py` | `scripts/common/lockfiles.sh` | `set_killed/is_killed/check_killed`, `set_paused/clear_paused/is_paused`, `check_operational` |
| `platform.py` | `scripts/common/platform.sh` | `get_platform()`, `get_shell_config_file()`, `has_command()` |
| `opencode.py` | `scripts/common/opencode.sh` | `opencode_run()`, `opencode_reap()`, `OpenCodeResult`, `OpenCodeNotFoundError` |
| `config.py` | *(no bash original)* | `load_config()`, `load_typed_config()`, `AdjutantConfig` (pydantic) |
| `model.py` | *(no bash original)* | `resolve_kb_model()` — model name resolution for KB sub-agents |
| `process.py` | *(no bash original)* | `PidLock`, `kill_graceful()`, `kill_process_tree()`, `find_by_cmdline()`, `pid_is_alive()`, `read_pid_file()` |

### `src/adjutant/lib/` — Supporting libraries

| Module | Purpose |
|---|---|
| `http.py` | `get_client()` — httpx singleton used by all HTTP callers |
| `ndjson.py` | `parse_ndjson()`, `NDJSONResult(text, session_id, error_type, events)` |

### `src/adjutant/lifecycle/` — Lifecycle management

| Module | Replaces | Purpose |
|---|---|---|
| `cron.py` | `pulse_cron.sh`, `review_cron.sh` | `pulse_cron_entry()`, `review_cron_entry()` — crontab-invoked heartbeat runners |
| `update.py` | `update.sh` | `get_latest_version()`, `download_and_apply()`, `run_update()` — self-update via GitHub |
| `control.py` | `pause.sh`, `resume.sh`, `restart.sh`, `emergency_kill.sh`, `startup.sh` | `pause()`, `resume()`, `restart()`, `emergency_kill()`, `startup()` |

### `src/adjutant/observability/` — Status and monitoring

| Module | Replaces | Purpose |
|---|---|---|
| `journal_rotate.py` | `journal_rotate.sh` | `rotate_journal()` — delete journal files older than retention period |
| `status.py` | `status.sh` | `get_status()` — formatted multiline status report (state, jobs, heartbeat, log count) |
| `usage_estimate.py` | `usage_estimate.sh` | `get_usage_estimate()` — parse JSONL usage log, format session/weekly cap display |

### `src/adjutant/capabilities/kb/` — Knowledge base

| Module | Replaces | Purpose |
|---|---|---|
| `run.py` | `kb/run.sh` | `run_kb(name, prompt, adj_dir)` — spawn opencode sub-agent in KB workspace |
| `query.py` | `kb/query.sh` | `kb_query(name, question, adj_dir)` — high-level query wrapper |
| `manage.py` | `kb/manage.sh` | `kb_create()`, `kb_list()`, `kb_exists()`, `kb_count()`, `kb_get_field()`, `kb_register()`, `kb_scaffold()` |

### `src/adjutant/capabilities/schedule/` — Scheduled jobs

| Module | Replaces | Purpose |
|---|---|---|
| `manage.py` | `schedule/manage.sh` | `schedule_list()`, `schedule_get_field()`, `schedule_count()`, `schedule_exists()`, `schedule_set_enabled()` |
| `install.py` | `schedule/install.sh` | `install_all()` — reconcile crontab from `adjutant.yaml` schedules block |
| `notify_wrap.py` | `schedule/notify_wrap.sh` | `run_notify_wrap()` — run job + send Telegram notification; always exits 0 for cron |

### `src/adjutant/capabilities/screenshot/` — Screenshots

| Module | Replaces | Purpose |
|---|---|---|
| `screenshot.py` | `screenshot/screenshot.sh` | `take_and_send()` (alias `run_screenshot`) — Playwright screenshot → sendPhoto/sendDocument; calls `playwright_screenshot.mjs` via Node |

### `src/adjutant/capabilities/vision/` — Image analysis

| Module | Replaces | Purpose |
|---|---|---|
| `vision.py` | `vision/vision.sh` | `run_vision(image_path, prompt, adj_dir)` — opencode `--file` image analysis |

### `src/adjutant/capabilities/search/` — Web search

| Module | Replaces | Purpose |
|---|---|---|
| `search.py` | `search/search.sh` | `web_search()` (alias `run_search`) — Brave Search API → `OK:` / `ERROR:` result |

### `src/adjutant/news/` — News pipeline

| Module | Replaces | Purpose |
|---|---|---|
| `fetch.py` | `news/fetch.sh` | `fetch_news(adj_dir)` — HN/Reddit/blogs → `state/news_raw/<date>.json` |
| `analyze.py` | `news/analyze.sh` | `analyze_news(adj_dir)` — dedup + keyword filter + Haiku LLM ranking |
| `briefing.py` | `news/briefing.sh` | `run_briefing(adj_dir)` — orchestrator: fetch → analyze → format → notify → cleanup |

### `src/adjutant/setup/` — Installation and repair

| Module | Replaces | Purpose |
|---|---|---|
| `wizard.py` | `setup/wizard.sh` + `helpers.sh` | `wiz_*` UI primitives + `run_wizard()` top-level orchestrator; prompts 7 steps interactively |
| `install.py` | `setup/install.sh` | `run_install()` — prerequisite check, download, wizard invocation |
| `repair.py` | `setup/repair.sh` | `run_repair(adj_dir)` — health check + auto-fix |
| `uninstall.py` | `setup/uninstall.sh` | `run_uninstall(adj_dir)` — remove crontab, lockfiles, optional rm |

### `src/adjutant/setup/steps/` — Setup wizard steps

| Module | Replaces | Purpose |
|---|---|---|
| `prerequisites.py` | `steps/prerequisites.sh` | `step_prerequisites()` — check Python, bats, Node, npm, git |
| `install_path.py` | `steps/install_path.sh` | `step_install_path()` — confirm/choose install directory; returns `Path \| None` |
| `identity.py` | `steps/identity.sh` | `step_identity(adj_dir)` — LLM-generated soul.md + heart.md via wiz prompts |
| `messaging.py` | `steps/messaging.sh` | `step_messaging(adj_dir)` — Telegram bot token + chat ID; sets `WIZARD_TELEGRAM_ENABLED` |
| `features.py` | `steps/features.sh` | `step_features(adj_dir)` — enable/disable news, screenshot, vision, search in adjutant.yaml |
| `service.py` | `steps/service.sh` | `step_service(adj_dir)` — launchd/systemd + crontab + PATH alias |
| `autonomy.py` | `steps/autonomy.sh` | `step_autonomy(adj_dir)` — autonomous pulse/review enable + quiet hours |
| `schedule_wizard.py` | `steps/schedule_wizard.sh` | `run_schedule_wizard(adj_dir)` — interactive schedule creation UI |
| `kb_wizard.py` | `steps/kb_wizard.sh` | `run_kb_wizard(adj_dir)` — interactive KB creation UI |

### `src/adjutant/messaging/` — Messaging infrastructure

| Module | Replaces | Purpose |
|---|---|---|
| `adaptor.py` | `messaging/adaptor.sh` | `MessagingAdaptor` abstract base class: `send_text`, `send_photo`, `react`, `typing_start`, `typing_stop` |
| `dispatch.py` | `messaging/dispatch.sh` | `dispatch_message()`, `dispatch_photo()` — rate-limit (rolling 60s window), command routing, in-flight `asyncio.Task` cancellation |

### `src/adjutant/messaging/telegram/` — Telegram backend

| Module | Replaces | Purpose |
|---|---|---|
| `send.py` | `telegram/send.sh` | `msg_send_text()`, `msg_send_photo()`, `msg_react()`, `msg_typing_start()`, `msg_typing_stop()`, `msg_authorize()`, `TelegramSender` |
| `photos.py` | `telegram/photos.sh` | `tg_download_photo()`, `tg_handle_photo()`, dedup helpers |
| `chat.py` | `telegram/chat.sh` | `run_chat(message, adj_dir)` — opencode session continuity (2h timeout); `get_session_id/save_session/touch_session` |
| `commands.py` | `telegram/commands.sh` | 14 command handlers: `cmd_status/pause/resume/kill/pulse/restart/reflect_request/reflect_confirm/help/model/screenshot/search/kb/schedule` |
| `service.py` | `telegram/service.sh` | `listener_start/stop/restart/status()` — three-tier PID tracking (lockpid → pidfile → psutil) |
| `listener.py` | `telegram/listener.sh` | `main()` long-poll loop — single-instance `PidLock`, processes only LAST update per batch, routes to dispatch |
| `reply.py` | *(early migration)* | `send_reply(message, adj_dir)` — simple reply wrapper (4000 char limit) |
| `notify.py` | *(early migration)* | `send_notify(message, adj_dir)` — notification wrapper (4096 char limit) |

### `src/adjutant/cli.py` — CLI entrypoint

Click-based CLI: `adjutant {start,stop,restart,status,pulse,reflect,update,wizard,install,uninstall,repair}`.

---

## Test suite

**1055 tests, all passing** as of 2026-03-10.

```
tests/unit/
  test_briefing.py         test_capabilities_kb.py    test_capabilities_schedule.py
  test_chat.py             test_commands.py           test_config.py
  test_control.py          test_cron.py               test_dispatch.py
  test_env.py              test_features.py           test_fetch.py
  test_http.py             test_identity.py           test_install.py
  test_install_path.py     test_journal_rotate.py     test_kb_query.py
  test_kb_run.py           test_kb_wizard.py          test_listener.py
  test_lockfiles.py        test_logging.py            test_messaging_adaptor.py
  test_messaging_dispatch.py  test_model.py           test_ndjson.py
  test_notify.py           test_notify_wrap.py        test_opencode.py
  test_paths.py            test_platform.py           test_prerequisites.py
  test_process.py          test_reply.py              test_repair.py
  test_schedule_wizard.py  test_screenshot.py         test_search.py
  test_service.py          test_status.py             test_telegram_chat.py
  test_telegram_commands.py  test_telegram_listener.py  test_telegram_photos.py
  test_telegram_send.py    test_telegram_service.py   test_uninstall.py
  test_update.py           test_usage_estimate.py     test_vision.py
  test_wizard.py
```

Run with: `.venv/bin/pytest tests/unit/ -q`

---

## Inconsistencies found

Documented in full in `docs/reference/inconsistencies.md`.

| Date | Finding |
|---|---|
| 2026-03-09 | `reply.sh` clamps at 4000 chars; `notify.sh` at 4096. Both preserved faithfully. |
| 2026-03-09 | `wizard.sh` default model was stale `claude-sonnet-4-5`; Python wizard uses `claude-sonnet-4-6`. |
| 2026-03-09 | `notify.sh` does not set `parse_mode`; `reply.sh` does. Faithfully preserved. |

---

## Key decisions and gotchas

**Function-local imports everywhere in messaging.** `dispatch.py`, `commands.py`,
`chat.py`, `listener.py`, and `photos.py` all import their heavy dependencies
inside function bodies to avoid circular imports and defer loading. Tests must
patch at the **source module path** (`adjutant.core.opencode.opencode_run`, not
`adjutant.messaging.telegram.chat.opencode_run`).

**`run_screenshot` / `run_search` aliases.** `screenshot.py` exports
`take_and_send` as its primary function; `search.py` exports `web_search`.
Both have module-level aliases (`run_screenshot = take_and_send`,
`run_search = web_search`) for the command handlers in `commands.py` that
import by the alias name.

**`dispatch_photo` bug fixed.** Original `dispatch.py` passed `adj_dir` as the
4th positional argument to `tg_handle_photo()` when `caption` was expected.
Fixed: call now passes `caption` as 4th positional and `adj_dir` as keyword.

**`opencode_reap` is async in `commands.py`.** `_run_opencode_prompt()` calls
`await opencode_reap(adj_dir)` — but `opencode_reap` in `core/opencode.py` is
synchronous. `commands.py` wraps it in `asyncio.to_thread` if needed, or calls
it directly when already in a thread context. Tests must account for this.

**`listener.py` processes only the LAST update per batch.** Matches the
original bash behavior — intentional to avoid replay storms after a backlog.
Offset is advanced past ALL returned updates regardless.

**`service.py` three-tier PID tracking:** (1) `listener.lock/pid` written by
the listener itself; (2) `telegram.pid` written by the launcher; (3) psutil
`find_by_cmdline` for orphans. Priority in that order.

**`emergency_kill.py` disables crontab entirely** — backs up to
`state/crontab.backup`, then removes the crontab. `startup.py` restores from
backup on next start.

**`schedule/install.py` writes notify_wrap calls as `python3 <path>`** — the
installed crontab lines reference `src/adjutant/capabilities/schedule/notify_wrap.py`
directly.

**`send.py` typing implementation** uses `threading.Thread` + `threading.Event`,
stored in module-level `_TYPING_THREADS: dict[str, tuple[Thread, Event]]`.

**`wizard.py` step dispatch** dynamically imports `adjutant.setup.steps.<name>`
and calls `step_<name>(adj_dir)`. All steps accept `(adj_dir: Path, *, dry_run: bool = False) -> bool`
except `step_prerequisites()` (no adj_dir) and `step_install_path()` (returns `Path | None`).

**No CI.** Discipline-enforced. All 1055 tests must pass before any release.

---

## Git history (condensed)

| Commit | Description |
|---|---|
| `6958207` | Phase 1: foundation modules + tests |
| `5cbb97e` | Migrate 5 bash leaf scripts to Python; drop `tests_py/` |
| `305f7cf` | Add Python ignores to `.gitignore`; untrack `__pycache__` |
| `34fdd01` | Migrate 7 more bash scripts; add 162 tests; update CLI; drop 18 bash scripts |
| `b8e…` | Batch 2: Observability + Lifecycle; 784 tests |
| `…` | Batch 3: Capabilities (kb, schedule, screenshot, vision, search) |
| `…` | Batch 4: News pipeline |
| `…` | Batch 5: Setup steps (120 tests); 904 tests total |
| `8a4f694` | Batch 6: Messaging core (151 tests); 1055 tests total; all bash deleted |
