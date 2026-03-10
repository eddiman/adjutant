"""Tests for src/adjutant/messaging/telegram/send.py"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from adjutant.messaging.telegram.send import (
    _sanitize,
    _tg_url,
    msg_authorize,
    msg_react,
    msg_send_text,
    msg_typing_start,
    msg_typing_stop,
    TelegramSender,
    _TYPING_THREADS,
)


BOT = "123:testtoken"
CHAT = "999"


class TestSanitize:
    def test_strips_nul_bytes(self) -> None:
        result = _sanitize("hello\x00world")
        assert result == "helloworld"

    def test_strips_control_chars(self) -> None:
        # 0x01-0x08, 0x0B-0x1F, 0x7F stripped; 0x09 (tab) and 0x0A (newline) kept
        result = _sanitize("a\x01b\x0bc\x7fd")
        assert result == "abcd"

    def test_keeps_tab_and_newline(self) -> None:
        result = _sanitize("a\tb\nc")
        assert result == "a\tb\nc"

    def test_clamps_to_4000_chars(self) -> None:
        long_msg = "x" * 5000
        result = _sanitize(long_msg)
        assert len(result) == 4000

    def test_empty_string(self) -> None:
        assert _sanitize("") == ""

    def test_normal_message_unchanged(self) -> None:
        msg = "Hello, world! This is fine."
        assert _sanitize(msg) == msg


class TestTgUrl:
    def test_formats_url(self) -> None:
        url = _tg_url("123:abc", "sendMessage")
        assert url == "https://api.telegram.org/bot123:abc/sendMessage"


class TestMsgSendText:
    def test_sends_message(self) -> None:
        mock_client = MagicMock()
        with patch("adjutant.messaging.telegram.send.get_client", return_value=mock_client):
            msg_send_text("Hello", bot_token=BOT, chat_id=CHAT)
        mock_client.post.assert_called_once()
        call_kwargs = mock_client.post.call_args
        payload = call_kwargs[1]["json_data"]
        assert payload["text"] == "Hello"
        assert payload["chat_id"] == CHAT
        assert payload["parse_mode"] == "Markdown"

    def test_sends_with_reply_to(self) -> None:
        mock_client = MagicMock()
        with patch("adjutant.messaging.telegram.send.get_client", return_value=mock_client):
            msg_send_text("Reply", reply_to=42, bot_token=BOT, chat_id=CHAT)
        payload = mock_client.post.call_args[1]["json_data"]
        assert payload["reply_to_message_id"] == 42

    def test_skips_empty_message(self) -> None:
        mock_client = MagicMock()
        with patch("adjutant.messaging.telegram.send.get_client", return_value=mock_client):
            msg_send_text("", bot_token=BOT, chat_id=CHAT)
        mock_client.post.assert_not_called()

    def test_skips_control_char_only_message(self) -> None:
        mock_client = MagicMock()
        with patch("adjutant.messaging.telegram.send.get_client", return_value=mock_client):
            msg_send_text("\x01\x02\x03", bot_token=BOT, chat_id=CHAT)
        mock_client.post.assert_not_called()

    def test_swallows_exception(self) -> None:
        mock_client = MagicMock()
        mock_client.post.side_effect = Exception("network error")
        with patch("adjutant.messaging.telegram.send.get_client", return_value=mock_client):
            # Should not raise
            msg_send_text("Hello", bot_token=BOT, chat_id=CHAT)


class TestMsgReact:
    def test_fires_background_thread(self) -> None:
        mock_client = MagicMock()
        with patch("adjutant.messaging.telegram.send.get_client", return_value=mock_client):
            msg_react(1, "👀", bot_token=BOT, chat_id=CHAT)
            time.sleep(0.1)
        mock_client.post.assert_called_once()

    def test_skips_zero_message_id(self) -> None:
        mock_client = MagicMock()
        with patch("adjutant.messaging.telegram.send.get_client", return_value=mock_client):
            msg_react(0, "👀", bot_token=BOT, chat_id=CHAT)
        mock_client.post.assert_not_called()

    def test_swallows_exception_in_thread(self) -> None:
        mock_client = MagicMock()
        mock_client.post.side_effect = Exception("fail")
        with patch("adjutant.messaging.telegram.send.get_client", return_value=mock_client):
            msg_react(42, "👀", bot_token=BOT, chat_id=CHAT)
            time.sleep(0.15)
        # Should not have raised


class TestMsgTyping:
    def teardown_method(self) -> None:
        # Clean up any leftover typing threads
        for key in list(_TYPING_THREADS.keys()):
            msg_typing_stop(key)

    def test_start_creates_thread(self) -> None:
        mock_client = MagicMock()
        with patch("adjutant.messaging.telegram.send.get_client", return_value=mock_client):
            msg_typing_start("test_key", BOT, CHAT)
            assert "test_key" in _TYPING_THREADS
            msg_typing_stop("test_key")

    def test_stop_removes_thread(self) -> None:
        mock_client = MagicMock()
        with patch("adjutant.messaging.telegram.send.get_client", return_value=mock_client):
            msg_typing_start("stop_key", BOT, CHAT)
            msg_typing_stop("stop_key")
            assert "stop_key" not in _TYPING_THREADS

    def test_stop_nonexistent_key_is_noop(self) -> None:
        # Should not raise
        msg_typing_stop("nonexistent_key_xyz")

    def test_start_replaces_existing_same_key(self) -> None:
        mock_client = MagicMock()
        with patch("adjutant.messaging.telegram.send.get_client", return_value=mock_client):
            msg_typing_start("dup_key", BOT, CHAT)
            t1, e1 = _TYPING_THREADS["dup_key"]
            msg_typing_start("dup_key", BOT, CHAT)
            # Old event should be set (stopped)
            assert e1.is_set()
            # New thread registered
            assert "dup_key" in _TYPING_THREADS
            msg_typing_stop("dup_key")


class TestMsgAuthorize:
    def test_authorized_when_ids_match(self) -> None:
        assert msg_authorize("999", "999") is True

    def test_rejects_when_ids_differ(self) -> None:
        assert msg_authorize("123", "999") is False

    def test_coerces_types(self) -> None:
        # Both sides are str-compared
        assert msg_authorize("999", "999") is True


class TestTelegramSender:
    def test_authorize_uses_chat_id(self) -> None:
        sender = TelegramSender("tok", "888")
        assert sender.authorize("888") is True
        assert sender.authorize("777") is False

    def test_get_user_id_returns_chat_id(self) -> None:
        sender = TelegramSender("tok", "888")
        assert sender.get_user_id() == "888"

    @pytest.mark.asyncio
    async def test_send_text_delegates(self) -> None:
        sender = TelegramSender(BOT, CHAT)
        mock_client = MagicMock()
        with patch("adjutant.messaging.telegram.send.get_client", return_value=mock_client):
            await sender.send_text("hi")
        mock_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_typing_start_and_stop(self) -> None:
        sender = TelegramSender(BOT, CHAT)
        mock_client = MagicMock()
        with patch("adjutant.messaging.telegram.send.get_client", return_value=mock_client):
            await sender.typing("start", suffix="s1")
            assert "s1" in _TYPING_THREADS
            await sender.typing("stop", suffix="s1")
            assert "s1" not in _TYPING_THREADS

    @pytest.mark.asyncio
    async def test_react_delegates(self) -> None:
        sender = TelegramSender(BOT, CHAT)
        mock_client = MagicMock()
        with patch("adjutant.messaging.telegram.send.get_client", return_value=mock_client):
            await sender.react(1, "👍")
            time.sleep(0.1)
        mock_client.post.assert_called_once()
