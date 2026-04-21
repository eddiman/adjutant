"""Tests for src/adjutant/messaging/telegram/photos.py"""

from __future__ import annotations

import asyncio
import hashlib
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from adjutant.messaging.telegram.photos import (
    _VISION_DISABLED_MESSAGE,
    _photo_dedup_cleanup,
    _photo_is_duplicate,
    tg_handle_photo,
    tg_download_photo,
)


BOT = "123:testtoken"


class TestPhotoDedupCleanup:
    def test_removes_old_markers(self, tmp_path: Path) -> None:
        marker = tmp_path / "old_marker"
        marker.write_text("x")
        # Set mtime to 120 seconds ago
        old_time = time.time() - 120
        import os

        os.utime(str(marker), (old_time, old_time))
        _photo_dedup_cleanup(tmp_path)
        assert not marker.exists()

    def test_keeps_recent_markers(self, tmp_path: Path) -> None:
        marker = tmp_path / "new_marker"
        marker.write_text("x")
        # mtime is now (default)
        _photo_dedup_cleanup(tmp_path)
        assert marker.exists()

    def test_handles_empty_dir(self, tmp_path: Path) -> None:
        # Should not raise
        _photo_dedup_cleanup(tmp_path)

    def test_handles_missing_dir(self, tmp_path: Path) -> None:
        # Should not raise
        _photo_dedup_cleanup(tmp_path / "nonexistent")


class TestPhotoIsDuplicate:
    def test_first_check_returns_false_and_creates_marker(self, tmp_path: Path) -> None:
        file_id = "abc123"
        result = _photo_is_duplicate(file_id, tmp_path)
        assert result is False
        digest = hashlib.md5(file_id.encode()).hexdigest()
        assert (tmp_path / digest).exists()

    def test_second_check_returns_true(self, tmp_path: Path) -> None:
        file_id = "abc123"
        _photo_is_duplicate(file_id, tmp_path)  # first call
        result = _photo_is_duplicate(file_id, tmp_path)  # second call
        assert result is True

    def test_different_file_ids_not_duplicate(self, tmp_path: Path) -> None:
        _photo_is_duplicate("id1", tmp_path)
        result = _photo_is_duplicate("id2", tmp_path)
        assert result is False

    def test_creates_dedup_dir_if_missing(self, tmp_path: Path) -> None:
        dedup_dir = tmp_path / "photo_dedup"
        assert not dedup_dir.exists()
        _photo_is_duplicate("someid", dedup_dir)
        assert dedup_dir.exists()


class TestTgDownloadPhoto:
    def test_returns_none_when_get_file_fails(self, tmp_path: Path) -> None:
        mock_client = MagicMock()
        mock_client.get.side_effect = Exception("network error")
        with patch("adjutant.lib.http.get_client", return_value=mock_client):
            result = tg_download_photo("fid", bot_token=BOT, adj_dir=tmp_path)
        assert result is None

    def test_returns_none_when_ok_false(self, tmp_path: Path) -> None:
        mock_client = MagicMock()
        mock_client.get.return_value = {"ok": False}
        with patch("adjutant.lib.http.get_client", return_value=mock_client):
            result = tg_download_photo("fid", bot_token=BOT, adj_dir=tmp_path)
        assert result is None

    def test_returns_none_when_no_file_path(self, tmp_path: Path) -> None:
        mock_client = MagicMock()
        mock_client.get.return_value = {"ok": True, "result": {"file_path": ""}}
        with patch("adjutant.lib.http.get_client", return_value=mock_client):
            result = tg_download_photo("fid", bot_token=BOT, adj_dir=tmp_path)
        assert result is None

    def test_returns_path_on_success(self, tmp_path: Path) -> None:
        mock_client = MagicMock()
        mock_client.get.return_value = {
            "ok": True,
            "result": {"file_path": "photos/file.jpg"},
        }
        # Mock the httpx download
        mock_response = MagicMock()
        mock_response.content = b"fake image data"
        mock_response.raise_for_status = MagicMock()

        mock_http_client = MagicMock()
        mock_http_client.get.return_value = mock_response
        mock_http_client.__enter__ = MagicMock(return_value=mock_http_client)
        mock_http_client.__exit__ = MagicMock(return_value=False)

        with patch("adjutant.lib.http.get_client", return_value=mock_client):
            with patch("httpx.Client", return_value=mock_http_client):
                result = tg_download_photo("fid", bot_token=BOT, adj_dir=tmp_path)

        assert result is not None
        assert result.suffix == ".jpg"
        assert result.parent == tmp_path / "photos"

    def test_uses_jpg_extension_when_no_extension(self, tmp_path: Path) -> None:
        mock_client = MagicMock()
        mock_client.get.return_value = {
            "ok": True,
            "result": {"file_path": "photos/filwithoutdot"},
        }
        mock_response = MagicMock()
        mock_response.content = b"data"
        mock_response.raise_for_status = MagicMock()
        mock_http_client = MagicMock()
        mock_http_client.get.return_value = mock_response
        mock_http_client.__enter__ = MagicMock(return_value=mock_http_client)
        mock_http_client.__exit__ = MagicMock(return_value=False)

        with patch("adjutant.lib.http.get_client", return_value=mock_client):
            with patch("httpx.Client", return_value=mock_http_client):
                result = tg_download_photo("fid", bot_token=BOT, adj_dir=tmp_path)

        assert result is not None
        assert result.suffix == ".jpg"

    def test_returns_none_when_download_fails(self, tmp_path: Path) -> None:
        mock_client = MagicMock()
        mock_client.get.return_value = {
            "ok": True,
            "result": {"file_path": "photos/file.jpg"},
        }
        mock_http_client = MagicMock()
        mock_http_client.get.side_effect = Exception("download failed")
        mock_http_client.__enter__ = MagicMock(return_value=mock_http_client)
        mock_http_client.__exit__ = MagicMock(return_value=False)

        with patch("adjutant.lib.http.get_client", return_value=mock_client):
            with patch("httpx.Client", return_value=mock_http_client):
                result = tg_download_photo("fid", bot_token=BOT, adj_dir=tmp_path)

        assert result is None


