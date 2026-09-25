"""OpenCode invocation wrapper — run, reap, health check.

- opencode_run(): Invoke opencode with timeout + per-invocation orphan cleanup
- opencode_reap(): Periodic cleanup of orphaned language-server processes
- opencode_health_check(): Verify the binary is callable

Key contract:
  - opencode_run owns a separate process group for each invocation
  - timeout and cancellation terminate only that owned process group
  - partial stdout and stderr are preserved after timeout
  - Reaper has 2 kill rules: orphan, RSS runaway
    (The `stranded under web server` rule was removed when the native
    `opencode web` server was retired in favor of adjutant's own web/app.)
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import shutil
import signal
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import psutil

from adjutant.core.logging import adj_log
from adjutant.core.process import pid_is_alive

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

_PARTIAL_OUTPUT_LIMIT = 256 * 1024


@dataclass
class OpenCodeResult:
    """Result from an opencode invocation."""

    stdout: str
    stderr: str
    returncode: int
    timed_out: bool = False
    timeout_phase: str | None = None
    spawn_seconds: float = 0.0
    execution_seconds: float = 0.0
    cleanup_seconds: float = 0.0


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


async def opencode_run(
    args: list[str],
    timeout: float | None = None,
    startup_timeout: float | None = None,
    env: dict[str, str] | None = None,
    on_stdout_line: Callable[[str], Awaitable[None] | None] | None = None,
    on_spawn: Callable[[dict[str, int | float | None]], Awaitable[None] | None] | None = None,
) -> OpenCodeResult:
    """Run opencode with optional timeout and per-invocation orphan cleanup.

    Starts each invocation in its own process group so timeout and cancellation
    can terminate the owned process tree without scanning or signalling
    unrelated language-server processes.

    Args:
        args: Arguments to pass to opencode (e.g. ["run", "--agent", "adjutant", ...]).
        timeout: Timeout in seconds. None for no timeout.
        env: Additional environment variables.

    Returns:
        OpenCodeResult with stdout, stderr, returncode, and timed_out flag.
    """
    opencode_bin = _find_opencode()

    # Merge environment
    run_env = os.environ.copy()
    if env:
        run_env.update(env)

    spawn_started = time.monotonic()
    spawn_call = asyncio.create_subprocess_exec(
        opencode_bin,
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=run_env,
        start_new_session=True,
    )
    try:
        if startup_timeout:
            proc = await asyncio.wait_for(spawn_call, timeout=startup_timeout)
        else:
            proc = await spawn_call
    except TimeoutError:
        return OpenCodeResult(
            stdout="",
            stderr="OpenCode process startup timed out",
            returncode=-1,
            timed_out=True,
            timeout_phase="startup",
            spawn_seconds=time.monotonic() - spawn_started,
        )
    spawn_seconds = time.monotonic() - spawn_started
    if on_spawn is not None:
        try:
            process = psutil.Process(proc.pid)
            evidence: dict[str, int | float | None] = {
                "pid": proc.pid,
                "pid_create_time": process.create_time(),
                "process_group_id": os.getpgid(proc.pid),
            }
            outcome = on_spawn(evidence)
            if asyncio.iscoroutine(outcome):
                await outcome
        except (psutil.Error, OSError) as exc:
            adj_log("opencode", f"Could not record spawned process evidence: {exc}")

    timed_out = False
    execution_seconds = 0.0
    cleanup_seconds = 0.0
    stdout_buffer = _BoundedOutput(_PARTIAL_OUTPUT_LIMIT)
    stderr_buffer = _BoundedOutput(_PARTIAL_OUTPUT_LIMIT)
    stdout_task = asyncio.create_task(
        _drain_stream(proc.stdout, stdout_buffer, on_line=on_stdout_line)
    )
    stderr_task = asyncio.create_task(_drain_stream(proc.stderr, stderr_buffer))
    wait_task = asyncio.create_task(proc.wait())
    execution_started = time.monotonic()
    try:
        if timeout:
            await asyncio.wait_for(asyncio.shield(wait_task), timeout=timeout)
        else:
            await wait_task
        execution_seconds = time.monotonic() - execution_started
    except TimeoutError:
        timed_out = True
        execution_seconds = time.monotonic() - execution_started
        cleanup_started = time.monotonic()
        await _terminate_process(proc)
        await wait_task
        cleanup_seconds = time.monotonic() - cleanup_started
    except asyncio.CancelledError:
        await _terminate_process(proc)
        with contextlib.suppress(Exception, asyncio.CancelledError):
            await asyncio.shield(wait_task)
            await asyncio.shield(asyncio.gather(stdout_task, stderr_task))
        raise

    await asyncio.gather(stdout_task, stderr_task)
    stdout_bytes = stdout_buffer.value()
    stderr_bytes = stderr_buffer.value()

    return OpenCodeResult(
        stdout=stdout_bytes.decode(errors="replace") if stdout_bytes else "",
        stderr=stderr_bytes.decode(errors="replace") if stderr_bytes else "",
        returncode=proc.returncode if proc.returncode is not None else -1,
        timed_out=timed_out,
        timeout_phase="runtime" if timed_out else None,
        spawn_seconds=spawn_seconds,
        execution_seconds=execution_seconds,
        cleanup_seconds=cleanup_seconds,
    )


async def _terminate_process(proc: asyncio.subprocess.Process) -> None:
    """Terminate and reap one invocation's owned process group."""
    _signal_process_group(proc, signal.SIGTERM)
    if proc.returncode is not None:
        return
    try:
        await asyncio.wait_for(proc.wait(), timeout=2.0)
    except TimeoutError:
        _signal_process_group(proc, signal.SIGKILL)
        await proc.wait()


