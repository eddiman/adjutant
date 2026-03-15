# Phase 8 — Scheduling Plugin System

**Status**: Complete — originally designed for bash, re-implemented in Python during the rewrite.

## Goal

Replace the hardcoded, per-job crontab installation pattern with a generic scheduling plugin system. Users can register any scheduled job (Adjutant-internal or external, e.g. a KB fetch script) by adding an entry to `adjutant.yaml schedules:` or running `adjutant schedule add`. No Adjutant repo edits required for new jobs.

---

> **Note (2026-03-15):** This document was written for the bash-era architecture. The
> scheduling system was re-implemented in Python as part of the full rewrite (PR #1,
> `f3f7d88`). All bash script references below (`scripts/capabilities/schedule/manage.sh`,
> etc.) now correspond to Python modules under `src/adjutant/capabilities/schedule/`. The
> design decisions, schema, and CLI interface remain identical. See the mapping below.
>
> | Bash (this doc) | Python (actual) |
> |-----------------|-----------------|
> | `scripts/capabilities/schedule/manage.sh` | `src/adjutant/capabilities/schedule/manage.py` |
> | `scripts/capabilities/schedule/install.sh` | `src/adjutant/capabilities/schedule/install.py` |
> | `scripts/setup/steps/schedule_wizard.sh` | `src/adjutant/setup/steps/schedule_wizard.py` |
> | `scripts/lifecycle/pulse_cron.sh` | `src/adjutant/capabilities/schedule/notify_wrap.py` |
> | `scripts/lifecycle/review_cron.sh` | `src/adjutant/capabilities/schedule/notify_wrap.py` |
> | `adjutant schedule` CLI | `src/adjutant/cli.py` (Click subcommands) |

## Background

### What existed before this phase

- Cron jobs were installed directly into the system crontab by the setup wizard (`service.sh`, `autonomy.sh`), one hardcoded helper per job type.
- `status.sh` identified jobs by hardcoded name patterns (`news_briefing.sh`, `prompts/pulse.md`, `prompts/review.md`). Any other job showed as "Unknown Job".
- `emergency_kill.sh` killed processes by a hardcoded list of script names.
- `autonomy.sh` installed pulse/review cron entries as raw `opencode run --print` inline commands, with no wrapper scripts.
- There was no registry of scheduled jobs — raw crontab was the only source of truth.
- Adding a new recurring job required editing `service.sh`, `status.sh`, `emergency_kill.sh`, and the CLI.

### Design decisions

| Decision | Rationale |
|---|---|
| Registry lives in `adjutant.yaml schedules:` | Consistent with `features:` and `autonomy:` patterns. Single config file. |
| Executor model: script path | Works for both internal and external scripts. Consistent, auditable, no arbitrary shell injection. |
| `status.sh` reads registry, not crontab | Crontab is an implementation detail. Status is accurate even during recovery. |
| Creation via interactive CLI wizard | Multi-field job creation is awkward over Telegram. CLI wizard is friendlier and scriptable. |
| No `/schedule add` via Telegram | See above. `/schedule list`, `run`, `enable`, `disable` are sufficient for runtime management. |
| Pulse/review use thin wrapper scripts | `opencode run --print` inline commands in crontab are hard to manage and kill by name. Wrappers normalize them into the script-path model. |
| `autonomy.pulse_schedule` / `autonomy.review_schedule` removed | All schedule config lives in `schedules:`. `autonomy:` retains only `enabled:`. |
| `features.news.schedule` removed | Same reason. `features.news:` retains `enabled:` and `config_path:` only. |
| Crontab marker: `# adjutant:<name>` | Name-scoped, backwards-compatible (still contains `.adjutant`). Enables per-job install/uninstall without touching other entries. |

---

## Schema

### `adjutant.yaml schedules:` block

New top-level section. Each entry is a named scheduled job:

```yaml
schedules:
  - name: "news_briefing"
    description: "Daily AI news digest"
    schedule: "0 8 * * 1-5"          # standard crontab syntax
    script: "scripts/news/briefing.sh"  # relative to ADJ_DIR, or absolute path
    log: "state/news_briefing.log"    # relative to ADJ_DIR, or absolute path
    enabled: true

  - name: "autonomous_pulse"
    description: "Scheduled autonomous pulse check"
    schedule: "0 9,17 * * 1-5"
    script: "scripts/lifecycle/pulse_cron.sh"
    log: "state/pulse.log"
    enabled: false

  - name: "autonomous_review"
    description: "End-of-day review"
    schedule: "0 20 * * 1-5"
    script: "scripts/lifecycle/review_cron.sh"
    log: "state/review.log"
    enabled: false

  # KB-backed job example:
  # - name: "ops_fetch"
  #   description: "Fetch fresh state for an operational KB"
  #   schedule: "0 9,16 * * 1-5"
  #   kb_name: "ops-kb"
  #   kb_operation: "fetch"
  #   log: "/absolute/path/to/ops-kb/state/fetch.log"
  #   enabled: false
```