class TestTgHandlePhoto:
    @pytest.mark.asyncio
    async def test_returns_disabled_message_when_vision_feature_off(self, tmp_path: Path) -> None:
        sent: list[str] = []

        class _Config:
            def is_feature_enabled(self, feature: str) -> bool:
                return False

        def _fake_send(msg, reply_to=None, *, bot_token, chat_id):
            sent.append(msg)

        with (
            patch("adjutant.core.config.load_typed_config", return_value=_Config()),
            patch("adjutant.messaging.telegram.send.msg_send_text", _fake_send),
            patch("adjutant.messaging.telegram.send.msg_react"),
        ):
            await tg_handle_photo(
                "999",
                42,
                "file123",
                "",
                bot_token=BOT,
                chat_id="999",
                adj_dir=tmp_path,
            )

        assert sent == [_VISION_DISABLED_MESSAGE]
        assert not (tmp_path / "photos").exists()

    @pytest.mark.asyncio
    async def test_sends_model_error_reply_from_vision(self, tmp_path: Path) -> None:
        sent: list[str] = []
        tasks: list[asyncio.Task[None]] = []

        class _Config:
            def is_feature_enabled(self, feature: str) -> bool:
                return True

        photo_path = tmp_path / "photos" / "saved.jpg"
        photo_path.parent.mkdir(parents=True)
        photo_path.write_bytes(b"img")
        original_create_task = asyncio.create_task

        async def _fake_to_thread(func, /, *args, **kwargs):
            return func(*args, **kwargs)

        def _fake_send(msg, reply_to=None, *, bot_token, chat_id):
            sent.append(msg)

        def _capture_task(coro):
            task = original_create_task(coro)
            tasks.append(task)
            return task

        with (
            patch("adjutant.core.config.load_typed_config", return_value=_Config()),
            patch("asyncio.to_thread", side_effect=_fake_to_thread),
            patch("asyncio.create_task", side_effect=_capture_task),
            patch("adjutant.messaging.telegram.photos.tg_download_photo", return_value=photo_path),
            patch(
                "adjutant.capabilities.vision.vision.run_vision",
                return_value="The configured vision model `github-copilot/gpt-5.4-mini` isn't available.",
            ),
            patch("adjutant.messaging.telegram.send.msg_send_text", _fake_send),
            patch("adjutant.messaging.telegram.send.msg_react"),
            patch("adjutant.messaging.telegram.send.msg_typing_start"),
            patch("adjutant.messaging.telegram.send.msg_typing_stop"),
            patch("adjutant.messaging.telegram.chat.run_chat", new=AsyncMock()),
        ):
            await tg_handle_photo(
                "999",
                42,
                "file123",
                "",
                bot_token=BOT,
                chat_id="999",
                adj_dir=tmp_path,
            )
            await asyncio.gather(*tasks)

        assert sent == [
            "The configured vision model `github-copilot/gpt-5.4-mini` isn't available."
        ]
