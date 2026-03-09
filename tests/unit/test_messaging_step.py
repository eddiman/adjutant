"""Tests for src/adjutant/setup/steps/messaging.py"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from adjutant.setup.steps.messaging import (
    _read_env_cred,
    _validate_token,
    step_messaging,
)


class TestReadEnvCred:
    def test_returns_value(self, tmp_path: Path) -> None:
        env = tmp_path / ".env"
        env.write_text("TELEGRAM_BOT_TOKEN=12345:abc\n")
        assert _read_env_cred(env, "TELEGRAM_BOT_TOKEN") == "12345:abc"

    def test_strips_quotes(self, tmp_path: Path) -> None:
        env = tmp_path / ".env"
        env.write_text('TELEGRAM_BOT_TOKEN="12345:abc"\n')
        assert _read_env_cred(env, "TELEGRAM_BOT_TOKEN") == "12345:abc"

    def test_returns_empty_when_key_missing(self, tmp_path: Path) -> None:
        env = tmp_path / ".env"
        env.write_text("OTHER_KEY=value\n")
        assert _read_env_cred(env, "TELEGRAM_BOT_TOKEN") == ""

    def test_returns_empty_when_file_missing(self, tmp_path: Path) -> None:
        assert _read_env_cred(tmp_path / ".env", "TELEGRAM_BOT_TOKEN") == ""


class TestValidateToken:
    def test_returns_username_on_success(self) -> None:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": True, "result": {"username": "mybot"}}
        mock_session = MagicMock()
        mock_session.get.return_value = mock_resp
        with patch(
            "adjutant.setup.steps.messaging._get_http_client",
            return_value=mock_session,
        ):
            result = _validate_token("12345:abc")
        assert result == "mybot"

    def test_returns_none_on_error_response(self) -> None:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": False}
        mock_session = MagicMock()
        mock_session.get.return_value = mock_resp
        with patch(
            "adjutant.setup.steps.messaging._get_http_client",
            return_value=mock_session,
        ):
            result = _validate_token("bad_token")
        assert result is None

    def test_returns_none_on_exception(self) -> None:
        with patch(
            "adjutant.setup.steps.messaging._get_http_client",
            side_effect=Exception("network error"),
        ):
            result = _validate_token("12345:abc")
        assert result is None


class TestStepMessaging:
    def test_skips_when_user_declines(self, tmp_path: Path, capsys) -> None:
        with patch("builtins.input", return_value="n"):
            result = step_messaging(tmp_path)
        assert result is True

    def test_uses_existing_credentials_when_valid(self, tmp_path: Path, capsys) -> None:
        env = tmp_path / ".env"
        env.write_text("TELEGRAM_BOT_TOKEN=12345:abc\nTELEGRAM_CHAT_ID=999\n")
        # User says Y to set up, then N to re-configure
        responses = iter(["y", "n"])
        with patch("builtins.input", side_effect=lambda: next(responses)):
            result = step_messaging(tmp_path)
        assert result is True

    def test_writes_env_file_on_success(self, tmp_path: Path, capsys) -> None:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": True, "result": {"username": "testbot"}}
        mock_session = MagicMock()
        mock_session.get.return_value = mock_resp
        # Y to setup, N (have token), paste token, Y ready, auto-detect fails, manual chat_id
        responses = iter(["y", "y", "12345:ValidToken", "y", "999"])
        with patch("builtins.input", side_effect=lambda: next(responses)):
            with patch(
                "adjutant.setup.steps.messaging._get_http_client",
                return_value=mock_session,
            ):
                # auto-detect returns None so we fall to manual
                with patch(
                    "adjutant.setup.steps.messaging._auto_detect_chat_id",
                    return_value=None,
                ):
                    result = step_messaging(tmp_path)
        assert result is True
        env = tmp_path / ".env"
        assert env.is_file()
        content = env.read_text()
        assert "12345:ValidToken" in content
        assert "999" in content

    def test_dry_run_does_not_write_env(self, tmp_path: Path, capsys) -> None:
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"ok": True, "result": {"username": "bot"}}
        mock_session = MagicMock()
        mock_session.get.return_value = mock_resp
        # Y setup, Y have token, paste token, Y ready
        responses = iter(["y", "y", "12345:Token", "y"])
        with patch("builtins.input", side_effect=lambda: next(responses)):
            with patch(
                "adjutant.setup.steps.messaging._get_http_client",
                return_value=mock_session,
            ):
                with patch(
                    "adjutant.setup.steps.messaging._auto_detect_chat_id",
                    return_value="777",
                ):
                    result = step_messaging(tmp_path, dry_run=True)
        assert result is True
        assert not (tmp_path / ".env").is_file()
