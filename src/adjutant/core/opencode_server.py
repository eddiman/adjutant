"""Owned persistent OpenCode server and its small HTTP control client.

The server is local-only, protected with a generated password, and identified by
both PID and process creation time before Adjutant sends it a signal. This keeps
server reuse separate from the durable operation database and prevents stale PID
files from targeting an unrelated process.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import os
import secrets
import signal
import socket
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any

import psutil

from adjutant.core.logging import adj_log
from adjutant.core.opencode import OpenCodeNotFoundError, _find_opencode

if TYPE_CHECKING:
    from pathlib import Path

    from adjutant.core.config import PersistentOpenCodeConfig


class OpenCodeServerError(RuntimeError):
    """Raised when the managed server cannot satisfy its control contract."""


class OpenCodeServerDrainingError(OpenCodeServerError):
    """Raised when new work must avoid an instance that is draining."""


@dataclass(frozen=True)
class OpenCodeServerEndpoint:
    """Connection details for one verified server instance."""

    url: str
    username: str
    password: str
    instance_id: str
    pid: int
    version: str | None
    reused: bool
    startup_seconds: float
    rss_bytes: int

    def client(self, *, timeout: float = 10.0) -> OpenCodeServerClient:
        return OpenCodeServerClient(
            self.url,
            username=self.username,
            password=self.password,
            timeout=timeout,
        )


@dataclass
class OpenCodeServerState:
    """Non-secret ownership state persisted beside the worker state."""

    instance_id: str
    pid: int
    pid_create_time: float
    url: str
    port: int
    username: str
    status: str
    started_at: float
    last_used_at: float
    version: str | None = None
    restart_count: int = 0
    last_error: str | None = None


class OpenCodeServerClient:
    """Authenticated calls to documented OpenCode server endpoints."""

    def __init__(
        self,
        base_url: str,
        *,
        username: str,
        password: str,
        timeout: float = 10.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.timeout = timeout

    def _request(
        self,
        path: str,
        *,
        method: str = "GET",
        body: dict[str, Any] | None = None,
        workdir: Path | None = None,
    ) -> Any:
        separator = "&" if "?" in path else "?"
        query = ""
        if workdir is not None:
            query = separator + urllib.parse.urlencode({"directory": str(workdir)})
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(
            f"{self.base_url}{path}{query}",
            data=data,
            method=method,
            headers={
                "Authorization": "Basic "
                + base64.b64encode(f"{self.username}:{self.password}".encode()).decode(),
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:  # noqa: S310
                raw = response.read()
        except (OSError, urllib.error.HTTPError, urllib.error.URLError) as exc:
            raise OpenCodeServerError(f"OpenCode server request failed: {exc}") from exc
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise OpenCodeServerError("OpenCode server returned invalid JSON") from exc

    def health(self) -> dict[str, Any]:
        result = self._request("/global/health")
        if not isinstance(result, dict) or result.get("healthy") is not True:
            raise OpenCodeServerError("OpenCode server health response was not healthy")
        return result

    def abort_session(self, session_id: str, *, workdir: Path | None = None) -> bool:
        result = self._request(
            f"/session/{urllib.parse.quote(session_id, safe='')}/abort",
            method="POST",
            workdir=workdir,
        )
        return result is True

    def session_status(self, *, workdir: Path | None = None) -> dict[str, Any]:
        result = self._request("/session/status", workdir=workdir)
        return result if isinstance(result, dict) else {}

    def session_messages(
        self,
        session_id: str,
        *,
        workdir: Path | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        path = f"/session/{urllib.parse.quote(session_id, safe='')}/message"
        query_workdir = workdir
        result = self._request(f"{path}?limit={limit}", workdir=query_workdir)
        return result if isinstance(result, list) else []

    def delete_session(self, session_id: str, *, workdir: Path | None = None) -> bool:
        result = self._request(
            f"/session/{urllib.parse.quote(session_id, safe='')}",
            method="DELETE",
            workdir=workdir,
        )
        return result is True


class ManagedOpenCodeServer:
    """Start, verify, reuse, drain, and stop one Adjutant-owned server."""

    def __init__(self, adj_dir: Path, config: PersistentOpenCodeConfig) -> None:
        self.adj_dir = adj_dir
        self.config = config
        self.state_dir = adj_dir / "state"
        self.state_path = self.state_dir / "opencode-server.json"
        self.secret_path = self.state_dir / "opencode-server.secret"
        self.log_path = self.state_dir / "opencode-server.log"
        self._lock = asyncio.Lock()

    async def ensure_ready(self) -> OpenCodeServerEndpoint:
        """Return a healthy endpoint, restarting stale or oversized ownership."""
        async with self._lock:
            password = self._password()
            state = self._read_state()
            if (
                state is not None
                and state.status == "failed"
                and time.time() - state.last_used_at < self.config.restart_backoff_seconds
            ):
                wait_seconds = self.config.restart_backoff_seconds - (
                    time.time() - state.last_used_at
                )
                raise OpenCodeServerError(
                    f"OpenCode server restart backoff active for {wait_seconds:.1f}s"
                )
            if state is not None and self._owned_process(state) is not None:
                if state.status == "draining":
                    raise OpenCodeServerDrainingError("OpenCode server is draining")
                rss = self._rss_bytes(state.pid)
                hard = self._memory_bytes(self.config.hard_memory_mb)
                soft = self._memory_bytes(self.config.soft_memory_mb)
                if soft is not None and rss > soft and not (hard is not None and rss > hard):
                    state.status = "draining"
                    self._write_state(state)
                    raise OpenCodeServerDrainingError(
                        "OpenCode server exceeded its soft memory limit and is draining"
                    )
                should_restart = bool(hard is not None and rss > hard)
                if not should_restart:
                    client = OpenCodeServerClient(
                        state.url,
                        username=state.username,
                        password=password,
                        timeout=float(self.config.health_interval_seconds),
                    )
                    try:
                        health = await asyncio.to_thread(client.health)
                    except OpenCodeServerError:
                        should_restart = True
                    else:
                        state.status = "ready"
                        state.version = str(health.get("version") or state.version or "") or None
                        state.last_used_at = time.time()
                        self._write_state(state)
                        return self._endpoint(
                            state,
                            password=password,
                            reused=True,
                            startup_seconds=0.0,
                        )
                if should_restart:
                    state.status = "draining"
                    self._write_state(state)
                    await asyncio.to_thread(self._stop_owned, state)

            return await self._start(password, previous=state)

    async def _start(
        self,
        password: str,
        *,
        previous: OpenCodeServerState | None,
    ) -> OpenCodeServerEndpoint:
        try:
            binary = _find_opencode()
        except OpenCodeNotFoundError as exc:
            raise OpenCodeServerError(str(exc)) from exc
        self.state_dir.mkdir(parents=True, exist_ok=True)
        port = self._available_port()
        instance_id = f"ocs-{uuid.uuid4().hex}"
        env = os.environ.copy()
        env["OPENCODE_SERVER_USERNAME"] = self.config.username
        env["OPENCODE_SERVER_PASSWORD"] = password
        env["ADJUTANT_OPENCODE_SERVER_INSTANCE"] = instance_id
        started = time.monotonic()
        with open(self.log_path, "a") as log_handle:  # noqa: SIM115
            process = subprocess.Popen(
                [
                    binary,
                    "serve",
                    "--hostname",
                    "127.0.0.1",
                    "--port",
                    str(port),
                ],
                cwd=str(self.adj_dir),
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=log_handle,
                stderr=log_handle,
                start_new_session=True,
            )
        create_time = psutil.Process(process.pid).create_time()
        state = OpenCodeServerState(
            instance_id=instance_id,
            pid=process.pid,
            pid_create_time=create_time,
            url=f"http://127.0.0.1:{port}",
            port=port,
            username=self.config.username,
            status="starting",
            started_at=time.time(),
            last_used_at=time.time(),
            restart_count=(previous.restart_count + 1 if previous else 0),
        )
        self._write_state(state)
        client = OpenCodeServerClient(
            state.url,
            username=state.username,
            password=password,
            timeout=min(2.0, float(self.config.health_interval_seconds)),
        )
        deadline = time.monotonic() + self.config.startup_timeout_seconds
        error = "server did not become healthy"
        while time.monotonic() < deadline:
            if process.poll() is not None:
                error = f"server exited with code {process.returncode}"
                break
            try:
                health = await asyncio.to_thread(client.health)
            except OpenCodeServerError as exc:
                error = str(exc)
                await asyncio.sleep(0.1)
                continue
            state.status = "ready"
            state.version = str(health.get("version") or "") or None
            state.last_used_at = time.time()
            self._write_state(state)
            elapsed = time.monotonic() - started
            adj_log(
                "opencode-server",
                f"Started {instance_id} pid={process.pid} port={port} in {elapsed:.3f}s",
            )
            return self._endpoint(
                state,
                password=password,
                reused=False,
                startup_seconds=elapsed,
            )
        state.status = "failed"
        state.last_error = error
        state.last_used_at = time.time()
        self._write_state(state)
        await asyncio.to_thread(self._stop_owned, state)
        raise OpenCodeServerError(f"OpenCode server startup failed: {error}")

    async def stop(self) -> bool:
        """Stop the recorded server only when PID identity still matches."""
        async with self._lock:
            state = self._read_state()
            if state is None:
                return False
            stopped = await asyncio.to_thread(self._stop_owned, state)
            state.status = "stopped"
            state.last_used_at = time.time()
            self._write_state(state)
            return stopped

    async def maintain(self, *, active_clients: int = 0) -> str:
        """Apply idle and memory policies without interrupting soft-limit work."""
        async with self._lock:
            state = self._read_state()
            if state is None or self._owned_process(state) is None:
                return "stopped"
            rss = self._rss_bytes(state.pid)
            hard = self._memory_bytes(self.config.hard_memory_mb)
            soft = self._memory_bytes(self.config.soft_memory_mb)
            idle = time.time() - state.last_used_at
            if state.status == "draining":
                if active_clients > 0:
                    return "draining"
                await asyncio.to_thread(self._stop_owned, state)
                state.status = "stopped"
                state.last_used_at = time.time()
                self._write_state(state)
                return "soft_limit_stopped"
            if hard is not None and rss > hard:
                state.status = "draining"
                self._write_state(state)
                await asyncio.to_thread(self._stop_owned, state)
                state.status = "stopped"
                state.last_used_at = time.time()
                self._write_state(state)
                return "hard_limit_stopped"
            if soft is not None and rss > soft:
                state.status = "draining"
                self._write_state(state)
                if active_clients == 0:
                    await asyncio.to_thread(self._stop_owned, state)
                    state.status = "stopped"
                    state.last_used_at = time.time()
                    self._write_state(state)
                    return "soft_limit_stopped"
                return "draining"
            if idle > self.config.idle_timeout_seconds and active_clients == 0:
                await asyncio.to_thread(self._stop_owned, state)
                state.status = "stopped"
                state.last_used_at = time.time()
                self._write_state(state)
                return "idle_stopped"
            return "ready"

    def status(self) -> dict[str, Any] | None:
        state = self._read_state()
        if state is None:
            return None
        data = asdict(state)
        data["owned_process_alive"] = self._owned_process(state) is not None
        data["rss_bytes"] = self._rss_bytes(state.pid) if data["owned_process_alive"] else 0
        return data

    def _endpoint(
        self,
        state: OpenCodeServerState,
        *,
        password: str,
        reused: bool,
        startup_seconds: float,
    ) -> OpenCodeServerEndpoint:
        return OpenCodeServerEndpoint(
            url=state.url,
            username=state.username,
            password=password,
            instance_id=state.instance_id,
            pid=state.pid,
            version=state.version,
            reused=reused,
            startup_seconds=startup_seconds,
            rss_bytes=self._rss_bytes(state.pid),
        )

    def _password(self) -> str:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        try:
            password = self.secret_path.read_text().strip()
        except FileNotFoundError:
            password = secrets.token_urlsafe(32)
            fd = os.open(self.secret_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as handle:
                handle.write(password)
        if not password:
            raise OpenCodeServerError("Managed OpenCode server password is empty")
        with contextlib.suppress(OSError):
            self.secret_path.chmod(0o600)
        return password

    def _read_state(self) -> OpenCodeServerState | None:
        try:
            raw = json.loads(self.state_path.read_text())
            return OpenCodeServerState(**raw)
        except (FileNotFoundError, OSError, TypeError, ValueError, json.JSONDecodeError):
            return None

    def _write_state(self, state: OpenCodeServerState) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        temporary = self.state_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(asdict(state), sort_keys=True))
        temporary.replace(self.state_path)

    @staticmethod
    def _available_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])

    @staticmethod
    def _memory_bytes(value_mb: int | None) -> int | None:
        return value_mb * 1024 * 1024 if value_mb is not None else None

    @staticmethod
    def _owned_process(state: OpenCodeServerState) -> psutil.Process | None:
        try:
            process = psutil.Process(state.pid)
            if abs(process.create_time() - state.pid_create_time) > 0.01:
                return None
            cmdline = process.cmdline()
            if "serve" not in cmdline:
                return None
            return process
        except (psutil.Error, OSError):
            return None

    @classmethod
    def _rss_bytes(cls, pid: int) -> int:
        try:
            root = psutil.Process(pid)
            processes = [root, *root.children(recursive=True)]
        except (psutil.Error, OSError):
            return 0
        total = 0
        for process in processes:
            try:
                if process.is_running():
                    total += process.memory_info().rss
            except (psutil.Error, OSError):
                continue
        return total

    @classmethod
    def _stop_owned(cls, state: OpenCodeServerState) -> bool:
        process = cls._owned_process(state)
        if process is None:
            return False
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(state.pid, signal.SIGTERM)
        try:
            process.wait(timeout=5)
        except psutil.TimeoutExpired:
            with contextlib.suppress(ProcessLookupError, PermissionError):
                os.killpg(state.pid, signal.SIGKILL)
            with contextlib.suppress(psutil.Error):
                process.wait(timeout=2)
        return True


def stop_managed_opencode_server(adj_dir: Path) -> bool:
    """Synchronous lifecycle helper for restart and emergency shutdown."""
    from adjutant.core.config import load_typed_config

    config = load_typed_config(adj_dir / "adjutant.yaml").operations.persistent_opencode
    manager = ManagedOpenCodeServer(adj_dir, config)
    state = manager._read_state()  # noqa: SLF001 - lifecycle identity check
    if state is None:
        return False
    stopped = manager._stop_owned(state)  # noqa: SLF001 - lifecycle identity check
    state.status = "stopped"
    state.last_used_at = time.time()
    manager._write_state(state)  # noqa: SLF001 - lifecycle state update
    return stopped


def abort_owned_opencode_session(
    adj_dir: Path,
    *,
    server_instance_id: str,
    session_id: str,
    workdir: Path | None = None,
) -> bool:
    """Abort one session only when it belongs to the current owned server."""
    from adjutant.core.config import load_typed_config

    config = load_typed_config(adj_dir / "adjutant.yaml").operations.persistent_opencode
    manager = ManagedOpenCodeServer(adj_dir, config)
    state = manager._read_state()  # noqa: SLF001 - recovery identity check
    if (
        state is None
        or state.instance_id != server_instance_id
        or manager._owned_process(state) is None  # noqa: SLF001 - recovery identity check
    ):
        return False
    endpoint = manager._endpoint(  # noqa: SLF001 - verified recovery endpoint
        state,
        password=manager._password(),  # noqa: SLF001 - owned secret
        reused=True,
        startup_seconds=0.0,
    )
    return endpoint.client(timeout=5.0).abort_session(session_id, workdir=workdir)
