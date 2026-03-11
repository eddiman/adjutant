# Scheduled Jobs

Adjutant can run any script on a cron schedule — internal Adjutant jobs (news briefing, pulse, review) or external scripts from your knowledge bases. All scheduled jobs are declared in `adjutant.yaml schedules:` and managed through a single registry.

---

## How it works

Each job in `adjutant.yaml schedules:` has:
- A **name** — used for CLI and Telegram commands
- A **schedule** — standard cron syntax (5 fields)
- A **script** — path to an executable file (relative to your Adjutant directory, or absolute), or
- A **KB operation pair** — `kb_name` + `kb_operation` for generic KB execution
- A **log** — where stdout/stderr is written
- An **enabled** flag — `true` installs the crontab entry; `false` keeps the registry entry but removes it from crontab

When a job is enabled, Adjutant installs a crontab line in the format:

```
0 8 * * 1-5 /path/to/script.sh >> /path/to/log 2>&1  # adjutant:news_briefing
```

The `# adjutant:<name>` comment is the identity marker. It lets Adjutant manage individual entries without touching the rest of your crontab.

---

## Default jobs

Three jobs are pre-declared in `adjutant.yaml.example`. They are all disabled by default:

| Name | CLI command | Default schedule |
|---|---|---|
| `news_briefing` | `adjutant news` | Weekdays at 8:00am |
| `autonomous_pulse` | `adjutant pulse` | Weekdays at 9am and 5pm |
| `autonomous_review` | `adjutant review` | Weekdays at 8pm |

Each job's `script` field in `adjutant.yaml` should point to the virtualenv Python binary and the appropriate CLI command (e.g. `.venv/bin/python -m adjutant pulse`). The setup wizard writes these correctly when you enable the relevant features.

`news_briefing` is enabled when `features.news.enabled: true` (via the setup wizard or manually). `autonomous_pulse` and `autonomous_review` are enabled when `heartbeat.enabled: true`.

---

## Adding a new scheduled job

### Interactive wizard (recommended)

```bash
adjutant schedule add
```

The wizard collects:
1. **Name** — lowercase alphanumeric with hyphens/underscores (`portfolio-fetch`, `my_report`)
2. **Description** — shown in `adjutant schedule list` and `/schedule list`
3. **Script path** — absolute path, or relative to your Adjutant directory
4. **Schedule** — cron syntax, with examples shown inline
5. **Log file** — defaults to `state/<name>.log`

Common schedule examples shown during the wizard:

| Cron expression | Meaning |
|---|---|
| `0 8 * * 1-5` | Weekdays at 8:00am |
| `0 9,17 * * 1-5` | Weekdays at 9am and 5pm |
| `0 * * * *` | Every hour |
| `*/30 * * * *` | Every 30 minutes |
| `0 20 * * 1-5` | Weekdays at 8pm |
| `0 6 * * *` | Every day at 6am |

The wizard validates the name (uniqueness), warns if the script file doesn't exist or isn't executable (but lets you proceed), and installs the crontab entry immediately on confirmation.

### Manual (edit adjutant.yaml directly)

Add an entry to the `schedules:` block:

```yaml
schedules:
  - name: "portfolio_fetch"
    description: "Fetch Nordnet portfolio positions and prices"
    schedule: "0 9,16 * * 1-5"
    script: "/absolute/path/to/portfolio-kb/scripts/fetch.sh"
    log: "/absolute/path/to/portfolio-kb/state/fetch.log"
    enabled: true
```

Then sync the crontab:

```bash
adjutant schedule sync
```

---

## Managing jobs

### CLI

```bash
adjutant schedule list              # Table of all jobs: name, enabled, schedule, description
adjutant schedule add               # Interactive wizard
adjutant schedule enable <name>     # Enable job → install crontab entry
adjutant schedule disable <name>    # Disable job → remove crontab entry, keep registry
adjutant schedule remove <name>     # Remove from registry and crontab (irreversible)
adjutant schedule sync              # Reconcile crontab with registry (idempotent)
adjutant schedule run <name>        # Run a job immediately in foreground (for testing)
adjutant schedule --help            # Show usage
```

