"""Retention for durable evidence and Adjutant-owned backend sessions."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

from adjutant.core.config import load_typed_config
from adjutant.core.logging import adj_log
from adjutant.core.opencode_server import ManagedOpenCodeServer, OpenCodeServerError
from adjutant.operations.store import OperationStore

_DAY_SECONDS = 86400


async def run_retention(
    adj_dir: Path,
    *,
    store: OperationStore | None = None,
    now: float | None = None,
) -> dict[str, Any]:
    """Delete expired evidence while retaining failed session cleanups."""
    config = load_typed_config(adj_dir / "adjutant.yaml")
    retention = config.operations.retention
    current = time.time() if now is None else now
    operation_store = store or OperationStore(adj_dir)
    session_cutoff = current - retention.backend_sessions_days * _DAY_SECONDS
    session_rows = operation_store.list_owned_backend_sessions_before(session_cutoff)
    protected_operations: set[str] = set()
    deleted_sessions = 0

    if session_rows and config.operations.persistent_opencode.enabled:
        manager = ManagedOpenCodeServer(adj_dir, config.operations.persistent_opencode)
        try:
            endpoint = await manager.ensure_ready()
        except OpenCodeServerError as exc:
            protected_operations.update(row[0] for row in session_rows)
            adj_log("operations", f"Backend session retention deferred: {exc}")
        else:
            client = endpoint.client(timeout=config.operations.timeouts.connection_seconds)
            for operation_id, session_id, server_instance_id, workdir in session_rows:
                # Sessions belong to one OpenCode server process. A different
                # instance cannot retain this session, so do not issue a
                # repeated delete request that can only return 404.
                if server_instance_id != endpoint.instance_id:
                    deleted_sessions += 1
                    continue
                try:
                    deleted = await asyncio.to_thread(
                        client.delete_session,
                        session_id,
                        workdir=Path(workdir) if workdir else None,
                    )
                except OpenCodeServerError as exc:
                    protected_operations.add(operation_id)
                    adj_log(
                        "operations",
                        f"Backend session {session_id} retention deferred: {exc}",
                    )
                else:
                    if deleted:
                        deleted_sessions += 1
                    else:
                        protected_operations.add(operation_id)
    elif session_rows:
        protected_operations.update(row[0] for row in session_rows)

    counts = operation_store.prune_retention(
        completed_before=current - retention.completed_days * _DAY_SECONDS,
        events_before=current - retention.events_days * _DAY_SECONDS,
        deliveries_before=current - retention.deliveries_days * _DAY_SECONDS,
        protected_operation_ids=protected_operations,
    )
    return {
        **counts,
        "backend_sessions": deleted_sessions,
        "protected_operations": len(protected_operations),
    }
