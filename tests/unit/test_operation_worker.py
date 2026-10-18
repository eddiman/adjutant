"""Tests for bounded durable operation execution."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from adjutant.core.backend import ExecutionEvent, ExecutionEventType, LLMResult
from adjutant.operations.models import OperationState, SideEffectClass
from adjutant.operations.store import OperationStore
from adjutant.operations.worker import OperationWorker

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.asyncio
async def test_worker_persists_result_and_all_delivery_chunks(tmp_path: Path) -> None:
    store = OperationStore(tmp_path)
    operation = store.create_operation(
        kind="telegram_chat",
        source="telegram",
        payload={"text": "hello", "reply_to_message_id": 7},
        telegram_chat_id="42",
        side_effect_class=SideEffectClass.UNKNOWN,
    )

    async def handler(_operation):
        return LLMResult(text="a" * 8100, session_id="session-1")

    worker = OperationWorker(tmp_path, store=store, handler=handler, worker_id="worker")
    result = await worker.run_once()

    assert result is not None
    assert result.id == operation.id
    assert result.state is OperationState.SUCCEEDED
    assert result.result_text == "a" * 8100
    deliveries = store.list_deliveries(operation.id)
    assert [len(item.payload["text"]) for item in deliveries] == [4000, 4000, 100]
    assert len(store.list_attempts(operation.id)) == 1


@pytest.mark.asyncio
async def test_worker_shows_typing_for_telegram_operation_lifetime(tmp_path: Path) -> None:
    store = OperationStore(tmp_path)
    operation = store.create_operation(
        kind="telegram_chat",
        source="telegram",
        payload={"text": "hello"},
        telegram_chat_id="42",
    )

    async def handler(_operation):
        return LLMResult(text="done")

    delivery = SimpleNamespace(bot_token="token", chat_id="42")
    worker = OperationWorker(
        tmp_path,
        store=store,
        handler=handler,
        worker_id="worker",
        runtime_seconds=30,
        cancellation_grace_seconds=5,
        delivery_worker=delivery,  # type: ignore[arg-type]
    )
    with (
        patch("adjutant.messaging.telegram.send.msg_typing_start") as typing_start,
        patch("adjutant.messaging.telegram.send.msg_typing_stop") as typing_stop,
    ):
        result = await worker.run_once()

    assert result is not None
    key = f"operation_{operation.id}"
    typing_start.assert_called_once_with(key, "token", "42", max_duration=40)
    typing_stop.assert_called_once_with(key)


@pytest.mark.asyncio
async def test_worker_stops_typing_after_timeout(tmp_path: Path) -> None:
    store = OperationStore(tmp_path)
    operation = store.create_operation(
        kind="telegram_chat",
        source="telegram",
        payload={"text": "hello"},
        telegram_chat_id="42",
    )

    async def handler(_operation):
        await asyncio.sleep(10)
        return LLMResult(text="late")

    worker = OperationWorker(
        tmp_path,
        store=store,
        handler=handler,
        worker_id="worker",
        runtime_seconds=0.01,
        cancellation_grace_seconds=0.01,
        delivery_worker=SimpleNamespace(bot_token="token", chat_id="42"),  # type: ignore[arg-type]
    )
    with (
        patch("adjutant.messaging.telegram.send.msg_typing_start"),
        patch("adjutant.messaging.telegram.send.msg_typing_stop") as typing_stop,
    ):
        result = await worker.run_once()

    assert result is not None
    assert result.state is OperationState.TIMED_OUT
    typing_stop.assert_called_once_with(f"operation_{operation.id}")


@pytest.mark.asyncio
async def test_photo_preparation_runs_inside_tracked_worker(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "adjutant.yaml").write_text("features:\n  vision:\n    enabled: true\n")
    image = tmp_path / "photo.jpg"
    image.write_bytes(b"image")
    store = OperationStore(tmp_path)
    operation = store.create_operation(
        kind="telegram_photo",
        source="telegram",
        payload={"file_id": "file-1", "caption": "What is the total?"},
    )
    worker = OperationWorker(tmp_path, store=store)
    monkeypatch.setattr(
        "adjutant.core.env.require_telegram_credentials",
        lambda _path: ("token", "42"),
    )
    monkeypatch.setattr(
        "adjutant.messaging.telegram.photos.tg_download_photo",
        lambda *_args, **_kwargs: image,
    )
    worker_loop = asyncio.get_running_loop()

    async def analyze_photo(*_args, **_kwargs):
        assert asyncio.get_running_loop() is worker_loop
        return "Total: 12.00"

    monkeypatch.setattr(
        "adjutant.capabilities.vision.vision.run_vision_async",
        analyze_photo,
    )

    prompt = await worker._prepare_photo_prompt(operation)  # noqa: SLF001

    assert "What is the total?" in prompt
    assert "Total: 12.00" in prompt
    assert "untrusted evidence" in prompt
    assert f"Saved local attachment path: {image}" in prompt
    persisted = store.get_operation(operation.id)
    assert persisted is not None
    assert persisted.payload["local_attachment_path"] == str(image)
    assert persisted.payload["attachment_media_type"] == "photo"


@pytest.mark.asyncio
async def test_photo_issue_write_always_asks_for_upload_consent(tmp_path: Path) -> None:
    store = OperationStore(tmp_path)
    operation = store.create_operation(
        kind="telegram_photo",
        source="telegram",
        payload={"file_id": "file-1", "caption": "Create an issue"},
        telegram_chat_id="42",
    )
    child = store.create_operation(
        kind="kb_write",
        source="kb",
        payload={"prompt": "Create issue"},
        parent_id=operation.id,
        execution_mode="inline",
    )
    store.claim_operation(child.id, "child-worker")
    store.transition(child.id, OperationState.RUNNING, worker_id="child-worker")
    store.transition(child.id, OperationState.SUCCEEDED, result_text="Created issue #55")

    async def handler(_operation):
        return LLMResult(text="Created and verified issue #55.")

    worker = OperationWorker(tmp_path, store=store, handler=handler, worker_id="worker")
    completed = await worker.run_once()

    assert completed is not None
    assert completed.result_text == (
        "Created and verified issue #55.\n\n"
        "Should I upload the saved photo or photos to the issue?"
    )
    deliveries = store.list_deliveries(operation.id)
    assert deliveries[0].payload["text"].endswith("photos to the issue?")


def test_photo_issue_write_preserves_existing_upload_question(tmp_path: Path) -> None:
    store = OperationStore(tmp_path)
    operation = store.create_operation(
        kind="telegram_photo",
        source="telegram",
        payload={},
    )
    child = store.create_operation(
        kind="kb_write",
        source="kb",
        payload={},
        parent_id=operation.id,
    )
    child = replace(child, state=OperationState.SUCCEEDED)

    text = OperationWorker._ensure_photo_issue_upload_question(  # noqa: SLF001
        operation,
        "Created issue #55. Should I upload the photos?",
        [child],
    )

    assert text == "Created issue #55. Should I upload the photos?"


@pytest.mark.asyncio
async def test_worker_runtime_timeout_is_terminal_and_deliverable(tmp_path: Path) -> None:
    store = OperationStore(tmp_path)
    operation = store.create_operation(
        kind="telegram_chat",
        source="telegram",
        payload={"text": "hello", "reply_to_message_id": 7},
        telegram_chat_id="42",
    )

    async def handler(_operation):
        await asyncio.sleep(10)
        return LLMResult(text="late")

    worker = OperationWorker(
        tmp_path,
        store=store,
        handler=handler,
        worker_id="worker",
        runtime_seconds=0.01,
    )
    result = await worker.run_once()

    assert result is not None
    assert result.id == operation.id
    assert result.state is OperationState.TIMED_OUT
    assert result.error_type == "timeout"
    assert len(store.list_deliveries(operation.id)) == 1


@pytest.mark.asyncio
async def test_uncertain_disconnect_transitions_through_reconciliation(
    tmp_path: Path,
) -> None:
    store = OperationStore(tmp_path)
    operation = store.create_operation(
        kind="telegram_chat",
        source="telegram",
        payload={"text": "hello"},
        telegram_chat_id="42",
    )

    async def handler(_operation):
        return LLMResult(
            text="",
            error_type="reconciliation_required",
            returncode=1,
            session_id="session-uncertain",
            server_instance_id="server-1",
            reconciliation_status='{"type": "busy"}',
        )

    worker = OperationWorker(tmp_path, store=store, handler=handler, worker_id="worker")
    result = await worker.run_once()

    assert result is not None
    assert result.state is OperationState.INTERRUPTED
    assert result.recovery_status == '{"type": "busy"}'
    assert result.error_type == "reconciliation_required"
    assert "did not replay" in store.list_deliveries(operation.id)[0].payload["text"]
    attempt = store.list_attempts(operation.id)[0]
    assert attempt.state == OperationState.INTERRUPTED.value
    assert attempt.backend_session_id == "session-uncertain"
    assert attempt.server_instance_id == "server-1"


@pytest.mark.asyncio
async def test_runtime_context_propagates_parent_id_to_persistent_tools(
    tmp_path: Path,
) -> None:
    store = OperationStore(tmp_path)
    operation = store.create_operation(
        kind="telegram_chat",
        source="telegram",
        payload={"text": "Check IxDA"},
        telegram_chat_id="42",
    )
    requests = []

    class Backend:
        async def execute(self, request):
            requests.append(request)
            yield ExecutionEvent(
                type=ExecutionEventType.COMPLETED,
                result=LLMResult(text="done"),
            )

    worker = OperationWorker(tmp_path, store=store, worker_id="worker")
    with patch("adjutant.operations.worker.get_backend", return_value=Backend()):
        result = await worker._execute_backend(operation)  # noqa: SLF001

    assert result.text == "done"
    assert f"ADJUTANT_PARENT_OPERATION_ID={operation.id}" in requests[0].prompt
    assert requests[0].prompt.endswith("Check IxDA")


@pytest.mark.asyncio
async def test_cancel_request_stops_running_handler(tmp_path: Path) -> None:
    store = OperationStore(tmp_path)
    operation = store.create_operation(
        kind="telegram_chat",
        source="telegram",
        payload={"text": "hello"},
    )
    started = asyncio.Event()

    async def handler(_operation):
        started.set()
        await asyncio.sleep(10)
        return LLMResult(text="late")

    worker = OperationWorker(
        tmp_path,
        store=store,
        handler=handler,
        worker_id="worker",
        lease_seconds=0.3,
    )
    task = asyncio.create_task(worker.run_once())
    await started.wait()
    store.request_cancel(operation.id)
    result = await asyncio.wait_for(task, timeout=2)

    assert result is not None
    assert result.state is OperationState.CANCELLED


@pytest.mark.asyncio
async def test_worker_records_quiet_progress_warning(tmp_path: Path) -> None:
    store = OperationStore(tmp_path)
    operation = store.create_operation(kind="prompt", source="test", payload={})

    async def handler(_operation):
        await asyncio.sleep(0.2)
        return LLMResult(text="done")

    worker = OperationWorker(
        tmp_path,
        store=store,
        handler=handler,
        worker_id="worker",
        lease_seconds=0.15,
        progress_warning_seconds=0.01,
        runtime_seconds=1,
    )
    result = await worker.run_once()

    assert result is not None
    assert result.state is OperationState.SUCCEEDED
    assert any(event.event_type == "progress_warning" for event in store.list_events(operation.id))


@pytest.mark.asyncio
async def test_worker_queues_status_edits_and_final_reply(tmp_path: Path) -> None:
    store = OperationStore(tmp_path)
    operation = store.create_operation(
        kind="telegram_chat",
        source="telegram",
        payload={"text": "hello", "reply_to_message_id": 7},
        telegram_chat_id="42",
    )
    store.set_status_message_id(operation.id, 55)

    async def handler(_operation):
        return LLMResult(text="done")

    worker = OperationWorker(tmp_path, store=store, handler=handler, worker_id="worker")
    result = await worker.run_once()

    assert result is not None
    deliveries = store.list_deliveries(operation.id)
    assert [item.payload.get("method", "send") for item in deliveries] == [
        "edit",
        "edit",
        "send",
    ]
    assert deliveries[-1].payload["text"] == "done"


@pytest.mark.asyncio
async def test_unrelated_operations_run_in_separate_concurrent_executions(
    tmp_path: Path,
) -> None:
    store = OperationStore(tmp_path)
    first = store.create_operation(kind="prompt", source="test", payload={})
    second = store.create_operation(kind="prompt", source="test", payload={})
    both_started = asyncio.Event()
    release = asyncio.Event()
    active = 0
    max_active = 0

    async def handler(_operation):
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        if active == 2:
            both_started.set()
        await release.wait()
        active -= 1
        return LLMResult(text="done")

    worker = OperationWorker(
        tmp_path,
        store=store,
        handler=handler,
        worker_id="worker",
        concurrency=2,
        poll_interval_seconds=0.01,
    )
    task = asyncio.create_task(worker.run_forever())
    await asyncio.wait_for(both_started.wait(), timeout=1)
    release.set()
    while True:
        states = {store.get_operation(first.id).state, store.get_operation(second.id).state}  # type: ignore[union-attr]
        if states == {OperationState.SUCCEEDED}:
            break
        await asyncio.sleep(0.01)
    worker.stop()
    await asyncio.wait_for(task, timeout=1)

    assert max_active == 2
