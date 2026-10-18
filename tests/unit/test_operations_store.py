"""Tests for the durable operation store."""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING

import pytest

from adjutant.operations.models import DeliveryState, OperationState, SideEffectClass
from adjutant.operations.store import (
    InvalidOperationTransitionError,
    LostOperationOwnershipError,
    OperationStore,
)

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def store(tmp_path: Path) -> OperationStore:
    result = OperationStore(tmp_path)
    result.initialize()
    return result


class TestSchema:
    def test_initialize_is_idempotent(self, store: OperationStore) -> None:
        store.initialize()
        store.initialize()
        assert store.database_path.is_file()


class TestOperations:
    def test_create_and_read(self, store: OperationStore) -> None:
        operation = store.create_operation(
            kind="telegram_text",
            source="telegram",
            payload={"text": "hello"},
            side_effect_class=SideEffectClass.READ_ONLY,
        )

        loaded = store.get_operation(operation.id)
        assert loaded is not None
        assert loaded.state is OperationState.QUEUED
        assert loaded.payload == {"text": "hello"}
        assert loaded.correlation_id == loaded.id
        assert loaded.side_effect_class is SideEffectClass.READ_ONLY

        updated = store.set_status_message_id(operation.id, 99)
        assert updated.status_message_id == 99

    def test_update_operation_payload_merges_framework_metadata(
        self,
        store: OperationStore,
    ) -> None:
        operation = store.create_operation(
            kind="telegram_photo",
            source="telegram",
            payload={"caption": "Create an issue"},
        )

        updated = store.update_operation_payload(
            operation.id,
            {"local_attachment_path": "/tmp/photo.jpg"},
        )

        assert updated.payload == {
            "caption": "Create an issue",
            "local_attachment_path": "/tmp/photo.jpg",
        }
        assert store.get_operation(operation.id).payload == updated.payload  # type: ignore[union-attr]

    def test_claim_and_complete(self, store: OperationStore) -> None:
        operation = store.create_operation(kind="chat", source="test", payload={})

        claimed = store.claim_next("worker-1", lease_seconds=30)
        assert claimed is not None
        assert claimed.id == operation.id
        assert claimed.state is OperationState.STARTING
        assert claimed.lease_owner == "worker-1"
        assert claimed.attempt_count == 1

        running = store.transition(
            operation.id,
            OperationState.RUNNING,
            worker_id="worker-1",
            lease_seconds=30,
        )
        assert running.state is OperationState.RUNNING

        completed = store.transition(
            operation.id,
            OperationState.SUCCEEDED,
            result_text="done",
        )
        assert completed.state is OperationState.SUCCEEDED
        assert completed.result_text == "done"
        assert completed.completed_at is not None
        assert completed.lease_owner is None

    def test_rejects_invalid_transition(self, store: OperationStore) -> None:
        operation = store.create_operation(kind="chat", source="test", payload={})
        with pytest.raises(InvalidOperationTransitionError, match="queued -> succeeded"):
            store.transition(operation.id, OperationState.SUCCEEDED)

    def test_dependencies_block_claim_until_success(self, store: OperationStore) -> None:
        parent = store.create_operation(kind="parent", source="test", payload={})
        child = store.create_operation(
            kind="child",
            source="test",
            payload={},
            dependency_ids=(parent.id,),
        )

        claimed_parent = store.claim_next("worker")
        assert claimed_parent is not None
        assert claimed_parent.id == parent.id
        assert store.claim_next("other-worker") is None

        store.transition(parent.id, OperationState.RUNNING, worker_id="worker")
        store.transition(parent.id, OperationState.SUCCEEDED)

        claimed_child = store.claim_next("other-worker")
        assert claimed_child is not None
        assert claimed_child.id == child.id

    def test_concurrent_claims_return_operation_once(self, store: OperationStore) -> None:
        operation = store.create_operation(kind="chat", source="test", payload={})

        with ThreadPoolExecutor(max_workers=2) as executor:
            claims = list(
                executor.map(
                    lambda worker: store.claim_next(worker),
                    ("worker-1", "worker-2"),
                )
            )

        claimed = [item for item in claims if item is not None]
        assert len(claimed) == 1
        assert claimed[0].id == operation.id

    def test_concurrent_active_snapshots_remain_atomic(self, store: OperationStore) -> None:
        operation = store.create_operation(kind="pulse", source="test", payload={})

        with ThreadPoolExecutor(max_workers=8) as executor:
            snapshots = list(executor.map(lambda _index: store.sync_active_snapshot(), range(24)))

        assert all(snapshot[0]["id"] == operation.id for snapshot in snapshots)
        persisted = json.loads(
            (store.adj_dir / "state" / "active_operations.json").read_text()
        )
        assert persisted[0]["id"] == operation.id

    def test_claims_specific_child_without_consuming_parent_queue(
        self, store: OperationStore
    ) -> None:
        first = store.create_operation(kind="first", source="test", payload={})
        child = store.create_operation(
            kind="child",
            source="test",
            payload={},
            parent_id=first.id,
        )

        claimed = store.claim_operation(child.id, "inline-worker")

        assert claimed is not None
        assert claimed.id == child.id
        assert store.get_operation(first.id).state is OperationState.QUEUED  # type: ignore[union-attr]

    def test_cancel_queued_operation_is_terminal(self, store: OperationStore) -> None:
        operation = store.create_operation(kind="chat", source="test", payload={})
        cancelled = store.request_cancel(operation.id)
        assert cancelled.state is OperationState.CANCELLED
        assert cancelled.cancel_requested is True
        assert cancelled.completed_at is not None

    def test_cancel_running_operation_requests_worker_stop(self, store: OperationStore) -> None:
        operation = store.create_operation(kind="chat", source="test", payload={})
        store.claim_next("worker")
        store.transition(operation.id, OperationState.RUNNING, worker_id="worker")

        requested = store.request_cancel(operation.id)
        assert requested.state is OperationState.CANCEL_REQUESTED
        assert requested.cancel_requested is True

    def test_completion_and_deliveries_commit_together(self, store: OperationStore) -> None:
        operation = store.create_operation(kind="chat", source="test", payload={})
        store.claim_next("worker")
        store.transition(operation.id, OperationState.RUNNING, worker_id="worker")

        completed = store.complete_with_deliveries(
            operation.id,
            OperationState.SUCCEEDED,
            result_text="done",
            deliveries=(("telegram", {"text": "done"}, 0),),
        )

        assert completed.state is OperationState.SUCCEEDED
        deliveries = store.list_deliveries(operation.id)
        assert len(deliveries) == 1
        assert deliveries[0].payload == {"text": "done"}

    def test_records_execution_attempt(self, store: OperationStore) -> None:
        operation = store.create_operation(kind="chat", source="test", payload={})
        claimed = store.claim_next("worker")
        assert claimed is not None
        attempt = store.start_attempt(claimed, "worker")
        finished = store.update_attempt(
            attempt.id,
            state=OperationState.SUCCEEDED.value,
            completed=True,
            backend_session_id="session-1",
            returncode=0,
        )

        assert finished.completed_at is not None
        assert finished.backend_session_id == "session-1"
        assert store.list_attempts(operation.id) == [finished]

    def test_recovers_expired_leases_by_side_effect_class(self, store: OperationStore) -> None:
        read = store.create_operation(
            kind="query",
            source="test",
            payload={},
            side_effect_class=SideEffectClass.READ_ONLY,
        )
        store.claim_next("worker", lease_seconds=0)
        store.transition(read.id, OperationState.RUNNING, worker_id="worker", lease_seconds=0)

        mutation = store.create_operation(
            kind="write",
            source="test",
            payload={},
            side_effect_class=SideEffectClass.MUTATING,
        )
        store.claim_next("worker", lease_seconds=0)
        store.transition(
            mutation.id,
            OperationState.RUNNING,
            worker_id="worker",
            lease_seconds=0,
        )

        recovered, _ = store.recover_expired_leases(now=10**12)

        assert recovered == 2
        assert store.get_operation(read.id).state is OperationState.QUEUED  # type: ignore[union-attr]
        assert store.get_operation(mutation.id).state is OperationState.RECONCILING  # type: ignore[union-attr]

    def test_inline_acceptance_is_atomic_and_not_daemon_claimable(
        self, store: OperationStore
    ) -> None:
        parent = store.create_operation(kind="prompt", source="test", payload={})
        claimed_parent = store.claim_next("parent", lease_seconds=60)
        assert claimed_parent is not None
        parent_attempt = store.start_attempt(
            claimed_parent, "parent", runtime_seconds=1800
        )
        parent = store.transition(
            parent.id,
            OperationState.RUNNING,
            worker_id="parent",
            lease_seconds=60,
            expected_attempt_id=parent_attempt.id,
        )
        assert parent.deadline_at is not None

        child, attempt = store.create_inline_operation(
            kind="kb_write",
            source="kb",
            payload={"prompt": "write once"},
            worker_id="inline",
            lease_seconds=60,
            parent_id=parent.id,
            parent_attempt_id=parent_attempt.id,
            deadline_at=parent.deadline_at - 15,
            side_effect_class=SideEffectClass.MUTATING,
        )

        assert child.state is OperationState.STARTING
        assert child.current_attempt_id == attempt.id
        assert child.attempt_count == 1
        assert attempt.owner_pid is not None
        assert attempt.owner_pid_create_time is not None
        assert store.list_attempts(child.id) == [attempt]
        assert store.claim_next("daemon") is None

    def test_inline_read_is_interrupted_instead_of_stranded_or_daemon_replayed(
        self, store: OperationStore
    ) -> None:
        parent = store.create_operation(kind="prompt", source="test", payload={})
        parent_claim = store.claim_next("parent", lease_seconds=60)
        assert parent_claim is not None
        parent_attempt = store.start_attempt(parent_claim, "parent", runtime_seconds=1800)
        parent = store.transition(
            parent.id,
            OperationState.RUNNING,
            worker_id="parent",
            lease_seconds=60,
            expected_attempt_id=parent_attempt.id,
        )
        assert parent.deadline_at is not None
        child, attempt = store.create_inline_operation(
            kind="kb_query",
            source="kb",
            payload={},
            worker_id="inline",
            lease_seconds=0,
            parent_id=parent.id,
            parent_attempt_id=parent_attempt.id,
            deadline_at=parent.deadline_at - 15,
            side_effect_class=SideEffectClass.READ_ONLY,
        )

        recovered, _ = store.recover_expired_leases(now=child.created_at + 1)

        assert recovered == 1
        current = store.get_operation(child.id)
        assert current is not None
        assert current.state is OperationState.INTERRUPTED
        assert current.recovery_status == "inline_caller_lost"
        assert store.claim_next("daemon") is None
        closed = store.get_attempt(attempt.id)
        assert closed is not None and closed.completed_at is not None

    def test_terminal_result_closes_attempt_in_same_transaction(
        self, store: OperationStore
    ) -> None:
        operation = store.create_operation(kind="prompt", source="test", payload={})
        claimed = store.claim_next("worker", lease_seconds=60)
        assert claimed is not None
        attempt = store.start_attempt(claimed, "worker", runtime_seconds=60)
        running = store.transition(
            operation.id,
            OperationState.RUNNING,
            worker_id="worker",
            lease_seconds=60,
            expected_attempt_id=attempt.id,
        )

        store.complete_with_deliveries(
            running.id,
            OperationState.SUCCEEDED,
            result_text="done",
            worker_id="worker",
            expected_attempt_id=attempt.id,
        )

        closed = store.get_attempt(attempt.id)
        assert closed is not None
        assert closed.state == OperationState.SUCCEEDED.value
        assert closed.completed_at is not None

    def test_recovery_closes_attempt_and_fences_stale_completion(
        self, store: OperationStore
    ) -> None:
        operation = store.create_operation(
            kind="write",
            source="test",
            payload={},
            side_effect_class=SideEffectClass.MUTATING,
        )
        claimed = store.claim_next("worker", lease_seconds=0)
        assert claimed is not None
        attempt = store.start_attempt(claimed, "worker", runtime_seconds=60)
        store.transition(
            operation.id,
            OperationState.RUNNING,
            worker_id="worker",
            lease_seconds=0,
            expected_attempt_id=attempt.id,
        )

        recovered, _ = store.recover_expired_leases(now=10**12)

        assert recovered == 1
        current = store.get_operation(operation.id)
        assert current is not None
        assert current.state is OperationState.RECONCILING
        assert current.current_attempt_id is None
        closed = store.get_attempt(attempt.id)
        assert closed is not None
        assert closed.state == OperationState.INTERRUPTED.value
        assert closed.completed_at is not None
        with pytest.raises(LostOperationOwnershipError):
            store.complete_with_deliveries(
                operation.id,
                OperationState.SUCCEEDED,
                worker_id="worker",
                expected_attempt_id=attempt.id,
            )

    def test_heartbeat_and_recovery_have_one_ownership_winner(
        self, store: OperationStore
    ) -> None:
        operation = store.create_operation(
            kind="query",
            source="test",
            payload={},
            side_effect_class=SideEffectClass.READ_ONLY,
        )
        claimed = store.claim_next("worker", lease_seconds=0)
        assert claimed is not None
        attempt = store.start_attempt(claimed, "worker", runtime_seconds=60)
        store.transition(
            operation.id,
            OperationState.RUNNING,
            worker_id="worker",
            lease_seconds=0,
            expected_attempt_id=attempt.id,
        )
        recovery_time = time.time()

        with ThreadPoolExecutor(max_workers=2) as executor:
            renewal_future = executor.submit(
                store.renew_lease,
                operation.id,
                "worker",
                lease_seconds=60,
                expected_attempt_id=attempt.id,
            )
            recovery_future = executor.submit(
                store.recover_expired_leases,
                now=recovery_time,
            )
            renewed = renewal_future.result()
            recovered, _ = recovery_future.result()

        assert (renewed, recovered) in {(True, 0), (False, 1)}
        current = store.get_operation(operation.id)
        assert current is not None
        if renewed:
            assert current.current_attempt_id == attempt.id
            assert current.state is OperationState.RUNNING
        else:
            assert current.current_attempt_id is None
            assert current.state is OperationState.QUEUED

    def test_deadline_is_not_extended_after_read_only_recovery(
        self, store: OperationStore
    ) -> None:
        operation = store.create_operation(
            kind="query",
            source="test",
            payload={},
            side_effect_class=SideEffectClass.READ_ONLY,
        )
        first_claim = store.claim_next("worker-1", lease_seconds=0)
        assert first_claim is not None
        first_attempt = store.start_attempt(
            first_claim, "worker-1", runtime_seconds=120
        )
        first = store.get_operation(operation.id)
        assert first is not None and first.deadline_at is not None
        store.transition(
            operation.id,
            OperationState.RUNNING,
            worker_id="worker-1",
            lease_seconds=0,
            expected_attempt_id=first_attempt.id,
        )
        store.recover_expired_leases(now=first.created_at + 1)

        second_claim = store.claim_next("worker-2", lease_seconds=60)
        assert second_claim is not None
        store.start_attempt(second_claim, "worker-2", runtime_seconds=600)
        second = store.get_operation(operation.id)
        assert second is not None
        assert second.deadline_at == first.deadline_at

    def test_parent_cancel_only_propagates_to_execution_children(
        self, store: OperationStore
    ) -> None:
        parent = store.create_operation(kind="prompt", source="test", payload={})
        claimed = store.claim_next("parent", lease_seconds=60)
        assert claimed is not None
        parent_attempt = store.start_attempt(claimed, "parent", runtime_seconds=1800)
        parent = store.transition(
            parent.id,
            OperationState.RUNNING,
            worker_id="parent",
            lease_seconds=60,
            expected_attempt_id=parent_attempt.id,
        )
        assert parent.deadline_at is not None
        inline, _ = store.create_inline_operation(
            kind="kb_query",
            source="kb",
            payload={},
            worker_id="inline",
            lease_seconds=60,
            parent_id=parent.id,
            parent_attempt_id=parent_attempt.id,
            deadline_at=parent.deadline_at - 15,
            side_effect_class=SideEffectClass.READ_ONLY,
        )
        followup = store.create_operation(
            kind="telegram_chat",
            source="telegram",
            payload={},
            parent_id=parent.id,
        )

        store.request_cancel(parent.id)

        assert store.get_operation(inline.id).state is OperationState.CANCEL_REQUESTED  # type: ignore[union-attr]
        assert store.get_operation(followup.id).state is OperationState.QUEUED  # type: ignore[union-attr]

    def test_retention_preserves_terminal_dependency_of_active_work(
        self, store: OperationStore
    ) -> None:
        parent = store.create_operation(kind="prompt", source="test", payload={})
        store.claim_next("worker")
        store.transition(parent.id, OperationState.RUNNING, worker_id="worker")
        store.transition(parent.id, OperationState.SUCCEEDED)
        child = store.create_operation(
            kind="prompt",
            source="test",
            payload={},
            dependency_ids=(parent.id,),
        )
        with store._connect() as conn:  # noqa: SLF001 - arrange retention age
            conn.execute("UPDATE operations SET completed_at=1 WHERE id=?", (parent.id,))

        counts = store.prune_retention(
            completed_before=2,
            events_before=0,
            deliveries_before=0,
        )

        assert counts["operations"] == 0
        assert store.get_operation(parent.id) is not None
        assert store.get_operation(child.id) is not None


