"""Data contracts for durable operations."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class OperationState(StrEnum):
    """Durable execution state."""

    QUEUED = "queued"
    STARTING = "starting"
    RUNNING = "running"
    WAITING_CHILDREN = "waiting_children"
    WAITING_INPUT = "waiting_input"
    CANCEL_REQUESTED = "cancel_requested"
    RECONCILING = "reconciling"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"

    @property
    def terminal(self) -> bool:
        return self in {
            OperationState.SUCCEEDED,
            OperationState.FAILED,
            OperationState.TIMED_OUT,
            OperationState.CANCELLED,
            OperationState.INTERRUPTED,
        }


class DeliveryState(StrEnum):
    """Outbound delivery state."""

    PENDING = "pending"
    SENDING = "sending"
    RETRY_WAIT = "retry_wait"
    DELIVERED = "delivered"
    BLOCKED = "blocked"


class SideEffectClass(StrEnum):
    """Replay safety classification for an operation."""

    READ_ONLY = "read_only"
    IDEMPOTENT = "idempotent"
    MUTATING = "mutating"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Operation:
    """Persisted operation record."""

    id: str
    kind: str
    source: str
    state: OperationState
    payload: dict[str, Any]
    created_at: float
    updated_at: float
    telegram_bot_id: str | None = None
    telegram_update_id: int | None = None
    telegram_chat_id: str | None = None
    telegram_message_id: int | None = None
    telegram_thread_id: int | None = None
    status_message_id: int | None = None
    parent_id: str | None = None
    dependency_ids: tuple[str, ...] = ()
    backend: str | None = None
    model: str | None = None
    variant: str | None = None
    agent: str | None = None
    workdir: str | None = None
    permission_fingerprint: str | None = None
    side_effect_class: SideEffectClass = SideEffectClass.UNKNOWN
    attempt_count: int = 0
    lease_owner: str | None = None
    lease_expires_at: float | None = None
    cancel_requested: bool = False
    started_at: float | None = None
    completed_at: float | None = None
    last_activity_at: float | None = None
    result_text: str | None = None
    error_type: str | None = None
    error_message: str | None = None
    recovery_status: str | None = None
    correlation_id: str | None = None
    execution_mode: str = "daemon"
    deadline_at: float | None = None
    parent_attempt_id: str | None = None
    current_attempt_id: str | None = None
    origin_session_id: str | None = None
    origin_tool_call_id: str | None = None


@dataclass(frozen=True)
class OperationEvent:
    """One ordered event emitted during an operation."""

    operation_id: str
    sequence: int
    event_type: str
    created_at: float
    public_message: str | None = None
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Delivery:
    """One durable outbound delivery record."""

    id: str
    operation_id: str
    destination: str
    payload: dict[str, Any]
    state: DeliveryState
    created_at: float
    updated_at: float
    chunk_number: int = 0
    telegram_message_id: int | None = None
    attempt_count: int = 0
    next_attempt_at: float | None = None
    lease_owner: str | None = None
    lease_expires_at: float | None = None
    uncertain: bool = False
    last_error: str | None = None


@dataclass(frozen=True)
class ExecutionAttempt:
    """Evidence for one worker attempt."""

    id: str
    operation_id: str
    attempt_number: int
    worker_id: str
    started_at: float
    state: str
    pid: int | None = None
    pid_create_time: float | None = None
    process_group_id: int | None = None
    owner_pid: int | None = None
    owner_pid_create_time: float | None = None
    server_instance_id: str | None = None
    backend_session_id: str | None = None
    backend_message_id: str | None = None
    completed_at: float | None = None
    returncode: int | None = None
    timeout_reason: str | None = None
    peak_rss_bytes: int | None = None
