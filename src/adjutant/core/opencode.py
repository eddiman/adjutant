"""OpenCode invocation wrapper — run, reap, health check.

- opencode_run(): Invoke opencode with timeout + per-invocation orphan cleanup
- opencode_reap(): Periodic cleanup of orphaned language-server processes
- opencode_health_check(): Verify the binary is callable

Key contract:
  - opencode_run snapshots language-server PIDs before/after, kills orphans
  - asyncio.wait_for wraps proc.communicate() (NOT create_subprocess_exec)
  - Reaper has 2 kill rules: orphan, RSS runaway
    (The `stranded under web server` rule was removed when the native
    `opencode web` server was retired in favor of adjutant's own web/app.)
"""

from __future__ import annotations

import asyncio
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

import psutil

from adjutant.core.logging import adj_log
from adjutant.core.process import pid_is_alive


@dataclass
class OpenCodeResult:
    """Result from an opencode invocation."""

    stdout: str
    stderr: str
    returncode: int
    timed_out: bool = False


class OpenCodeNotFoundError(Exception):
    """Raised when the opencode binary is not on PATH."""


def _find_opencode() -> str:
    """Find the opencode binary.

    Resolution order:
      1. OPENCODE_BIN environment variable (explicit override)
      2. shutil.which("opencode") (standard PATH lookup)

    The env var is useful in cron or other minimal-PATH environments
    where /opt/homebrew/bin (or similar) is not in PATH.
    """
    env_bin = os.environ.get("OPENCODE_BIN")
    if env_bin:
        if os.path.isfile(env_bin) and os.access(env_bin, os.X_OK):
            return env_bin
        raise OpenCodeNotFoundError(f"OPENCODE_BIN={env_bin} is set but is not an executable file")
    path = shutil.which("opencode")
    if path is None:
        raise OpenCodeNotFoundError("opencode not found on PATH")
    return path


def _get_language_server_pids() -> set[int]:
    """Snapshot PIDs of bash-language-server and yaml-language-server processes."""
    pids: set[int] = set()
    for proc in psutil.process_iter(["pid", "cmdline"]):
        try:
            cmdline = " ".join(proc.info["cmdline"] or [])
            if "bash-language-server" in cmdline or "yaml-language-server" in cmdline:
                pids.add(proc.info["pid"])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return pids


def _kill_pids(pids: set[int]) -> None:
    """TERM then KILL a set of PIDs (synchronous)."""
    for pid in pids:
        try:
            os.kill(pid, 15)  # SIGTERM
        except (ProcessLookupError, PermissionError):
            pass

    if pids:
        import time

        time.sleep(1)
        for pid in pids:
            try:
                os.kill(pid, 9)  # SIGKILL
            except (ProcessLookupError, PermissionError):
                pass


async def opencode_run(
    args: list[str],
    timeout: float | None = None,
    env: dict[str, str] | None = None,
) -> OpenCodeResult:
    """Run opencode with optional timeout and per-invocation orphan cleanup.

    Matches bash opencode_run() from opencode.sh:
    - Snapshots language-server PIDs before/after
    - Kills any new orphans that appeared during the invocation
    - Wraps proc.communicate() with asyncio.wait_for (not create_subprocess_exec)

    Args:
        args: Arguments to pass to opencode (e.g. ["run", "--agent", "adjutant", ...]).
        timeout: Timeout in seconds. None for no timeout.
        env: Additional environment variables.

    Returns:
        OpenCodeResult with stdout, stderr, returncode, and timed_out flag.
    """
    opencode_bin = _find_opencode()

    # Snapshot language-server PIDs before invocation
    before_pids = await asyncio.to_thread(_get_language_server_pids)

    # Merge environment
    run_env = os.environ.copy()
    if env:
        run_env.update(env)

    proc = await asyncio.create_subprocess_exec(
        opencode_bin,
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=run_env,
    )

    timed_out = False
    try:
        if timeout:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        else:
            stdout_bytes, stderr_bytes = await proc.communicate()
    except TimeoutError:
        # Clean up the subprocess on timeout
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=2.0)
        except TimeoutError:
            proc.kill()
            await proc.wait()
        timed_out = True
        stdout_bytes = b""
        stderr_bytes = b""

    # Snapshot language-server PIDs after invocation
    after_pids = await asyncio.to_thread(_get_language_server_pids)

    # Kill any new orphans from this invocation
    new_pids = after_pids - before_pids
    if new_pids:
        await asyncio.to_thread(_kill_pids, new_pids)

    return OpenCodeResult(
        stdout=stdout_bytes.decode(errors="replace") if stdout_bytes else "",
        stderr=stderr_bytes.decode(errors="replace") if stderr_bytes else "",
        returncode=proc.returncode if proc.returncode is not None else -1,
        timed_out=timed_out,
    )