### Telegram

```
/schedule               List all registered jobs
/schedule list          Same as above
/schedule run <name>    Run a job immediately (result sent to chat)
/schedule enable <name> Enable a job
/schedule disable <name> Disable a job
```

Note: there is no `/schedule add` — use the CLI wizard for job creation.

---

## Registering a KB operation as a scheduled job

Prefer scheduling KB work through Adjutant's generic KB runner instead of pointing directly at external KB script paths.

```yaml
schedules:
  - name: "ops_fetch"
    description: "Fetch fresh state for an operational KB"
    schedule: "0 9,12,15 * * 1-5"
    kb_name: "ops-kb"
    kb_operation: "fetch"
    log: "/absolute/path/to/ops-kb/state/fetch.log"
    enabled: true
```

This runs the equivalent of:

```bash
adjutant kb run ops-kb fetch
```

The KB must already be registered in `knowledge_bases/registry.yaml`.

Adjutant resolves `kb_operation: fetch` at install and run time in this order:
1. If `kb.yaml` declares `cli_module`, runs `python -m <cli_module> fetch`
2. Otherwise, runs `<kb-path>/scripts/fetch.sh`

**Script requirements (shell path):**
- Must be executable (`chmod +x`)
- Exit 0 on success, non-zero on failure
- Stdout is captured by `/schedule run <name>` and shown in Telegram

---

## Schema reference

```yaml
schedules:
  - name: "job-name"          # required — unique, lowercase alphanumeric + hyphens/underscores
    description: "What it does"  # required — shown in list and /schedule
    schedule: "0 8 * * 1-5"  # required — 5-field cron syntax
    script: "scripts/foo.sh"  # optional — relative to ADJ_DIR, or absolute
    kb_name: "my-kb"          # optional alternative to script
    kb_operation: "fetch"     # optional alternative to script
    log: "state/foo.log"      # optional — defaults to state/<name>.log
    enabled: true             # required — true = installed in crontab
```

---

## Migrating an existing cron entry

If you have a manually-installed cron job that isn't in the registry, add it to `adjutant.yaml schedules:` and run `adjutant schedule sync`. Sync will install the named entry. The old unnamed entry (without a `# adjutant:<name>` suffix) is left untouched — remove it manually from `crontab -e` after verifying the new entry is installed.

---

## Emergency kill and recovery

When `adjutant kill` (or `/kill`) is triggered:
- All registered script processes are killed by path (from the registry)
- The full crontab is backed up to `state/crontab.backup` and then wiped

When `adjutant startup` recovers from KILLED state:
- The crontab backup is restored
- The schedule registry is re-synced to crontab (`adjutant schedule sync`) to catch any jobs added since the backup

---

## macOS: Full Disk Access for cron

On macOS, `/usr/sbin/cron` requires **Full Disk Access** to read and write files under `~/Documents/`, `~/Desktop/`, or any path protected by TCC. Without it, cron will silently spawn the job but all output is discarded and no files are written.

**Symptom:** Jobs fire at the correct time (visible in `crontab -l`) but the log file is never updated and Telegram notifications never arrive. Running the script manually works fine.

**Fix:**

1. Open **System Settings → Privacy & Security → Full Disk Access**
2. Click `+`, press `Cmd+Shift+G`, enter `/usr/sbin/cron`, click Open
3. Toggle it on

This is a one-time system setting and survives reboots. It does not affect portability — on Linux, cron has no equivalent restriction.

---

## Troubleshooting

**Job shows `[not in crontab]` in `adjutant status`**

The registry says the job is enabled but the crontab entry is missing. Fix with:
```bash
adjutant schedule sync
```

**Job was installed before phase 8 (no `# adjutant:<name>` marker)**

Old-format entries (containing `.adjutant` but without `# adjutant:<name>`) are left untouched by `schedule sync`. Remove them manually from `crontab -e`, then run `adjutant schedule sync` to install the new-format entry.

**Script not found or not executable**

```bash
chmod +x /path/to/script.sh
adjutant schedule run <name>   # test it
```
