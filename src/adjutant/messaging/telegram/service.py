"""Telegram listener lifecycle manager — start/stop/restart/status.

Replaces: scripts/messaging/telegram/service.sh

Manages the long-running listener process that polls Telegram getUpdates.
The listener runs as a subprocess launched via sys.executable -m
adjutant.messaging.telegram.listener so it inherits the same Python
environment.

PID tracking (three-tier, priority order):
  1. LOCKPID (adj_dir/state/listener.lock/pid) — written by the listener itself
  2. PIDFILE (adj_dir/state/telegram.pid) — written by this launcher
  3. psutil find_by_cmdline — catches orphans that lost both files
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

from adjutant.core.logging import adj_log
from adjutant.core.process import find_by_cmdline, kill_graceful, pid_is_alive, read_pid_file


_LISTENER_MODULE = "adjutant.messaging.telegram.listener"
_PIDFILE_NAME = "telegram.pid"
_LOCKDIR_NAME = "listener.lock"
_LOCKPID_NAME = "pid"
_LOGFILE_NAME = "telegram_listener.log"


def _paths(adj_dir: Path) -> tuple[Path, Path, Path, Path]:
    """Return (pidfile, lockdir, lockpid, logfile)."""
    state = adj_dir / "state"
    pidfile = state / _PIDFILE_NAME
    lockdir = state / _LOCKDIR_NAME
    lockpid = lockdir / _LOCKPID_NAME
    logfile = state / _LOGFILE_NAME
    return pidfile, lockdir, lockpid, logfile


def _find_listener_pid(adj_dir: Path) -> int | None:
    """Return the PID of the running listener, or None if not running.

    Priority:
      1. listener.lock/pid — the listener writes its own PID here
      2. telegram.pid — written by this launcher
      3. psutil find_by_cmdline — orphan detection
    """
    _, lockdir, lockpid, _ = _paths(adj_dir)

    # 1. Lock PID (authoritative)
    if lockdir.is_dir() and lockpid.is_file():
        try:
            pid = int(lockpid.read_text().strip())
            if pid_is_alive(pid):
                return pid
        except (ValueError, OSError):
            pass

    # 2. telegram.pid
    pidfile, _, _, _ = _paths(adj_dir)
    if pidfile.is_file():
        pid = read_pid_file(pidfile)
        if pid is not None:
            return pid

    # 3. psutil fallback
    procs = find_by_cmdline(_LISTENER_MODULE)
    if procs:
        pid = procs[0].pid
        if pid_is_alive(pid):
            return pid

    return None


def listener_start(adj_dir: Path) -> str:
    """Start the Telegram listener.

    Returns:
        Human-readable status string.
    """
    from adjutant.core.lockfiles import check_killed

    if not check_killed(adj_dir):
        return "Cannot start: system is in KILLED state."

    pidfile, lockdir, lockpid, logfile = _paths(adj_dir)

    existing_pid = _find_listener_pid(adj_dir)
    if existing_pid is not None:
        # Sync pidfile in case it drifted
        try:
            pidfile.write_text(str(existing_pid))
        except OSError:
            pass
        return f"Already running (PID {existing_pid})"

    # Clean up stale tracking files
    try:
        pidfile.unlink(missing_ok=True)
    except OSError:
        pass
    import shutil

    shutil.rmtree(lockdir, ignore_errors=True)

    # Ensure state dir and log file parent exist
    adj_dir.joinpath("state").mkdir(parents=True, exist_ok=True)
    logfile.parent.mkdir(parents=True, exist_ok=True)

    # Launch the listener as a detached subprocess
    log_fh = open(logfile, "a")
    proc = subprocess.Popen(
        [sys.executable, "-m", _LISTENER_MODULE],
        stdout=log_fh,
        stderr=log_fh,
        stdin=subprocess.DEVNULL,
        start_new_session=True,  # detach — equivalent to nohup + disown
    )
    log_fh.close()

    # Write launcher PID immediately
    try:
        pidfile.write_text(str(proc.pid))
    except OSError:
        pass

    adj_log("service", f"Listener launched (launcher PID {proc.pid})")

    # Wait up to 5 seconds for the listener to write its own PID into lockpid
    started = False
    for _ in range(5):
        time.sleep(1)
        if lockpid.is_file():
            try:
                real_pid = int(lockpid.read_text().strip())
                if pid_is_alive(real_pid):
                    # Sync pidfile to the real listener PID
                    try:
                        pidfile.write_text(str(real_pid))
                    except OSError:
                        pass
                    adj_log("service", f"Listener confirmed (PID {real_pid})")
                    started = True
                    return f"Started (PID {real_pid})"
            except (ValueError, OSError):
                pass

    if not started:
        # Check if the launcher PID is still alive (may not have created lock yet)
        if pid_is_alive(proc.pid):
            return f"Started (PID {proc.pid}) — but listener.lock not yet created"
        else:
            try:
                pidfile.unlink(missing_ok=True)
            except OSError:
                pass
            return f"Failed to start (check {logfile})"

    return f"Started (PID {proc.pid})"


def listener_stop(adj_dir: Path) -> str:
    """Stop the Telegram listener.

    Returns:
        Human-readable status string.
    """
    pidfile, lockdir, _, _ = _paths(adj_dir)

    pid = _find_listener_pid(adj_dir)
    if pid is not None:
        kill_graceful(pid, timeout=5.0)
        msg = f"Stopped (was PID {pid})"
    else:
        msg = "Not running"

    # Also kill any orphans found via psutil
    for proc in find_by_cmdline(_LISTENER_MODULE):
        try:
            kill_graceful(proc.pid, timeout=2.0)
        except Exception:
            pass

    # Clean up tracking files
    try:
        pidfile.unlink(missing_ok=True)
    except OSError:
        pass
    import shutil

    shutil.rmtree(lockdir, ignore_errors=True)

    adj_log("service", msg)
    return msg


def listener_restart(adj_dir: Path) -> str:
    """Stop then start the listener.

    Returns:
        Human-readable status string combining stop + start messages.
    """
    stop_msg = listener_stop(adj_dir)
    time.sleep(1)
    start_msg = listener_start(adj_dir)
    return f"{stop_msg}; {start_msg}"


def listener_status(adj_dir: Path) -> str:
    """Return the current listener status string.

    Returns:
        'Running (PID N)' or 'Stopped'.
    """
    pidfile, lockdir, _, _ = _paths(adj_dir)

    pid = _find_listener_pid(adj_dir)
    if pid is not None:
        # Sync pidfile if it drifted
        try:
            pidfile.write_text(str(pid))
        except OSError:
            pass
        return f"Running (PID {pid})"
    else:
        # Clean up stale files
        try:
            pidfile.unlink(missing_ok=True)
        except OSError:
            pass
        import shutil

        shutil.rmtree(lockdir, ignore_errors=True)
        return "Stopped"


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: service.py {start|stop|restart|status}.

    Returns:
        Exit code (0 on success, 1 on error).
    """
    import os

    adj_dir_raw = os.environ.get("ADJ_DIR", "").strip()
    if not adj_dir_raw:
        print("Error: ADJ_DIR environment variable not set.", file=sys.stderr)
        return 1

    adj_dir = Path(adj_dir_raw)

    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print("Usage: service.py {start|stop|restart|status}", file=sys.stderr)
        return 1

    command = args[0]

    if command == "start":
        print(listener_start(adj_dir))
    elif command == "stop":
        print(listener_stop(adj_dir))
    elif command == "restart":
        print(listener_restart(adj_dir))
    elif command == "status":
        print(listener_status(adj_dir))
    else:
        print(f"Usage: service.py {{start|stop|restart|status}}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
