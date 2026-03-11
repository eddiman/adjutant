# State & Lifecycle

How Adjutant tracks runtime state, manages lockfiles, and transitions between lifecycle states.

---

## State Files — `state/`

All runtime state lives under `ADJ_DIR/state/`. These files are gitignored and user-specific.

| File | Purpose |
|------|---------|
| `adjutant.log` | Unified structured log. Format: `[YYYY-MM-DD HH:MM:SS] [COMPONENT] message` |
| `telegram_offset` | Last-processed Telegram update ID. Prevents replaying already-seen messages on restart. |
| `listener.lock/` | Directory-based mutex. Only the process that successfully creates this directory can poll. Contains a `pid` file with the listener's PID. |
| `listener.lock/pid` | The authoritative PID of the running listener. |
| `telegram.pid` | PID written by `service.py start`. Kept in sync with `listener.lock/pid`. |
| `telegram_session.json` | Session ID for Claude Code chat continuity. Reused within a configured window; starts fresh after expiry. |
| `telegram_model.txt` | Currently selected LLM model for Telegram chat. Switched via `/model`. |
| `rate_limit_window` | Sliding-window timestamp log for rate limiting. |
| `pending_reflect` | Marker file indicating a `/reflect` confirmation is awaited. |
| `last_heartbeat.json` | Timestamp and summary of the last `/pulse` or `/reflect` run. |
| `usage_log.jsonl` | Rolling token usage log for session and weekly estimates. |
| `actions.jsonl` | JSONL audit log — one record per autonomous cycle or notification. |
| `notify_count_YYYY-MM-DD.txt` | Today's notification send counter. Enforces the daily budget. Resets at midnight automatically (date-scoped filename). |

---

## Lockfiles — `KILLED` and `PAUSED`

Two lockfiles at the root of `ADJ_DIR` control the system's operational state:

| File | Meaning | Effect |
|------|---------|--------|
| `ADJ_DIR/PAUSED` | Soft pause | Listener keeps running but drops all incoming messages |
| `ADJ_DIR/KILLED` | Hard stop | Listener will not start; all scripts check this before running |

These are plain files — their presence/absence is the entire state. Managed by `src/adjutant/core/lockfiles.py`:

| Function | What it does |
|----------|-------------|
| `is_paused` | Returns True if `PAUSED` exists |
| `is_killed` | Returns True if `KILLED` exists |
| `is_operational` | Returns True if neither lockfile exists |
| `set_paused` / `clear_paused` | Create / remove `PAUSED` |
| `set_killed` / `clear_killed` | Create / remove `KILLED` |
| `check_killed` | Returns silently when not killed; raises when killed |
| `check_paused` | Returns silently when not paused; raises when paused |
| `check_operational` | Composite check — `KILLED` takes precedence over `PAUSED` |

---

## Lifecycle State Machine

```
          adjutant start / adjutant startup
               │
               ▼
         ┌─────────────┐
         │ OPERATIONAL │◄──── adjutant restart
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
  adjutant resume ──► OPERATIONAL
```

- **OPERATIONAL → PAUSED**: `adjutant pause` or `/pause`. Creates `PAUSED` file. Listener keeps polling but drops messages.
- **PAUSED → OPERATIONAL**: `adjutant resume` or `/resume`. Removes `PAUSED` file.
- **OPERATIONAL → KILLED**: `adjutant kill` or `/kill`. Terminates all processes, creates `KILLED` file, disables cron.
- **KILLED → OPERATIONAL**: `adjutant start`. Detects and clears `KILLED` lockfile, then starts the listener fresh.

---

## Directory-Based Mutex

The listener lock uses a directory (`state/listener.lock/`) rather than a PID file directly. `mkdir` is atomic on POSIX filesystems — only one process can successfully create the directory. The PID inside `listener.lock/pid` is the real listener.

This pattern provides:
- **Race-free acquisition** — no TOCTOU window between checking and creating
- **Stale lock detection** — `service.py` checks whether the PID in `listener.lock/pid` is still running before declaring the listener alive
- **Two-layer tracking** — `listener.lock/pid` (written by the listener itself) and `telegram.pid` (written by the service manager) are kept in sync

---

## Lifecycle Modules — `src/adjutant/lifecycle/`

| Module | What it does |
|--------|-------------|
| `control.py` | `pause`, `resume`, `kill`, `startup`. Clears `KILLED` lockfile on startup; creates/removes `PAUSED`. Emergency kill terminates all Adjutant processes by pattern and backs up then wipes crontab. |
| `cron.py` | Runs the pulse and review prompts as cron-triggered subprocesses. |
| `update.py` | Compares `VERSION` against latest GitHub release, backs up, downloads, rsyncs new files into place. Personal files (`adjutant.yaml`, `.env`, `identity/`, `knowledge_bases/`) are never overwritten. |
