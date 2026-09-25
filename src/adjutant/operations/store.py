"""SQLite persistence for durable operations and deliveries."""

from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

from adjutant.operations.models import (
    Delivery,
    DeliveryState,
    ExecutionAttempt,
    Operation,
    OperationEvent,
    OperationState,
    SideEffectClass,
)

_SCHEMA_VERSION = 3

_ALLOWED_TRANSITIONS: dict[OperationState, set[OperationState]] = {
    OperationState.QUEUED: {
        OperationState.STARTING,
        OperationState.CANCEL_REQUESTED,
        OperationState.CANCELLED,
        OperationState.FAILED,
    },
    OperationState.STARTING: {
        OperationState.RUNNING,
        OperationState.CANCEL_REQUESTED,
        OperationState.RECONCILING,
        OperationState.FAILED,
        OperationState.TIMED_OUT,
        OperationState.CANCELLED,
        OperationState.INTERRUPTED,
    },
    OperationState.RUNNING: {
        OperationState.WAITING_CHILDREN,
        OperationState.WAITING_INPUT,
        OperationState.CANCEL_REQUESTED,
        OperationState.RECONCILING,
        OperationState.SUCCEEDED,
        OperationState.FAILED,
        OperationState.TIMED_OUT,
        OperationState.CANCELLED,
        OperationState.INTERRUPTED,
    },
    OperationState.WAITING_CHILDREN: {
        OperationState.RUNNING,
        OperationState.CANCEL_REQUESTED,
        OperationState.RECONCILING,
        OperationState.FAILED,
    },
    OperationState.WAITING_INPUT: {
        OperationState.RUNNING,
        OperationState.CANCEL_REQUESTED,
        OperationState.RECONCILING,
        OperationState.FAILED,
    },
    OperationState.CANCEL_REQUESTED: {
        OperationState.CANCELLED,
        OperationState.RECONCILING,
        OperationState.FAILED,
        OperationState.SUCCEEDED,
    },
    OperationState.RECONCILING: {
        OperationState.RUNNING,
        OperationState.SUCCEEDED,
        OperationState.FAILED,
        OperationState.INTERRUPTED,
    },
}


class InvalidOperationTransitionError(ValueError):
    """Raised when a state transition violates the operation state machine."""


class LostOperationOwnershipError(RuntimeError):
    """Raised when a stale attempt tries to modify recovered work."""


