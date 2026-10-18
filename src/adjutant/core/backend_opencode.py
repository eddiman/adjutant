"""OpenCode backend — wraps core/opencode.py behind the LLMBackend protocol.

This is the existing backend path. All OpenCode-specific logic stays in
opencode.py; this module adapts it to the unified LLMBackend interface.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import subprocess
import time
import uuid
from typing import TYPE_CHECKING, Any

from adjutant.core.backend import (
    BackendCapabilities,
    BackendNotFoundError,
    ExecutionEvent,
    ExecutionEventType,
    ExecutionRequest,
    ExecutionTimings,
    LLMResult,
)
from adjutant.core.logging import adj_log
from adjutant.core.opencode import (
    OpenCodeNotFoundError,
    OpenCodeResult,
    _find_opencode,
    opencode_health_check,
    opencode_reap,
    opencode_run,
)
from adjutant.core.opencode_server import (
    ManagedOpenCodeServer,
    OpenCodeServerDrainingError,
    OpenCodeServerEndpoint,
    OpenCodeServerError,
)
from adjutant.lib.ndjson import IncrementalNDJSONParser

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

# Model alias → full OpenCode model ID
_ALIASES: dict[str, str] = {
    "haiku": "anthropic/claude-haiku-4-5",
    "sonnet": "anthropic/claude-sonnet-4-6",
    "opus": "anthropic/claude-opus-4-6",
}

# Reverse: full model ID → alias (used by translate_model_id)
_REVERSE_ALIASES: dict[str, str] = {v: k for k, v in _ALIASES.items()}

_SERVER_MANAGERS: dict[str, ManagedOpenCodeServer] = {}


def _managed_server(request: ExecutionRequest) -> ManagedOpenCodeServer | None:
    """Return the configured manager for a durable worker request."""
    from pathlib import Path

    from adjutant.core.config import load_typed_config

    operation_kind = str((request.env or {}).get("ADJUTANT_OPERATION_KIND") or "")
    if operation_kind in {"kb_query", "kb_write"}:
        # Keep KB executions process-isolated until the persistent-server
        # permission and cross-workspace isolation gate is proven separately.
        return None

    raw_adj_dir = os.environ.get("ADJ_DIR", "").strip()
    candidates: list[Path] = []
    if raw_adj_dir:
        candidates.append(Path(raw_adj_dir))
    if request.workdir is not None:
        candidates.append(request.workdir)
    for adj_dir in candidates:
        config_path = adj_dir / "adjutant.yaml"
        if not config_path.is_file():
            continue
        config = load_typed_config(config_path)
        persistent = config.operations.persistent_opencode
        if not config.operations.enabled or not persistent.enabled:
            return None
        key = str(adj_dir.resolve())
        manager = _SERVER_MANAGERS.get(key)
        if manager is None:
            manager = ManagedOpenCodeServer(adj_dir, persistent)
            _SERVER_MANAGERS[key] = manager
        return manager
    return None


def _normalize_record(record: dict[str, Any]) -> list[ExecutionEvent]:
    """Map an OpenCode record without exposing tool arguments or reasoning."""
    record_type = str(record.get("type") or "")
    events: list[ExecutionEvent] = []
    session_id = record.get("sessionID")
    if record_type == "session.create":
        properties = record.get("properties")
        if isinstance(properties, dict):
            session_id = properties.get("sessionID") or session_id
    if session_id:
        events.append(
            ExecutionEvent(
                type=ExecutionEventType.SESSION_STARTED,
                session_id=str(session_id),
                public_message="Backend session established",
            )
        )

    if record_type == "text":
        part = record.get("part")
        text = part.get("text", "") if isinstance(part, dict) else part
        if isinstance(text, str) and text:
            events.append(ExecutionEvent(type=ExecutionEventType.TEXT_DELTA, text=text))
    elif record_type in {"tool", "tool.start", "tool_use", "tool.started"}:
        events.append(
            ExecutionEvent(
                type=ExecutionEventType.TOOL_STARTED,
                public_message="A tool step started",
            )
        )
    elif record_type in {"tool.end", "tool_result", "tool.finished"}:
        events.append(
            ExecutionEvent(
                type=ExecutionEventType.TOOL_FINISHED,
                public_message="A tool step finished",
            )
        )
    elif record_type in {"question", "waiting_input"}:
        events.append(
            ExecutionEvent(
                type=ExecutionEventType.WAITING_INPUT,
                public_message="The operation is waiting for input",
            )
        )
    elif record_type == "usage":
        usage = record.get("usage")
        events.append(
            ExecutionEvent(
                type=ExecutionEventType.USAGE,
                data=usage if isinstance(usage, dict) else {},
            )
        )
    elif record_type == "error":
        events.append(
            ExecutionEvent(
                type=ExecutionEventType.FAILED,
                # The CLI can emit an error record before it exits and before
                # reconciliation determines the terminal state. Persist the
                # evidence without publishing a premature terminal message.
                public_message=None,
            )
        )
    return events


class OpenCodeBackend:
    """LLMBackend implementation using the OpenCode CLI."""

    @property
    def name(self) -> str:
        return "opencode"

    @property
    def capabilities(self) -> BackendCapabilities:
        return BackendCapabilities(
            vision=True,
            model_listing=True,
            reaping=True,
            # web_server is False since the native `opencode web` server
            # was retired in favor of adjutant's own web/app.
            web_server=False,
            remote_session=False,
            streaming=True,
            cost_tracking=False,
            persistent_transport=True,
            reconnect=True,
            native_abort=True,
        )

    async def run(
        self,
        prompt: str,
        *,
        agent: str | None = None,
        workdir: Path | None = None,
        model: str | None = None,
        variant: str | None = None,
        session_id: str | None = None,
        startup_timeout: float | None = None,
        timeout: float | None = None,
        env: dict[str, str] | None = None,
        files: list[Path] | None = None,
        correlation_id: str | None = None,
    ) -> LLMResult:
        request = ExecutionRequest(
            prompt=prompt,
            agent=agent,
            workdir=workdir,
            model=model,
            variant=variant,
            session_id=session_id,
            startup_timeout=startup_timeout,
            timeout=timeout,
            env=env,
            files=files,
            correlation_id=correlation_id,
        )
        result: LLMResult | None = None
        async for event in self.execute(request):
            if event.result is not None:
                result = event.result
        if result is None:
            return LLMResult(
                text="",
                error_type="error",
                returncode=1,
                correlation_id=correlation_id,
            )
        return result

    async def execute(self, request: ExecutionRequest) -> AsyncIterator[ExecutionEvent]:
        """Yield normalized events while draining OpenCode output incrementally."""
        request_id = request.correlation_id or f"llm-{uuid.uuid4().hex[:12]}"
        args: list[str] = ["run"]

        manager = _managed_server(request)
        endpoint: OpenCodeServerEndpoint | None = None
        if manager is not None:
            try:
                endpoint = await manager.ensure_ready()
            except OpenCodeServerDrainingError:
                adj_log(
                    "backend",
                    f"[opencode] run id={request_id} using isolated CLI while server drains",
                )
            else:
                args += ["--attach", endpoint.url]

        if request.agent:
            args += ["--agent", request.agent]
        if request.workdir:
            args += ["--dir", str(request.workdir)]
        args += ["--format", "json"]
        if request.model:
            args += ["--model", self.resolve_alias(request.model)]
        if request.variant:
            args += ["--variant", request.variant]
        if request.session_id:
            args += ["--session", request.session_id]
        args.append(request.prompt)
        if request.files:
            for f in request.files:
                args += ["-f", str(f)]

        run_env = dict(request.env or {})
        run_env.setdefault("ADJUTANT_CORRELATION_ID", request_id)
        if endpoint is not None:
            run_env["OPENCODE_SERVER_USERNAME"] = endpoint.username
            run_env["OPENCODE_SERVER_PASSWORD"] = endpoint.password

        yield ExecutionEvent(
            type=ExecutionEventType.STARTED,
            public_message="Backend execution started",
            data={
                "correlation_id": request_id,
                "persistent_transport": endpoint is not None,
                "server_instance_id": endpoint.instance_id if endpoint else None,
                "server_reused": endpoint.reused if endpoint else False,
                "server_rss_bytes": endpoint.rss_bytes if endpoint else None,
            },
        )

        parser = IncrementalNDJSONParser(retain_events=100)
        queue: asyncio.Queue[ExecutionEvent | None] = asyncio.Queue()
        seen_session_id: str | None = None
        connection_established = asyncio.Event()

        async def _on_spawn(evidence: dict[str, int | float | None]) -> None:
            queue.put_nowait(
                ExecutionEvent(
                    type=ExecutionEventType.STARTED,
                    public_message=None,
                    data={
                        **evidence,
                        "server_instance_id": endpoint.instance_id if endpoint else None,
                    },
                )
            )

        async def _on_line(line: str) -> None:
            nonlocal seen_session_id
            record = parser.feed_line(line)
            if record is None:
                return
            connection_established.set()
            for event in _normalize_record(record):
                if event.type is ExecutionEventType.SESSION_STARTED:
                    if event.session_id == seen_session_id:
                        continue
                    seen_session_id = event.session_id
                queue.put_nowait(event)

        start = time.monotonic()

        async def _invoke() -> None:
            try:
                try:
                    run_task = asyncio.create_task(
                        opencode_run(
                            args,
                            timeout=request.timeout,
                            startup_timeout=request.startup_timeout,
                            env=run_env,
                            on_stdout_line=_on_line,
                            on_spawn=_on_spawn,
                        )
                    )
                    if endpoint is not None and request.connection_timeout:
                        connected_task = asyncio.create_task(connection_established.wait())
                        done, _ = await asyncio.wait(
                            {run_task, connected_task},
                            timeout=request.connection_timeout,
                            return_when=asyncio.FIRST_COMPLETED,
                        )
                        connected_task.cancel()
                        with contextlib.suppress(asyncio.CancelledError):
                            await connected_task
                        if not done:
                            run_task.cancel()
                            with contextlib.suppress(asyncio.CancelledError):
                                await run_task
                            oc_result = OpenCodeResult(
                                stdout="",
                                stderr="OpenCode server connection timed out",
                                returncode=-1,
                                timed_out=True,
                                timeout_phase="connection",
                            )
                        else:
                            oc_result = await run_task
                    else:
                        oc_result = await run_task
                except OpenCodeNotFoundError as exc:
                    raise BackendNotFoundError(str(exc)) from exc

                parsed_session_id = parser.result().session_id
                if endpoint is not None and parsed_session_id and oc_result.timed_out:
                    with contextlib.suppress(OpenCodeServerError):
                        await asyncio.to_thread(
                            endpoint.client(
                                timeout=request.connection_timeout or 10.0
                            ).abort_session,
                            parsed_session_id,
                            workdir=request.workdir,
                        )

                parse_started = time.monotonic()
                parsed = parser.result()
                if not parsed.events and oc_result.stdout:
                    for line in oc_result.stdout.splitlines():
                        parser.feed_line(line)
                    parsed = parser.result()
                parse_seconds = time.monotonic() - parse_started
                elapsed = time.monotonic() - start
                result = LLMResult(
                    text=parsed.text,
                    session_id=parsed.session_id,
                    error_type=parsed.error_type,
                    returncode=oc_result.returncode,
                    timed_out=oc_result.timed_out,
                    timeout_phase=oc_result.timeout_phase,
                    correlation_id=request_id,
                    server_instance_id=endpoint.instance_id if endpoint else None,
                    timings=ExecutionTimings(
                        spawn_seconds=oc_result.spawn_seconds,
                        execution_seconds=oc_result.execution_seconds,
                        cleanup_seconds=oc_result.cleanup_seconds,
                        parse_seconds=parse_seconds,
                        total_seconds=elapsed,
                    ),
                )
                if oc_result.timed_out:
                    result.error_type = "timeout"
                elif endpoint is not None and result.returncode != 0 and result.session_id:
                    result.error_type = "reconciliation_required"
                    try:
                        statuses = await asyncio.to_thread(
                            endpoint.client(
                                timeout=request.connection_timeout or 10.0
                            ).session_status,
                            workdir=request.workdir,
                        )
                    except OpenCodeServerError as exc:
                        result.reconciliation_status = f"status_unavailable:{exc}"
                    else:
                        status = statuses.get(result.session_id)
                        result.reconciliation_status = json.dumps(
                            status,
                            sort_keys=True,
                            default=str,
                        )

                event_type = (
                    ExecutionEventType.FAILED
                    if result.error_type or result.returncode != 0
                    else ExecutionEventType.COMPLETED
                )
                queue.put_nowait(
                    ExecutionEvent(
                        type=event_type,
                        public_message=(
                            "Backend execution completed"
                            if event_type is ExecutionEventType.COMPLETED
                            else "Backend execution failed"
                        ),
                        session_id=result.session_id,
                        error_type=result.error_type,
                        result=result,
                    )
                )
                adj_log(
                    "backend",
                    f"[opencode] run id={request_id} completed in {elapsed:.1f}s"
                    f" | spawn={oc_result.spawn_seconds:.3f}s"
                    f" execute={oc_result.execution_seconds:.3f}s"
                    f" cleanup={oc_result.cleanup_seconds:.3f}s"
                    f" parse={parse_seconds:.3f}s"
                    f" | model={request.model} variant={request.variant} agent={request.agent}"
                    f" | error_type={result.error_type}",
                )
            except asyncio.CancelledError:
                parsed_session_id = parser.result().session_id
                if endpoint is not None and parsed_session_id:
                    with contextlib.suppress(OpenCodeServerError):
                        await asyncio.to_thread(
                            endpoint.client(
                                timeout=request.connection_timeout or 10.0
                            ).abort_session,
                            parsed_session_id,
                            workdir=request.workdir,
                        )
                raise
            finally:
                queue.put_nowait(None)

        invocation = asyncio.create_task(_invoke())
        try:
            while True:
                event = await queue.get()
                if event is None:
                    break
                yield event
            await invocation
        finally:
            if not invocation.done():
                invocation.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await invocation

    def run_detached(
        self,
        prompt: str,
        *,
        agent: str | None = None,
        workdir: Path | None = None,
        model: str | None = None,
        variant: str | None = None,
        log_path: Path | None = None,
    ) -> None:
        try:
            opencode_bin = _find_opencode()
        except OpenCodeNotFoundError as exc:
            raise BackendNotFoundError(str(exc)) from exc

        args = [opencode_bin, "run"]
        if agent:
            args += ["--agent", agent]
        if workdir:
            args += ["--dir", str(workdir)]
        args += ["--format", "json"]
        if model:
            args += ["--model", self.resolve_alias(model)]
        if variant:
            args += ["--variant", variant]
        args.append(prompt)

        log_fh = open(log_path, "a") if log_path else None  # noqa: SIM115
        try:
            subprocess.Popen(
                args,
                stdout=log_fh or subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        finally:
            if log_fh is not None:
                log_fh.close()

    def run_sync(
        self,
        prompt: str,
        *,
        workdir: Path | None = None,
        timeout: float | None = None,
    ) -> int:
        try:
            opencode_bin = _find_opencode()
        except OpenCodeNotFoundError as exc:
            raise BackendNotFoundError(str(exc)) from exc

        args = [opencode_bin, "run"]
        if workdir:
            args += ["--dir", str(workdir)]
        args.append(prompt)

        start = time.monotonic()
        result = subprocess.run(args, timeout=timeout)  # noqa: S603
        elapsed = time.monotonic() - start

        adj_log(
            "backend",
            f"[opencode] run_sync completed in {elapsed:.1f}s | returncode={result.returncode}",
        )
        return result.returncode

    async def reap(self, adj_dir: Path) -> int:
        return await opencode_reap(adj_dir)

    async def health_check(self, adj_dir: Path) -> bool:
        return await opencode_health_check(adj_dir)

    async def list_models(self) -> str:
        try:
            opencode_bin = _find_opencode()
        except OpenCodeNotFoundError as exc:
            raise BackendNotFoundError(str(exc)) from exc

        proc = await asyncio.create_subprocess_exec(
            opencode_bin,
            "models",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        return stdout.decode(errors="replace") if stdout else ""

    def find_binary(self) -> str | None:
        try:
            return _find_opencode()
        except OpenCodeNotFoundError:
            return None

    def resolve_alias(self, alias: str) -> str:
        return _ALIASES.get(alias, alias)

    def translate_model_id(self, model_id: str) -> str:
        """Convert a model ID from another backend's format to this backend's."""
        return _ALIASES.get(model_id, model_id)
