# State & Lifecycle

How Adjutant tracks runtime state, manages lockfiles, and transitions between lifecycle states.

---

## State Files — `state/`

All runtime state lives under `~/.adjutant/state/`. These files are gitignored and user-specific.

| File | Purpose |
|------|---------|
| `adjutant.log` | Unified structured log. Format: `[YYYY-MM-DD HH:MM:SS] [COMPONENT] message` |
| `telegram_offset` | Last-processed Telegram update ID. Prevents replaying already-seen messages on restart. |
| `listener.lock/` | Directory-based mutex. Only the process that successfully creates this directory can poll. Contains a `pid` file with the listener's PID. |
| `listener.lock/pid` | The authoritative PID of the running listener. |
| `telegram.pid` | PID written by `service.sh start`. Kept in sync with `listener.lock/pid`. |
| `telegram_session.json` | Session ID for OpenCode chat continuity. Reused within a 2-hour window; starts fresh after expiry. |
| `telegram_model.txt` | Currently selected LLM model for Telegram chat. Switched via `/model`. |
| `rate_limit_window` | Sliding-window timestamp log for rate limiting. |
| `pending_reflect` | Marker file indicating a `/reflect` confirmation is awaited. |
| `last_heartbeat.json` | Timestamp and summary of the last `/pulse` or `/reflect` run. |
| `usage_log.jsonl` | Rolling token usage log for session and weekly estimates. |
| `opencode_web.pid` | PID of the running `opencode web --mdns` server, written by `startup.sh`. Read by `opencode.sh` to identify the web process for health checks and orphan reaping. |
| `opencode_web.log` | stdout/stderr of the `opencode web` server. Rotated on restart. |

---

## Lockfiles — `KILLED` and `PAUSED`

Two lockfiles at the root of `ADJ_DIR` control the system's operational state:

| File | Meaning | Effect |
|------|---------|--------|
| `~/.adjutant/PAUSED` | Soft pause | Listener keeps running but drops all incoming messages |
| `~/.adjutant/KILLED` | Hard stop | Listener will not start; all scripts check this before running |

These are plain files — their presence/absence is the entire state. Managed by `scripts/common/lockfiles.sh`:

| Function | What it does |
|----------|-------------|
| `is_paused` | Returns 0 if `PAUSED` exists |
| `is_killed` | Returns 0 if `KILLED` exists |
| `is_operational` | Returns 0 if neither lockfile exists |
| `set_paused` / `clear_paused` | Create / remove `PAUSED` |
| `set_killed` / `clear_killed` | Create / remove `KILLED` |
| `check_killed` | Returns 0 silently when not killed; returns 1 with error message when killed |
| `check_paused` | Returns 0 silently when not paused; returns 1 with error message when paused |
| `check_operational` | Composite check — `KILLED` takes precedence over `PAUSED` |

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

- **RUNNING → PAUSED**: `adjutant pause` or `/pause`. Creates `PAUSED` file. Listener keeps polling but drops messages.
- **PAUSED → RUNNING**: `adjutant resume` or `/resume`. Removes `PAUSED` file.
- **RUNNING → KILLED**: `adjutant kill` or `/kill`. Terminates all processes, creates `KILLED` file, disables cron.
- **KILLED → RUNNING**: `adjutant start`. Detects and clears `KILLED` lockfile, then starts the listener fresh.

---

## Directory-Based Mutex

The listener lock uses a directory (`state/listener.lock/`) rather than a PID file directly. `mkdir` is atomic on POSIX filesystems — only one process can successfully create the directory. The PID inside `listener.lock/pid` is the real listener.

This pattern provides:
- **Race-free acquisition** — no TOCTOU window between checking and creating
- **Stale lock detection** — `service.sh` checks whether the PID in `listener.lock/pid` is still running before declaring the listener alive
- **Two-layer tracking** — `listener.lock/pid` (written by the listener itself) and `telegram.pid` (written by the service manager) are kept in sync

---

## Lifecycle Scripts — `scripts/lifecycle/`

| Script | What it does |
|--------|-------------|
| `startup.sh` | Clears `KILLED` lockfile if present, optionally installs LaunchAgent, starts the listener |
| `pause.sh` | Creates `PAUSED` lockfile |
| `resume.sh` | Removes `PAUSED` lockfile |
| `emergency_kill.sh` | Creates `KILLED`, terminates all Adjutant processes by pattern, disables crontab |
| `restart.sh` | Stop + start, with confirmation prompt |
| `update.sh` | Compares `VERSION` against latest GitHub release, backs up, downloads, rsyncs, runs doctor |
