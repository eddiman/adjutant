# Lifecycle Guide

How to start, stop, pause, recover, and update Adjutant.

---

## States

Adjutant has three possible states:

| State | What it means | How to enter | How to exit |
|-------|--------------|-------------|------------|
| **RUNNING** | Listener is active and polling for messages | `adjutant start` | `adjutant stop`, `adjutant pause`, or `adjutant kill` |
| **PAUSED** | Listener is running but ignores all messages; `PAUSED` lockfile exists | `adjutant pause` or `/pause` | `adjutant resume` or `/resume` |
| **KILLED** | Hard stop; `KILLED` lockfile exists; nothing will start | `adjutant kill` or `/kill` | `adjutant startup` (interactive recovery, clears lockfile and restores crontab) |

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
| Auto-recovers on next start | No (stays paused) | Yes (lockfile cleared) |
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
          adjutant start / adjutant startup
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
      │
      ▼
  adjutant resume ──► RUNNING
```

Recovery from KILLED: `adjutant startup` (interactive recovery — clears lockfile, restores crontab, starts fresh).