**Field rules:**
- `name` — unique, lowercase alphanumeric + hyphens
- `schedule` — standard crontab syntax (5 fields)
- `script` — relative paths resolved from `ADJ_DIR`; absolute paths used as-is; must be executable
- `kb_name` + `kb_operation` — generic KB-backed alternative to `script`
- `log` — optional; defaults to `state/<name>.log` if omitted
- `enabled` — `true` installs crontab entry; `false` tracks in registry but does not install

### Crontab entry format

Each managed entry carries a name marker for unambiguous per-job management:

```
0 8 * * 1-5 /path/to/adjutant/scripts/news/briefing.sh >> /path/to/adjutant/state/news_briefing.log 2>&1  # adjutant:news_briefing
```

The `# adjutant:<name>` suffix is the identity marker. All entries still contain `.adjutant`, so existing `startup.sh` grep counts remain valid.

---

## New Files

> **Note:** The files below are described in their original bash form. The Python
> equivalents live under `src/adjutant/capabilities/schedule/` and `src/adjutant/setup/steps/`.

### `scripts/capabilities/schedule/manage.sh` → `src/adjutant/capabilities/schedule/manage.py`

Sourced library — CRUD over `adjutant.yaml schedules:`. No `yq` dependency (pure line-by-line YAML parsing).

Public functions:

| Function | Purpose |
|---|---|
| `schedule_count` | Count entries in registry |
| `schedule_exists name` | Boolean check |
| `schedule_list` | Tab-separated output including script or KB-backed operation fields |
| `schedule_get_field name field` | Read one field from an entry |
| `schedule_add name desc schedule script log` | Append entry, call `schedule_install_all` |
| `schedule_remove name` | Remove entry, call `schedule_uninstall_one` |
| `schedule_set_enabled name true\|false` | Toggle `enabled:`, call install/uninstall |

### `scripts/capabilities/schedule/install.sh` → `src/adjutant/capabilities/schedule/install.py`

Sourced library — owns all crontab interaction. Single source of truth for crontab format.

Public functions:

| Function | Purpose |
|---|---|
| `schedule_install_all` | Read registry, reconcile full crontab (idempotent) |
| `schedule_install_one name` | Resolve script or KB operation, build and install one crontab line |
| `schedule_uninstall_one name` | Remove line matching `# adjutant:<name>` |
| `schedule_run_now name` | Resolve script or KB operation, exec in foreground (for testing) |

Backwards compatibility: crontab lines containing `.adjutant` but without `# adjutant:<name>` (old format) are left untouched by `schedule_install_all`.

### `scripts/setup/steps/schedule_wizard.sh` → `src/adjutant/setup/steps/schedule_wizard.py`

Interactive creation wizard, called by `adjutant schedule add`.

Prompts (in order):
1. **Name** — validated unique, lowercase alphanumeric + hyphens
2. **Description** — free text
3. **Script path** — warns but does not block if file not found or not executable
4. **Schedule** — cron syntax; shows common examples inline
5. **Log file** — defaults to `state/<name>.log`

On completion: calls `schedule_add`, installs crontab entry immediately, prints summary, suggests `adjutant schedule run <name>` to test.

### `scripts/lifecycle/pulse_cron.sh` / `review_cron.sh` → `src/adjutant/capabilities/schedule/notify_wrap.py`

In the Python rewrite, both pulse and review cron wrappers are handled by a single `notify_wrap.py` module that reads the schedule entry, resolves the command (script or KB operation), executes it, and forwards structured JSON notification events from stderr to Telegram.

---

## Modified Files

> **Note:** The file references below are from the bash era. In the Python codebase,
> the equivalent changes were made to the corresponding Python modules. See the
> mapping table at the top of this document.

### `adjutant.yaml.example`
- Add top-level `schedules:` block with three built-in entries (news_briefing, autonomous_pulse, autonomous_review) and a commented external example.
- `autonomy:` — remove `pulse_schedule:` and `review_schedule:` keys. Retain `enabled:` only.
- `features.news:` — remove `schedule:` key. Retain `enabled:` and `config_path:`.

### `adjutant` (CLI entry point)
New `schedule` subcommand:

```
adjutant schedule list              List all registered jobs with status
adjutant schedule add               Interactive wizard to create a new job
adjutant schedule remove <name>     Remove a job from registry and crontab
adjutant schedule enable <name>     Enable a job (installs crontab entry)
adjutant schedule disable <name>    Disable a job (removes crontab entry, keeps registry)
adjutant schedule sync              Reconcile crontab with registry (idempotent)
adjutant schedule run <name>        Run a job immediately in foreground (for testing)
adjutant schedule help              Show usage
```

