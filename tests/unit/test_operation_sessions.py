"""Tests for durable conversation context and explicit dependencies."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

from adjutant.operations.models import OperationState
from adjutant.operations.service import OperationService
from adjutant.operations.sessions import build_conversation_prompt, resolve_followup_target
from adjutant.operations.store import OperationStore

if TYPE_CHECKING:
    from pathlib import Path


def _complete(store: OperationStore, operation_id: str, result: str) -> None:
    store.claim_operation(operation_id, "worker")
    store.transition(operation_id, OperationState.RUNNING, worker_id="worker")
    store.complete_with_deliveries(
        operation_id,
        OperationState.SUCCEEDED,
        result_text=result,
    )


def test_builds_bounded_context_from_completed_turns(tmp_path: Path) -> None:
    store = OperationStore(tmp_path)
    previous = store.create_operation(
        kind="telegram_chat",
        source="telegram",
        payload={"text": "What is the deadline?"},
        telegram_chat_id="42",
    )
    _complete(store, previous.id, "Friday")
    current = store.create_operation(
        kind="telegram_chat",
        source="telegram",
        payload={"text": "Move it one day later"},
        telegram_chat_id="42",
        parent_id=previous.id,
        dependency_ids=(previous.id,),
    )

    prompt = build_conversation_prompt(current, store)

    assert "What is the deadline?" in prompt
    assert "Friday" in prompt
    assert prompt.endswith("Move it one day later")


def test_resolves_explicit_id_and_status_reply(tmp_path: Path) -> None:
    store = OperationStore(tmp_path)
    operation = store.create_operation(
        kind="telegram_chat",
        source="telegram",
        payload={"text": "long work"},
        telegram_chat_id="42",
    )
    store.set_status_message_id(operation.id, 77)

    explicit = resolve_followup_target(
        store,
        chat_id="42",
        text=f"Use {operation.id} and continue",
    )
    reply = resolve_followup_target(
        store,
        chat_id="42",
        text="continue",
        reply_to_message_id=77,
    )

    assert explicit is not None and explicit.id == operation.id
    assert reply is not None and reply.id == operation.id


def test_acceptance_links_only_explicit_unfinished_followup(tmp_path: Path) -> None:
    (tmp_path / "adjutant.yaml").write_text("operations:\n  enabled: true\n")
    store = OperationStore(tmp_path)
    service = OperationService(tmp_path, store=store)
    target = store.create_operation(
        kind="telegram_chat",
        source="telegram",
        payload={"text": "long work"},
        telegram_chat_id="42",
    )

    with (
        patch("adjutant.operations.service.resolve_model_spec") as resolve_model,
        patch("adjutant.operations.service.get_model", return_value="cheap"),
    ):
        resolve_model.return_value.model = "test-model"
        resolve_model.return_value.variant = None
        dependent, _ = service.accept_telegram_chat(
            bot_id="bot",
            update_id=1,
            next_offset=2,
            chat_id="42",
            message_id=10,
            text=f"Continue {target.id}",
        )
        unrelated, _ = service.accept_telegram_chat(
            bot_id="bot",
            update_id=2,
            next_offset=3,
            chat_id="42",
            message_id=11,
            text="What is the weather?",
        )

    assert dependent.parent_id == target.id
    assert dependent.dependency_ids == (target.id,)
    assert unrelated.parent_id is None
    assert unrelated.dependency_ids == ()
