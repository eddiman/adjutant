"""Process management — psutil wrappers, PidLock, PID file handling.

Replaces bash patterns from opencode.sh, emergency_kill.sh, and listener.sh:
- Two-phase TERM→KILL graceful shutdown
- Process tree killing (replaces pkill -P)
- Command-line pattern search (replaces pgrep -f)
- PID file reading with stale detection (replaces kill -0 checks)
- mkdir-based atomic locking with PID storage (replaces mkdir + pid file pattern)
"""

from __future__ import annotations

import contextlib
import os
import shutil
from typing import TYPE_CHECKING

import psutil

from adjutant.core.logging import adj_log

if TYPE_CHECKING:
    from pathlib import Path


class PidLock:
    """mkdir-based atomic lock with PID storage and stale-lock recovery.

    Matches bash listener.sh:56-72:
    - mkdir for atomic acquire (no race conditions)
    - PID stored in lock_dir/pid (read by emergency_kill)
    - Stale lock detection: if PID is dead, remove and re-acquire
    """

    def __init__(self, lock_dir: Path) -> None:
        self.lock_dir = lock_dir
        self.pid_file = lock_dir / "pid"

    def acquire(self) -> bool:
        """Acquire the lock. Returns True on success, False if held by live process."""
        try:
            self.lock_dir.mkdir(parents=False, exist_ok=False)
        except FileExistsError:
            # Check if holder is still alive (stale lock detection)
            existing_pid = self._read_pid()
            if existing_pid and pid_is_alive(existing_pid):
                return False  # Another instance is genuinely running
            # Stale lock — previous process crashed without cleanup
            adj_log("process", f"Removing stale lock (PID {existing_pid} no longer running)")
            shutil.rmtree(self.lock_dir, ignore_errors=True)
            try:
                self.lock_dir.mkdir(parents=False, exist_ok=False)
            except FileExistsError:
                return False  # Race condition — another instance beat us
        self.pid_file.write_text(str(os.getpid()))
        return True

    def release(self) -> None:
        """Release the lock (called in finally/atexit)."""
        shutil.rmtree(self.lock_dir, ignore_errors=True)

    def _read_pid(self) -> int | None:
        """Read the PID from the lock directory."""
        try:
            return int(self.pid_file.read_text().strip())
        except (FileNotFoundError, ValueError):
            return None

    @property
    def held_pid(self) -> int | None:
        """Return the PID holding this lock, or None if not locked/stale."""
        pid = self._read_pid()
        if pid is not None and pid_is_alive(pid):
            return pid
        return None


def kill_graceful(pid: int, timeout: float = 2.0) -> bool:
    """Two-phase TERM→KILL. Returns True if process was terminated.

    Matches bash pattern: kill -TERM, sleep, kill -9.
    """
    try:
        proc = psutil.Process(pid)
        proc.terminate()  # SIGTERM
        try:
            proc.wait(timeout=timeout)
            return True
        except psutil.TimeoutExpired:
            proc.kill()  # SIGKILL
            proc.wait(timeout=1.0)
            return True
    except psutil.NoSuchProcess:
        return False


def kill_process_tree(pid: int, timeout: float = 2.0) -> None:
    """Kill a process and all its children (replaces pkill -P).

    TERM parent + children, wait, then KILL survivors.
    """
    try:
        parent = psutil.Process(pid)
        children = parent.children(recursive=True)
        # TERM parent + children
        for p in children + [parent]:
            with contextlib.suppress(psutil.NoSuchProcess):
                p.terminate()
        # Wait, then KILL survivors
        _, alive = psutil.wait_procs(children + [parent], timeout=timeout)
        for p in alive:
            with contextlib.suppress(psutil.NoSuchProcess):
                p.kill()
    except psutil.NoSuchProcess:
        pass


def find_by_cmdline(pattern: str) -> list[psutil.Process]:
    """Find processes by command-line pattern (replaces pgrep -f).

    Args:
        pattern: Substring to search for in the full command line.

    Returns:
        List of matching processes (excluding the current process).
    """
    results: list[psutil.Process] = []
    my_pid = os.getpid()
    for proc in psutil.process_iter(["pid", "cmdline"]):
        try:
            if proc.info["pid"] == my_pid:
                continue
            cmdline = " ".join(proc.info["cmdline"] or [])
            if pattern in cmdline:
                results.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return results


def pid_is_alive(pid: int) -> bool:
    """Check if PID exists (replaces kill -0).

    Returns True if the process exists. PermissionError means it exists
    but we can't signal it — still alive.
    """
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # Process exists, we just can't signal it


def read_pid_file(path: Path) -> int | None:
    """Read and validate a PID file.

    Returns:
        The PID if the file exists and the process is alive, else None.
    """
    try:
        content = path.read_text().strip()
        pid = int(content)
        if pid_is_alive(pid):
            return pid
        return None  # Stale PID
    except (FileNotFoundError, ValueError, OSError):
        return None
