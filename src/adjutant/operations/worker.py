"""Bounded worker for durable operations."""

from __future__ import annotations

import asyncio
import contextlib
import os
import socket
import time
from typing import TYPE_CHECKING, Protocol

from adjutant.core.backend import (
    ExecutionEventType,
    ExecutionRequest,
    LLMResult,
    get_backend,
)
from adjutant.core.logging import adj_log
from adjutant.operations.delivery import DeliveryWorker, split_telegram_text
from adjutant.operations.models import ExecutionAttempt, Operation, OperationState
from adjutant.operations.recovery import recover_worker_state
from adjutant.operations.store import OperationStore

if TYPE_CHECKING:
    from pathlib import Path


class OperationHandler(Protocol):
    async def __call__(self, operation: Operation) -> LLMResult: ...


class OperationWorker:
    """Executes claimed operations and persists results before delivery."""

    def __init__(
        self,
        adj_dir: Path,
        *,
        store: OperationStore | None = None,
        worker_id: str | None = None,
        concurrency: int = 2,
        poll_interval_seconds: float = 0.5,
        lease_seconds: float = 90.0,
        startup_seconds: float = 60.0,
        connection_seconds: float = 30.0,
        runtime_seconds: float = 1800.0,
        progress_warning_seconds: float = 90.0,
        cancellation_grace_seconds: float = 10.0,
        handler: OperationHandler | None = None,
        delivery_worker: DeliveryWorker | None = None,
    ) -> None:
        self.adj_dir = adj_dir
        self.store = store or OperationStore(adj_dir)
        self.worker_id = worker_id or f"{socket.gethostname()}-{os.getpid()}"
        self.concurrency = concurrency
        self.poll_interval_seconds = poll_interval_seconds
        self.lease_seconds = lease_seconds
        self.startup_seconds = startup_seconds
        self.connection_seconds = connection_seconds
        self.runtime_seconds = runtime_seconds
        self.progress_warning_seconds = progress_warning_seconds
        self.cancellation_grace_seconds = cancellation_grace_seconds
        self.handler = handler or self._execute_backend
        self.delivery_worker = delivery_worker
        self._stopping = False
        self._active_attempt_ids: dict[str, str] = {}

    async def _execute_backend(self, operation: Operation) -> LLMResult:
        if operation.kind not in {
            "telegram_chat",
            "telegram_photo",
            "prompt",
            "pulse",
            "review",
            "kb_query",
            "kb_write",
            "web_prompt",
        }:
            return LLMResult(
                text="",
                error_type="unsupported_operation",
                returncode=1,
                correlation_id=operation.correlation_id,
            )
        from adjutant.operations.sessions import build_conversation_prompt

        prompt = build_conversation_prompt(operation, self.store)
        if operation.kind == "telegram_photo":
            prompt = await self._prepare_photo_prompt(operation)
            if not prompt:
                return LLMResult(
                    text="I couldn't retrieve or analyze the photo. Try again.",
                    error_type="photo_analysis_failed",
                    returncode=1,
                    correlation_id=operation.correlation_id,
                )
        if operation.kind not in {"kb_query", "kb_write"}:
            prompt = self._add_runtime_context(prompt, operation.id)
        backend = get_backend(operation.backend)
        workdir = self.adj_dir
        if operation.workdir:
            from pathlib import Path

            workdir = Path(operation.workdir)
        request = ExecutionRequest(
            prompt=prompt,
            agent=operation.agent,
            workdir=workdir,
            model=operation.model,
            variant=operation.variant,
            startup_timeout=self.startup_seconds,
            connection_timeout=self.connection_seconds,
            timeout=(
                min(self.runtime_seconds, max(0.1, operation.deadline_at - time.time()))
                if operation.deadline_at is not None
                else self.runtime_seconds
            ),
            env={
                "ADJUTANT_PARENT_OPERATION_ID": operation.id,
                "ADJUTANT_OPERATION_ID": operation.id,
                "ADJUTANT_OPERATION_KIND": operation.kind,
            },
            correlation_id=operation.correlation_id or operation.id,
        )
        result: LLMResult | None = None
        async for event in backend.execute(request):
            if event.result is not None:
                result = event.result
            if event.type is ExecutionEventType.TEXT_DELTA:
                continue
            if (
                event.type in {ExecutionEventType.COMPLETED, ExecutionEventType.FAILED}
                and event.result is not None
            ):
                continue
            attempt_id = self._active_attempt_ids.get(operation.id)
            if attempt_id is not None and (
                event.session_id
                or event.data.get("server_instance_id")
                or event.data.get("pid")
            ):
                self.store.update_attempt(
                    attempt_id,
                    state=OperationState.RUNNING.value,
                    pid=event.data.get("pid"),
                    pid_create_time=event.data.get("pid_create_time"),
                    process_group_id=event.data.get("process_group_id"),
                    server_instance_id=event.data.get("server_instance_id"),
                    backend_session_id=event.session_id,
                    backend_message_id=event.data.get("message_id"),
                )
            self.store.append_event(
                operation.id,
                event.type.value,
                public_message=event.public_message,
                data={
                    "session_id": event.session_id,
                    "error_type": event.error_type,
                    **event.data,
                },
            )
            if event.public_message:
                self._enqueue_status(operation, event.public_message)
        if result is None:
            return LLMResult(
                text="",
                error_type="missing_final_event",
                returncode=1,
                correlation_id=operation.correlation_id or operation.id,
            )
        return result

    @staticmethod
    def _add_runtime_context(prompt: str, operation_id: str) -> str:
        """Carry per-operation metadata through persistent server tool calls.

        Environment variables passed to ``opencode run --attach`` belong to the
        short-lived CLI process. Tools execute under the persistent server, so
        nested Adjutant CLI calls need the parent ID in the prompt as well.
        """
        return (
            "<adjutant-runtime-context>\n"
            f"Current durable operation ID: {operation_id}\n"
            "When invoking an Adjutant KB query, write, query-all, or cross-query, "
            "run one standalone command and prefix it with "
            f"`ADJUTANT_PARENT_OPERATION_ID={operation_id}`. Do not use a pipeline, "
            "compound command, background execution, or command substitution. If the "
            "tool call ends early, inspect the accepted child ID and do not repeat a "
            "write until its authoritative outcome is known. "
            "Keep this orchestration metadata out of the user-facing answer.\n"
            "</adjutant-runtime-context>\n\n"
            f"{prompt}"
        )

    async def _prepare_photo_prompt(self, operation: Operation) -> str:
        """Download and extract photo evidence inside the tracked attempt."""
        from adjutant.capabilities.vision.vision import run_vision
        from adjutant.core.config import load_typed_config
        from adjutant.core.env import require_telegram_credentials
        from adjutant.messaging.telegram.photos import (
            _build_attachment_message,
            _build_vision_prompt,
            tg_download_photo,
        )

        config = load_typed_config(self.adj_dir / "adjutant.yaml")
        if not config.is_feature_enabled("vision"):
            return "Vision is disabled, so the photo cannot be analyzed."
        file_id = str(operation.payload.get("file_id") or "")
        caption = str(operation.payload.get("caption") or "")
        if not file_id:
            return ""
        bot_token, _ = require_telegram_credentials(self.adj_dir / ".env")
        local_path = await asyncio.to_thread(
            tg_download_photo,
            file_id,
            bot_token=bot_token,
            adj_dir=self.adj_dir,
        )
        if local_path is None:
            return ""
        analysis = await asyncio.to_thread(
            run_vision,
            str(local_path),
            _build_vision_prompt(caption),
            self.adj_dir,
        )
        if not analysis:
            return ""
        return _build_attachment_message(caption, analysis)

    async def run_claimed(
        self,
        operation: Operation,
        *,
        attempt: ExecutionAttempt | None = None,
    ) -> Operation:
        """Execute one already claimed operation."""
        typing_key: str | None = None
        if self.delivery_worker is not None and operation.telegram_chat_id is not None:
            from adjutant.messaging.telegram.send import msg_typing_start

            typing_key = f"operation_{operation.id}"
            msg_typing_start(
                typing_key,
                self.delivery_worker.bot_token,
                operation.telegram_chat_id,
                max_duration=self.runtime_seconds + self.cancellation_grace_seconds + 5,
            )
        try:
            return await self._run_claimed(operation, attempt=attempt)
        finally:
            self._active_attempt_ids.pop(operation.id, None)
            if typing_key is not None:
                from adjutant.messaging.telegram.send import msg_typing_stop

                msg_typing_stop(typing_key)

    async def _run_claimed(
        self,
        operation: Operation,
        *,
        attempt: ExecutionAttempt | None = None,
    ) -> Operation:
        """Execute one operation while its Telegram activity is already visible."""
        attempt = attempt or self.store.start_attempt(
            operation,
            self.worker_id,
            runtime_seconds=self.runtime_seconds,
        )
        self._active_attempt_ids[operation.id] = attempt.id
        current = self.store.get_operation(operation.id)
        if current is None:
            raise RuntimeError(f"Operation {operation.id} disappeared before execution")
        operation = current
        running = self.store.transition(
            operation.id,
            OperationState.RUNNING,
            worker_id=self.worker_id,
            lease_seconds=self.lease_seconds,
            expected_attempt_id=attempt.id,
        )
        self.store.update_attempt(attempt.id, state=OperationState.RUNNING.value)
        self.store.append_event(operation.id, "started", public_message="Operation started")
        self._enqueue_status(running, "Operation started")
        task = asyncio.create_task(self.handler(running))
        heartbeat = asyncio.create_task(self._supervise(running.id, attempt.id, task))
        remaining = (
            max(0.0, running.deadline_at - time.time())
            if running.deadline_at is not None
            else self.runtime_seconds
        )
        try:
            result = await asyncio.wait_for(task, timeout=remaining)
        except TimeoutError:
            task.cancel()
            await self._await_cancelled(task)
            message = "Operation reached its persisted execution deadline."
            completed = self._complete(
                running,
                OperationState.TIMED_OUT,
                result_text=None,
                error_type="timeout",
                error_message=message,
                delivery_text=message,
            )
            self.store.update_attempt(
                attempt.id,
                state=OperationState.TIMED_OUT.value,
                completed=True,
                timeout_reason="runtime ceiling",
            )
            self.store.append_event(operation.id, "failed", public_message=message)
            return completed
        except asyncio.CancelledError:
            task.cancel()
            await self._await_cancelled(task)
            current = self.store.get_operation(operation.id)
            if current is not None and current.state is OperationState.CANCEL_REQUESTED:
                message = "Operation cancelled. External changes, if any, were not undone."
                completed = self._complete(
                    current,
                    OperationState.CANCELLED,
                    result_text=None,
                    error_type="cancelled",
                    error_message=message,
                    delivery_text=message,
                )
                self.store.update_attempt(
                    attempt.id,
                    state=OperationState.CANCELLED.value,
                    completed=True,
                )
                self.store.append_event(operation.id, "cancelled", public_message=message)
                return completed
            raise
        except Exception as exc:  # noqa: BLE001 - persist worker failures
            message = f"Operation failed: {exc}"
            completed = self._complete(
                running,
                OperationState.FAILED,
                result_text=None,
                error_type="worker_error",
                error_message=str(exc),
                delivery_text=message,
            )
            self.store.update_attempt(
                attempt.id,
                state=OperationState.FAILED.value,
                completed=True,
            )
            self.store.append_event(operation.id, "failed", public_message=message)
            return completed
        finally:
            heartbeat.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await heartbeat

        if result.timed_out:
            state = OperationState.TIMED_OUT
            error_type = "timeout"
        elif result.error_type == "reconciliation_required":
            running = self.store.transition(
                running.id,
                OperationState.RECONCILING,
                worker_id=self.worker_id,
                lease_seconds=self.lease_seconds,
                recovery_status=(
                    result.reconciliation_status or "backend_disconnect_after_start"
                ),
                expected_attempt_id=attempt.id,
            )
            state = OperationState.INTERRUPTED
            error_type = result.error_type
        elif result.error_type or result.returncode != 0:
            state = OperationState.FAILED
            error_type = result.error_type or "backend_error"
        else:
            state = OperationState.SUCCEEDED
            error_type = None
        text = result.text.strip()
        active_children = [
            child
            for child in self.store.list_execution_children(operation.id)
            if not child.state.terminal
        ]
        if state is OperationState.SUCCEEDED and active_children:
            state = OperationState.INTERRUPTED
            error_type = "child_execution_unsettled"
            child_ids = ", ".join(child.id for child in active_children)
            text = (
                "The parent response finished while attached KB work was still unsettled. "
                f"Inspect these child operations before retrying: {child_ids}"
            )
        if state is OperationState.INTERRUPTED and not text:
            text = (
                "The backend connection was interrupted after execution started. "
                "Adjutant did not replay the request automatically because the earlier "
                "execution outcome was uncertain."
            )
        elif not text:
            text = "The operation finished without a text result."
        completed = self._complete(
            running,
            state,
            result_text=result.text or None,
            error_type=error_type,
            error_message=error_type,
            delivery_text=text,
        )
        self.store.update_attempt(
            attempt.id,
            state=state.value,
            completed=True,
            backend_session_id=result.session_id,
            server_instance_id=result.server_instance_id,
            returncode=result.returncode,
            timeout_reason=(
                (result.timeout_phase or "backend timeout") if result.timed_out else None
            ),
        )
        event_type = "completed" if state is OperationState.SUCCEEDED else "failed"
        self.store.append_event(operation.id, event_type, public_message=text[:500])
        return completed

    async def _supervise(
        self,
        operation_id: str,
        attempt_id: str,
        task: asyncio.Task[LLMResult],
    ) -> None:
        interval = max(0.1, min(self.lease_seconds / 3, 5.0))
        warned_activity_at: float | None = None
        while not task.done():
            await asyncio.sleep(interval)
            current = self.store.get_operation(operation_id)
            if current is None:
                task.cancel()
                return
            if current.state is OperationState.CANCEL_REQUESTED:
                task.cancel()
                return
            last_activity = current.last_activity_at or current.started_at or current.created_at
            if (
                time.time() - last_activity >= self.progress_warning_seconds
                and warned_activity_at != last_activity
            ):
                warning_event = self.store.append_event(
                    operation_id,
                    "progress_warning",
                    public_message=(
                        "The operation is still running, but the backend has not emitted "
                        "new progress."
                    ),
                )
                self._enqueue_status(
                    current,
                    "The operation is still running, but the backend has not emitted new progress.",
                )
                warned_activity_at = warning_event.created_at
            if not self.store.renew_lease(
                operation_id,
                self.worker_id,
                lease_seconds=self.lease_seconds,
                expected_attempt_id=attempt_id,
            ):
                task.cancel()
                return

    async def _await_cancelled(self, task: asyncio.Task[LLMResult]) -> None:
        with contextlib.suppress(TimeoutError, asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=self.cancellation_grace_seconds)

    def _complete(
        self,
        operation: Operation,
        state: OperationState,
        *,
        result_text: str | None,
        error_type: str | None,
        error_message: str | None,
        delivery_text: str,
    ) -> Operation:
        deliveries: list[tuple[str, dict[str, object], int]] = []
        if operation.status_message_id and operation.telegram_chat_id:
            deliveries.append(
                (
                    "telegram",
                    {
                        "method": "edit",
                        "chat_id": operation.telegram_chat_id,
                        "message_id": operation.status_message_id,
                        "text": f"`{operation.id}`: {state.value}.",
                    },
                    -1,
                )
            )
        if operation.telegram_chat_id:
            reply_to = operation.payload.get("reply_to_message_id")
            for index, chunk in enumerate(split_telegram_text(delivery_text)):
                deliveries.append(
                    (
                        "telegram",
                        {
                            "chat_id": operation.telegram_chat_id,
                            "reply_to_message_id": reply_to,
                            "text": chunk,
                        },
                        index,
                    )
                )
        attempt_id = self._active_attempt_ids.get(operation.id)
        completed = self.store.complete_with_deliveries(
            operation.id,
            state,
            result_text=result_text,
            error_type=error_type,
            error_message=error_message,
            deliveries=tuple(deliveries),
            worker_id=self.worker_id if attempt_id is not None else None,
            expected_attempt_id=attempt_id,
        )
        self.store.sync_active_snapshot()
        return completed

    def _enqueue_status(self, operation: Operation, message: str) -> None:
        if operation.status_message_id is None or operation.telegram_chat_id is None:
            return
        self.store.enqueue_delivery(
            operation.id,
            destination="telegram",
            payload={
                "method": "edit",
                "chat_id": operation.telegram_chat_id,
                "message_id": operation.status_message_id,
                "text": f"`{operation.id}`: {message}",
            },
            chunk_number=-1,
        )

    async def run_once(self) -> Operation | None:
        operation = self.store.claim_next(self.worker_id, lease_seconds=self.lease_seconds)
        if operation is None:
            return None
        self.store.sync_active_snapshot()
        return await self.run_claimed(operation)

    async def run_forever(self) -> None:
        """Recover leases, then run bounded execution and delivery loops."""
        recover_worker_state(self.adj_dir, store=self.store)
        tasks: set[asyncio.Task[Operation]] = set()
        adj_log(
            "operations",
            f"Worker {self.worker_id} started concurrency={self.concurrency}",
        )
        while not self._stopping:
            self._fail_blocked_dependencies()
            while len(tasks) < self.concurrency:
                operation = self.store.claim_next(
                    self.worker_id,
                    lease_seconds=self.lease_seconds,
                )
                if operation is None:
                    break
                self.store.sync_active_snapshot()
                tasks.add(asyncio.create_task(self.run_claimed(operation)))

            if self.delivery_worker is not None:
                await self.delivery_worker.run_once()

            if tasks:
                done, pending = await asyncio.wait(
                    tasks,
                    timeout=self.poll_interval_seconds,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                tasks = set(pending)
                for task in done:
                    try:
                        task.result()
                    except Exception as exc:  # noqa: BLE001
                        adj_log("operations", f"Worker task failed outside persistence: {exc}")
            else:
                await asyncio.sleep(self.poll_interval_seconds)

        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    def stop(self) -> None:
        self._stopping = True

    def _fail_blocked_dependencies(self) -> None:
        for operation in self.store.list_blocked_by_failed_dependency():
            message = "A required earlier operation did not complete successfully."
            try:
                self._complete(
                    operation,
                    OperationState.FAILED,
                    result_text=None,
                    error_type="dependency_failed",
                    error_message=message,
                    delivery_text=message,
                )
                self.store.append_event(
                    operation.id,
                    "failed",
                    public_message=message,
                )
            except Exception as exc:  # noqa: BLE001 - another worker may resolve it first
                adj_log(
                    "operations",
                    f"Could not fail dependency-blocked operation {operation.id}: {exc}",
                )
