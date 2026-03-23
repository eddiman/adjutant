"""Tests for src/adjutant/messaging/telegram/chat.py"""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from adjutant.core.backend import BackendNotFoundError, LLMResult
from adjutant.messaging.telegram.chat import (
    SESSION_TIMEOUT,
    get_model,
    get_session_id,
    run_chat,
    save_session,
    touch_session,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _llm_result(text="OK", session_id=None, error_type=None, returncode=0, timed_out=False):
    return LLMResult(
        text=text, session_id=session_id, error_type=error_type,
        returncode=returncode, timed_out=timed_out,
    )


def _mock_backend(result=None):
    backend = MagicMock()
    backend.run = AsyncMock(return_value=result or _llm_result())
    return backend


# ---------------------------------------------------------------------------
# get_model
# ---------------------------------------------------------------------------


class TestGetModel:
    def test_reads_model_from_file(self, tmp_path: Path) -> None:
        state = tmp_path / "state"
        state.mkdir()
        (state / "telegram_model.txt").write_text("anthropic/claude-opus-4-5\n")
        assert get_model(tmp_path) == "anthropic/claude-opus-4-5"

    def test_falls_back_to_default_when_missing(self, tmp_path: Path) -> None:
        assert get_model(tmp_path) == "anthropic/claude-haiku-4-5"

    def test_falls_back_when_file_is_empty(self, tmp_path: Path) -> None:
        state = tmp_path / "state"
        state.mkdir()
        (state / "telegram_model.txt").write_text("   \n")
        assert get_model(tmp_path) == "anthropic/claude-haiku-4-5"


# ---------------------------------------------------------------------------
# get_session_id
# ---------------------------------------------------------------------------


class TestGetSessionId:
    def _write_session(self, tmp_path: Path, session_id: str, age_seconds: int = 0) -> None:
        state = tmp_path / "state"
        state.mkdir(exist_ok=True)
        epoch = int(time.time()) - age_seconds
        data = {"session_id": session_id, "last_message_epoch": epoch}
        (state / "telegram_session.json").write_text(json.dumps(data))

    def test_returns_session_when_recent(self, tmp_path: Path) -> None:
        self._write_session(tmp_path, "sess123", age_seconds=60)
        assert get_session_id(tmp_path) == "sess123"

    def test_returns_none_when_expired(self, tmp_path: Path) -> None:
        self._write_session(tmp_path, "sess123", age_seconds=SESSION_TIMEOUT + 10)
        assert get_session_id(tmp_path) is None

    def test_returns_none_when_no_file(self, tmp_path: Path) -> None:
        assert get_session_id(tmp_path) is None

    def test_returns_none_when_corrupt_json(self, tmp_path: Path) -> None:
        state = tmp_path / "state"
        state.mkdir()
        (state / "telegram_session.json").write_text("{bad json}")
        assert get_session_id(tmp_path) is None

    def test_returns_none_when_no_session_id_key(self, tmp_path: Path) -> None:
        state = tmp_path / "state"
        state.mkdir()
        data = {"last_message_epoch": int(time.time()) - 10}
        (state / "telegram_session.json").write_text(json.dumps(data))
        assert get_session_id(tmp_path) is None


# ---------------------------------------------------------------------------
# save_session / touch_session
# ---------------------------------------------------------------------------


class TestSaveSession:
    def test_writes_session_file(self, tmp_path: Path) -> None:
        save_session("sid_abc", tmp_path)
        session_file = tmp_path / "state" / "telegram_session.json"
        assert session_file.is_file()
        data = json.loads(session_file.read_text())
        assert data["session_id"] == "sid_abc"
        assert "last_message_epoch" in data
        assert "last_message_at" in data

    def test_creates_state_dir(self, tmp_path: Path) -> None:
        save_session("sid_abc", tmp_path)
        assert (tmp_path / "state").is_dir()


class TestTouchSession:
    def test_updates_timestamp(self, tmp_path: Path) -> None:
        save_session("sid_abc", tmp_path)
        session_file = tmp_path / "state" / "telegram_session.json"
        old_epoch = json.loads(session_file.read_text())["last_message_epoch"]

        time.sleep(0.01)
        touch_session(tmp_path)
        new_epoch = json.loads(session_file.read_text())["last_message_epoch"]
        assert new_epoch >= old_epoch

    def test_noop_when_no_session_file(self, tmp_path: Path) -> None:
        # Should not raise
        touch_session(tmp_path)


# ---------------------------------------------------------------------------
# run_chat
# ---------------------------------------------------------------------------


class TestRunChat:
    @pytest.mark.asyncio
    async def test_returns_reply_on_success(self, tmp_path: Path) -> None:
        backend = _mock_backend(_llm_result(text="hello", session_id="sid1"))
        with patch("adjutant.core.backend.get_backend", return_value=backend):
            reply = await run_chat("hi", tmp_path)
        assert reply == "hello"

    @pytest.mark.asyncio
    async def test_saves_new_session(self, tmp_path: Path) -> None:
        backend = _mock_backend(_llm_result(text="reply", session_id="new_sid"))
        with patch("adjutant.core.backend.get_backend", return_value=backend):
            await run_chat("hello", tmp_path)

        session_file = tmp_path / "state" / "telegram_session.json"
        assert session_file.is_file()
        data = json.loads(session_file.read_text())
        assert data["session_id"] == "new_sid"

    @pytest.mark.asyncio
    async def test_returns_error_on_backend_not_found(self, tmp_path: Path) -> None:
        backend = MagicMock()
        backend.run = AsyncMock(side_effect=BackendNotFoundError("not found"))
        with patch("adjutant.core.backend.get_backend", return_value=backend):
            reply = await run_chat("hi", tmp_path)
        assert "not available" in reply.lower()

    @pytest.mark.asyncio
    async def test_returns_timeout_message_for_anthropic_model(self, tmp_path: Path) -> None:
        state = tmp_path / "state"
        state.mkdir()
        (state / "telegram_model.txt").write_text("anthropic/claude-haiku-4-5")

        backend = _mock_backend(_llm_result(returncode=-1, timed_out=True))
        with patch("adjutant.core.backend.get_backend", return_value=backend):
            reply = await run_chat("hi", tmp_path)

        assert "timed out" in reply.lower() or "timeout" in reply.lower()
        assert "anthropic" in reply.lower()

    @pytest.mark.asyncio
    async def test_returns_generic_timeout_for_non_anthropic(self, tmp_path: Path) -> None:
        state = tmp_path / "state"
        state.mkdir()
        (state / "telegram_model.txt").write_text("openai/gpt-4")

        backend = _mock_backend(_llm_result(returncode=-1, timed_out=True))
        with patch("adjutant.core.backend.get_backend", return_value=backend):
            reply = await run_chat("hi", tmp_path)

        assert "timed out" in reply.lower() or "timeout" in reply.lower()

    @pytest.mark.asyncio
    async def test_returns_model_not_found_message(self, tmp_path: Path) -> None:
        backend = _mock_backend(_llm_result(error_type="model_not_found"))
        with patch("adjutant.core.backend.get_backend", return_value=backend):
            reply = await run_chat("hi", tmp_path)
        assert "no longer available" in reply.lower() or "model" in reply.lower()

    @pytest.mark.asyncio
    async def test_returns_fallback_on_empty_reply(self, tmp_path: Path) -> None:
        backend = _mock_backend(_llm_result(text=""))
        with patch("adjutant.core.backend.get_backend", return_value=backend):
            reply = await run_chat("hi", tmp_path)
        assert "didn't get a response" in reply.lower() or "went wrong" in reply.lower()

    @pytest.mark.asyncio
    async def test_uses_existing_session_when_fresh(self, tmp_path: Path) -> None:
        state = tmp_path / "state"
        state.mkdir()
        session_data = {
            "session_id": "existing_sid",
            "last_message_epoch": int(time.time()) - 10,
        }
        (state / "telegram_session.json").write_text(json.dumps(session_data))

        backend = _mock_backend(_llm_result(text="reply", session_id="existing_sid"))
        with patch("adjutant.core.backend.get_backend", return_value=backend):
            await run_chat("hello", tmp_path)

        # Verify session_id was passed to backend.run
        call_kwargs = backend.run.call_args[1]
        assert call_kwargs["session_id"] == "existing_sid"
