"""Database initialization and WAL lifetime regressions."""

from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from adjutant.operations.store import OperationStore

if TYPE_CHECKING:
    from pathlib import Path


def test_idle_polls_keep_sidecars_and_database_content_unchanged(tmp_path: Path) -> None:
    store = OperationStore(tmp_path)
    wal = store.database_path.with_suffix(".sqlite3-wal")
    shm = store.database_path.with_suffix(".sqlite3-shm")
    with store.keep_open():
        before = store.database_path.read_bytes()
        modified = store.database_path.stat().st_mtime_ns
        inodes = (wal.stat().st_ino, shm.stat().st_ino)
        for _ in range(20):
            assert store.list_blocked_by_failed_dependency() == []
            assert store.claim_next("worker") is None
            assert store.claim_delivery("delivery") is None
            assert (wal.stat().st_ino, shm.stat().st_ino) == inodes
            assert wal.stat().st_size == 0
        assert store.database_path.read_bytes() == before
        assert store.database_path.stat().st_mtime_ns == modified
    assert not wal.exists()
    assert not shm.exists()


def test_idle_polls_do_not_repeat_schema_or_migration_statements(tmp_path: Path) -> None:
    store = OperationStore(tmp_path)
    statements: list[str] = []
    connect = sqlite3.connect

    def traced_connect(*args, **kwargs):
        conn = connect(*args, **kwargs)
        conn.set_trace_callback(statements.append)
        return conn

    with store.keep_open(), patch("sqlite3.connect", side_effect=traced_connect):
        for _ in range(3):
            store.list_blocked_by_failed_dependency()
            store.claim_next("worker")
            store.claim_delivery("delivery")
    assert statements
    assert not any(
        sql.lstrip().upper().startswith(("CREATE", "ALTER", "INSERT", "UPDATE"))
        or "TABLE_INFO" in sql.upper()
        or "JOURNAL_MODE" in sql.upper()
        for sql in statements
    )


def test_keep_open_allows_other_writers_and_checkpointing(tmp_path: Path) -> None:
    store = OperationStore(tmp_path)
    with store.keep_open():
        other = OperationStore(tmp_path)
        operation = other.create_operation(kind="prompt", source="test", payload={})
        claimed = store.claim_next("worker")
        assert claimed is not None
        assert claimed.id == operation.id
        with sqlite3.connect(store.database_path) as conn:
            assert conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone() == (0, 0, 0)


def test_keep_open_closes_sidecars_after_exception(tmp_path: Path) -> None:
    store = OperationStore(tmp_path)
    with pytest.raises(RuntimeError, match="worker failed"), store.keep_open():
        raise RuntimeError("worker failed")
    assert not store.database_path.with_suffix(".sqlite3-wal").exists()
    assert not store.database_path.with_suffix(".sqlite3-shm").exists()
    assert OperationStore(tmp_path).claim_next("restarted") is None


@pytest.mark.parametrize("shared_store", [True, False])
def test_concurrent_initialization_and_claims(tmp_path: Path, shared_store: bool) -> None:
    store = OperationStore(tmp_path)

    def enqueue(index: int) -> str:
        writer = store if shared_store else OperationStore(tmp_path)
        return writer.create_operation(kind="prompt", source="test", payload={"i": index}).id

    with ThreadPoolExecutor(max_workers=4) as executor:
        ids = set(executor.map(enqueue, range(12)))
        claims = list(executor.map(lambda i: store.claim_next(f"worker-{i}"), range(16)))
    assert {claim.id for claim in claims if claim is not None} == ids
    assert sum(claim is not None for claim in claims) == len(ids)


def test_failed_initialization_rolls_back_and_can_retry(tmp_path: Path) -> None:
    store = OperationStore(tmp_path)
    connect = sqlite3.connect

    class FailingConnection(sqlite3.Connection):
        def execute(self, sql, parameters=()):
            if sql.startswith("UPDATE operations SET execution_mode"):
                raise sqlite3.OperationalError("injected migration failure")
            return super().execute(sql, parameters)

    def failing_connect(*args, **kwargs):
        return connect(*args, **kwargs, factory=FailingConnection)

    with (
        patch("sqlite3.connect", side_effect=failing_connect),
        pytest.raises(sqlite3.OperationalError, match="injected migration failure"),
    ):
        store.initialize()
    with connect(store.database_path) as conn:
        assert conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() == []
    store.initialize()
    assert store.claim_next("worker") is None
