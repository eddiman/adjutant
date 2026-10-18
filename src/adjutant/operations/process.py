"""Lifecycle control for the durable operation worker process."""

from __future__ import annotations

import contextlib
import shutil
import subprocess
import sys
import time
from typing import TYPE_CHECKING

from adjutant.core.config import load_typed_config
from adjutant.core.logging import adj_log
from adjutant.core.process import find_by_cmdline, kill_graceful, pid_is_alive, read_pid_file

if TYPE_CHECKING:
    from pathlib import Path

_MODULE = "adjutant.operations.daemon"
_PIDFILE_NAME = "operation-worker.pid"
_LOCKDIR_NAME = "operation-worker.lock"
_LOGFILE_NAME = "operation-worker.log"


def _paths(adj_dir: Path) -> tuple[Path, Path, Path, Path]:
    state = adj_dir / "state"
    lockdir = state / _LOCKDIR_NAME
    return (
        state / _PIDFILE_NAME,
        lockdir,
        lockdir / "pid",
        state / _LOGFILE_NAME,
    )


def _find_pid(adj_dir: Path) -> int | None:
    pidfile, _, lockpid, _ = _paths(adj_dir)
    for path in (lockpid, pidfile):
        pid = read_pid_file(path)
        if pid is not None and pid_is_alive(pid):
            return pid
    matches = find_by_cmdline(_MODULE)
    return matches[0].pid if matches else None


def worker_start(adj_dir: Path) -> str:
    config = load_typed_config(adj_dir / "adjutant.yaml")
    if not config.operations.enabled:
        return "Durable operation worker disabled"
    existing = _find_pid(adj_dir)
    if existing is not None:
        return f"Operation worker already running (PID {existing})"

    pidfile, lockdir, lockpid, logfile = _paths(adj_dir)
    pidfile.parent.mkdir(parents=True, exist_ok=True)
    pidfile.unlink(missing_ok=True)
    shutil.rmtree(lockdir, ignore_errors=True)
    with open(logfile, "a") as log_handle:
        process = subprocess.Popen(
            [sys.executable, "-m", _MODULE],
            stdout=log_handle,
            stderr=log_handle,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    pidfile.write_text(str(process.pid))
    for _ in range(5):
        time.sleep(1)
        locked_pid = read_pid_file(lockpid)
        if locked_pid is not None and pid_is_alive(locked_pid):
            pidfile.write_text(str(locked_pid))
            adj_log("operations", f"Operation worker confirmed (PID {locked_pid})")
            return f"Operation worker started (PID {locked_pid})"
    if pid_is_alive(process.pid):
        return f"Operation worker started (PID {process.pid}), lock pending"
    pidfile.unlink(missing_ok=True)
    return f"Operation worker failed to start (check {logfile})"


def worker_stop(adj_dir: Path) -> str:
    pidfile, lockdir, _, _ = _paths(adj_dir)
    pid = _find_pid(adj_dir)
    if pid is not None:
        kill_graceful(pid, timeout=10.0)
        result = f"Operation worker stopped (was PID {pid})"
    else:
        result = "Operation worker not running"
    for process in find_by_cmdline(_MODULE):
        with contextlib.suppress(Exception):
            kill_graceful(process.pid, timeout=2.0)
    pidfile.unlink(missing_ok=True)
    shutil.rmtree(lockdir, ignore_errors=True)
    try:
        from adjutant.core.opencode_server import stop_managed_opencode_server

        server_stopped = stop_managed_opencode_server(adj_dir)
    except Exception as exc:  # noqa: BLE001 - shutdown remains best effort
        adj_log("operations", f"Managed OpenCode server stop failed: {exc}")
        server_stopped = False
    if server_stopped:
        result += "; managed OpenCode server stopped"
    adj_log("operations", result)
    return result


def worker_status(adj_dir: Path) -> str:
    pid = _find_pid(adj_dir)
    return f"Running (PID {pid})" if pid is not None else "Stopped"