class TestTelegramInbox:
    def test_accept_and_offset_are_atomic_and_idempotent(self, store: OperationStore) -> None:
        first, inserted = store.accept_telegram_update(
            bot_id="bot-1",
            update_id=100,
            next_offset=101,
            kind="telegram_text",
            payload={"text": "hello"},
            chat_id="42",
            message_id=7,
        )
        duplicate, duplicate_inserted = store.accept_telegram_update(
            bot_id="bot-1",
            update_id=100,
            next_offset=101,
            kind="telegram_text",
            payload={"text": "different retry payload"},
            chat_id="42",
            message_id=7,
        )

        assert inserted is True
        assert duplicate_inserted is False
        assert duplicate.id == first.id
        assert duplicate.payload == {"text": "hello"}
        assert store.get_telegram_offset("bot-1") == 101
        assert len(store.list_operations()) == 1

    def test_offset_never_moves_backwards(self, store: OperationStore) -> None:
        store.advance_telegram_offset("bot-1", 50)
        store.advance_telegram_offset("bot-1", 20)
        assert store.get_telegram_offset("bot-1") == 50


class TestEvents:
    def test_sequences_events_per_operation(self, store: OperationStore) -> None:
        operation = store.create_operation(kind="chat", source="test", payload={})
        first = store.append_event(operation.id, "started", public_message="Started")
        second = store.append_event(operation.id, "progress", data={"step": 2})

        assert first.sequence == 1
        assert second.sequence == 2
        assert store.list_events(operation.id) == [first, second]
        assert store.list_events(operation.id, after_sequence=1) == [second]


