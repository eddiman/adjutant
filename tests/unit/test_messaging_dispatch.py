"""Tests for src/adjutant/messaging/dispatch.py"""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from adjutant.messaging.dispatch import (
    _INFLIGHT,
    _RATE_LIMIT_WINDOW,
    _cancel_inflight,
    _check_rate_limit,
    _rate_limit_max,
    dispatch_message,
    dispatch_photo,
)


BOT = "123:testtoken"
CHAT = "999"


# ---------------------------------------------------------------------------
# _rate_limit_max
# ---------------------------------------------------------------------------


class TestRateLimitMax:
    def test_default_is_10(self, monkeypatch) -> None:
        monkeypatch.delenv("ADJUTANT_RATE_LIMIT_MAX", raising=False)
        assert _rate_limit_max() == 10

    def test_reads_from_env(self, monkeypatch) -> None:
        monkeypatch.setenv("ADJUTANT_RATE_LIMIT_MAX", "5")
        assert _rate_limit_max() == 5

    def test_falls_back_on_invalid_env(self, monkeypatch) -> None:
        monkeypatch.setenv("ADJUTANT_RATE_LIMIT_MAX", "bad")
        assert _rate_limit_max() == 10


# ---------------------------------------------------------------------------
# _check_rate_limit
# ---------------------------------------------------------------------------


