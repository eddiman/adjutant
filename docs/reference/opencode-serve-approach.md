# opencode serve — Hardened Lifecycle Approach

Reference document for the approach implemented in commit `c2488e7` and reverted in `9be78f2`.

Reverted on 2026-03-08 because it introduced regressions. Preserved here so the design can be revisited cleanly.

---

## Why it was written

At the time of writing, `opencode web` was renamed to `opencode serve` in the opencode binary. The commit updated all references and added two hardening measures on top of the rename:

1. **Fixed-port binding** — `startup.sh` passes `--port ${OPENCODE_WEB_PORT:-4096}` when launching `opencode serve`, so the health check always hits the right process and a second accidental instance cannot silently bind a random port.
2. **Multi-PID reaper** — `opencode_reap` collected all running `opencode serve` PIDs via `pgrep` on every sweep (not just the one written in `opencode_web.pid`), catching language-server orphans under stale or double-started serve processes.

---

## Changes made in c2488e7

### `scripts/lifecycle/startup.sh`

```bash
# Before
nohup opencode web > "${ADJ_DIR}/state/opencode_web.log" 2>&1 &

# After
_STARTUP_WEB_PORT="${OPENCODE_WEB_PORT:-4096}"
nohup opencode serve --port "${_STARTUP_WEB_PORT}" --mdns > "${ADJ_DIR}/state/opencode_web.log" 2>&1 &
```

Orphan cleanup on double-start:
```bash
_running_web_pid="$(pgrep -f "opencode serve" 2>/dev/null | head -1)"
if [ -n "${_running_web_pid}" ]; then
  echo "  Killing orphaned opencode serve process(es)..."
  pkill -TERM -f "opencode serve" 2>/dev/null || true
  sleep 1
  pkill -KILL -f "opencode serve" 2>/dev/null || true
fi
```

### `scripts/common/opencode.sh` — `opencode_reap`

Old approach (single tracked PID):
```bash
local _web_pid
_web_pid="$(_opencode_web_pid)"   # reads opencode_web.pid

# Only reaps language servers whose parent == tracked PID
if [ -n "${_web_pid}" ] && [ "${_ppid}" = "${_web_pid}" ]; then
  kill -TERM "${_pid}" 2>/dev/null || true
fi
```

New approach (all serve PIDs):
```bash
local _all_serve_pids
_all_serve_pids="$(pgrep -f 'opencode serve' 2>/dev/null || true)"

# Reaps language servers whose parent is ANY running serve process
for _serve_pid in ${_all_serve_pids}; do
  if [ "${_ppid}" = "${_serve_pid}" ]; then
    kill -TERM "${_pid}" 2>/dev/null || true
    _killed=$((_killed + 1))
    break
  fi
done
```

The multi-PID approach handles the failure mode where two `opencode serve` processes run simultaneously after an unclean restart — the old process accumulates language-server children indefinitely because the reaper only checked the PID-file entry.

### Other files touched

All references to `opencode web` → `opencode serve` across:
- `scripts/lifecycle/restart.sh`
- `scripts/messaging/telegram/commands.sh`
- `scripts/observability/status.sh`
- `scripts/setup/uninstall.sh`
- `tests/integration/commands.bats`
- `tests/run`
- All docs (`AGENTS.md`, `docs/architecture/*`, `docs/development/testing.md`, `docs/guides/commands.md`)

---

## Why it was reverted

The rename introduced test regressions and the `pgrep -f 'opencode serve'` pattern in the multi-PID reaper matched too broadly in some environments. Rather than debug both issues under time pressure, the whole commit was reverted and the `opencode web` lifecycle restored.

The RSS-based runaway kill (rule c in `opencode_reap`) and the other session fixes (timeout reductions, reaper interval, KB logging) were re-applied on top of the revert in commit `66db21e`.

---

## How to re-apply

If `opencode serve` becomes the stable command name in a future opencode release:

1. Cherry-pick `c2488e7` onto the current HEAD, resolve any conflicts.
2. Or apply the two hardening measures manually:
   - Add `--port "${OPENCODE_WEB_PORT:-4096}"` to the `opencode serve` invocation in `startup.sh`.
   - Replace the single-`_web_pid` block in `opencode_reap` with the `pgrep -f 'opencode serve'` multi-PID loop shown above.
3. Do a global find-and-replace of `opencode web` → `opencode serve` across all scripts and docs.
4. Run the full test suite before releasing.
