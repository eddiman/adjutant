# Lifecycle Guide

How to start, stop, pause, recover, and update Adjutant.

---

## States

Adjutant has three possible states:

| State | What it means | How to enter | How to exit |
|-------|--------------|-------------|------------|
| **RUNNING** | Listener is active and polling for messages | `adjutant start` | `adjutant stop`, `adjutant pause`, or `adjutant kill` |
| **PAUSED** | Listener is running but ignores all messages; `PAUSED` lockfile exists | `adjutant pause` or `/pause` | `adjutant resume` or `/resume` |
| **KILLED** | Hard stop; `KILLED` lockfile exists; nothing will start until explicit recovery | `adjutant kill` or `/kill` | `adjutant startup` (clears lockfile, restores crontab, starts fresh) |

Check the current state at any time:

```bash
adjutant status
```

Or from Telegram:

```
/status
```

---

## Normal Operation

### Start

```bash
adjutant start
```

Starts the Telegram listener in the background. The listener polls the Telegram API in a continuous loop. Acquires a directory-based mutex (`state/listener.lock/`) to prevent duplicate instances.

If a `KILLED` lockfile exists, use `adjutant startup` for full recovery (see below).

### Stop

```bash
adjutant stop
```

Kills the listener process using its stored PID. Any in-flight response that has already started will complete; new messages will not be processed until the listener is restarted.

### Restart

```bash
adjutant restart
```

Stop followed by start. Useful after configuration changes or after pulling an update manually.

---

## Pause and Resume

Pausing is a soft stop. Use it when you want Adjutant to stop responding temporarily without triggering a full emergency shutdown.

```bash
# Pause (from terminal)
adjutant pause

# Pause (from Telegram)
/pause

# Resume (from terminal)
adjutant resume

# Resume (from Telegram)
/resume
```

While paused:
- The listener process continues running and polling
- All incoming messages are silently dropped
- The `PAUSED` lockfile at `$ADJ_DIR/PAUSED` controls this behaviour
- `adjutant status` / `/status` will show `PAUSED`

Both `pause` and `resume` are idempotent — calling them when already in the target state has no effect.

---

## Emergency Kill

Use this when something is wrong: a runaway loop, unexpected file changes, excessive resource use, or erratic behaviour.

```bash
# From terminal
adjutant kill

# From Telegram
/kill
```

What happens:
1. Creates `$ADJ_DIR/KILLED` lockfile
2. Terminates all Adjutant-related processes (listener, LLM backend, any background jobs)
3. Disables cron jobs (backed up to `state/crontab.backup`)
4. Logs the event and sends a Telegram notification

After a kill, **nothing will start** until the lockfile is cleared. This is intentional — it prevents accidental restart after an emergency.

### Recovering from a kill

```bash
adjutant startup
```

`adjutant startup` detects the `KILLED` lockfile, enters recovery mode, and walks through:
1. Removing the `KILLED` lockfile
2. Restoring the crontab from `state/crontab.backup`
3. Re-syncing the schedule registry to crontab
4. Starting the Telegram listener
5. Sending a Telegram notification confirming recovery

Note: `adjutant start` (without `startup`) will refuse to start if a `KILLED` lockfile is present — use `adjutant startup` for full recovery.

### KILLED vs PAUSED

| | PAUSED | KILLED |
|-|--------|--------|
| Listener still runs | Yes | No |
| New messages processed | No | No |
| Requires explicit recovery | `adjutant resume` | `adjutant startup` (will not auto-recover) |
| Severity | Low — routine use | High — emergency only |

---

## Auto-Start on Login

To start Adjutant automatically when you log in to your Mac:

```bash
adjutant startup
```

This installs a LaunchAgent plist at `~/Library/LaunchAgents/com.adjutant.telegram.plist`. The listener will start on every login without manual intervention.

To remove the LaunchAgent:

```bash
launchctl unload ~/Library/LaunchAgents/com.adjutant.telegram.plist
rm ~/Library/LaunchAgents/com.adjutant.telegram.plist
```

---

## Update

```bash
adjutant update
```

Self-update flow:
1. Checks the current `VERSION` against the latest GitHub release tag
2. If already up to date, exits with no changes
3. If an update is available:
   - Backs up the current installation
   - Downloads the release tarball
   - Rsyncs new files into place (your personal files — `adjutant.yaml`, `.env`, `identity/`, `knowledge_bases/` — are never overwritten)
   - Runs `adjutant doctor` to verify the updated installation

After updating, restart the listener to pick up any script changes:

```bash
adjutant restart
```

---

## Doctor

```bash
adjutant doctor
```

Checks that required tools are installed (`bash`, `curl`, `python3`, and your configured LLM backend binary), credentials are present in `.env`, identity files exist, and the listener state. Does not modify anything — read-only diagnostic.

---

## Lifecycle State Machine

```
          adjutant start
               │
               ▼
         ┌─────────────┐
         │   RUNNING   │◄──── adjutant restart
         └─────┬───────┘
               │
      ┌────────┴────────┐
      ▼                 ▼
  adjutant pause    adjutant kill  /kill
      │                 │
      ▼                 ▼
  PAUSED            KILLED
      │                 │
      ▼                 ▼
  adjutant resume   adjutant startup
      │                 │
      ▼                 ▼
    RUNNING           RUNNING
```

Recovery from KILLED requires `adjutant startup` -- not `adjutant start`. `adjutant start` will refuse if a `KILLED` lockfile is present.

---

## Active Operation Tracking

When a pulse or review is running, Adjutant writes a marker file at `state/active_operation.json`. This allows external clients (like the web dashboard) to observe the running state without holding open an HTTP connection.

