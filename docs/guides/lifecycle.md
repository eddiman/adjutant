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
2. Terminates all Adjutant-related processes (listener, opencode, any background jobs)
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

This installs a LaunchAgent plist at `~/Library/LaunchAgents/adjutant.telegram.plist`. The listener will start on every login without manual intervention.

To remove the LaunchAgent:

```bash
launchctl unload ~/Library/LaunchAgents/adjutant.telegram.plist
rm ~/Library/LaunchAgents/adjutant.telegram.plist
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

Checks that all required tools are installed (`bash`, `curl`, `jq`, `python3`, `opencode`), credentials are present in `.env`, identity files exist, and the listener state. Does not modify anything — read-only diagnostic.

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

When a pulse or review is running, Adjutant writes a marker file at `state/active_operation.json`. This allows external clients (like the Mariposa dashboard) to observe the running state without holding open an HTTP connection.

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
| `mariposa` | Triggered from the Mariposa dashboard (spawns `adjutant pulse`) |

### Staleness detection

If the marker is older than 30 minutes and the recorded PID is no longer alive, it is treated as stale and automatically cleaned up. This handles edge cases like SIGKILL or power loss.

---

## Post-Operation Notifications

After a successful pulse or review, Adjutant sends a Telegram notification with a summary of results. This happens automatically regardless of how the operation was triggered (CLI, crontab, Mariposa, or Telegram).

The notification includes:
- Which KBs were checked
- Any issues found
- Whether the findings were escalated
- Where the trigger came from

Notifications use the daily budget system (`notifications.max_per_day` in `adjutant.yaml`, default 3). If the budget is exhausted, the notification is silently skipped. The pulse/review itself still completes normally.

Note: when triggered from Telegram via `/pulse`, the notification is redundant since the results are already sent as a chat reply. Both are sent, but the daily budget prevents excess.
