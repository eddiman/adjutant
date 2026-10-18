"""Durable outbound delivery processing."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Protocol

from adjutant.core.logging import adj_log
from adjutant.messaging.telegram.send import (
    TelegramDeliveryReceipt,
    msg_edit_text,
    msg_send_text,
)
from adjutant.operations.store import OperationStore

if TYPE_CHECKING:
    from pathlib import Path

    from adjutant.operations.models import Delivery


class TextSender(Protocol):
    def __call__(
        self,
        message: str,
        reply_to: int | None = None,
        *,
        bot_token: str,
        chat_id: str,
    ) -> TelegramDeliveryReceipt: ...


class TextEditor(Protocol):
    def __call__(
        self,
        message_id: int,
        message: str,
        *,
        bot_token: str,
        chat_id: str,
    ) -> TelegramDeliveryReceipt: ...


def split_telegram_text(text: str, *, max_length: int = 4000) -> list[str]:
    """Split complete results without silently truncating them."""
    if not text:
        return []
    chunks: list[str] = []
    remaining = text
    while len(remaining) > max_length:
        split_at = remaining.rfind("\n\n", 0, max_length + 1)
        if split_at < max_length // 2:
            split_at = remaining.rfind("\n", 0, max_length + 1)
        if split_at < max_length // 2:
            split_at = remaining.rfind(" ", 0, max_length + 1)
        if split_at <= 0:
            split_at = max_length
        chunk = remaining[:split_at].rstrip()
        if not chunk:
            chunk = remaining[:max_length]
            split_at = max_length
        chunks.append(chunk)
        remaining = remaining[split_at:].lstrip()
    if remaining:
        chunks.append(remaining)
    return chunks


class DeliveryWorker:
    """Claims and sends persisted outbound deliveries."""

    def __init__(
        self,
        adj_dir: Path,
        *,
        bot_token: str,
        chat_id: str,
        store: OperationStore | None = None,
        worker_id: str = "delivery-worker",
        sender: TextSender = msg_send_text,
        editor: TextEditor = msg_edit_text,
        max_attempts: int = 8,
        retry_base_seconds: float = 2.0,
        lease_seconds: float = 60.0,
    ) -> None:
        self.store = store or OperationStore(adj_dir)
        self.worker_id = worker_id
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.sender = sender
        self.editor = editor
        self.max_attempts = max_attempts
        self.retry_base_seconds = retry_base_seconds
        self.lease_seconds = lease_seconds

    async def run_once(self) -> Delivery | None:
        """Send one due delivery and persist the observed outcome."""
        delivery = self.store.claim_delivery(
            self.worker_id,
            lease_seconds=self.lease_seconds,
        )
        if delivery is None:
            return None
        if delivery.destination != "telegram":
            return self.store.finish_delivery(
                delivery.id,
                delivered=False,
                error=f"unsupported destination: {delivery.destination}",
            )

        payload = delivery.payload
        message = str(payload.get("text") or "")
        reply_to_raw = payload.get("reply_to_message_id")
        reply_to = reply_to_raw if isinstance(reply_to_raw, int) else None
        destination_chat = str(payload.get("chat_id") or self.chat_id)
        method = str(payload.get("method") or "send")
        if method == "edit":
            target_message_id = payload.get("message_id")
            if not isinstance(target_message_id, int):
                return self.store.finish_delivery(
                    delivery.id,
                    delivered=False,
                    error="edit delivery missing message_id",
                )
            receipt = await asyncio.to_thread(
                self.editor,
                target_message_id,
                message,
                bot_token=self.bot_token,
                chat_id=destination_chat,
            )
        else:
            receipt = await asyncio.to_thread(
                self.sender,
                message,
                reply_to,
                bot_token=self.bot_token,
                chat_id=destination_chat,
            )
        if receipt.delivered:
            adj_log(
                "operations",
                f"Delivery {delivery.id} confirmed telegram_msg={receipt.message_id}",
            )
            return self.store.finish_delivery(
                delivery.id,
                delivered=True,
                telegram_message_id=receipt.message_id,
            )

        should_retry = delivery.attempt_count < self.max_attempts
        retry_after = None
        if should_retry:
            retry_after = self.retry_base_seconds * (2 ** max(0, delivery.attempt_count - 1))
        adj_log(
            "operations",
            f"Delivery {delivery.id} failed attempt={delivery.attempt_count} "
            f"uncertain={receipt.uncertain} retry={should_retry} error={receipt.error}",
        )
        return self.store.finish_delivery(
            delivery.id,
            delivered=False,
            uncertain=receipt.uncertain,
            error=receipt.error or "delivery_failed",
            retry_after_seconds=retry_after,
        )
