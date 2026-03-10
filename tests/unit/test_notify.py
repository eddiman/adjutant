"""Tests for src/adjutant/messaging/telegram/notify.py"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from adjutant.messaging.telegram.notify import (
    BudgetExceededError,
    _count_file,
    _read_count,
    _sanitize,
    _write_count,
    get_max_per_day,
    main,
    send_notify,
)


# ---------------------------------------------------------------------------
# _sanitize
# ---------------------------------------------------------------------------


class TestSanitize:
    def test_strips_control_chars(self) -> None:
        raw = "hello\x00world\x07!\x1b[31mred\x7f"
        result = _sanitize(raw)
        assert result == "helloworld![31mred"

    def test_preserves_newlines_and_tabs(self) -> None:
        assert "\n" in _sanitize("line1\nline2")
        assert "\t" in _sanitize("col1\tcol2")

    def test_clamps_to_4096_chars(self) -> None:
        long_msg = "a" * 5000
        result = _sanitize(long_msg)
        assert len(result) == 4096

    def test_normal_message_unchanged(self) -> None:
        msg = "Hello, world! This is a normal message."
        assert _sanitize(msg) == msg

    def test_empty_string(self) -> None:
        assert _sanitize("") == ""

    def test_unicode_preserved(self) -> None:
        msg = "こんにちは 🌍"
        assert _sanitize(msg) == msg


# ---------------------------------------------------------------------------
# count file helpers
# ---------------------------------------------------------------------------


class TestCountHelpers:
    def test_count_file_uses_today(self, tmp_path: Path) -> None:
        d = date(2024, 3, 15)
        f = _count_file(tmp_path, d)
        assert f.name == "notify_count_2024-03-15.txt"

    def test_read_count_returns_zero_when_missing(self, tmp_path: Path) -> None:
        assert _read_count(tmp_path) == 0

    def test_read_count_returns_stored_value(self, tmp_path: Path) -> None:
        d = date(2024, 3, 15)
        _count_file(tmp_path, d).write_text("2")
        assert _read_count(tmp_path, d) == 2

    def test_read_count_returns_zero_on_invalid(self, tmp_path: Path) -> None:
        d = date(2024, 3, 15)
        _count_file(tmp_path, d).write_text("not-a-number")
        assert _read_count(tmp_path, d) == 0

    def test_write_count_creates_directory(self, tmp_path: Path) -> None:
        state_dir = tmp_path / "state"
        d = date(2024, 3, 15)
        _write_count(state_dir, 5, d)
        assert _count_file(state_dir, d).read_text() == "5"

    def test_write_count_overwrites_existing(self, tmp_path: Path) -> None:
        d = date(2024, 3, 15)
        _write_count(tmp_path, 1, d)
        _write_count(tmp_path, 3, d)
        assert _count_file(tmp_path, d).read_text() == "3"


# ---------------------------------------------------------------------------
# get_max_per_day
# ---------------------------------------------------------------------------


class TestGetMaxPerDay:
    def _make_config(self, tmp_path: Path, max_per_day: int = 3) -> Path:
        cfg = tmp_path / "adjutant.yaml"
        cfg.write_text(f"notifications:\n  max_per_day: {max_per_day}\ninstance:\n  name: test\n")
        return tmp_path

    def test_reads_value_from_config(self, tmp_path: Path) -> None:
        adj_dir = self._make_config(tmp_path, max_per_day=5)
        assert get_max_per_day(adj_dir) == 5

    def test_default_is_3(self, tmp_path: Path) -> None:
        # write a minimal config without max_per_day
        cfg = tmp_path / "adjutant.yaml"
        cfg.write_text("instance:\n  name: test\n")
        assert get_max_per_day(tmp_path) == 3


# ---------------------------------------------------------------------------
# send_notify
# ---------------------------------------------------------------------------


class TestSendNotify:
    def _setup(self, tmp_path: Path, max_per_day: int = 3) -> tuple[Path, Path]:
        cfg = tmp_path / "adjutant.yaml"
        cfg.write_text(f"notifications:\n  max_per_day: {max_per_day}\ninstance:\n  name: test\n")
        env_path = tmp_path / ".env"
        env_path.write_text("TELEGRAM_BOT_TOKEN=tok\nTELEGRAM_CHAT_ID=456\n")
        (tmp_path / "state").mkdir()
        return tmp_path, env_path

    def test_sends_message_and_increments_count(self, tmp_path: Path) -> None:
        adj_dir, env_path = self._setup(tmp_path)
        d = date(2024, 1, 1)

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_client = MagicMock()
        mock_client.post.return_value = mock_resp

        with patch("adjutant.messaging.telegram.notify.get_client", return_value=mock_client):
            count, max_pd = send_notify("hello", adj_dir, env_path=env_path, today=d)

        assert count == 1
        assert max_pd == 3
        mock_client.post.assert_called_once()

    def test_raises_budget_exceeded_when_at_limit(self, tmp_path: Path) -> None:
        adj_dir, env_path = self._setup(tmp_path, max_per_day=2)
        d = date(2024, 1, 1)
        _write_count(adj_dir / "state", 2, d)

        with pytest.raises(BudgetExceededError) as exc_info:
            send_notify("hello", adj_dir, env_path=env_path, today=d)

        assert exc_info.value.count == 2
        assert exc_info.value.max_count == 2

    def test_raises_value_error_on_empty_message(self, tmp_path: Path) -> None:
        adj_dir, env_path = self._setup(tmp_path)
        with pytest.raises(ValueError, match="empty"):
            send_notify("\x00\x01", adj_dir, env_path=env_path)

    def test_no_parse_mode_in_payload(self, tmp_path: Path) -> None:
        """notify.sh does NOT set parse_mode (unlike reply.sh)."""
        adj_dir, env_path = self._setup(tmp_path)
        d = date(2024, 1, 1)

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_client = MagicMock()
        mock_client.post.return_value = mock_resp

        with patch("adjutant.messaging.telegram.notify.get_client", return_value=mock_client):
            send_notify("msg", adj_dir, env_path=env_path, today=d)

        payload = mock_client.post.call_args[1]["json_data"]
        assert "parse_mode" not in payload

    def test_count_persists_across_calls(self, tmp_path: Path) -> None:
        adj_dir, env_path = self._setup(tmp_path, max_per_day=5)
        d = date(2024, 1, 1)

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_client = MagicMock()
        mock_client.post.return_value = mock_resp

        with patch("adjutant.messaging.telegram.notify.get_client", return_value=mock_client):
            c1, _ = send_notify("first", adj_dir, env_path=env_path, today=d)
            c2, _ = send_notify("second", adj_dir, env_path=env_path, today=d)

        assert c1 == 1
        assert c2 == 2


# ---------------------------------------------------------------------------
# BudgetExceededError
# ---------------------------------------------------------------------------


class TestBudgetExceededError:
    def test_message_format(self) -> None:
        err = BudgetExceededError(3, 3)
        assert "3/3" in str(err)
        assert err.count == 3
        assert err.max_count == 3


# ---------------------------------------------------------------------------
# main (CLI)
# ---------------------------------------------------------------------------


class TestMain:
    def _setup(self, tmp_path: Path) -> Path:
        cfg = tmp_path / "adjutant.yaml"
        cfg.write_text("notifications:\n  max_per_day: 3\ninstance:\n  name: test\n")
        env_path = tmp_path / ".env"
        env_path.write_text("TELEGRAM_BOT_TOKEN=tok\nTELEGRAM_CHAT_ID=456\n")
        (tmp_path / "state").mkdir()
        return tmp_path

    def test_returns_1_on_no_args(self) -> None:
        rc = main([])
        assert rc == 1

    def test_returns_1_when_adj_dir_not_set(self) -> None:
        env = {k: v for k, v in os.environ.items() if k != "ADJ_DIR"}
        with patch.dict(os.environ, env, clear=True):
            rc = main(["hello"])
        assert rc == 1

    def test_returns_0_on_success(self, tmp_path: Path) -> None:
        adj_dir = self._setup(tmp_path)

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_client = MagicMock()
        mock_client.post.return_value = mock_resp

        with (
            patch.dict(os.environ, {"ADJ_DIR": str(adj_dir)}),
            patch("adjutant.messaging.telegram.notify.get_client", return_value=mock_client),
        ):
            rc = main(["hello from test"])

        assert rc == 0

    def test_returns_1_on_budget_exceeded(self, tmp_path: Path) -> None:
        adj_dir = self._setup(tmp_path)
        d = date.today()
        _write_count(adj_dir / "state", 3, d)

        with patch.dict(os.environ, {"ADJ_DIR": str(adj_dir)}):
            rc = main(["should be blocked"])

        assert rc == 1