async def opencode_reap(adj_dir: Path | None = None) -> int:
    """Kill orphaned language-server processes.

    Two kill rules:
      (a) Orphaned: parent is PID 1 or parent process is gone
      (b) RSS runaway: exceeds memory threshold regardless of parentage

    (The `stranded under web server` rule was removed when the native
    `opencode web` server was retired — language servers now only leak
    on genuine orphan or memory runaway.)

    Args:
        adj_dir: Adjutant root directory. Defaults to $ADJ_DIR. Currently
                 unused but kept in the signature for API compatibility.

    Returns:
        Number of processes reaped.
    """
    if adj_dir is None:
        adj_dir = Path(os.environ.get("ADJ_DIR", Path.home() / ".adjutant"))

    rss_limit_kb = int(os.environ.get("OPENCODE_LANGSERVER_RSS_LIMIT_KB", "524288"))

    def _scan() -> list[tuple[int, str]]:
        """Scan for language servers to kill. Returns [(pid, reason), ...]."""
        targets: list[tuple[int, str]] = []
        for proc in psutil.process_iter(["pid", "ppid", "cmdline", "memory_info"]):
            try:
                cmdline = " ".join(proc.info["cmdline"] or [])
                if "bash-language-server" not in cmdline and "yaml-language-server" not in cmdline:
                    continue

                ppid = proc.info["ppid"]
                mem_info = proc.info["memory_info"]
                rss_kb = (mem_info.rss if mem_info else 0) // 1024

                # Rule (b): RSS runaway
                if rss_kb > rss_limit_kb:
                    targets.append((proc.info["pid"], "rss"))
                    continue

                # Rule (a): Orphaned — parent is init or gone
                is_orphan = ppid <= 1 or not pid_is_alive(ppid)
                if is_orphan:
                    targets.append((proc.info["pid"], "orphan"))
                    continue
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        return targets

    targets = await asyncio.to_thread(_scan)

    if not targets:
        return 0

    # Log and TERM
    for pid, reason in targets:
        adj_log("opencode", f"Reaping {reason}: pid={pid}")
        try:
            os.kill(pid, 15)  # SIGTERM
        except (ProcessLookupError, PermissionError):
            pass

    # Wait 1s, then KILL survivors
    await asyncio.sleep(1.0)
    for pid, _ in targets:
        try:
            os.kill(pid, 0)  # Check if still alive
            os.kill(pid, 9)  # SIGKILL
        except (ProcessLookupError, PermissionError):
            pass

    adj_log("opencode", f"Reaped {len(targets)} language-server process(es)")
    return len(targets)


async def opencode_health_check(adj_dir: Path | None = None) -> bool:
    """Verify the opencode binary is callable.

    Previously this was a two-stage probe that checked an HTTP endpoint on
    the native `opencode web` server and restarted it on failure. The
    `opencode web` lifecycle has been retired — adjutant's own `web/app`
    is now the remote access UI — so this is now a simple binary
    availability check.

    Args:
        adj_dir: Adjutant root directory. Accepted for signature
                 compatibility with the LLMBackend protocol; unused.

    Returns:
        True if the opencode binary can be located, False otherwise.
    """
    _ = adj_dir  # unused — kept for protocol compatibility
    try:
        _find_opencode()
        return True
    except OpenCodeNotFoundError:
        return False
