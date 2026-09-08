# Pause and Schedule Semantics

**Created**: 2026-07-15
**Status**: Implemented

---

## Issue 1: Pause did not fully silence scheduled work [x]

`adjutant pause` and `/pause` created `PAUSED`, but left Adjutant-managed cron entries installed. Scheduled jobs could still fire, and notification paths did not consistently honor the paused state.

**Fix:** Pause now removes only crontab lines marked `# adjutant:<name>`, preserving unrelated user entries. Cron execution, scheduled-job notification wrapping, and notification delivery also check `PAUSED` so stale invocations cannot produce autonomous work or notifications. Startup preserves the paused state instead of re-installing managed schedules.

**Files changed:**
- `src/adjutant/lifecycle/control.py` — pause removes managed cron entries; resume restores enabled entries
- `src/adjutant/lifecycle/cron.py` — paused cron runs and completion notifications are skipped
- `src/adjutant/capabilities/schedule/install.py` — managed-entry removal and paused installation guards
- `src/adjutant/capabilities/schedule/notify_wrap.py` — paused scheduled jobs do not run or notify
- `src/adjutant/messaging/telegram/notify.py` — autonomous notifications are suppressed while paused
- `src/adjutant/messaging/telegram/commands.py` — `/pause` and `/resume` use lifecycle control
- `tests/unit/test_control.py`, `test_cron.py`, `test_notify.py`, `test_notify_wrap.py`, `test_schedule_install.py` — pause/resume, stale cron, notification, and unrelated-crontab coverage

---

## Issue 2: CLI schedule mutations did not synchronize cron [x]

`adjutant schedule enable`, `disable`, and `remove` updated the registry but did not pass `adj_dir` to the schedule helpers. As a result, their messages claimed cron had changed even though no cron mutation occurred. Telegram schedule commands already passed `adj_dir` correctly.

**Fix:** CLI mutations now pass `adj_dir`, so enabling installs and disabling/removing removes the corresponding managed cron entry. When paused, enabling a job records `enabled: true` in the registry but defers installation until resume; CLI and Telegram messages state this explicitly. `schedule sync` also preserves the paused state.

**Files changed:**
- `src/adjutant/cli.py` — cron-aware schedule mutations and paused-state messages
- `src/adjutant/messaging/telegram/commands.py` — accurate paused schedule-enable message
- `tests/unit/test_cli.py` — CLI enable, disable, remove, sync, and paused-enable coverage

---

## Issue 3: Two apparent scheduling switches caused configuration drift [x]

Current docs, the configuration template, and setup wizard presented `heartbeat.enabled` as a master scheduling switch even though runtime scheduling was driven by `schedules[].enabled`.

**Fix:** Each schedule's `enabled` field is now documented as the runtime source of truth. The wizard no longer writes `heartbeat.enabled`, and current templates no longer include it. `heartbeat.enabled` remains accepted as a legacy compatibility field but has no runtime scheduling effect.

**Files changed:**
- `src/adjutant/setup/steps/autonomy.py` and `src/adjutant/setup/wizard.py` — no heartbeat scheduling switch write or state
- `adjutant.yaml.example` — removed stale heartbeat scheduling configuration
- `docs/guides/configuration.md`, `autonomy.md`, `schedules.md` — single scheduling source of truth
- `tests/unit/test_autonomy.py` — verifies the wizard only writes notification configuration

---

## Issue 4: Documentation and user-facing messages did not match runtime [x]

Lifecycle and command docs described pause as dropping all messages, while the intended contract permits manual status/resume control. Schedule commands also claimed cron installation while paused.

**Fix:** Updated lifecycle, autonomy, commands, schedules, configuration, troubleshooting, web, README, and developer guides to describe the silent-pause contract, KILLED precedence, managed-cron boundaries, manual-control availability, deferred schedule installation, and manual lockfile caveat.

**Files changed:**
- `README.md`
- `docs/architecture/autonomy.md`, `docs/architecture/state.md`
- `docs/development/plugin-guide.md`, `docs/development/setup-wizard.md`
- `docs/guides/autonomy.md`, `commands.md`, `configuration.md`, `lifecycle.md`, `schedules.md`, `troubleshooting.md`, `web.md`

---

## Verification

- Full Python suite: `1454 passed, 73 skipped`.
- Playwright runtime check: `OK:playwright available`.
- `git diff --check` passed.

## Commit Status

- Initial pause implementation: `d8d600c` (`fix: silence scheduled work while paused`) pushed to `main`.
- Schedule-source-of-truth, CLI synchronization, and documentation follow-up changes are included with this reference.

## Knowledge Base Check

All six registered knowledge bases were queried for records of these framework changes. None contained a matching record. This document is the repository reference for the plan and completed work.
