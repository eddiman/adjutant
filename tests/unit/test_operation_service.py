"""Tests for durable operation submission and recovery boundaries."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from adjutant.core.backend import ResolvedModel
from adjutant.messaging.telegram.send import TelegramDeliveryReceipt
from adjutant.operations.delivery import DeliveryWorker
from adjutant.operations.models import OperationState
from adjutant.operations.service import OperationService
from adjutant.operations.store import OperationStore

if TYPE_CHECKING:
    from pathlib import Path


def test_telegram_acceptance_freezes_backend_model_and_offset(tmp_path: Path) -> None:
    (tmp_path / "adjutant.yaml").write_text(
        "llm:\n  backend: claude-cli\n"
        "operations:\n  enabled: true\n"
        "messaging:\n  telegram:\n    default_model: cheap\n"
    )
    service = OperationService(tmp_path)
    with patch(
        "adjutant.operations.service.resolve_model_spec",
        return_value=ResolvedModel(model="sonnet", variant="high"),
    ):
        operation, inserted = service.accept_telegram_chat(
            bot_id="bot",
            update_id=10,
            next_offset=11,
            chat_id="42",
            message_id=5,
            text="hello",
        )

    assert inserted is True
    assert operation.backend == "claude-cli"
    assert operation.model == "sonnet"
    assert operation.variant == "high"
    assert operation.correlation_id == operation.id
    assert service.store.get_telegram_offset("bot") == 11
    snapshot = __import__("json").loads(
        (tmp_path / "state" / "active_operations.json").read_text()
    )
    assert snapshot[0]["id"] == operation.id
    assert snapshot[0]["state"] == "queued"


def test_photo_acceptance_is_durable_before_download(tmp_path: Path) -> None:
    (tmp_path / "adjutant.yaml").write_text(
        "llm:\n  backend: opencode\n"
        "operations:\n  enabled: true\n"
        "messaging:\n  telegram:\n    default_model: cheap\n"
    )
    service = OperationService(tmp_path)
    with patch(
        "adjutant.operations.service.resolve_model_spec",
        return_value=ResolvedModel(model="anthropic/test", variant="medium"),
    ):
        operation, inserted = service.accept_telegram_photo(
            bot_id="bot",
            update_id=12,
            next_offset=13,
            chat_id="42",
            message_id=6,
            file_id="telegram-file",
            caption="Read this receipt",
            media_group_id="album-1",
        )

    assert inserted is True
    assert operation.kind == "telegram_photo"
    assert operation.payload["file_id"] == "telegram-file"
    assert operation.payload["caption"] == "Read this receipt"
    assert operation.payload["media_group_id"] == "album-1"
    assert service.store.get_telegram_offset("bot") == 13


@pytest.mark.asyncio
async def test_restart_delivers_persisted_result_without_rerunning(tmp_path: Path) -> None:
    store = OperationStore(tmp_path)
    operation = store.create_operation(
        kind="telegram_chat",
        source="telegram",
        payload={"text": "request", "reply_to_message_id": 5},
        telegram_chat_id="42",
    )
    store.claim_next("old-worker")
    store.transition(operation.id, OperationState.RUNNING, worker_id="old-worker")
    store.complete_with_deliveries(
        operation.id,
        OperationState.SUCCEEDED,
        result_text="persisted answer",
        deliveries=(
            (
                "telegram",
                {"chat_id": "42", "reply_to_message_id": 5, "text": "persisted answer"},
                0,
            ),
        ),
    )
    sent: list[str] = []

    def sender(message, reply_to=None, *, bot_token, chat_id):
        sent.append(message)
        return TelegramDeliveryReceipt(delivered=True, message_id=20)

    restarted_delivery = DeliveryWorker(
        tmp_path,
        bot_token="token",
        chat_id="42",
        store=store,
        sender=sender,
    )
    delivered = await restarted_delivery.run_once()

    assert delivered is not None
    assert sent == ["persisted answer"]
    assert store.claim_next("new-worker") is None
    assert store.get_operation(operation.id).attempt_count == 1  # type: ignore[union-attr]
