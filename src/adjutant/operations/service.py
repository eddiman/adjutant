"""Submission and inspection API for durable operations."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from adjutant.core.config import load_config, load_typed_config
from adjutant.core.model import resolve_model_spec
from adjutant.messaging.telegram.chat import get_model
from adjutant.operations.models import Operation, SideEffectClass
from adjutant.operations.store import OperationStore

if TYPE_CHECKING:
    from pathlib import Path


class OperationService:
    """High-level operation API used by listeners, commands, and capabilities."""

    def __init__(self, adj_dir: Path, *, store: OperationStore | None = None) -> None:
        self.adj_dir = adj_dir
        self.store = store or OperationStore(adj_dir)
        self.store.initialize()

    def accept_telegram_chat(
        self,
        *,
        bot_id: str,
        update_id: int,
        next_offset: int,
        chat_id: str,
        message_id: int,
        text: str,
        thread_id: int | None = None,
        reply_to_message_id: int | None = None,
    ) -> tuple[Operation, bool]:
        """Accept one Telegram chat turn and freeze its execution settings."""
        typed_config = load_typed_config(self.adj_dir / "adjutant.yaml")
        config = load_config(self.adj_dir / "adjutant.yaml")
        model_spec = get_model(self.adj_dir)
        resolved = resolve_model_spec(
            model_spec,
            self.adj_dir / "state",
            config,
            default_to_chat=True,
        )
        payload: dict[str, Any] = {
            "text": text,
            "reply_to_message_id": message_id,
        }
        from adjutant.operations.sessions import resolve_followup_target

        target = resolve_followup_target(
            self.store,
            chat_id=chat_id,
            text=text,
            reply_to_message_id=reply_to_message_id,
        )
        dependencies: tuple[str, ...] = ()
        if target is not None and not target.state.terminal:
            dependencies = (target.id,)
        if target is not None:
            payload["followup_to_operation_id"] = target.id
        operation, inserted = self.store.accept_telegram_update(
            bot_id=bot_id,
            update_id=update_id,
            next_offset=next_offset,
            kind="telegram_chat",
            payload=payload,
            chat_id=chat_id,
            message_id=message_id,
            thread_id=thread_id,
            parent_id=target.id if target is not None else None,
            dependency_ids=dependencies,
            backend=typed_config.llm.backend,
            model=resolved.model,
            variant=resolved.variant,
            agent="adjutant",
            workdir=str(self.adj_dir),
            side_effect_class=SideEffectClass.UNKNOWN,
        )
        self.store.sync_active_snapshot()
        return operation, inserted

    def accept_telegram_photo(
        self,
        *,
        bot_id: str,
        update_id: int,
        next_offset: int,
        chat_id: str,
        message_id: int,
        file_id: str,
        caption: str,
        thread_id: int | None = None,
    ) -> tuple[Operation, bool]:
        """Accept a photo before download or model execution begins."""
        typed_config = load_typed_config(self.adj_dir / "adjutant.yaml")
        config = load_config(self.adj_dir / "adjutant.yaml")
        resolved = resolve_model_spec(
            get_model(self.adj_dir),
            self.adj_dir / "state",
            config,
            default_to_chat=True,
        )
        operation, inserted = self.store.accept_telegram_update(
            bot_id=bot_id,
            update_id=update_id,
            next_offset=next_offset,
            kind="telegram_photo",
            payload={
                "file_id": file_id,
                "caption": caption,
                "reply_to_message_id": message_id,
            },
            chat_id=chat_id,
            message_id=message_id,
            thread_id=thread_id,
            backend=typed_config.llm.backend,
            model=resolved.model,
            variant=resolved.variant,
            agent="adjutant",
            workdir=str(self.adj_dir),
            side_effect_class=SideEffectClass.UNKNOWN,
        )
        self.store.sync_active_snapshot()
        return operation, inserted

    def submit(
        self,
        *,
        kind: str,
        source: str,
        payload: dict[str, Any],
        parent_id: str | None = None,
        dependency_ids: tuple[str, ...] = (),
        side_effect_class: SideEffectClass = SideEffectClass.UNKNOWN,
        backend: str | None = None,
        model: str | None = None,
        variant: str | None = None,
        agent: str | None = None,
        workdir: str | None = None,
        telegram_chat_id: str | None = None,
        telegram_message_id: int | None = None,
        telegram_thread_id: int | None = None,
    ) -> Operation:
        """Submit work from a non-Telegram caller."""
        config = load_typed_config(self.adj_dir / "adjutant.yaml")
        operation = self.store.create_operation(
            kind=kind,
            source=source,
            payload=payload,
            parent_id=parent_id,
            dependency_ids=dependency_ids,
            side_effect_class=side_effect_class,
            backend=backend or config.llm.backend,
            model=model,
            variant=variant,
            agent=agent,
            workdir=workdir or str(self.adj_dir),
            telegram_chat_id=telegram_chat_id,
            telegram_message_id=telegram_message_id,
            telegram_thread_id=telegram_thread_id,
        )
        self.store.sync_active_snapshot()
        return operation

    def cancel(self, operation_id: str) -> Operation:
        operation = self.store.request_cancel(operation_id)
        self.store.sync_active_snapshot()
        return operation

    def get(self, operation_id: str) -> Operation | None:
        return self.store.get_operation(operation_id)

    def list_recent(self, *, limit: int = 20) -> list[Operation]:
        return self.store.list_operations(limit=limit)