def _signal_process_group(proc: asyncio.subprocess.Process, sig: signal.Signals) -> None:
    """Signal the process group created for one OpenCode invocation."""
    try:
        os.killpg(proc.pid, sig)
    except ProcessLookupError:
        pass
    except PermissionError:
        with contextlib.suppress(ProcessLookupError):
            proc.send_signal(sig)


def _bounded_partial_output(output: bytes) -> bytes:
    """Retain the beginning and end of partial output within a fixed limit."""
    if len(output) <= _PARTIAL_OUTPUT_LIMIT:
        return output

    marker = b"\n... partial output truncated ...\n"
    retained = _PARTIAL_OUTPUT_LIMIT - len(marker)
    head_size = retained // 2
    tail_size = retained - head_size
    return output[:head_size] + marker + output[-tail_size:]


class _BoundedOutput:
    """Retain the beginning and rolling end of a byte stream."""

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self._head_limit = limit // 2
        self._tail_limit = limit - self._head_limit
        self._head = bytearray()
        self._tail = bytearray()
        self._truncated = False

    def append(self, chunk: bytes) -> None:
        remaining = chunk
        if len(self._head) < self._head_limit:
            take = min(self._head_limit - len(self._head), len(remaining))
            self._head.extend(remaining[:take])
            remaining = remaining[take:]
        if remaining:
            self._tail.extend(remaining)
            if len(self._tail) > self._tail_limit:
                del self._tail[: len(self._tail) - self._tail_limit]
                self._truncated = True

    def value(self) -> bytes:
        if not self._truncated:
            return bytes(self._head + self._tail)
        marker = b"\n... partial output truncated ...\n"
        tail_budget = max(0, self.limit - len(self._head) - len(marker))
        return bytes(self._head) + marker + bytes(self._tail[-tail_budget:])


async def _drain_stream(
    stream: asyncio.StreamReader | None,
    output: _BoundedOutput,
    *,
    on_line: Callable[[str], Awaitable[None] | None] | None = None,
) -> None:
    """Drain a pipe continuously and optionally publish complete lines."""
    if stream is None:
        return
    pending = bytearray()
    while True:
        chunk = await stream.read(65536)
        if not chunk:
            break
        output.append(chunk)
        if on_line is None:
            continue
        pending.extend(chunk)
        while True:
            newline = pending.find(b"\n")
            if newline < 0:
                break
            line = bytes(pending[:newline])
            del pending[: newline + 1]
            await _publish_line(on_line, line)
    if on_line is not None and pending:
        await _publish_line(on_line, bytes(pending))


async def _publish_line(
    callback: Callable[[str], Awaitable[None] | None],
    line: bytes,
) -> None:
    try:
        outcome = callback(line.decode(errors="replace"))
        if asyncio.iscoroutine(outcome):
            await outcome
    except Exception as exc:  # noqa: BLE001 - parser observers cannot block pipe draining
        adj_log("opencode", f"stdout event callback failed: {exc}")


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
        try:
            processes = list(
                psutil.process_iter(["pid", "ppid", "cmdline", "memory_info"])
            )
        except (PermissionError, psutil.Error) as exc:
            adj_log("opencode", f"Process scan unavailable: {exc}")
            return targets
        for proc in processes:
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
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.kill(pid, 15)  # SIGTERM

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
