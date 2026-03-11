"""OpenCode invocation wrapper — run, reap, health check.

Replaces bash opencode.sh:
- opencode_run(): Invoke opencode with timeout + per-invocation orphan cleanup
- opencode_reap(): Periodic cleanup of orphaned language-server processes
- opencode_health_check(): Two-stage probe (HTTP ping + API call) with restart

Key contract:
  - opencode_run snapshots language-server PIDs before/after, kills orphans
  - asyncio.wait_for wraps proc.communicate() (NOT create_subprocess_exec)
  - Reaper has 3 kill rules: orphan, stranded under web, RSS runaway
"""

from __future__ import annotations

import asyncio
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

import psutil

from adjutant.core.logging import adj_log
from adjutant.core.process import kill_graceful, pid_is_alive, read_pid_file


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
    """Find the opencode binary on PATH."""
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
    except asyncio.TimeoutError:
        # Clean up the subprocess on timeout
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=2.0)
        except asyncio.TimeoutError:
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

    Matches bash opencode_reap() from opencode.sh — three kill rules:
      (a) Orphaned: parent is PID 1 or parent process is gone
      (b) Stranded: parent is the opencode web server PID
      (c) RSS runaway: exceeds memory threshold regardless of parentage

    Args:
        adj_dir: Adjutant root directory. Defaults to $ADJ_DIR.

    Returns:
        Number of processes reaped.
    """
    if adj_dir is None:
        adj_dir = Path(os.environ.get("ADJ_DIR", Path.home() / ".adjutant"))

    web_pid_file = adj_dir / "state" / "opencode_web.pid"
    web_pid = read_pid_file(web_pid_file)

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

                # Rule (c): RSS runaway
                if rss_kb > rss_limit_kb:
                    targets.append((proc.info["pid"], "rss"))
                    continue

                # Rule (a): Orphaned — parent is init or gone
                is_orphan = ppid <= 1 or not pid_is_alive(ppid)
                if is_orphan:
                    targets.append((proc.info["pid"], "orphan"))
                    continue

                # Rule (b): Stranded under web server
                if web_pid is not None and ppid == web_pid:
                    targets.append((proc.info["pid"], "stranded"))
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
    """Two-stage health probe with restart-and-retry on failure.

    Matches bash opencode_health_check() from opencode.sh:
    - Stage 1: HTTP ping to opencode web server root path
    - Stage 2: Real API call with cheapest model
    - On failure: restart opencode web, wait up to 20s for recovery

    Args:
        adj_dir: Adjutant root directory. Defaults to $ADJ_DIR.

    Returns:
        True if healthy (or recovered). False if unrecoverable.
    """
    if adj_dir is None:
        adj_dir = Path(os.environ.get("ADJ_DIR", Path.home() / ".adjutant"))

    port = int(os.environ.get("OPENCODE_WEB_PORT", "4096"))
    base_url = f"http://localhost:{port}/"

    async def _http_ping() -> bool:
        """Stage 1: HTTP ping."""
        pid_file = adj_dir / "state" / "opencode_web.pid"
        if not read_pid_file(pid_file):
            return False
        try:
            import httpx

            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(base_url)
                return resp.status_code == 200
        except Exception:
            return False

    async def _api_probe() -> bool:
        """Stage 2: Real API call with cheapest model."""
        try:
            result = await opencode_run(
                ["run", "--model", "anthropic/claude-haiku-4-5", "--format", "json", "ping"],
                timeout=8,
            )
            # Accept exit 0 OR any JSON with "type" key
            return result.returncode == 0 or '"type"' in result.stdout
        except OpenCodeNotFoundError:
            return False

    # Try probe
    if await _http_ping() and await _api_probe():
        return True

    adj_log("opencode", "Health check failed — restarting opencode web server")

    # Attempt restart via lifecycle restart script
    restart_sh = adj_dir / "scripts" / "lifecycle" / "restart.sh"
    if restart_sh.exists():
        restart_proc = await asyncio.create_subprocess_exec(
            "bash",
            str(restart_sh),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        # Don't await — poll for recovery instead

    # Wait up to 20s for recovery via HTTP polling
    for _ in range(20):
        await asyncio.sleep(1.0)
        if await _http_ping():
            adj_log("opencode", "Health check recovered after restart")
            return True

    adj_log("opencode", "Health check failed — could not recover after restart")
    return False