class TestCheckRateLimit:
    def test_allows_first_message(self, tmp_path: Path) -> None:
        assert _check_rate_limit(tmp_path) is True

    def test_allows_up_to_max(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("ADJUTANT_RATE_LIMIT_MAX", "3")
        for _ in range(3):
            result = _check_rate_limit(tmp_path)
        assert result is True

    def test_rejects_over_max(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("ADJUTANT_RATE_LIMIT_MAX", "3")
        for _ in range(3):
            _check_rate_limit(tmp_path)
        result = _check_rate_limit(tmp_path)  # 4th message
        assert result is False

    def test_creates_state_dir(self, tmp_path: Path) -> None:
        _check_rate_limit(tmp_path)
        assert (tmp_path / "state").is_dir()

    def test_prunes_old_timestamps(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.setenv("ADJUTANT_RATE_LIMIT_MAX", "2")
        # Write old timestamps (outside the 60s window)
        state = tmp_path / "state"
        state.mkdir()
        old_time = int(time.time()) - _RATE_LIMIT_WINDOW - 10
        (state / "rate_limit_window").write_text(f"{old_time}\n{old_time}\n{old_time}\n")
        # Should be allowed because old timestamps were pruned
        assert _check_rate_limit(tmp_path) is True


# ---------------------------------------------------------------------------
# _cancel_inflight
# ---------------------------------------------------------------------------


class TestCancelInflight:
    def setup_method(self) -> None:
        _INFLIGHT.clear()

    def teardown_method(self) -> None:
        _INFLIGHT.clear()

    def test_cancels_other_tasks(self) -> None:
        loop = asyncio.new_event_loop()
        try:

            async def _slow():
                await asyncio.sleep(100)

            task_old = loop.create_task(_slow())
            _INFLIGHT["msg_old"] = task_old
            _INFLIGHT["msg_new"] = loop.create_task(_slow())

            _cancel_inflight("msg_new")

            # task.cancel() requests cancellation but doesn't settle immediately;
            # run the loop one step so the task processes the cancellation.
            loop.run_until_complete(asyncio.sleep(0))

            assert task_old.cancelled() or task_old.cancelling() > 0
            assert "msg_old" not in _INFLIGHT
        finally:
            # Clean up remaining tasks
            for t in list(_INFLIGHT.values()):
                t.cancel()
            _INFLIGHT.clear()
            loop.close()

    def test_does_not_cancel_current_task(self) -> None:
        loop = asyncio.new_event_loop()
        try:

            async def _slow():
                await asyncio.sleep(100)

            task_current = loop.create_task(_slow())
            _INFLIGHT["msg_current"] = task_current

            _cancel_inflight("msg_current")

            assert not task_current.cancelled()
        finally:
            task_current.cancel()
            _INFLIGHT.clear()
            loop.close()


# ---------------------------------------------------------------------------
# dispatch_message — authorization
# ---------------------------------------------------------------------------


class TestDispatchMessageAuth:
    @pytest.mark.asyncio
    async def test_rejects_unauthorized_sender(self, tmp_path: Path) -> None:
        mock_send = MagicMock()
        with patch("adjutant.messaging.telegram.send.msg_send_text", mock_send):
            await dispatch_message("hello", 1, "evil_user", tmp_path, bot_token=BOT, chat_id=CHAT)
        mock_send.assert_not_called()

    @pytest.mark.asyncio
    async def test_accepts_authorized_sender(self, tmp_path: Path) -> None:
        sent = []

        async def mock_cmd_status(message_id, adj_dir, *, bot_token, chat_id):
            sent.append("status_called")

        with patch("adjutant.messaging.telegram.commands.cmd_status", mock_cmd_status):
            with patch("adjutant.messaging.dispatch._check_rate_limit", return_value=True):
                await dispatch_message("/status", 1, CHAT, tmp_path, bot_token=BOT, chat_id=CHAT)
        assert "status_called" in sent


# ---------------------------------------------------------------------------
# dispatch_message — rate limiting
# ---------------------------------------------------------------------------


class TestDispatchMessageRateLimit:
    @pytest.mark.asyncio
    async def test_rate_limit_sends_warning(self, tmp_path: Path) -> None:
        sent = []

        def _fake_send(msg, reply_to=None, *, bot_token, chat_id):
            sent.append(msg)

        with patch("adjutant.messaging.dispatch._check_rate_limit", return_value=False):
            with patch("adjutant.messaging.telegram.send.msg_send_text", _fake_send):
                await dispatch_message("hello", 1, CHAT, tmp_path, bot_token=BOT, chat_id=CHAT)

        assert any("too quickly" in m.lower() or "wait" in m.lower() for m in sent)


# ---------------------------------------------------------------------------
# dispatch_message — pending reflect flow
# ---------------------------------------------------------------------------


class TestDispatchMessagePendingReflect:
    @pytest.mark.asyncio
    async def test_confirm_routes_to_reflect_confirm(self, tmp_path: Path) -> None:
        state = tmp_path / "state"
        state.mkdir()
        (state / "pending_reflect").touch()

        confirm_called = []

        async def mock_reflect_confirm(message_id, adj_dir, *, bot_token, chat_id):
            confirm_called.append(True)

        with patch(
            "adjutant.messaging.telegram.commands.cmd_reflect_confirm", mock_reflect_confirm
        ):
            with patch("adjutant.messaging.dispatch._check_rate_limit", return_value=True):
                await dispatch_message("/confirm", 1, CHAT, tmp_path, bot_token=BOT, chat_id=CHAT)

        assert confirm_called

    @pytest.mark.asyncio
    async def test_non_confirm_cancels_reflect(self, tmp_path: Path) -> None:
        state = tmp_path / "state"
        state.mkdir()
        (state / "pending_reflect").touch()

        sent = []

        def _fake_send(msg, reply_to=None, *, bot_token, chat_id):
            sent.append(msg)

        with patch("adjutant.messaging.telegram.send.msg_send_text", _fake_send):
            with patch("adjutant.messaging.dispatch._check_rate_limit", return_value=True):
                await dispatch_message(
                    "something else", 1, CHAT, tmp_path, bot_token=BOT, chat_id=CHAT
                )

        assert not (state / "pending_reflect").exists()
        assert any("cancelled" in m.lower() for m in sent)


# ---------------------------------------------------------------------------
# dispatch_message — command routing
# ---------------------------------------------------------------------------


class TestDispatchMessageCommandRouting:
    @pytest.mark.asyncio
    async def test_routes_status_command(self, tmp_path: Path) -> None:
        called = []

        async def mock_cmd(message_id, adj_dir, *, bot_token, chat_id):
            called.append("status")

        with patch("adjutant.messaging.telegram.commands.cmd_status", mock_cmd):
            with patch("adjutant.messaging.dispatch._check_rate_limit", return_value=True):
                await dispatch_message("/status", 1, CHAT, tmp_path, bot_token=BOT, chat_id=CHAT)

        assert "status" in called

    @pytest.mark.asyncio
    async def test_routes_pause_command(self, tmp_path: Path) -> None:
        called = []

        async def mock_cmd(message_id, adj_dir, *, bot_token, chat_id):
            called.append("pause")

        with patch("adjutant.messaging.telegram.commands.cmd_pause", mock_cmd):
            with patch("adjutant.messaging.dispatch._check_rate_limit", return_value=True):
                await dispatch_message("/pause", 1, CHAT, tmp_path, bot_token=BOT, chat_id=CHAT)

        assert "pause" in called

    @pytest.mark.asyncio
    async def test_routes_screenshot_with_url(self, tmp_path: Path) -> None:
        called = []

        async def mock_cmd(url, message_id, adj_dir, *, bot_token, chat_id):
            called.append(url)

        with patch("adjutant.messaging.telegram.commands.cmd_screenshot", mock_cmd):
            with patch("adjutant.messaging.dispatch._check_rate_limit", return_value=True):
                await dispatch_message(
                    "/screenshot https://example.com",
                    1,
                    CHAT,
                    tmp_path,
                    bot_token=BOT,
                    chat_id=CHAT,
                )

        assert "https://example.com" in called

    @pytest.mark.asyncio
    async def test_routes_screenshot_no_url_sends_usage(self, tmp_path: Path) -> None:
        sent = []

        def _fake_send(msg, reply_to=None, *, bot_token, chat_id):
            sent.append(msg)

        with patch("adjutant.messaging.telegram.send.msg_send_text", _fake_send):
            with patch("adjutant.messaging.dispatch._check_rate_limit", return_value=True):
                await dispatch_message(
                    "/screenshot", 1, CHAT, tmp_path, bot_token=BOT, chat_id=CHAT
                )

        assert any("url" in m.lower() or "example" in m.lower() for m in sent)

    @pytest.mark.asyncio
    async def test_routes_search_no_query_sends_usage(self, tmp_path: Path) -> None:
        sent = []

        def _fake_send(msg, reply_to=None, *, bot_token, chat_id):
            sent.append(msg)

        with patch("adjutant.messaging.telegram.send.msg_send_text", _fake_send):
            with patch("adjutant.messaging.dispatch._check_rate_limit", return_value=True):
                await dispatch_message("/search", 1, CHAT, tmp_path, bot_token=BOT, chat_id=CHAT)

        assert any("query" in m.lower() for m in sent)


# ---------------------------------------------------------------------------
# dispatch_photo — authorization
# ---------------------------------------------------------------------------


class TestDispatchPhoto:
    @pytest.mark.asyncio
    async def test_rejects_unauthorized_photo_sender(self, tmp_path: Path) -> None:
        handle_called = []

        async def mock_handle(*args, **kwargs):
            handle_called.append(True)

        with patch("adjutant.messaging.telegram.photos.tg_handle_photo", mock_handle):
            await dispatch_photo("evil_user", 1, "file123", tmp_path, bot_token=BOT, chat_id=CHAT)

        assert not handle_called

    @pytest.mark.asyncio
    async def test_authorized_photo_routes_to_handler(self, tmp_path: Path) -> None:
        handle_called = []

        async def mock_handle(
            from_id, message_id, file_id, caption, *, bot_token, chat_id, adj_dir
        ):
            handle_called.append((from_id, file_id))

        with patch("adjutant.messaging.telegram.photos.tg_handle_photo", mock_handle):
            await dispatch_photo(
                CHAT, 1, "file123", tmp_path, bot_token=BOT, chat_id=CHAT, caption="nice"
            )

        assert len(handle_called) == 1
        assert handle_called[0] == (CHAT, "file123")