### `scripts/setup/steps/service.sh`
- Remove `_service_install_news_cron`.
- Add `_service_install_schedules`: source `schedule/install.sh`, call `schedule_install_all`.
- Call `_service_install_schedules` in `step_service` (unconditionally — it's a no-op if no jobs are enabled).

### `scripts/setup/steps/features.sh`
- Remove `schedule:` key write from `_features_update_config`. The `_features_yaml_set_bool "news" ...` call for `enabled` and `config_path` remains.

### `scripts/setup/steps/autonomy.sh`
- Remove pulse/review custom schedule input prompts from `step_autonomy`.
- Remove `_autonomy_install_crons` function entirely.
- `_autonomy_update_config`: write only `autonomy.enabled` — remove `pulse_schedule`/`review_schedule` awk manipulation.
- When `WIZARD_AUTONOMY_ENABLED=true`: call `schedule_set_enabled autonomous_pulse true` and `schedule_set_enabled autonomous_review true` instead of installing cron entries directly.

### `scripts/observability/status.sh`
- Remove crontab-parsing block with hardcoded `JOB_NAME` patterns.
- Replace with: source `schedule/manage.sh`, iterate `schedule_list`, format output from registry.
- Cross-reference live crontab to flag enabled jobs not found in crontab (`[not in crontab]`).

### `scripts/lifecycle/emergency_kill.sh`
- Remove hardcoded `pkill` block for news job scripts.
- Replace with: source `schedule/manage.sh`, iterate `schedule_list`, `pkill -TERM -f` each registered script path.
- Crontab backup and wipe unchanged.

### `scripts/lifecycle/startup.sh`
- After crontab restore on recovery: source `schedule/install.sh`, call `schedule_install_all` to catch jobs added since the backup.

### `scripts/messaging/dispatch.sh`
- Add `/schedule` and `/schedule *` routing to the `case` statement.

### `scripts/messaging/telegram/commands.sh`
- Add `cmd_schedule` handler with subcommands: `list`, `run <name>`, `enable <name>`, `disable <name>`.
- Update `cmd_help` to include `/schedule`.

---

## Files Touched Summary

### Bash era (as originally planned)

| File | Type | Change |
|---|---|---|
| `scripts/capabilities/schedule/manage.sh` | New | CRUD helpers |
| `scripts/capabilities/schedule/install.sh` | New | Crontab reconciler |
| `scripts/setup/steps/schedule_wizard.sh` | New | Interactive creation wizard |
| `scripts/lifecycle/pulse_cron.sh` | New | Thin opencode wrapper for pulse |
| `scripts/lifecycle/review_cron.sh` | New | Thin opencode wrapper for review |

### Python rewrite (actual implementation)

| File | Type | Change |
|---|---|---|
| `src/adjutant/capabilities/schedule/manage.py` | New | CRUD helpers, pure-Python YAML parsing |
| `src/adjutant/capabilities/schedule/install.py` | New | Crontab reconciler, `_resolve_command()` |
| `src/adjutant/capabilities/schedule/notify_wrap.py` | New | Cron wrapper for pulse/review/KB operations |
| `src/adjutant/setup/steps/schedule_wizard.py` | New | Interactive creation wizard |
| `src/adjutant/cli.py` | Edit | Added `schedule` subcommand group |
| `src/adjutant/messaging/dispatch.py` | Edit | Added `/schedule` routing |
| `src/adjutant/messaging/telegram/commands.py` | Edit | Added `cmd_schedule`, updated `cmd_help` |
| `src/adjutant/lifecycle/control.py` | Edit | Registry-driven process kill on emergency |
| `adjutant.yaml.example` | Edit | Added `schedules:` block |
| `tests/unit/test_schedule_*.py` | New | Unit tests for manage, install, wizard |

---

## Documentation Required

All of the following must be written or updated as part of this phase:

- **`docs/guides/schedules.md`** (new) — User guide: what schedules are, how to add a job via `adjutant schedule add`, the `adjutant.yaml schedules:` schema, crontab marker format, how to migrate an existing cron entry into the registry, examples.
- **`docs/guides/commands.md`** — Add `/schedule list`, `/schedule run`, `/schedule enable`, `/schedule disable` to the Telegram commands reference.
- **`docs/guides/configuration.md`** — Document the `schedules:` top-level block, the simplified `autonomy:` block (removed `pulse_schedule`/`review_schedule`), and the removal of `features.news.schedule`.
- **`docs/development/plugin-guide.md`** — Add a section on registering a scheduled job from a KB or external script: how to add an entry to `schedules:`, what the script must do (exit 0/non-zero, stdout is captured for `/schedule run`).
- **`docs/architecture/overview.md`** — Update the cron/scheduling section to reflect the registry-driven model.
- **`docs/guides/autonomy.md`** — Update to reflect removal of `pulse_schedule`/`review_schedule` from the `autonomy:` block; note that schedules are now in `schedules:`.
