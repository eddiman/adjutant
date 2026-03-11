"""Tests for src/adjutant/messaging/telegram/listener.py

Focus on unit-testable helpers: _load_offset, _save_offset, _poll_once.
The main() polling loop is integration-level and not covered here.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from adjutant.messaging.telegram.listener import (
    _load_offset,
    _poll_once,
    _save_offset,
)


# ---------------------------------------------------------------------------
# _load_offset
# ---------------------------------------------------------------------------


class TestLoadOffset:
    def test_returns_zero_when_no_file(self, tmp_path: Path) -> None:
        assert _load_offset(tmp_path) == 0

    def test_reads_valid_offset(self, tmp_path: Path) -> None:
        state = tmp_path / "state"
        state.mkdir()
        (state / "telegram_offset").write_text("42\n")
        assert _load_offset(tmp_path) == 42

    def test_returns_zero_when_file_is_empty(self, tmp_path: Path) -> None:
        state = tmp_path / "state"
        state.mkdir()
        (state / "telegram_offset").write_text("  \n")
        assert _load_offset(tmp_path) == 0

    def test_returns_zero_and_resets_corrupt_file(self, tmp_path: Path) -> None:
        state = tmp_path / "state"
        state.mkdir()
        offset_file = state / "telegram_offset"
        offset_file.write_text("not_a_number\n")
        result = _load_offset(tmp_path)
        assert result == 0
        # File should be reset to "0\n"
        assert offset_file.read_text() == "0\n"

    def test_returns_zero_when_state_dir_missing(self, tmp_path: Path) -> None:
        # No state/ directory
        assert _load_offset(tmp_path) == 0


# ---------------------------------------------------------------------------
# _save_offset
# ---------------------------------------------------------------------------


class TestSaveOffset:
    def test_writes_offset_to_file(self, tmp_path: Path) -> None:
        state = tmp_path / "state"
        state.mkdir()
        _save_offset(tmp_path, 100)
        content = (state / "telegram_offset").read_text()
        assert content == "100\n"

    def test_overwrites_existing_offset(self, tmp_path: Path) -> None:
        state = tmp_path / "state"
        state.mkdir()
        (state / "telegram_offset").write_text("50\n")
        _save_offset(tmp_path, 99)
        assert (state / "telegram_offset").read_text() == "99\n"

    def test_handles_missing_state_dir_gracefully(self, tmp_path: Path) -> None:
        # State dir doesn't exist — should not raise
        _save_offset(tmp_path, 5)


# ---------------------------------------------------------------------------
# _poll_once
# ---------------------------------------------------------------------------


class TestPollOnce:
    @pytest.mark.asyncio
    async def test_returns_updates_on_ok_response(self) -> None:
        fake_updates = [{"update_id": 1, "message": {"text": "hi"}}]
        fake_client = MagicMock()
        fake_client.get = MagicMock(return_value={"ok": True, "result": fake_updates})

        with patch("adjutant.lib.http.get_client", return_value=fake_client):
            result = await _poll_once("fake_token", 0)

        assert result == fake_updates

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_updates(self) -> None:
        fake_client = MagicMock()
        fake_client.get = MagicMock(return_value={"ok": True, "result": []})

        with patch("adjutant.lib.http.get_client", return_value=fake_client):
            result = await _poll_once("fake_token", 0)

        assert result == []

    @pytest.mark.asyncio
    async def test_returns_none_when_ok_is_false(self) -> None:
        fake_client = MagicMock()
        fake_client.get = MagicMock(return_value={"ok": False})

        with patch("adjutant.lib.http.get_client", return_value=fake_client):
            result = await _poll_once("fake_token", 0)

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_exception(self) -> None:
        fake_client = MagicMock()
        fake_client.get = MagicMock(side_effect=ConnectionError("network down"))

        with patch("adjutant.lib.http.get_client", return_value=fake_client):
            result = await _poll_once("fake_token", 0)

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_response_is_not_dict(self) -> None:
        fake_client = MagicMock()
        fake_client.get = MagicMock(return_value=None)

        with patch("adjutant.lib.http.get_client", return_value=fake_client):
            result = await _poll_once("fake_token", 0)

        assert result is None

    @pytest.mark.asyncio
    async def test_uses_offset_in_request(self) -> None:
        fake_client = MagicMock()
        fake_client.get = MagicMock(return_value={"ok": True, "result": []})

        with patch("adjutant.lib.http.get_client", return_value=fake_client):
            await _poll_once("tok", 500)

        call_args = fake_client.get.call_args
        params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("params", {})
        # The second positional arg to client.get is params
        assert params.get("offset") == 500 or (
            len(call_args[0]) > 1 and call_args[0][1].get("offset") == 500
        )
