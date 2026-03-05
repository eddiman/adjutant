# Autonomy Mode

Adjutant can operate on your behalf without real-time oversight. In autonomy mode, it queries your knowledge bases on a schedule, surfaces significant signals as Telegram notifications, and keeps a machine-readable log of every action it takes. You retain full control at all times via a filesystem kill switch and a hard notification budget.

---

## 1. What autonomy mode does

The autonomous cycle has three tiers:

| Tier | Prompt | Cadence | Purpose |
|------|--------|---------|---------|
| **Pulse** | `prompts/pulse.md` | Configurable (default: 2×/day) | Lightweight scan of all KBs — flag anything significant |
| **Escalation** | `prompts/escalation.md` | Triggered by pulse | Deep read of a flagged insight — decide whether to notify |
| **Review** | `prompts/review.md` | Configurable (default: 1×/day at 8pm) | Thorough daily synthesis across all KBs, processes pending insights |

**What it never does without you:**
- Call `notify.sh` more than `max_per_day` times (hard script-layer block)
- Act during quiet hours (enforced in `notify.sh`)
- Continue when `PAUSED` exists (checked first in every prompt)
- Write anything real when `debug.dry_run: true`

---

## 2. Enabling autonomy

### Via the setup wizard (recommended)

Run `adjutant setup`. Step 7 "Autonomy Configuration" asks:
1. Enable autonomous pulse checks? [y/N]
2. Maximum notifications per day? [3]
3. Enable quiet hours? [y/N]

If you answer yes to enabling, the wizard writes `autonomy.enabled: true` to `adjutant.yaml` and enables the `autonomous_pulse` and `autonomous_review` schedule entries (installing their crontab entries). The default schedules are weekdays 9am/5pm for pulse and weekdays 8pm for review.

### Manually in `adjutant.yaml`

```yaml
autonomy:
  enabled: true

notifications:
  max_per_day: 3
  quiet_hours:
    enabled: false
    start: "22:00"
    end: "07:00"
```

Then enable the schedule entries:

```bash
adjutant schedule enable autonomous_pulse
adjutant schedule enable autonomous_review
```

---

## 3. Configuring pulse cadence and review schedule

Pulse and review schedules are managed as regular schedule entries in `adjutant.yaml schedules:`. See the [Schedules guide](schedules.md) for full documentation.

To change the schedule of `autonomous_pulse`:

```bash
# Disable current entry and remove it
adjutant schedule disable autonomous_pulse
adjutant schedule remove autonomous_pulse

# Add it back with a new schedule
adjutant schedule add
# Name: autonomous_pulse
# Description: Scheduled autonomous pulse check across knowledge bases
# Script path: scripts/lifecycle/pulse_cron.sh
# Schedule: 0 12 * * *      ← your new schedule
# Log file: state/pulse.log
```

Or edit `adjutant.yaml schedules:` directly and run `adjutant schedule sync`.

Common schedule examples:

| Schedule | Cron expression |
|----------|----------------|
| Weekdays 9am and 5pm (default) | `0 9,17 * * 1-5` |
| Every 4 hours on weekdays | `0 */4 * * 1-5` |
| Once daily at noon | `0 12 * * *` |
| Weekday evenings at 8pm | `0 20 * * 1-5` |

---

## 4. Notification budget and quiet hours

### Hard budget

`notifications.max_per_day` sets the daily ceiling. Once that many notifications have been sent, `notify.sh` outputs `ERROR:budget_exceeded` and exits 1 — no further Telegram messages are sent for the rest of the calendar day regardless of what the LLM decides.

The counter resets at midnight (it is a date-stamped file: `state/notify_count_YYYY-MM-DD.txt`).

```yaml
notifications:
  max_per_day: 5   # increase for busier workflows
```

### Quiet hours

When enabled, `notify.sh` will suppress sends between the configured hours. The agent can still run pulses and reviews — it just will not deliver Telegram messages during those hours.

```yaml
notifications:
  quiet_hours:
    enabled: true
    start: "22:00"
    end: "07:00"
```

---

## 5. Understanding the action ledger

Every autonomous cycle appends a JSON line to `state/actions.jsonl`. This file is your machine-readable audit trail — you can grep it, `tail` it, or process it with `jq`.

**Schema:**

```jsonc
// Pulse completed
{"ts":"2026-03-05T09:00:00Z","type":"pulse","kbs_checked":["work","ml-papers"],"issues_found":[],"escalated":false}

// Notification sent
{"ts":"2026-03-05T09:00:01Z","type":"notify","detail":"[work] Sprint deadline approaching in 2 days."}

// Escalation processed
{"ts":"2026-03-05T09:00:02Z","type":"escalation","trigger":"2026-03-05-0900.md","action":"notified","project":"work"}

// Daily review completed
{"ts":"2026-03-05T20:00:00Z","type":"review","kbs_checked":["work","ml-papers"],"insights_sent":1,"recommendations":["Review sprint scope"]}

// Dry-run record (no side effects)
{"ts":"2026-03-05T09:00:00Z","type":"pulse","dry_run":true,"kbs_checked":["work"],"issues_found":[],"escalated":false}
```

The file is gitignored (covered by `state/`) and lives only on your machine.

---

## 6. Pausing and resuming

### Soft pause (recommended)

```bash
adjutant pause        # creates ADJ_DIR/PAUSED
adjutant resume       # removes ADJ_DIR/PAUSED
```

Or directly:

```bash
touch "$HOME/.adjutant/PAUSED"   # pause
rm "$HOME/.adjutant/PAUSED"      # resume
```

When `PAUSED` exists, every autonomous prompt outputs a skip message and stops immediately. Nothing is written to `insights/`, `state/`, or `actions.jsonl`.

### Via Telegram

```
/pause    — creates PAUSED
/resume   — removes PAUSED
/status   — shows current state
```

---

## 7. Dry-run mode

Dry-run lets you test the full autonomous cycle with zero side effects:

```yaml
debug:
  dry_run: true
```

With this set:
- All three prompts run their full logic
- **No** files are written to `insights/pending/`
- **No** `notify.sh` calls are made
- **No** `state/last_heartbeat.json` update
- Every journal entry is prefixed `[DRY RUN]`
- `state/actions.jsonl` records `"dry_run":true` so you can verify the cycle ran

Reset after testing:

```yaml
debug:
  dry_run: false
```

---

## 8. Reading the `/status` output

`adjutant status` (or `/status` in Telegram) now includes an "Autonomous activity" section:

```
Status: RUNNING

Registered cron jobs:
  - Autonomous Pulse: Schedule: 0 9,17 * * 1-5
    → opencode run --print ".../prompts/pulse.md" ...
  - Daily Review: Schedule: 0 20 * * 1-5
    → opencode run --print ".../prompts/review.md" ...

Autonomous activity:
  Last cycle: pulse at 2026-03-05T09:00:00Z
  Notifications today: 1/3
  Recent actions:
    2026-03-05T09:00:00Z  pulse
    2026-03-05T09:00:01Z  notify
```

**Fields:**
- **Last cycle** — type and timestamp of the most recent heartbeat (pulse/review/escalation)
- **Notifications today** — current count vs. daily budget
- **Recent actions** — last 5 entries from `state/actions.jsonl`, timestamp + type