```json
{
  "action": "pulse",
  "started_at": "2026-03-18T21:30:00+00:00",
  "pid": 12345,
  "source": "cron"
}
```

The marker is created before the operation starts and removed when it finishes (in a `finally` block, so it's cleaned up even on failure).

### Source values

| Source | Meaning |
|--------|---------|
| `cron` | Triggered from CLI (`adjutant pulse`) or crontab |
| `telegram` | Triggered via `/pulse` or `/reflect` → `/confirm` in Telegram |
| `adjutant-web` | Triggered from the web dashboard (spawns `adjutant pulse`) |

### Staleness detection

If the marker is older than 30 minutes and the recorded PID is no longer alive, it is treated as stale and automatically cleaned up. This handles edge cases like SIGKILL or power loss.

---

## Post-Operation Notifications

After a successful pulse or review, Adjutant sends a Telegram notification with a summary of results. This happens automatically regardless of how the operation was triggered (CLI, crontab, adjutant-web, or Telegram).

The notification includes:
- Which KBs were checked
- Any issues found
- Whether the findings were escalated
- Where the trigger came from

Notifications use the daily budget system (`notifications.max_per_day` in `adjutant.yaml`, default 3). If the budget is exhausted, the notification is silently skipped. The pulse/review itself still completes normally.

Note: when triggered from Telegram via `/pulse`, the notification is redundant since the results are already sent as a chat reply. Both are sent, but the daily budget prevents excess.

---

## Morning Brief

The morning brief is a proactive daily summary designed for the user, not for system health. It combines:

- Current priorities from `heart.md` with KB status updates
- Deadlines in the next 7 days from all KBs
- Unprocessed insights from `insights/pending/`
- Overnight changes since the last pulse

```bash
# Run from terminal
adjutant brief

# Run from Telegram
/brief

# Schedule via crontab (e.g., every weekday at 07:30)
# In adjutant.yaml schedules:
# - name: morning-brief
#   schedule: "30 7 * * 1-5"
#   script: "adjutant brief"
#   enabled: true
```

The brief uses `kb query-all` internally to query all KBs in parallel, making it significantly faster than a sequential pulse. Output is sent as a single Telegram notification, kept under 800 characters for phone readability.

The brief differs from pulse in purpose: pulse is a system-level health check that writes to journal and escalates issues. The brief is a user-facing daily planner that tells you what to focus on today.

---

## Self-Assessment

The self-assessment is a weekly introspection cycle where Adjutant evaluates its own effectiveness and proposes improvements. It runs through `prompts/self_assess.md` and:

1. Reviews the past week's journal entries
2. Analyzes notification outcomes (which were useful, which were noise)
3. Compares `heart.md` priorities against actual activity
4. Evaluates signal-to-noise ratio, coverage, and timing
5. Proposes specific changes to priorities, notification frequency, and KB query patterns

```bash
# Run from terminal
adjutant self-assess

# Run from Telegram (any of these work)
/self-assess
/selfassess
/assess

# Schedule via crontab (e.g., every Sunday at 20:00)
# In adjutant.yaml schedules:
# - name: weekly-self-assess
#   schedule: "0 20 * * 0"
#   script: "adjutant self-assess"
#   enabled: true
```

**Safety:** The self-assessment never modifies `identity/soul.md` or `identity/heart.md` directly. All proposed changes are written to `insights/pending/self-assessment-YYYY-WNN.md` for the user to review and approve. This keeps the human in the loop for any behavioural changes.

---

## Autonomy Configuration

Adjutant supports graduated autonomy levels via the `autonomy` section in `adjutant.yaml`:

```yaml
autonomy:
  level: 2                    # 1=notify-only, 2=suggest+approve, 3=act+notify, 4=autonomous
  auto_approve:
    - kb_data_refresh         # Actions that don't need approval at level 3+
    - memory_digest
  require_approval:
    - heart_update            # Actions that always need approval, regardless of level
    - notification_rule
```

| Level | Behaviour |
|-------|-----------|
| 1 | Notify-only — never act without explicit instruction |
| 2 | Suggest and act on approval (default) — proposes changes, waits for confirmation |
| 3 | Act and notify — performs actions autonomously, then tells you what it did |
| 4 | Fully autonomous — acts silently, logs only |

The `auto_approve` list specifies actions that can proceed without user approval at level 3 and above. The `require_approval` list specifies actions that always need explicit approval, regardless of autonomy level.

---

## Parallel KB Queries

Pulse now uses `kb query-all` to query all registered KBs concurrently instead of sequentially. With 6 KBs at ~70 seconds each, this reduces pulse wall time from ~7 minutes to ~80 seconds.

The `kb query-all` command:
- Reads all KB entries from `knowledge_bases/registry.yaml`
- Uses each KB's `query_hint` field for targeted questions
- Falls back to a generic status query if no hint is set
- Runs all queries via `asyncio.gather()` for maximum concurrency
- Returns a combined result with one section per KB

```bash
# Query all KBs with default hints
adjutant kb query-all

# Override with a custom question for all KBs
adjutant kb query-all -q "What deadlines are in the next 7 days?"
```

---

## Cross-KB Intelligence

The `kb cross-query` command enables multi-domain synthesis — asking questions that span multiple KBs:

```bash
adjutant kb cross-query "Do I have any scheduling conflicts?" --kbs ixda,fagkomite
```

This:
1. Queries the specified KBs in parallel
2. Feeds all responses into a synthesis prompt
3. Returns a unified answer that identifies cross-domain connections and conflicts

Use this when you need insights that no single KB can provide alone.