class TestDeliveries:
    def test_delivery_success(self, store: OperationStore) -> None:
        operation = store.create_operation(kind="chat", source="test", payload={})
        delivery = store.enqueue_delivery(
            operation.id,
            destination="telegram",
            payload={"chat_id": "42", "text": "done"},
        )

        claimed = store.claim_delivery("delivery-worker")
        assert claimed is not None
        assert claimed.id == delivery.id
        assert claimed.state is DeliveryState.SENDING

        finished = store.finish_delivery(
            delivery.id,
            delivered=True,
            telegram_message_id=88,
        )
        assert finished.state is DeliveryState.DELIVERED
        assert finished.telegram_message_id == 88

    def test_failed_delivery_can_retry(self, store: OperationStore) -> None:
        operation = store.create_operation(kind="chat", source="test", payload={})
        delivery = store.enqueue_delivery(
            operation.id,
            destination="telegram",
            payload={"chat_id": "42", "text": "done"},
        )
        store.claim_delivery("delivery-worker")

        failed = store.finish_delivery(
            delivery.id,
            delivered=False,
            uncertain=True,
            error="network error",
            retry_after_seconds=0,
        )
        assert failed.state is DeliveryState.RETRY_WAIT
        assert failed.uncertain is True

        retry = store.claim_delivery("delivery-worker")
        assert retry is not None
        assert retry.id == delivery.id
        assert retry.attempt_count == 2

    def test_expired_sending_delivery_returns_to_retry(self, store: OperationStore) -> None:
        operation = store.create_operation(kind="chat", source="test", payload={})
        delivery = store.enqueue_delivery(
            operation.id,
            destination="telegram",
            payload={"text": "done"},
        )
        store.claim_delivery("worker", lease_seconds=0)

        _, recovered = store.recover_expired_leases(now=10**12)

        assert recovered == 1
        loaded = store.list_deliveries(operation.id)[0]
        assert loaded.id == delivery.id
        assert loaded.state is DeliveryState.RETRY_WAIT
        assert loaded.uncertain is True
