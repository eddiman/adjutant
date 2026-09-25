"""Conversation context and explicit follow-up dependency handling."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from adjutant.operations.models import Operation
    from adjutant.operations.store import OperationStore

_OPERATION_REFERENCE = re.compile(r"\bop-[0-9a-f]{8,32}\b")
_MAX_CONTEXT_CHARS = 12000
_MAX_TURN_CHARS = 3000


def resolve_followup_target(
    store: OperationStore,
    *,
    chat_id: str,
    text: str,
    reply_to_message_id: int | None = None,
) -> Operation | None:
    """Resolve an explicit operation ID or Telegram reply target."""
    for match in _OPERATION_REFERENCE.finditer(text):
        operation = store.find_operation_reference(match.group(0))
        if operation is not None and operation.telegram_chat_id == chat_id:
            return operation
    if reply_to_message_id is not None:
        return store.find_telegram_operation(chat_id, reply_to_message_id)
    return None


def build_conversation_prompt(operation: Operation, store: OperationStore) -> str:
    """Build bounded deterministic context for an operation-owned session."""
    prompt = str(operation.payload.get("text") or operation.payload.get("prompt") or "")
    if operation.kind != "telegram_chat" or operation.telegram_chat_id is None:
        return prompt

    context = store.list_conversation_operations(
        operation.telegram_chat_id,
        before_created_at=operation.created_at,
        limit=6,
    )
    context_by_id = {item.id: item for item in context}
    for dependency_id in operation.dependency_ids:
        dependency = store.get_operation(dependency_id)
        if dependency is not None and dependency.result_text:
            context_by_id[dependency.id] = dependency

    blocks: list[str] = []
    used = 0
    for previous in context_by_id.values():
        request = str(previous.payload.get("text") or previous.payload.get("prompt") or "")
        answer = previous.result_text or ""
        block = (
            f"Previous user turn ({previous.id}):\n{request[:_MAX_TURN_CHARS]}\n"
            f"Previous completed answer:\n{answer[:_MAX_TURN_CHARS]}"
        )
        if used + len(block) > _MAX_CONTEXT_CHARS:
            break
        blocks.append(block)
        used += len(block)
    if not blocks:
        return prompt
    return (
        "Use the completed conversation context below to resolve references in the new turn. "
        "Do not claim that unfinished or failed work completed.\n\n"
        + "\n\n".join(blocks)
        + f"\n\nNew user turn:\n{prompt}"
    )