class OperationStore:
    """Transactional operation store backed by SQLite."""

    def __init__(self, adj_dir: Path, *, database_path: Path | None = None) -> None:
        self.adj_dir = adj_dir
        self.database_path = database_path or adj_dir / "state" / "operations.sqlite3"

    def initialize(self) -> None:
        """Create or migrate the operation database."""
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS operations (
                    id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    source TEXT NOT NULL,
                    state TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    telegram_bot_id TEXT,
                    telegram_update_id INTEGER,
                    telegram_chat_id TEXT,
                    telegram_message_id INTEGER,
                    telegram_thread_id INTEGER,
                    status_message_id INTEGER,
                    parent_id TEXT REFERENCES operations(id),
                    dependency_ids_json TEXT NOT NULL DEFAULT '[]',
                    backend TEXT,
                    model TEXT,
                    variant TEXT,
                    agent TEXT,
                    workdir TEXT,
                    permission_fingerprint TEXT,
                    side_effect_class TEXT NOT NULL,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    lease_owner TEXT,
                    lease_expires_at REAL,
                    cancel_requested INTEGER NOT NULL DEFAULT 0,
                    started_at REAL,
                    completed_at REAL,
                    last_activity_at REAL,
                    result_text TEXT,
                    error_type TEXT,
                    error_message TEXT,
                    recovery_status TEXT,
                    correlation_id TEXT NOT NULL,
                    execution_mode TEXT NOT NULL DEFAULT 'daemon',
                    deadline_at REAL,
                    parent_attempt_id TEXT,
                    current_attempt_id TEXT,
                    origin_session_id TEXT,
                    origin_tool_call_id TEXT
                );

                CREATE INDEX IF NOT EXISTS operations_state_created_idx
                    ON operations(state, created_at);
                CREATE INDEX IF NOT EXISTS operations_parent_idx
                    ON operations(parent_id);

                CREATE TABLE IF NOT EXISTS telegram_inbox (
                    bot_id TEXT NOT NULL,
                    update_id INTEGER NOT NULL,
                    operation_id TEXT NOT NULL REFERENCES operations(id),
                    payload_json TEXT NOT NULL,
                    accepted_at REAL NOT NULL,
                    PRIMARY KEY (bot_id, update_id)
                );

                CREATE TABLE IF NOT EXISTS telegram_offsets (
                    bot_id TEXT PRIMARY KEY,
                    next_offset INTEGER NOT NULL,
                    updated_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS operation_events (
                    operation_id TEXT NOT NULL REFERENCES operations(id),
                    sequence INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    public_message TEXT,
                    data_json TEXT NOT NULL,
                    PRIMARY KEY (operation_id, sequence)
                );

                CREATE TABLE IF NOT EXISTS execution_attempts (
                    id TEXT PRIMARY KEY,
                    operation_id TEXT NOT NULL REFERENCES operations(id),
                    attempt_number INTEGER NOT NULL,
                    worker_id TEXT NOT NULL,
                    state TEXT NOT NULL,
                    started_at REAL NOT NULL,
                    completed_at REAL,
                    pid INTEGER,
                    pid_create_time REAL,
                    process_group_id INTEGER,
                    owner_pid INTEGER,
                    owner_pid_create_time REAL,
                    server_instance_id TEXT,
                    backend_session_id TEXT,
                    backend_message_id TEXT,
                    returncode INTEGER,
                    timeout_reason TEXT,
                    peak_rss_bytes INTEGER,
                    UNIQUE (operation_id, attempt_number)
                );

                CREATE TABLE IF NOT EXISTS deliveries (
                    id TEXT PRIMARY KEY,
                    operation_id TEXT NOT NULL REFERENCES operations(id),
                    destination TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    state TEXT NOT NULL,
                    chunk_number INTEGER NOT NULL DEFAULT 0,
                    telegram_message_id INTEGER,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    next_attempt_at REAL,
                    lease_owner TEXT,
                    lease_expires_at REAL,
                    uncertain INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );

                CREATE INDEX IF NOT EXISTS deliveries_state_next_idx
                    ON deliveries(state, next_attempt_at, created_at);
                """
            )
            conn.execute(
                "INSERT INTO metadata(key, value) VALUES('schema_version', ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (str(_SCHEMA_VERSION),),
            )
            columns = {
                str(row["name"]) for row in conn.execute("PRAGMA table_info(operations)").fetchall()
            }
            if "status_message_id" not in columns:
                conn.execute("ALTER TABLE operations ADD COLUMN status_message_id INTEGER")
            additions = {
                "execution_mode": "TEXT NOT NULL DEFAULT 'daemon'",
                "deadline_at": "REAL",
                "parent_attempt_id": "TEXT",
                "current_attempt_id": "TEXT",
                "origin_session_id": "TEXT",
                "origin_tool_call_id": "TEXT",
            }
            for name, declaration in additions.items():
                if name not in columns:
                    conn.execute(f"ALTER TABLE operations ADD COLUMN {name} {declaration}")
            attempt_columns = {
                str(row["name"])
                for row in conn.execute("PRAGMA table_info(execution_attempts)").fetchall()
            }
            if "owner_pid" not in attempt_columns:
                conn.execute("ALTER TABLE execution_attempts ADD COLUMN owner_pid INTEGER")
            if "owner_pid_create_time" not in attempt_columns:
                conn.execute(
                    "ALTER TABLE execution_attempts ADD COLUMN owner_pid_create_time REAL"
                )
            conn.execute(
                "UPDATE operations SET execution_mode='inline' "
                "WHERE source='kb' AND kind IN ('kb_query', 'kb_write') "
                "AND parent_id IS NOT NULL AND execution_mode='daemon'"
            )
            conn.execute(
                "UPDATE operations SET current_attempt_id=("
                "SELECT a.id FROM execution_attempts a WHERE a.operation_id=operations.id "
                "ORDER BY a.attempt_number DESC LIMIT 1) "
                "WHERE current_attempt_id IS NULL AND state IN (?, ?, ?, ?, ?) "
                "AND EXISTS(SELECT 1 FROM execution_attempts a "
                "WHERE a.operation_id=operations.id)",
                (
                    OperationState.STARTING.value,
                    OperationState.RUNNING.value,
                    OperationState.WAITING_CHILDREN.value,
                    OperationState.WAITING_INPUT.value,
                    OperationState.CANCEL_REQUESTED.value,
                ),
            )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.database_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 5000")
        conn.execute("PRAGMA journal_mode = WAL")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def create_operation(
        self,
        *,
        kind: str,
        source: str,
        payload: dict[str, Any],
        operation_id: str | None = None,
        parent_id: str | None = None,
        dependency_ids: tuple[str, ...] = (),
        telegram_bot_id: str | None = None,
        telegram_update_id: int | None = None,
        telegram_chat_id: str | None = None,
        telegram_message_id: int | None = None,
        telegram_thread_id: int | None = None,
        backend: str | None = None,
        model: str | None = None,
        variant: str | None = None,
        agent: str | None = None,
        workdir: str | None = None,
        permission_fingerprint: str | None = None,
        side_effect_class: SideEffectClass = SideEffectClass.UNKNOWN,
        execution_mode: str = "daemon",
        deadline_at: float | None = None,
        parent_attempt_id: str | None = None,
        origin_session_id: str | None = None,
        origin_tool_call_id: str | None = None,
    ) -> Operation:
        """Insert a queued operation and return it."""
        self.initialize()
        operation_id = operation_id or _new_id("op")
        now = time.time()
        with self._connect() as conn:
            self._insert_operation(
                conn,
                operation_id=operation_id,
                kind=kind,
                source=source,
                payload=payload,
                now=now,
                parent_id=parent_id,
                dependency_ids=dependency_ids,
                telegram_bot_id=telegram_bot_id,
                telegram_update_id=telegram_update_id,
                telegram_chat_id=telegram_chat_id,
                telegram_message_id=telegram_message_id,
                telegram_thread_id=telegram_thread_id,
                backend=backend,
                model=model,
                variant=variant,
                agent=agent,
                workdir=workdir,
                permission_fingerprint=permission_fingerprint,
                side_effect_class=side_effect_class,
                execution_mode=execution_mode,
                deadline_at=deadline_at,
                parent_attempt_id=parent_attempt_id,
                origin_session_id=origin_session_id,
                origin_tool_call_id=origin_tool_call_id,
            )
        operation = self.get_operation(operation_id)
        if operation is None:
            raise RuntimeError(f"Operation {operation_id} disappeared after insertion")
        return operation

    def create_inline_operation(
        self,
        *,
        kind: str,
        source: str,
        payload: dict[str, Any],
        worker_id: str,
        lease_seconds: float,
        parent_id: str,
        deadline_at: float,
        parent_attempt_id: str,
        backend: str | None = None,
        model: str | None = None,
        variant: str | None = None,
        agent: str | None = None,
        workdir: str | None = None,
        side_effect_class: SideEffectClass = SideEffectClass.UNKNOWN,
        origin_session_id: str | None = None,
        origin_tool_call_id: str | None = None,
    ) -> tuple[Operation, ExecutionAttempt]:
        """Accept, claim, and start an inline child in one transaction."""
        self.initialize()
        now = time.time()
        operation_id = _new_id("op")
        attempt_id = _new_id("attempt")
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            parent = conn.execute(
                "SELECT state, current_attempt_id, deadline_at FROM operations WHERE id=?",
                (parent_id,),
            ).fetchone()
            if parent is None:
                raise LostOperationOwnershipError(f"Parent operation {parent_id} was not found")
            if parent["current_attempt_id"] != parent_attempt_id:
                raise LostOperationOwnershipError(
                    f"Parent operation {parent_id} no longer owns attempt {parent_attempt_id}"
                )
            if OperationState(parent["state"]).terminal:
                raise LostOperationOwnershipError(f"Parent operation {parent_id} is complete")
            parent_deadline = parent["deadline_at"]
            if parent_deadline is None or float(parent_deadline) < deadline_at:
                raise LostOperationOwnershipError(
                    f"Child deadline exceeds parent operation {parent_id} deadline"
                )
            self._insert_operation(
                conn,
                operation_id=operation_id,
                kind=kind,
                source=source,
                payload=payload,
                now=now,
                parent_id=parent_id,
                backend=backend,
                model=model,
                variant=variant,
                agent=agent,
                workdir=workdir,
                side_effect_class=side_effect_class,
                execution_mode="inline",
                deadline_at=deadline_at,
                parent_attempt_id=parent_attempt_id,
                origin_session_id=origin_session_id,
                origin_tool_call_id=origin_tool_call_id,
            )
            conn.execute(
                "UPDATE operations SET state=?, started_at=?, last_activity_at=?, "
                "lease_owner=?, lease_expires_at=?, attempt_count=1, current_attempt_id=? "
                "WHERE id=?",
                (
                    OperationState.STARTING.value,
                    now,
                    now,
                    worker_id,
                    now + lease_seconds,
                    attempt_id,
                    operation_id,
                ),
            )
            conn.execute(
                "INSERT INTO execution_attempts"
                "(id, operation_id, attempt_number, worker_id, state, started_at, owner_pid, "
                "owner_pid_create_time) VALUES(?, ?, 1, ?, ?, ?, ?, ?)",
                (
                    attempt_id,
                    operation_id,
                    worker_id,
                    OperationState.STARTING.value,
                    now,
                    os.getpid(),
                    _process_birth_time(os.getpid()),
                ),
            )
            conn.execute(
                "INSERT INTO operation_events"
                "(operation_id, sequence, event_type, created_at, public_message, data_json) "
                "VALUES(?, 1, 'accepted', ?, ?, ?)",
                (
                    operation_id,
                    now,
                    f"Inline child {operation_id} accepted",
                    _json({"attempt_id": attempt_id, "parent_attempt_id": parent_attempt_id}),
                ),
            )
            operation_row = conn.execute(
                "SELECT * FROM operations WHERE id=?", (operation_id,)
            ).fetchone()
            attempt_row = conn.execute(
                "SELECT * FROM execution_attempts WHERE id=?", (attempt_id,)
            ).fetchone()
        if operation_row is None or attempt_row is None:
            raise RuntimeError(f"Inline operation {operation_id} disappeared after acceptance")
        return self._operation_from_row(operation_row), self._attempt_from_row(attempt_row)

    def accept_telegram_update(
        self,
        *,
        bot_id: str,
        update_id: int,
        next_offset: int,
        kind: str,
        payload: dict[str, Any],
        chat_id: str,
        message_id: int,
        thread_id: int | None = None,
        parent_id: str | None = None,
        dependency_ids: tuple[str, ...] = (),
        backend: str | None = None,
        model: str | None = None,
        variant: str | None = None,
        agent: str | None = None,
        workdir: str | None = None,
        permission_fingerprint: str | None = None,
        side_effect_class: SideEffectClass = SideEffectClass.UNKNOWN,
    ) -> tuple[Operation, bool]:
        """Atomically accept one Telegram update and advance its bot offset.

        Returns the operation and ``True`` when it was newly inserted. A
        duplicate update returns the original operation and ``False``.
        """
        self.initialize()
        now = time.time()
        operation_id = _new_id("op")
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                "SELECT operation_id FROM telegram_inbox WHERE bot_id=? AND update_id=?",
                (bot_id, update_id),
            ).fetchone()
            if existing is not None:
                self._advance_offset(conn, bot_id, next_offset, now)
                row = conn.execute(
                    "SELECT * FROM operations WHERE id=?", (existing["operation_id"],)
                ).fetchone()
                if row is None:
                    raise RuntimeError("Telegram inbox references a missing operation")
                return self._operation_from_row(row), False

            self._insert_operation(
                conn,
                operation_id=operation_id,
                kind=kind,
                source="telegram",
                payload=payload,
                now=now,
                telegram_bot_id=bot_id,
                telegram_update_id=update_id,
                telegram_chat_id=chat_id,
                telegram_message_id=message_id,
                telegram_thread_id=thread_id,
                parent_id=parent_id,
                dependency_ids=dependency_ids,
                backend=backend,
                model=model,
                variant=variant,
                agent=agent,
                workdir=workdir,
                permission_fingerprint=permission_fingerprint,
                side_effect_class=side_effect_class,
            )
            conn.execute(
                "INSERT INTO telegram_inbox"
                "(bot_id, update_id, operation_id, payload_json, accepted_at) "
                "VALUES(?, ?, ?, ?, ?)",
                (bot_id, update_id, operation_id, _json(payload), now),
            )
            self._advance_offset(conn, bot_id, next_offset, now)
            row = conn.execute("SELECT * FROM operations WHERE id=?", (operation_id,)).fetchone()
            if row is None:
                raise RuntimeError("Accepted operation could not be read")
            return self._operation_from_row(row), True

    def get_telegram_offset(self, bot_id: str, *, default: int = 0) -> int:
        """Return the next Telegram update offset stored for one bot."""
        self.initialize()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT next_offset FROM telegram_offsets WHERE bot_id=?", (bot_id,)
            ).fetchone()
        return int(row["next_offset"]) if row is not None else default

    def advance_telegram_offset(self, bot_id: str, next_offset: int) -> None:
        """Advance a bot offset for an update that produces no operation."""
        self.initialize()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            self._advance_offset(conn, bot_id, next_offset, time.time())

    def set_status_message_id(self, operation_id: str, message_id: int) -> Operation:
        """Record the Telegram acknowledgement used for progress edits."""
        self.initialize()
        now = time.time()
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE operations SET status_message_id=?, updated_at=? WHERE id=?",
                (message_id, now, operation_id),
            )
            if cursor.rowcount != 1:
                raise KeyError(operation_id)
            row = conn.execute("SELECT * FROM operations WHERE id=?", (operation_id,)).fetchone()
        if row is None:
            raise KeyError(operation_id)
        return self._operation_from_row(row)

    def get_operation(self, operation_id: str) -> Operation | None:
        self.initialize()
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM operations WHERE id=?", (operation_id,)).fetchone()
        return self._operation_from_row(row) if row is not None else None

    def find_telegram_operation(
        self,
        chat_id: str,
        message_id: int,
    ) -> Operation | None:
        """Resolve an original or acknowledgement Telegram message to an operation."""
        self.initialize()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM operations WHERE telegram_chat_id=? "
                "AND (telegram_message_id=? OR status_message_id=?) "
                "ORDER BY created_at DESC LIMIT 1",
                (chat_id, message_id, message_id),
            ).fetchone()
        return self._operation_from_row(row) if row is not None else None

    def find_operation_reference(self, reference: str) -> Operation | None:
        """Resolve an exact operation ID or an unambiguous ID prefix."""
        self.initialize()
        with self._connect() as conn:
            exact = conn.execute("SELECT * FROM operations WHERE id=?", (reference,)).fetchone()
            if exact is not None:
                return self._operation_from_row(exact)
            rows = conn.execute(
                "SELECT * FROM operations WHERE id LIKE ? ORDER BY created_at DESC LIMIT 2",
                (f"{reference}%",),
            ).fetchall()
        if len(rows) != 1:
            return None
        return self._operation_from_row(rows[0])

    def list_conversation_operations(
        self,
        chat_id: str,
        *,
        before_created_at: float | None = None,
        limit: int = 6,
    ) -> list[Operation]:
        """Return recent terminal Telegram turns oldest first for context."""
        self.initialize()
        params: list[Any] = [chat_id, OperationState.SUCCEEDED.value]
        condition = ""
        if before_created_at is not None:
            condition = " AND created_at<?"
            params.append(before_created_at)
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM operations WHERE telegram_chat_id=? AND state=?"
                f"{condition} ORDER BY created_at DESC LIMIT ?",
                params,
            ).fetchall()
        return [self._operation_from_row(row) for row in reversed(rows)]

    def list_operations(
        self,
        *,
        states: tuple[OperationState, ...] | None = None,
        limit: int = 50,
    ) -> list[Operation]:
        """List operations newest first."""
        self.initialize()
        query = "SELECT * FROM operations"
        params: list[Any] = []
        if states:
            placeholders = ",".join("?" for _ in states)
            query += f" WHERE state IN ({placeholders})"
            params.extend(state.value for state in states)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._operation_from_row(row) for row in rows]

    def sync_active_snapshot(self) -> list[dict[str, Any]]:
        """Write the operation-list compatibility snapshot used by local clients."""
        self.initialize()
        active_states = (
            OperationState.QUEUED,
            OperationState.STARTING,
            OperationState.RUNNING,
            OperationState.WAITING_CHILDREN,
            OperationState.WAITING_INPUT,
            OperationState.CANCEL_REQUESTED,
            OperationState.RECONCILING,
        )
        placeholders = ",".join("?" for _ in active_states)
        with self._connect() as conn:
            # A write transaction serializes snapshot producers across worker
            # processes. Query after acquiring it so a delayed writer cannot
            # overwrite a newer operation list with stale state.
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute(
                "SELECT * FROM operations WHERE state IN ("
                f"{placeholders}) ORDER BY created_at DESC LIMIT 500",
                tuple(state.value for state in active_states),
            ).fetchall()
            operations = [self._operation_from_row(row) for row in rows]
            snapshot = [
                {
                    "id": operation.id,
                    "action": str(operation.payload.get("action") or operation.kind),
                    "kind": operation.kind,
                    "state": operation.state.value,
                    "source": operation.source,
                    "created_at": datetime.fromtimestamp(operation.created_at, UTC).isoformat(),
                    "started_at": (
                        datetime.fromtimestamp(operation.started_at, UTC).isoformat()
                        if operation.started_at is not None
                        else None
                    ),
                    "parent_id": operation.parent_id,
                }
                for operation in operations
            ]
            snapshot_path = self.adj_dir / "state" / "active_operations.json"
            snapshot_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = snapshot_path.with_suffix(".tmp")
            temporary.write_text(json.dumps(snapshot, sort_keys=True))
            temporary.replace(snapshot_path)
        return snapshot

    def list_owned_backend_sessions_before(
        self,
        cutoff: float,
    ) -> list[tuple[str, str, str, str | None]]:
        """Return only sessions recorded on completed Adjutant attempts."""
        self.initialize()
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT o.id AS operation_id, a.backend_session_id, "
                "a.server_instance_id, o.workdir "
                "FROM execution_attempts a JOIN operations o ON o.id=a.operation_id "
                "WHERE a.backend_session_id IS NOT NULL AND a.server_instance_id IS NOT NULL "
                "AND o.completed_at IS NOT NULL AND o.completed_at<?",
                (cutoff,),
            ).fetchall()
        return [
            (
                str(row["operation_id"]),
                str(row["backend_session_id"]),
                str(row["server_instance_id"]),
                row["workdir"],
            )
            for row in rows
        ]

    def prune_retention(
        self,
        *,
        completed_before: float,
        events_before: float,
        deliveries_before: float,
        protected_operation_ids: set[str] | None = None,
    ) -> dict[str, int]:
        """Prune terminal operation evidence without touching active dependencies."""
        self.initialize()
        counts = {"operations": 0, "events": 0, "deliveries": 0, "attempts": 0}
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            counts["events"] = conn.execute(
                "DELETE FROM operation_events WHERE created_at<?",
                (events_before,),
            ).rowcount
            counts["deliveries"] = conn.execute(
                "DELETE FROM deliveries WHERE updated_at<? AND state IN (?, ?)",
                (
                    deliveries_before,
                    DeliveryState.DELIVERED.value,
                    DeliveryState.BLOCKED.value,
                ),
            ).rowcount
            active_rows = conn.execute(
                "SELECT parent_id, dependency_ids_json FROM operations "
                "WHERE state NOT IN (?, ?, ?, ?, ?)",
                (
                    OperationState.SUCCEEDED.value,
                    OperationState.FAILED.value,
                    OperationState.TIMED_OUT.value,
                    OperationState.CANCELLED.value,
                    OperationState.INTERRUPTED.value,
                ),
            ).fetchall()
            protected: set[str] = set(protected_operation_ids or ())
            for row in active_rows:
                if row["parent_id"]:
                    protected.add(str(row["parent_id"]))
                protected.update(str(value) for value in json.loads(row["dependency_ids_json"]))
            candidates = conn.execute(
                "SELECT id FROM operations WHERE completed_at IS NOT NULL AND completed_at<?",
                (completed_before,),
            ).fetchall()
            operation_ids = [
                str(row["id"]) for row in candidates if str(row["id"]) not in protected
            ]
            for operation_id in operation_ids:
                conn.execute("DELETE FROM telegram_inbox WHERE operation_id=?", (operation_id,))
                conn.execute("DELETE FROM operation_events WHERE operation_id=?", (operation_id,))
                conn.execute("DELETE FROM deliveries WHERE operation_id=?", (operation_id,))
                counts["attempts"] += conn.execute(
                    "DELETE FROM execution_attempts WHERE operation_id=?",
                    (operation_id,),
                ).rowcount
                counts["operations"] += conn.execute(
                    "DELETE FROM operations WHERE id=?",
                    (operation_id,),
                ).rowcount
        self.sync_active_snapshot()
        return counts

    def list_blocked_by_failed_dependency(self, *, limit: int = 100) -> list[Operation]:
        """Return queued operations whose dependency ended unsuccessfully."""
        self.initialize()
        blocked: list[Operation] = []
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM operations WHERE state=? ORDER BY created_at ASC LIMIT ?",
                (OperationState.QUEUED.value, limit),
            ).fetchall()
            for row in rows:
                dependency_ids = tuple(json.loads(row["dependency_ids_json"]))
                if not dependency_ids:
                    continue
                placeholders = ",".join("?" for _ in dependency_ids)
                dependencies = conn.execute(
                    f"SELECT state FROM operations WHERE id IN ({placeholders})",
                    dependency_ids,
                ).fetchall()
                if any(
                    OperationState(item["state"]).terminal
                    and OperationState(item["state"]) is not OperationState.SUCCEEDED
                    for item in dependencies
                ):
                    blocked.append(self._operation_from_row(row))
        return blocked

    def claim_next(self, worker_id: str, *, lease_seconds: float = 60.0) -> Operation | None:
        """Claim the oldest runnable queued operation."""
        self.initialize()
        now = time.time()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute(
                "SELECT * FROM operations WHERE state=? AND execution_mode='daemon' "
                "ORDER BY created_at ASC",
                (OperationState.QUEUED.value,),
            ).fetchall()
            selected: sqlite3.Row | None = None
            for row in rows:
                dependency_ids = tuple(json.loads(row["dependency_ids_json"]))
                if self._dependencies_succeeded(conn, dependency_ids):
                    selected = row
                    break
            if selected is None:
                return None
            operation_id = str(selected["id"])
            conn.execute(
                "UPDATE operations SET state=?, updated_at=?, started_at=COALESCE(started_at, ?), "
                "last_activity_at=?, lease_owner=?, lease_expires_at=?, "
                "attempt_count=attempt_count+1 WHERE id=? AND state=?",
                (
                    OperationState.STARTING.value,
                    now,
                    now,
                    now,
                    worker_id,
                    now + lease_seconds,
                    operation_id,
                    OperationState.QUEUED.value,
                ),
            )
            row = conn.execute("SELECT * FROM operations WHERE id=?", (operation_id,)).fetchone()
            return self._operation_from_row(row) if row is not None else None

    def claim_operation(
        self,
        operation_id: str,
        worker_id: str,
        *,
        lease_seconds: float = 60.0,
    ) -> Operation | None:
        """Claim a specific queued operation for safe inline child execution."""
        self.initialize()
        now = time.time()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM operations WHERE id=?", (operation_id,)).fetchone()
            if row is None or row["state"] != OperationState.QUEUED.value:
                return None
            dependency_ids = tuple(json.loads(row["dependency_ids_json"]))
            if not self._dependencies_succeeded(conn, dependency_ids):
                return None
            cursor = conn.execute(
                "UPDATE operations SET state=?, updated_at=?, started_at=COALESCE(started_at, ?), "
                "last_activity_at=?, lease_owner=?, lease_expires_at=?, "
                "attempt_count=attempt_count+1 WHERE id=? AND state=?",
                (
                    OperationState.STARTING.value,
                    now,
                    now,
                    now,
                    worker_id,
                    now + lease_seconds,
                    operation_id,
                    OperationState.QUEUED.value,
                ),
            )
            if cursor.rowcount != 1:
                return None
            claimed = conn.execute(
                "SELECT * FROM operations WHERE id=?", (operation_id,)
            ).fetchone()
        return self._operation_from_row(claimed) if claimed is not None else None

    def transition(
        self,
        operation_id: str,
        new_state: OperationState,
        *,
        worker_id: str | None = None,
        lease_seconds: float | None = None,
        result_text: str | None = None,
        error_type: str | None = None,
        error_message: str | None = None,
        recovery_status: str | None = None,
        expected_attempt_id: str | None = None,
    ) -> Operation:
        """Move one operation through the validated state machine."""
        self.initialize()
        now = time.time()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM operations WHERE id=?", (operation_id,)).fetchone()
            if row is None:
                raise KeyError(operation_id)
            self._assert_ownership(row, worker_id, expected_attempt_id)
            current = OperationState(row["state"])
            if new_state != current and new_state not in _ALLOWED_TRANSITIONS.get(current, set()):
                raise InvalidOperationTransitionError(f"{current.value} -> {new_state.value}")

            completed_at = now if new_state.terminal else row["completed_at"]
            lease_owner = row["lease_owner"]
            lease_expires_at = row["lease_expires_at"]
            if new_state.terminal:
                lease_owner = None
                lease_expires_at = None
            elif worker_id is not None:
                lease_owner = worker_id
                if lease_seconds is not None:
                    lease_expires_at = now + lease_seconds

            conn.execute(
                "UPDATE operations SET state=?, updated_at=?, last_activity_at=?, "
                "completed_at=?, lease_owner=?, lease_expires_at=?, "
                "result_text=COALESCE(?, result_text), "
                "error_type=COALESCE(?, error_type), error_message=COALESCE(?, error_message), "
                "recovery_status=COALESCE(?, recovery_status) WHERE id=?",
                (
                    new_state.value,
                    now,
                    now,
                    completed_at,
                    lease_owner,
                    lease_expires_at,
                    result_text,
                    error_type,
                    error_message,
                    recovery_status,
                    operation_id,
                ),
            )
            updated = conn.execute(
                "SELECT * FROM operations WHERE id=?", (operation_id,)
            ).fetchone()
        if updated is None:
            raise RuntimeError(f"Operation {operation_id} disappeared after transition")
        return self._operation_from_row(updated)

    def complete_with_deliveries(
        self,
        operation_id: str,
        new_state: OperationState,
        *,
        result_text: str | None = None,
        error_type: str | None = None,
        error_message: str | None = None,
        deliveries: tuple[tuple[str, dict[str, Any], int], ...] = (),
        worker_id: str | None = None,
        expected_attempt_id: str | None = None,
    ) -> Operation:
        """Persist a terminal result and its outbound deliveries atomically."""
        if not new_state.terminal:
            raise ValueError(f"Completion state must be terminal, got {new_state.value}")
        self.initialize()
        now = time.time()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM operations WHERE id=?", (operation_id,)).fetchone()
            if row is None:
                raise KeyError(operation_id)
            self._assert_ownership(row, worker_id, expected_attempt_id)
            current = OperationState(row["state"])
            if new_state != current and new_state not in _ALLOWED_TRANSITIONS.get(current, set()):
                raise InvalidOperationTransitionError(f"{current.value} -> {new_state.value}")

            conn.execute(
                "UPDATE operations SET state=?, updated_at=?, last_activity_at=?, "
                "completed_at=?, lease_owner=NULL, lease_expires_at=NULL, "
                "result_text=COALESCE(?, result_text), error_type=COALESCE(?, error_type), "
                "error_message=COALESCE(?, error_message) WHERE id=?",
                (
                    new_state.value,
                    now,
                    now,
                    now,
                    result_text,
                    error_type,
                    error_message,
                    operation_id,
                ),
            )
            if expected_attempt_id is not None:
                conn.execute(
                    "UPDATE execution_attempts SET state=?, completed_at=COALESCE(completed_at, ?) "
                    "WHERE id=? AND operation_id=?",
                    (new_state.value, now, expected_attempt_id, operation_id),
                )
            for destination, payload, chunk_number in deliveries:
                conn.execute(
                    "INSERT INTO deliveries"
                    "(id, operation_id, destination, payload_json, state, chunk_number, "
                    "created_at, updated_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        _new_id("delivery"),
                        operation_id,
                        destination,
                        _json(payload),
                        DeliveryState.PENDING.value,
                        chunk_number,
                        now,
                        now,
                    ),
                )
            updated = conn.execute(
                "SELECT * FROM operations WHERE id=?", (operation_id,)
            ).fetchone()
        if updated is None:
            raise RuntimeError(f"Operation {operation_id} disappeared after completion")
        return self._operation_from_row(updated)

    def start_attempt(
        self,
        operation: Operation,
        worker_id: str,
        *,
        runtime_seconds: float | None = None,
    ) -> ExecutionAttempt:
        """Record execution ownership after an operation has been claimed."""
        self.initialize()
        attempt_id = _new_id("attempt")
        now = time.time()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            owner = conn.execute(
                "SELECT lease_owner, state, deadline_at FROM operations WHERE id=?",
                (operation.id,),
            ).fetchone()
            if (
                owner is None
                or owner["lease_owner"] != worker_id
                or owner["state"] != OperationState.STARTING.value
            ):
                raise LostOperationOwnershipError(
                    f"Operation {operation.id} is no longer owned by {worker_id}"
                )
            deadline_at = owner["deadline_at"]
            if deadline_at is None and runtime_seconds is not None:
                deadline_at = now + runtime_seconds
            conn.execute(
                "INSERT INTO execution_attempts"
                "(id, operation_id, attempt_number, worker_id, state, started_at, "
                "owner_pid, owner_pid_create_time) VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    attempt_id,
                    operation.id,
                    operation.attempt_count,
                    worker_id,
                    OperationState.STARTING.value,
                    now,
                    os.getpid(),
                    _process_birth_time(os.getpid()),
                ),
            )
            conn.execute(
                "UPDATE operations SET current_attempt_id=?, deadline_at=COALESCE(deadline_at, ?) "
                "WHERE id=? AND lease_owner=?",
                (attempt_id, deadline_at, operation.id, worker_id),
            )
            row = conn.execute(
                "SELECT * FROM execution_attempts WHERE id=?", (attempt_id,)
            ).fetchone()
        if row is None:
            raise RuntimeError(f"Attempt {attempt_id} disappeared after insertion")
        return self._attempt_from_row(row)

    def get_attempt(self, attempt_id: str) -> ExecutionAttempt | None:
        """Return one attempt by its durable identifier."""
        self.initialize()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM execution_attempts WHERE id=?", (attempt_id,)
            ).fetchone()
        return self._attempt_from_row(row) if row is not None else None

    def list_execution_children(self, parent_id: str) -> list[Operation]:
        """Return only inline execution children, excluding conversational links."""
        self.initialize()
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM operations WHERE parent_id=? AND execution_mode='inline' "
                "ORDER BY created_at ASC",
                (parent_id,),
            ).fetchall()
        return [self._operation_from_row(row) for row in rows]

    def abandon_attempt(
        self,
        operation_id: str,
        attempt_id: str,
        worker_id: str,
        *,
        reason: str,
    ) -> Operation:
        """Fence an interrupted inline owner without replaying uncertain work."""
        self.initialize()
        now = time.time()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM operations WHERE id=?", (operation_id,)
            ).fetchone()
            if row is None:
                raise KeyError(operation_id)
            self._assert_ownership(row, worker_id, attempt_id)
            side_effect = SideEffectClass(row["side_effect_class"])
            state = (
                OperationState.RECONCILING
                if side_effect in {SideEffectClass.MUTATING, SideEffectClass.UNKNOWN}
                else OperationState.INTERRUPTED
            )
            conn.execute(
                "UPDATE execution_attempts SET state=?, completed_at=?, timeout_reason=? "
                "WHERE id=? AND completed_at IS NULL",
                (OperationState.INTERRUPTED.value, now, reason, attempt_id),
            )
            conn.execute(
                "UPDATE operations SET state=?, updated_at=?, last_activity_at=?, "
                "completed_at=?, lease_owner=NULL, lease_expires_at=NULL, "
                "current_attempt_id=NULL, recovery_status=?, error_type=? WHERE id=?",
                (
                    state.value,
                    now,
                    now,
                    now if state.terminal else None,
                    reason,
                    "caller_interrupted",
                    operation_id,
                ),
            )
            updated = conn.execute(
                "SELECT * FROM operations WHERE id=?", (operation_id,)
            ).fetchone()
        if updated is None:
            raise RuntimeError(f"Operation {operation_id} disappeared after abandonment")
        return self._operation_from_row(updated)

    def update_attempt(
        self,
        attempt_id: str,
        *,
        state: str,
        completed: bool = False,
        pid: int | None = None,
        pid_create_time: float | None = None,
        process_group_id: int | None = None,
        server_instance_id: str | None = None,
        backend_session_id: str | None = None,
        backend_message_id: str | None = None,
        returncode: int | None = None,
        timeout_reason: str | None = None,
        peak_rss_bytes: int | None = None,
        require_current: bool = True,
    ) -> ExecutionAttempt:
        """Update execution evidence for one attempt."""
        self.initialize()
        completed_at = time.time() if completed else None
        with self._connect() as conn:
            attempt_owner = conn.execute(
                "SELECT operation_id FROM execution_attempts WHERE id=?", (attempt_id,)
            ).fetchone()
            if attempt_owner is None:
                raise KeyError(attempt_id)
            if require_current:
                operation_owner = conn.execute(
                    "SELECT current_attempt_id FROM operations WHERE id=?",
                    (attempt_owner["operation_id"],),
                ).fetchone()
                if operation_owner is None or operation_owner["current_attempt_id"] != attempt_id:
                    raise LostOperationOwnershipError(
                        f"Attempt {attempt_id} no longer owns its operation"
                    )
            conn.execute(
                "UPDATE execution_attempts SET state=?, "
                "completed_at=COALESCE(?, completed_at), pid=COALESCE(?, pid), "
                "pid_create_time=COALESCE(?, pid_create_time), "
                "process_group_id=COALESCE(?, process_group_id), "
                "server_instance_id=COALESCE(?, server_instance_id), "
                "backend_session_id=COALESCE(?, backend_session_id), "
                "backend_message_id=COALESCE(?, backend_message_id), "
                "returncode=COALESCE(?, returncode), "
                "timeout_reason=COALESCE(?, timeout_reason), "
                "peak_rss_bytes=COALESCE(?, peak_rss_bytes) WHERE id=?",
                (
                    state,
                    completed_at,
                    pid,
                    pid_create_time,
                    process_group_id,
                    server_instance_id,
                    backend_session_id,
                    backend_message_id,
                    returncode,
                    timeout_reason,
                    peak_rss_bytes,
                    attempt_id,
                ),
            )
            row = conn.execute(
                "SELECT * FROM execution_attempts WHERE id=?", (attempt_id,)
            ).fetchone()
        if row is None:
            raise KeyError(attempt_id)
        return self._attempt_from_row(row)

    def list_attempts(self, operation_id: str) -> list[ExecutionAttempt]:
        """Return execution attempts for an operation in attempt order."""
        self.initialize()
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM execution_attempts WHERE operation_id=? ORDER BY attempt_number ASC",
                (operation_id,),
            ).fetchall()
        return [self._attempt_from_row(row) for row in rows]

    def list_expired_attempts(
        self,
        *,
        now: float | None = None,
    ) -> list[tuple[Operation, ExecutionAttempt]]:
        """Return current attempts whose operation lease has expired."""
        self.initialize()
        current_time = time.time() if now is None else now
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT o.id AS operation_id, o.current_attempt_id AS attempt_id "
                "FROM operations o WHERE o.current_attempt_id IS NOT NULL "
                "AND o.lease_expires_at IS NOT NULL AND o.lease_expires_at<=? "
                "AND o.state IN (?, ?, ?, ?, ?)",
                (
                    current_time,
                    OperationState.STARTING.value,
                    OperationState.RUNNING.value,
                    OperationState.WAITING_CHILDREN.value,
                    OperationState.WAITING_INPUT.value,
                    OperationState.CANCEL_REQUESTED.value,
                ),
            ).fetchall()
            result: list[tuple[Operation, ExecutionAttempt]] = []
            for row in rows:
                operation_row = conn.execute(
                    "SELECT * FROM operations WHERE id=?", (row["operation_id"],)
                ).fetchone()
                attempt_row = conn.execute(
                    "SELECT * FROM execution_attempts WHERE id=?", (row["attempt_id"],)
                ).fetchone()
                if operation_row is not None and attempt_row is not None:
                    result.append(
                        (
                            self._operation_from_row(operation_row),
                            self._attempt_from_row(attempt_row),
                        )
                    )
        return result

    def renew_lease(
        self,
        operation_id: str,
        worker_id: str,
        *,
        lease_seconds: float,
        expected_attempt_id: str | None = None,
    ) -> bool:
        """Renew a lease held by one worker."""
        self.initialize()
        now = time.time()
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE operations SET lease_expires_at=?, updated_at=? "
                "WHERE id=? AND lease_owner=? "
                "AND (? IS NULL OR current_attempt_id=?) "
                "AND state NOT IN (?, ?, ?, ?, ?)",
                (
                    now + lease_seconds,
                    now,
                    operation_id,
                    worker_id,
                    expected_attempt_id,
                    expected_attempt_id,
                    OperationState.SUCCEEDED.value,
                    OperationState.FAILED.value,
                    OperationState.TIMED_OUT.value,
                    OperationState.CANCELLED.value,
                    OperationState.INTERRUPTED.value,
                ),
            )
            return cursor.rowcount == 1

    def request_cancel(self, operation_id: str) -> Operation:
        """Persist a cancellation request without assuming execution stopped."""
        self.initialize()
        now = time.time()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM operations WHERE id=?", (operation_id,)).fetchone()
            if row is None:
                raise KeyError(operation_id)
            state = OperationState(row["state"])
            if state.terminal:
                return self._operation_from_row(row)
            next_state = (
                OperationState.CANCELLED
                if state is OperationState.QUEUED
                else OperationState.CANCEL_REQUESTED
            )
            completed_at = now if next_state.terminal else None
            conn.execute(
                "UPDATE operations SET state=?, cancel_requested=1, updated_at=?, "
                "last_activity_at=?, completed_at=?, "
                "lease_owner=CASE WHEN ? THEN NULL ELSE lease_owner END, "
                "lease_expires_at=CASE WHEN ? THEN NULL ELSE lease_expires_at END WHERE id=?",
                (
                    next_state.value,
                    now,
                    now,
                    completed_at,
                    int(next_state.terminal),
                    int(next_state.terminal),
                    operation_id,
                ),
            )
            updated = conn.execute(
                "SELECT * FROM operations WHERE id=?", (operation_id,)
            ).fetchone()
            conn.execute(
                "UPDATE operations SET state=?, cancel_requested=1, updated_at=?, "
                "last_activity_at=? WHERE parent_id=? AND execution_mode='inline' "
                "AND state IN (?, ?, ?, ?)",
                (
                    OperationState.CANCEL_REQUESTED.value,
                    now,
                    now,
                    operation_id,
                    OperationState.STARTING.value,
                    OperationState.RUNNING.value,
                    OperationState.WAITING_CHILDREN.value,
                    OperationState.WAITING_INPUT.value,
                ),
            )
        if updated is None:
            raise RuntimeError(f"Operation {operation_id} disappeared after cancellation")
        return self._operation_from_row(updated)

    def append_event(
        self,
        operation_id: str,
        event_type: str,
        *,
        public_message: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> OperationEvent:
        """Append one ordered event and update operation activity."""
        self.initialize()
        now = time.time()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT COALESCE(MAX(sequence), 0) + 1 AS sequence "
                "FROM operation_events WHERE operation_id=?",
                (operation_id,),
            ).fetchone()
            sequence = int(row["sequence"])
            conn.execute(
                "INSERT INTO operation_events"
                "(operation_id, sequence, event_type, created_at, public_message, data_json) "
                "VALUES(?, ?, ?, ?, ?, ?)",
                (operation_id, sequence, event_type, now, public_message, _json(data or {})),
            )
            conn.execute(
                "UPDATE operations SET updated_at=?, last_activity_at=? WHERE id=?",
                (now, now, operation_id),
            )
        return OperationEvent(
            operation_id=operation_id,
            sequence=sequence,
            event_type=event_type,
            created_at=now,
            public_message=public_message,
            data=data or {},
        )

    def list_events(self, operation_id: str, *, after_sequence: int = 0) -> list[OperationEvent]:
        self.initialize()
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM operation_events WHERE operation_id=? AND sequence>? "
                "ORDER BY sequence ASC",
                (operation_id, after_sequence),
            ).fetchall()
        return [
            OperationEvent(
                operation_id=str(row["operation_id"]),
                sequence=int(row["sequence"]),
                event_type=str(row["event_type"]),
                created_at=float(row["created_at"]),
                public_message=row["public_message"],
                data=json.loads(row["data_json"]),
            )
            for row in rows
        ]

    def enqueue_delivery(
        self,
        operation_id: str,
        *,
        destination: str,
        payload: dict[str, Any],
        chunk_number: int = 0,
    ) -> Delivery:
        """Create a pending outbound delivery."""
        self.initialize()
        delivery_id = _new_id("delivery")
        now = time.time()
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO deliveries"
                "(id, operation_id, destination, payload_json, state, chunk_number, "
                "created_at, updated_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    delivery_id,
                    operation_id,
                    destination,
                    _json(payload),
                    DeliveryState.PENDING.value,
                    chunk_number,
                    now,
                    now,
                ),
            )
            row = conn.execute("SELECT * FROM deliveries WHERE id=?", (delivery_id,)).fetchone()
        if row is None:
            raise RuntimeError(f"Delivery {delivery_id} disappeared after insertion")
        return self._delivery_from_row(row)

    def claim_delivery(
        self,
        worker_id: str,
        *,
        lease_seconds: float = 60.0,
    ) -> Delivery | None:
        """Claim the next pending or retryable delivery."""
        self.initialize()
        now = time.time()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM deliveries WHERE "
                "(state=? OR (state=? AND COALESCE(next_attempt_at, 0)<=?)) "
                "ORDER BY created_at ASC LIMIT 1",
                (DeliveryState.PENDING.value, DeliveryState.RETRY_WAIT.value, now),
            ).fetchone()
            if row is None:
                return None
            delivery_id = str(row["id"])
            conn.execute(
                "UPDATE deliveries SET state=?, lease_owner=?, lease_expires_at=?, "
                "attempt_count=attempt_count+1, updated_at=? WHERE id=?",
                (
                    DeliveryState.SENDING.value,
                    worker_id,
                    now + lease_seconds,
                    now,
                    delivery_id,
                ),
            )
            updated = conn.execute("SELECT * FROM deliveries WHERE id=?", (delivery_id,)).fetchone()
        return self._delivery_from_row(updated) if updated is not None else None

    def finish_delivery(
        self,
        delivery_id: str,
        *,
        delivered: bool,
        telegram_message_id: int | None = None,
        uncertain: bool = False,
        error: str | None = None,
        retry_after_seconds: float | None = None,
    ) -> Delivery:
        """Record a delivery result and optional retry."""
        self.initialize()
        now = time.time()
        if delivered:
            state = DeliveryState.DELIVERED
            next_attempt_at = None
        elif retry_after_seconds is not None:
            state = DeliveryState.RETRY_WAIT
            next_attempt_at = now + retry_after_seconds
        else:
            state = DeliveryState.BLOCKED
            next_attempt_at = None
        with self._connect() as conn:
            conn.execute(
                "UPDATE deliveries SET state=?, "
                "telegram_message_id=COALESCE(?, telegram_message_id), "
                "uncertain=?, last_error=?, next_attempt_at=?, lease_owner=NULL, "
                "lease_expires_at=NULL, updated_at=? WHERE id=?",
                (
                    state.value,
                    telegram_message_id,
                    int(uncertain),
                    error,
                    next_attempt_at,
                    now,
                    delivery_id,
                ),
            )
            row = conn.execute("SELECT * FROM deliveries WHERE id=?", (delivery_id,)).fetchone()
        if row is None:
            raise KeyError(delivery_id)
        return self._delivery_from_row(row)

    def list_deliveries(
        self,
        operation_id: str | None = None,
        *,
        states: tuple[DeliveryState, ...] | None = None,
        limit: int = 100,
    ) -> list[Delivery]:
        """List deliveries in creation order for recovery and inspection."""
        self.initialize()
        clauses: list[str] = []
        params: list[Any] = []
        if operation_id is not None:
            clauses.append("operation_id=?")
            params.append(operation_id)
        if states:
            placeholders = ",".join("?" for _ in states)
            clauses.append(f"state IN ({placeholders})")
            params.extend(state.value for state in states)
        query = "SELECT * FROM deliveries"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY created_at ASC, chunk_number ASC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._delivery_from_row(row) for row in rows]

    def recover_expired_leases(self, *, now: float | None = None) -> tuple[int, int]:
        """Recover operation and delivery leases left by dead workers.

        Read-only and idempotent operations can be queued again. Operations
        with uncertain external effects enter reconciliation and are not replayed.
        Sending deliveries return to retry wait because their Telegram outcome
        can be ambiguous.
        """
        self.initialize()
        current_time = time.time() if now is None else now
        operation_count = 0
        delivery_count = 0
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute(
                "SELECT * FROM operations WHERE lease_expires_at IS NOT NULL "
                "AND lease_expires_at<=? AND state IN (?, ?, ?, ?, ?)",
                (
                    current_time,
                    OperationState.STARTING.value,
                    OperationState.RUNNING.value,
                    OperationState.WAITING_CHILDREN.value,
                    OperationState.WAITING_INPUT.value,
                    OperationState.CANCEL_REQUESTED.value,
                ),
            ).fetchall()
            for row in rows:
                state = OperationState(row["state"])
                side_effect = SideEffectClass(row["side_effect_class"])
                if state is OperationState.CANCEL_REQUESTED:
                    next_state = OperationState.CANCELLED
                    recovery_status = "cancelled_after_expired_lease"
                elif side_effect in {SideEffectClass.MUTATING, SideEffectClass.UNKNOWN}:
                    next_state = OperationState.RECONCILING
                    recovery_status = "manual_reconciliation_required"
                elif row["execution_mode"] == "inline":
                    next_state = OperationState.INTERRUPTED
                    recovery_status = "inline_caller_lost"
                elif row["deadline_at"] is not None and row["deadline_at"] <= current_time:
                    next_state = OperationState.TIMED_OUT
                    recovery_status = "deadline_expired_during_recovery"
                elif side_effect in {SideEffectClass.READ_ONLY, SideEffectClass.IDEMPOTENT}:
                    next_state = OperationState.QUEUED
                    recovery_status = "requeued_after_expired_lease"
                else:
                    next_state = OperationState.RECONCILING
                    recovery_status = "manual_reconciliation_required"
                completed_at = current_time if next_state.terminal else None
                current_attempt_id = row["current_attempt_id"]
                if current_attempt_id:
                    conn.execute(
                        "UPDATE execution_attempts SET state=?, completed_at=?, "
                        "timeout_reason=COALESCE(timeout_reason, ?) "
                        "WHERE id=? AND completed_at IS NULL",
                        (
                            OperationState.INTERRUPTED.value,
                            current_time,
                            "lease expired; execution ownership revoked",
                            current_attempt_id,
                        ),
                    )
                conn.execute(
                    "UPDATE operations SET state=?, updated_at=?, lease_owner=NULL, "
                    "lease_expires_at=NULL, current_attempt_id=NULL, "
                    "completed_at=COALESCE(?, completed_at), "
                    "recovery_status=? WHERE id=?",
                    (
                        next_state.value,
                        current_time,
                        completed_at,
                        recovery_status,
                        row["id"],
                    ),
                )
                operation_count += 1

            cursor = conn.execute(
                "UPDATE deliveries SET state=?, next_attempt_at=?, lease_owner=NULL, "
                "lease_expires_at=NULL, uncertain=1, "
                "last_error=COALESCE(last_error, 'delivery lease expired'), updated_at=? "
                "WHERE state=? AND lease_expires_at IS NOT NULL AND lease_expires_at<=?",
                (
                    DeliveryState.RETRY_WAIT.value,
                    current_time,
                    current_time,
                    DeliveryState.SENDING.value,
                    current_time,
                ),
            )
            delivery_count = cursor.rowcount
        return operation_count, delivery_count

    def _insert_operation(
        self,
        conn: sqlite3.Connection,
        *,
        operation_id: str,
        kind: str,
        source: str,
        payload: dict[str, Any],
        now: float,
        parent_id: str | None = None,
        dependency_ids: tuple[str, ...] = (),
        telegram_bot_id: str | None = None,
        telegram_update_id: int | None = None,
        telegram_chat_id: str | None = None,
        telegram_message_id: int | None = None,
        telegram_thread_id: int | None = None,
        backend: str | None = None,
        model: str | None = None,
        variant: str | None = None,
        agent: str | None = None,
        workdir: str | None = None,
        permission_fingerprint: str | None = None,
        side_effect_class: SideEffectClass = SideEffectClass.UNKNOWN,
        execution_mode: str = "daemon",
        deadline_at: float | None = None,
        parent_attempt_id: str | None = None,
        origin_session_id: str | None = None,
        origin_tool_call_id: str | None = None,
    ) -> None:
        conn.execute(
            "INSERT INTO operations"
            "(id, kind, source, state, payload_json, created_at, updated_at, "
            "telegram_bot_id, telegram_update_id, telegram_chat_id, telegram_message_id, "
            "telegram_thread_id, parent_id, dependency_ids_json, backend, model, variant, "
            "agent, workdir, permission_fingerprint, side_effect_class, correlation_id, "
            "execution_mode, deadline_at, parent_attempt_id, origin_session_id, "
            "origin_tool_call_id) "
            "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
            "?, ?, ?, ?, ?, ?, ?)",
            (
                operation_id,
                kind,
                source,
                OperationState.QUEUED.value,
                _json(payload),
                now,
                now,
                telegram_bot_id,
                telegram_update_id,
                telegram_chat_id,
                telegram_message_id,
                telegram_thread_id,
                parent_id,
                _json(dependency_ids),
                backend,
                model,
                variant,
                agent,
                workdir,
                permission_fingerprint,
                side_effect_class.value,
                operation_id,
                execution_mode,
                deadline_at,
                parent_attempt_id,
                origin_session_id,
                origin_tool_call_id,
            ),
        )

    @staticmethod
    def _advance_offset(
        conn: sqlite3.Connection,
        bot_id: str,
        next_offset: int,
        now: float,
    ) -> None:
        conn.execute(
            "INSERT INTO telegram_offsets(bot_id, next_offset, updated_at) VALUES(?, ?, ?) "
            "ON CONFLICT(bot_id) DO UPDATE SET "
            "next_offset=MAX(telegram_offsets.next_offset, excluded.next_offset), "
            "updated_at=excluded.updated_at",
            (bot_id, next_offset, now),
        )

    @staticmethod
    def _dependencies_succeeded(conn: sqlite3.Connection, dependency_ids: tuple[str, ...]) -> bool:
        if not dependency_ids:
            return True
        placeholders = ",".join("?" for _ in dependency_ids)
        rows = conn.execute(
            f"SELECT id, state FROM operations WHERE id IN ({placeholders})",
            dependency_ids,
        ).fetchall()
        if len(rows) != len(dependency_ids):
            return False
        return all(row["state"] == OperationState.SUCCEEDED.value for row in rows)

    @staticmethod
    def _assert_ownership(
        row: sqlite3.Row,
        worker_id: str | None,
        expected_attempt_id: str | None,
    ) -> None:
        if worker_id is not None and row["lease_owner"] != worker_id:
            raise LostOperationOwnershipError(
                f"Operation {row['id']} is no longer leased to {worker_id}"
            )
        if expected_attempt_id is not None and row["current_attempt_id"] != expected_attempt_id:
            raise LostOperationOwnershipError(
                f"Attempt {expected_attempt_id} no longer owns operation {row['id']}"
            )

    @staticmethod
    def _operation_from_row(row: sqlite3.Row) -> Operation:
        return Operation(
            id=str(row["id"]),
            kind=str(row["kind"]),
            source=str(row["source"]),
            state=OperationState(row["state"]),
            payload=json.loads(row["payload_json"]),
            created_at=float(row["created_at"]),
            updated_at=float(row["updated_at"]),
            telegram_bot_id=row["telegram_bot_id"],
            telegram_update_id=row["telegram_update_id"],
            telegram_chat_id=row["telegram_chat_id"],
            telegram_message_id=row["telegram_message_id"],
            telegram_thread_id=row["telegram_thread_id"],
            status_message_id=row["status_message_id"],
            parent_id=row["parent_id"],
            dependency_ids=tuple(json.loads(row["dependency_ids_json"])),
            backend=row["backend"],
            model=row["model"],
            variant=row["variant"],
            agent=row["agent"],
            workdir=row["workdir"],
            permission_fingerprint=row["permission_fingerprint"],
            side_effect_class=SideEffectClass(row["side_effect_class"]),
            attempt_count=int(row["attempt_count"]),
            lease_owner=row["lease_owner"],
            lease_expires_at=row["lease_expires_at"],
            cancel_requested=bool(row["cancel_requested"]),
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            last_activity_at=row["last_activity_at"],
            result_text=row["result_text"],
            error_type=row["error_type"],
            error_message=row["error_message"],
            recovery_status=row["recovery_status"],
            correlation_id=row["correlation_id"],
            execution_mode=row["execution_mode"],
            deadline_at=row["deadline_at"],
            parent_attempt_id=row["parent_attempt_id"],
            current_attempt_id=row["current_attempt_id"],
            origin_session_id=row["origin_session_id"],
            origin_tool_call_id=row["origin_tool_call_id"],
        )

    @staticmethod
    def _delivery_from_row(row: sqlite3.Row) -> Delivery:
        return Delivery(
            id=str(row["id"]),
            operation_id=str(row["operation_id"]),
            destination=str(row["destination"]),
            payload=json.loads(row["payload_json"]),
            state=DeliveryState(row["state"]),
            created_at=float(row["created_at"]),
            updated_at=float(row["updated_at"]),
            chunk_number=int(row["chunk_number"]),
            telegram_message_id=row["telegram_message_id"],
            attempt_count=int(row["attempt_count"]),
            next_attempt_at=row["next_attempt_at"],
            lease_owner=row["lease_owner"],
            lease_expires_at=row["lease_expires_at"],
            uncertain=bool(row["uncertain"]),
            last_error=row["last_error"],
        )

    @staticmethod
    def _attempt_from_row(row: sqlite3.Row) -> ExecutionAttempt:
        return ExecutionAttempt(
            id=str(row["id"]),
            operation_id=str(row["operation_id"]),
            attempt_number=int(row["attempt_number"]),
            worker_id=str(row["worker_id"]),
            state=str(row["state"]),
            started_at=float(row["started_at"]),
            completed_at=row["completed_at"],
            pid=row["pid"],
            pid_create_time=row["pid_create_time"],
            process_group_id=row["process_group_id"],
            owner_pid=row["owner_pid"],
            owner_pid_create_time=row["owner_pid_create_time"],
            server_instance_id=row["server_instance_id"],
            backend_session_id=row["backend_session_id"],
            backend_message_id=row["backend_message_id"],
            returncode=row["returncode"],
            timeout_reason=row["timeout_reason"],
            peak_rss_bytes=row["peak_rss_bytes"],
        )


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex}"


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _process_birth_time(pid: int) -> float | None:
    try:
        import psutil

        return float(psutil.Process(pid).create_time())
    except Exception:  # noqa: BLE001 - optional process evidence must not block acceptance
        return None
