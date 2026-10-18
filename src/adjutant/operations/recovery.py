"""Restart recovery for durable operation workers."""

from __future__ import annotations

import contextlib
import os
import signal
from typing import TYPE_CHECKING

import psutil

from adjutant.core.logging import adj_log
from adjutant.operations.store import OperationStore

if TYPE_CHECKING:
    from pathlib import Path

    from adjutant.operations.models import ExecutionAttempt, Operation


def recover_worker_state(
    adj_dir: Path,
    *,
    store: OperationStore | None = None,
) -> tuple[int, int]:
    """Recover expired leases without replaying uncertain mutations."""
    operation_store = store or OperationStore(adj_dir)
    candidates = operation_store.list_expired_attempts()
    recovered_operations, recovered_deliveries = operation_store.recover_expired_leases()
    for operation, attempt in candidates:
        current = operation_store.get_operation(operation.id)
        if current is not None and current.current_attempt_id != attempt.id:
            _settle_revoked_attempt(adj_dir, operation, attempt)
    if recovered_operations or recovered_deliveries:
        adj_log(
            "operations",
            f"Recovered expired leases: operations={recovered_operations} "
            f"deliveries={recovered_deliveries}",
        )
    return recovered_operations, recovered_deliveries


def _settle_revoked_attempt(
    adj_dir: Path,
    operation: Operation,
    attempt: ExecutionAttempt,
) -> None:
    """Stop only the backend session or process recorded on a revoked attempt."""
    if attempt.server_instance_id and attempt.backend_session_id:
        from pathlib import Path

        from adjutant.core.opencode_server import (
            OpenCodeServerError,
            abort_owned_opencode_session,
        )

        try:
            aborted = abort_owned_opencode_session(
                adj_dir,
                server_instance_id=attempt.server_instance_id,
                session_id=attempt.backend_session_id,
                workdir=Path(operation.workdir) if operation.workdir else None,
            )
        except OpenCodeServerError as exc:
            adj_log(
                "operations",
                f"Could not abort recovered session {attempt.backend_session_id}: {exc}",
            )
        else:
            if aborted:
                adj_log(
                    "operations",
                    f"Aborted recovered session {attempt.backend_session_id}",
                )
        return

    if attempt.pid is not None and attempt.pid_create_time is not None:
        _terminate_owned_process(
            attempt.pid,
            attempt.pid_create_time,
            process_group_id=attempt.process_group_id,
            expected_terms=("claude" if operation.backend == "claude-cli" else "opencode",),
        )
        return

    if (
        operation.execution_mode == "inline"
        and attempt.owner_pid is not None
        and attempt.owner_pid_create_time is not None
    ):
        _terminate_owned_process(
            attempt.owner_pid,
            attempt.owner_pid_create_time,
            process_group_id=None,
            expected_terms=("adjutant", "kb"),
        )


def _terminate_owned_process(
    pid: int,
    create_time: float,
    *,
    process_group_id: int | None,
    expected_terms: tuple[str, ...],
) -> bool:
    try:
        process = psutil.Process(pid)
        if abs(process.create_time() - create_time) > 0.01:
            return False
        command = " ".join(process.cmdline()).lower()
        if not all(term in command for term in expected_terms):
            return False
        if process_group_id is not None and process_group_id != os.getpgrp():
            os.killpg(process_group_id, signal.SIGTERM)
        else:
            process.terminate()
        try:
            process.wait(timeout=2)
        except psutil.TimeoutExpired:
            if process_group_id is not None and process_group_id != os.getpgrp():
                with contextlib.suppress(ProcessLookupError, PermissionError):
                    os.killpg(process_group_id, signal.SIGKILL)
            else:
                with contextlib.suppress(psutil.Error):
                    process.kill()
        return True
    except (OSError, psutil.Error):
        return False
