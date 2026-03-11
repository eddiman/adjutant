# Setup Wizard — Implementation Reference

## Overview

`adjutant setup` is a Python interactive wizard that handles both fresh installs and repairs of an existing Adjutant installation. It is split across modules under `src/adjutant/setup/`.

```
src/adjutant/setup/
├── wizard.py          # Entry point, orchestration, completion banner
├── install.py         # Fresh install logic
├── repair.py          # Repair path — health checks and fix actions
├── uninstall.py       # Uninstall logic
└── steps/
    ├── prerequisites.py   # Step 0: read-only checks (no side effects)
    ├── install_path.py    # Step 1: resolve/create install directory
    ├── identity.py        # Step 2: soul.md, heart.md, registry.md
    ├── messaging.py       # Step 3/4: Telegram token + chat ID, .env write
    ├── features.py        # Step 5: news_config.json
    ├── service.py         # Step 6: chmod, rc-file alias, launchd/systemd/cron
    ├── autonomy.py        # Step 7: autonomy.enabled, schedule entries
    ├── kb_wizard.py       # KB creation sub-wizard (called from wizard.py)
    └── schedule_wizard.py # Schedule add sub-wizard
```

### Execution paths

- **Fresh install** (`ADJ_DIR` unset or pointing to a non-existent directory): runs all steps.
- **Repair** (existing install detected): runs health checks and offers to fix each issue found.

---

## Wizard UI helpers (`wizard.py`)

All interactive UI is funnelled through helper functions. These write prompt text to the terminal and return the user's choice. They handle non-interactive contexts (CI, piped stdin) gracefully by accepting defaults.

| Function | What it does |
|---|---|
| `wiz_confirm(prompt, default)` | Yes/No prompt — returns `True`/`False` |
| `wiz_choose(prompt, options)` | Select from a list — returns chosen item |
| `wiz_input(prompt, default)` | Free-text input — returns entered string |
| `wiz_multiline(prompt)` | Multi-line input — returns full text block |
| `wiz_secret(prompt)` | Hidden input (no echo) — returns secret string |

---

## `--dry-run` flag

### Activation

```bash
adjutant setup --dry-run
```

### Behavior contract

| Category | Normal | Dry-run |
|---|---|---|
| Prompts | Interactive | Auto-accept defaults (UI text still shown) |
| Filesystem writes | Executed | Suppressed; `[DRY RUN] Would: ...` printed inline |
| `chmod` calls | Executed | Suppressed; printed inline |
| HTTP calls | Executed | Suppressed; printed inline |
| claude run | Executed | Suppressed; printed inline |
| rc-file appends | Executed | Suppressed; printed inline |
| launchctl/systemctl | Executed | Suppressed; printed inline |
| crontab edits | Executed | Suppressed; printed inline |
| Completion banner | Normal text | `[DRY RUN] Simulation complete. No changes were made.` |

### Guard pattern for side-effectful actions

Every action that would modify the filesystem, network, or system config is wrapped:

```python
if dry_run:
    print(f"[DRY RUN] Would: write {target_file}")
else:
    target_file.write_text(content)
```

---

## Known edge cases and gotchas

### Default install path resolves to cwd

When `ADJ_DIR` is empty (fresh install simulation), the install path step resolves the default to the current working directory. In a non-interactive shell (e.g. a dry-run launched from `/Users`), this prints `/Users` as the default path. This is cosmetically odd but functionally correct — no directory is actually created in dry-run mode.

### Repair path

The wizard detects an existing installation by checking whether `ADJ_DIR` points to a directory that contains `adjutant.yaml`. If yes, it runs the repair path. If no, it runs the fresh install steps.

To force the fresh install path during dry-run testing:

```bash
ADJ_DIR="" adjutant setup --dry-run
```

To test the repair path on a live install:

```bash
adjutant setup --dry-run
```

### KB wizard sub-wizard

The KB creation wizard (`kb_wizard.py`) is invoked from the main wizard as an optional step. It prompts for name, path, description, model tier, and access level. It calls `kb_scaffold()` from `capabilities/kb/manage.py` to create the directory structure.

### Schedule wizard sub-wizard

`schedule_wizard.py` prompts for name, description, script path or KB operation, schedule, and log file. It calls `schedule_append()` from `capabilities/schedule/manage.py` to register the job, then `schedule_install()` to install the crontab entry.
