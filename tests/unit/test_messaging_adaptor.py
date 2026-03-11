"""Tests for src/adjutant/messaging/adaptor.py"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from adjutant.messaging.adaptor import MessagingAdaptor


class ConcreteAdaptor(MessagingAdaptor):
    """Minimal concrete implementation that satisfies abstract requirements."""

    async def send_text(self, message: str, reply_to_message_id: int | None = None) -> None:
        pass

    async def send_photo(self, file_path: Path, caption: str = "") -> None:
        pass

    async def start_listener(self) -> None:
        pass

    async def stop_listener(self) -> None:
        pass


class TestMessagingAdaptorContract:
    """Test that the ABC enforces required methods."""

    def test_cannot_instantiate_abstract_directly(self) -> None:
        with pytest.raises(TypeError):
            MessagingAdaptor()  # type: ignore[abstract]

    def test_concrete_implementation_instantiates(self) -> None:
        adaptor = ConcreteAdaptor()
        assert isinstance(adaptor, MessagingAdaptor)


class TestOptionalDefaults:
    """Test that optional methods have sensible defaults."""

    @pytest.mark.asyncio
    async def test_react_is_noop_by_default(self) -> None:
        adaptor = ConcreteAdaptor()
        # Should not raise
        await adaptor.react(123, "👀")

    @pytest.mark.asyncio
    async def test_typing_is_noop_by_default(self) -> None:
        adaptor = ConcreteAdaptor()
        await adaptor.typing("start")
        await adaptor.typing("stop", suffix="x")

    def test_authorize_allows_all_by_default(self) -> None:
        adaptor = ConcreteAdaptor()
        assert adaptor.authorize("any_user") is True
        assert adaptor.authorize("") is True
        assert adaptor.authorize("12345") is True

    def test_get_user_id_returns_unknown_by_default(self) -> None:
        adaptor = ConcreteAdaptor()
        assert adaptor.get_user_id() == "unknown"


class TestAbstractMethodSignatures:
    """Test that send_text and send_photo accept expected arguments."""

    @pytest.mark.asyncio
    async def test_send_text_with_reply_to(self) -> None:
        adaptor = ConcreteAdaptor()
        await adaptor.send_text("hello", reply_to_message_id=42)

    @pytest.mark.asyncio
    async def test_send_text_without_reply_to(self) -> None:
        adaptor = ConcreteAdaptor()
        await adaptor.send_text("hello")

    @pytest.mark.asyncio
    async def test_send_photo_with_caption(self) -> None:
        adaptor = ConcreteAdaptor()
        await adaptor.send_photo(Path("/tmp/img.png"), caption="test")

    @pytest.mark.asyncio
    async def test_send_photo_without_caption(self) -> None:
        adaptor = ConcreteAdaptor()
        await adaptor.send_photo(Path("/tmp/img.png"))

    @pytest.mark.asyncio
    async def test_start_and_stop_listener(self) -> None:
        adaptor = ConcreteAdaptor()
        await adaptor.start_listener()
        await adaptor.stop_listener()
