"""Retention tests for operation evidence and owned OpenCode sessions."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from adjutant.operations.models import OperationState
from adjutant.operations.retention import run_retention
from adjutant.operations.store import OperationStore

if TYPE_CHECKING:
    from pathlib import Path


def _completed_with_session(store: OperationStore, *, completed_at: float) -> str:
    operation = store.create_operation(
        kind="prompt",
        source="test",
        payload={"text": "old"},
        workdir=str(store.adj_dir),
    )
    claimed = store.claim_next("worker")
    assert claimed is not None
    attempt = store.start_attempt(claimed, "worker")
    store.transition(operation.id, OperationState.RUNNING, worker_id="worker")
    store.update_attempt(
        attempt.id,
        state=OperationState.SUCCEEDED.value,
        completed=True,
        server_instance_id="ocs-owned",
        backend_session_id="session-owned",
    )
    store.complete_with_deliveries(
        operation.id,
        OperationState.SUCCEEDED,
        result_text="done",
        deliveries=(("telegram", {"text": "done"}, 0),),
    )
    with store._connect() as conn:  # noqa: SLF001 - arrange retention age
        conn.execute(
            "UPDATE operations SET completed_at=? WHERE id=?",
            (completed_at, operation.id),
        )
        conn.execute(
            "UPDATE deliveries SET updated_at=? WHERE operation_id=?",
            (completed_at, operation.id),
        )
    return operation.id


@pytest.mark.asyncio
async def test_retention_deletes_only_recorded_owned_session(tmp_path: Path) -> None:
    (tmp_path / "adjutant.yaml").write_text(
        "operations:\n"
        "  enabled: true\n"
        "  retention:\n"
        "    completed_days: 0\n"
        "    events_days: 0\n"
        "    deliveries_days: 0\n"
        "    backend_sessions_days: 0\n"
        "  persistent_opencode:\n"
        "    enabled: true\n"
    )
    store = OperationStore(tmp_path)
    operation_id = _completed_with_session(store, completed_at=1.0)
    client = MagicMock()
    client.delete_session.return_value = True
    endpoint = MagicMock()
    endpoint.client.return_value = client

    with patch(
        "adjutant.operations.retention.ManagedOpenCodeServer.ensure_ready",
        new=AsyncMock(return_value=endpoint),
    ):
        result = await run_retention(tmp_path, store=store, now=100.0)

    client.delete_session.assert_called_once()
    assert client.delete_session.call_args.args == ("session-owned",)
    assert store.get_operation(operation_id) is None
    assert result["backend_sessions"] == 1
    assert result["operations"] == 1


@pytest.mark.asyncio
async def test_failed_owned_session_cleanup_preserves_operation(tmp_path: Path) -> None:
    (tmp_path / "adjutant.yaml").write_text(
        "operations:\n"
        "  enabled: true\n"
        "  retention:\n"
        "    completed_days: 0\n"
        "    events_days: 0\n"
        "    deliveries_days: 0\n"
        "    backend_sessions_days: 0\n"
        "  persistent_opencode:\n"
        "    enabled: true\n"
    )
    store = OperationStore(tmp_path)
    operation_id = _completed_with_session(store, completed_at=1.0)
    client = MagicMock()
    client.delete_session.return_value = False
    endpoint = MagicMock()
    endpoint.client.return_value = client

    with patch(
        "adjutant.operations.retention.ManagedOpenCodeServer.ensure_ready",
        new=AsyncMock(return_value=endpoint),
    ):
        result = await run_retention(tmp_path, store=store, now=100.0)

    assert store.get_operation(operation_id) is not None
    assert result["protected_operations"] == 1
