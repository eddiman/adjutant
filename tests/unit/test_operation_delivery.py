"""Tests for durable outbound delivery."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from adjutant.messaging.telegram.send import TelegramDeliveryReceipt
from adjutant.operations.delivery import DeliveryWorker, split_telegram_text
from adjutant.operations.models import DeliveryState
from adjutant.operations.store import OperationStore

if TYPE_CHECKING:
    from pathlib import Path


def test_split_telegram_text_preserves_complete_result() -> None:
    text = ("first paragraph\n\n" + "x" * 3900 + "\n\nlast paragraph") * 2
    chunks = split_telegram_text(text, max_length=4000)
    assert all(len(chunk) <= 4000 for chunk in chunks)
    assert "".join(chunks).replace("\n\n", "") == text.replace("\n\n", "")


@pytest.mark.asyncio
async def test_delivery_worker_persists_confirmed_receipt(tmp_path: Path) -> None:
    store = OperationStore(tmp_path)
    operation = store.create_operation(kind="chat", source="test", payload={})
    delivery = store.enqueue_delivery(
        operation.id,
        destination="telegram",
        payload={"chat_id": "42", "reply_to_message_id": 7, "text": "done"},
    )
    calls: list[tuple[str, int | None, str]] = []

    def sender(message, reply_to=None, *, bot_token, chat_id):
        calls.append((message, reply_to, chat_id))
        return TelegramDeliveryReceipt(delivered=True, message_id=91)

    worker = DeliveryWorker(
        tmp_path,
        bot_token="token",
        chat_id="42",
        store=store,
        sender=sender,
    )
    result = await worker.run_once()

    assert result is not None
    assert result.id == delivery.id
    assert result.state is DeliveryState.DELIVERED
    assert result.telegram_message_id == 91
    assert calls == [("done", 7, "42")]


@pytest.mark.asyncio
async def test_delivery_worker_retries_ambiguous_failure(tmp_path: Path) -> None:
    store = OperationStore(tmp_path)
    operation = store.create_operation(kind="chat", source="test", payload={})
    store.enqueue_delivery(
        operation.id,
        destination="telegram",
        payload={"text": "done"},
    )

    def sender(message, reply_to=None, *, bot_token, chat_id):
        return TelegramDeliveryReceipt(
            delivered=False,
            uncertain=True,
            error="connection reset",
        )

    worker = DeliveryWorker(
        tmp_path,
        bot_token="token",
        chat_id="42",
        store=store,
        sender=sender,
        retry_base_seconds=0.01,
    )
    result = await worker.run_once()

    assert result is not None
    assert result.state is DeliveryState.RETRY_WAIT
    assert result.uncertain is True


@pytest.mark.asyncio
async def test_delivery_worker_edits_known_status_message(tmp_path: Path) -> None:
    store = OperationStore(tmp_path)
    operation = store.create_operation(kind="chat", source="test", payload={})
    store.enqueue_delivery(
        operation.id,
        destination="telegram",
        payload={"method": "edit", "message_id": 44, "text": "running"},
    )
    edits: list[tuple[int, str]] = []

    def editor(message_id, message, *, bot_token, chat_id):
        edits.append((message_id, message))
        return TelegramDeliveryReceipt(delivered=True, message_id=message_id)

    worker = DeliveryWorker(
        tmp_path,
        bot_token="token",
        chat_id="42",
        store=store,
        editor=editor,
    )
    result = await worker.run_once()

    assert result is not None
    assert result.state is DeliveryState.DELIVERED
    assert edits == [(44, "running")]
