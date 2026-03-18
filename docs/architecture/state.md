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
| `telegram_session.json` | Session ID for OpenCode chat continuity. Reused within a configured window; starts fresh after expiry. |
| `telegram_model.txt` | Currently selected LLM model for Telegram chat. Switched via `/model`. |
| `rate_limit_window` | Sliding-window timestamp log for rate limiting. |
| `pending_reflect` | Marker file indicating a `/reflect` confirmation is awaited. |
| `last_heartbeat.json` | Timestamp and summary of the last `/pulse` or `/reflect` run. |
| `usage_log.jsonl` | Rolling token usage log for session and weekly estimates. |
| `actions.jsonl` | JSONL audit log — one record per autonomous cycle or notification. |
| `active_operation.json` | Marker for a currently running pulse or review. Written before opencode starts, removed when it finishes. Used by external clients (Mariposa, Telegram) to observe running state. |
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

## Active Operation Tracking

When a pulse or review starts, Adjutant writes `state/active_operation.json`:

```json
{
  "action": "pulse",
  "started_at": "2026-03-18T21:30:00+00:00",
  "pid": 12345,
  "source": "cron"
}
```

| Field | Values |
|-------|--------|
| `action` | `"pulse"`, `"review"` |
| `source` | `"cron"` (CLI/crontab), `"telegram"`, `"mariposa"` |
| `pid` | Process ID of the Python wrapper |
| `started_at` | ISO-8601 UTC timestamp |

The file is removed in a `finally` block when the operation completes (success or failure). This allows any client to observe whether an operation is running by reading a single file — no need to hold open an HTTP connection or track in-memory state.

**Staleness detection**: If the marker is older than 30 minutes AND the recorded PID is dead, `get_active_operation()` treats it as stale and deletes it. This handles SIGKILL or other unclean shutdowns.

Managed by `src/adjutant/core/lockfiles.py`:

| Function | What it does |
|----------|-------------|
| `set_active_operation(action, source, adj_dir)` | Write the marker |
| `get_active_operation(adj_dir)` | Read it, with staleness check |
| `clear_active_operation(adj_dir)` | Delete it |

### Entry points that write the marker

| Trigger | Code path | Source value |
|---------|-----------|-------------|
| `adjutant pulse` (CLI/crontab) | `lifecycle/cron.py` → `run_cron_prompt()` | `"cron"` |
| `adjutant review` (CLI/crontab) | `lifecycle/cron.py` → `run_cron_prompt()` | `"cron"` |
| Mariposa dashboard button | API spawns `adjutant pulse` → same as above | `"cron"` |
| Telegram `/pulse` | `commands.py` → `cmd_pulse()` | `"telegram"` |
| Telegram `/reflect` + `/confirm` | `commands.py` → `cmd_reflect_confirm()` | `"telegram"` |

### Post-completion notification

After a successful pulse or review (exit code 0), `run_cron_prompt()` reads `state/last_heartbeat.json` and sends a Telegram notification with a summary of what was found. This is budget-guarded and best-effort — failures are silently swallowed.

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
- **KILLED → OPERATIONAL**: `adjutant startup`. Detects and clears `KILLED` lockfile, restores crontab, then starts the listener fresh. Note: `adjutant start` will refuse if a `KILLED` lockfile is present.

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
| `cron.py` | Runs pulse and review prompts as subprocesses. Writes active-operation marker before start, clears on finish. Sends Telegram notification on success. |
| `update.py` | Compares `VERSION` against latest GitHub release, backs up, downloads, rsyncs new files into place. Personal files (`adjutant.yaml`, `.env`, `identity/`, `knowledge_bases/`) are never overwritten. |
