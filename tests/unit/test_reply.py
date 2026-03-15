"""Tests for src/adjutant/messaging/telegram/reply.py"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from adjutant.messaging.telegram.reply import _sanitize, send_reply, main


class TestSanitize:
    def test_strips_control_chars(self) -> None:
        # NUL, BEL, ESC, DEL
        raw = "hello\x00world\x07!\x1b[31mred\x7f"
        result = _sanitize(raw)
        assert result == "helloworld![31mred"

    def test_preserves_newlines_and_tabs(self) -> None:
        # 0x0A (newline) and 0x09 (tab) should be kept
        assert "\n" in _sanitize("line1\nline2")
        assert "\t" in _sanitize("col1\tcol2")

    def test_clamps_to_4000_chars(self) -> None:
        long_msg = "a" * 5000
        result = _sanitize(long_msg)
        assert len(result) == 4000

    def test_normal_message_unchanged(self) -> None:
        msg = "Hello, world! This is a normal message."
        assert _sanitize(msg) == msg

    def test_empty_string(self) -> None:
        assert _sanitize("") == ""

    def test_unicode_preserved(self) -> None:
        msg = "こんにちは 🌍"
        assert _sanitize(msg) == msg


class TestSendReply:
    def _make_env(self, tmp_path: Path) -> Path:
        env = tmp_path / ".env"
        env.write_text("TELEGRAM_BOT_TOKEN=test-token\nTELEGRAM_CHAT_ID=12345\n")
        return env

    def test_posts_to_telegram_api(self, tmp_path: Path) -> None:
        env_path = self._make_env(tmp_path)
        mock_client = MagicMock()
        mock_client.post.return_value = {"ok": True}

        with patch("adjutant.messaging.telegram.reply.get_client", return_value=mock_client):
            send_reply("Hello!", env_path=str(env_path))

        mock_client.post.assert_called_once()
        call_kwargs = mock_client.post.call_args
        url = call_kwargs[0][0]
        payload = call_kwargs[1]["json_data"]

        assert "test-token" in url
        assert "sendMessage" in url
        assert payload["chat_id"] == "12345"
        assert payload["text"] == "Hello!"
        assert payload["parse_mode"] == "Markdown"

    def test_includes_reply_to_when_set(self, tmp_path: Path) -> None:
        env_path = self._make_env(tmp_path)
        mock_client = MagicMock()
        mock_client.post.return_value = {"ok": True}

        with patch("adjutant.messaging.telegram.reply.get_client", return_value=mock_client):
            send_reply("Hi", reply_to_message_id=99, env_path=str(env_path))

        payload = mock_client.post.call_args[1]["json_data"]
        assert payload["reply_to_message_id"] == 99

    def test_omits_reply_to_when_none(self, tmp_path: Path) -> None:
        env_path = self._make_env(tmp_path)
        mock_client = MagicMock()
        mock_client.post.return_value = {"ok": True}

        with patch("adjutant.messaging.telegram.reply.get_client", return_value=mock_client):
            send_reply("Hi", env_path=str(env_path))

        payload = mock_client.post.call_args[1]["json_data"]
        assert "reply_to_message_id" not in payload

    def test_raises_on_empty_message_after_sanitise(self, tmp_path: Path) -> None:
        env_path = self._make_env(tmp_path)
        with pytest.raises(ValueError, match="empty"):
            send_reply("\x00\x01\x02", env_path=str(env_path))

    def test_raises_on_missing_credentials(self, tmp_path: Path) -> None:
        # No .env file created
        env_path = tmp_path / ".env"
        with pytest.raises(RuntimeError):
            send_reply("Hello", env_path=str(env_path))

    def test_raises_on_http_error(self, tmp_path: Path) -> None:
        """HTTP errors should propagate via HttpClientError."""
        from adjutant.lib.http import HttpClientError

        env_path = self._make_env(tmp_path)
        mock_client = MagicMock()
        mock_client.post.side_effect = HttpClientError("400 Bad Request", status_code=400)

        with (
            patch("adjutant.messaging.telegram.reply.get_client", return_value=mock_client),
            pytest.raises(Exception),
        ):
            send_reply("msg", env_path=str(env_path))


class TestMain:
    def _make_env(self, tmp_path: Path) -> str:
        env = tmp_path / ".env"
        env.write_text("TELEGRAM_BOT_TOKEN=tok\nTELEGRAM_CHAT_ID=456\n")
        return str(env)

    def test_returns_0_on_success(self, tmp_path: Path) -> None:
        env_path = self._make_env(tmp_path)
        mock_client = MagicMock()
        mock_client.post.return_value = {"ok": True}

        with patch("adjutant.messaging.telegram.reply.get_client", return_value=mock_client):
            with patch(
                "adjutant.messaging.telegram.reply.require_telegram_credentials",
                return_value=("tok", "456"),
            ):
                rc = main(["Hello from test"])
        assert rc == 0

    def test_returns_1_on_no_args(self) -> None:
        rc = main([])
        assert rc == 1

    def test_returns_1_on_error(self, tmp_path: Path) -> None:
        # No .env so credentials will fail
        env_path = tmp_path / ".env"
        with patch(
            "adjutant.messaging.telegram.reply.require_telegram_credentials",
            side_effect=RuntimeError("no creds"),
        ):
            rc = main(["oops"])
        assert rc == 1
