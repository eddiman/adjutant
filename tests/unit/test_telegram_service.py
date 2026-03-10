"""Tests for src/adjutant/messaging/telegram/service.py"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from adjutant.messaging.telegram.service import (
    _find_listener_pid,
    listener_restart,
    listener_start,
    listener_status,
    listener_stop,
    main,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_proc(pid: int) -> MagicMock:
    proc = MagicMock()
    proc.pid = pid
    return proc


# ---------------------------------------------------------------------------
# _find_listener_pid
# ---------------------------------------------------------------------------


class TestFindListenerPid:
    def test_returns_none_when_no_files_and_no_proc(self, tmp_path: Path) -> None:
        with patch("adjutant.messaging.telegram.service.find_by_cmdline", return_value=[]):
            result = _find_listener_pid(tmp_path)
        assert result is None

    def test_reads_lock_pid_when_alive(self, tmp_path: Path) -> None:
        state = tmp_path / "state"
        lockdir = state / "listener.lock"
        lockdir.mkdir(parents=True)
        (lockdir / "pid").write_text("1234")

        with patch("adjutant.messaging.telegram.service.pid_is_alive", return_value=True):
            with patch("adjutant.messaging.telegram.service.find_by_cmdline", return_value=[]):
                result = _find_listener_pid(tmp_path)

        assert result == 1234

    def test_skips_dead_lock_pid_and_falls_through(self, tmp_path: Path) -> None:
        state = tmp_path / "state"
        lockdir = state / "listener.lock"
        lockdir.mkdir(parents=True)
        (lockdir / "pid").write_text("9999")

        with patch("adjutant.messaging.telegram.service.pid_is_alive", return_value=False):
            with patch("adjutant.messaging.telegram.service.read_pid_file", return_value=None):
                with patch("adjutant.messaging.telegram.service.find_by_cmdline", return_value=[]):
                    result = _find_listener_pid(tmp_path)

        assert result is None

    def test_falls_back_to_pidfile(self, tmp_path: Path) -> None:
        state = tmp_path / "state"
        state.mkdir()
        (state / "telegram.pid").write_text("5678")

        with patch("adjutant.messaging.telegram.service.pid_is_alive", return_value=False):
            with patch("adjutant.messaging.telegram.service.read_pid_file", return_value=5678):
                with patch("adjutant.messaging.telegram.service.find_by_cmdline", return_value=[]):
                    result = _find_listener_pid(tmp_path)

        assert result == 5678

    def test_falls_back_to_psutil(self, tmp_path: Path) -> None:
        fake_proc = _make_proc(7777)
        with patch("adjutant.messaging.telegram.service.pid_is_alive", return_value=True):
            with patch(
                "adjutant.messaging.telegram.service.find_by_cmdline",
                return_value=[fake_proc],
            ):
                result = _find_listener_pid(tmp_path)

        assert result == 7777


# ---------------------------------------------------------------------------
# listener_status
# ---------------------------------------------------------------------------


class TestListenerStatus:
    def test_returns_running_when_pid_found(self, tmp_path: Path) -> None:
        with patch("adjutant.messaging.telegram.service._find_listener_pid", return_value=42):
            result = listener_status(tmp_path)
        assert "Running" in result
        assert "42" in result

    def test_returns_stopped_when_no_pid(self, tmp_path: Path) -> None:
        with patch("adjutant.messaging.telegram.service._find_listener_pid", return_value=None):
            result = listener_status(tmp_path)
        assert result == "Stopped"

    def test_syncs_pidfile_when_running(self, tmp_path: Path) -> None:
        state = tmp_path / "state"
        state.mkdir()
        with patch("adjutant.messaging.telegram.service._find_listener_pid", return_value=99):
            listener_status(tmp_path)
        pidfile = state / "telegram.pid"
        assert pidfile.is_file()
        assert pidfile.read_text().strip() == "99"


# ---------------------------------------------------------------------------
# listener_stop
# ---------------------------------------------------------------------------


class TestListenerStop:
    def test_stops_running_listener(self, tmp_path: Path) -> None:
        with patch("adjutant.messaging.telegram.service._find_listener_pid", return_value=1234):
            with patch("adjutant.messaging.telegram.service.kill_graceful") as mock_kill:
                with patch("adjutant.messaging.telegram.service.find_by_cmdline", return_value=[]):
                    result = listener_stop(tmp_path)

        mock_kill.assert_called_once_with(1234, timeout=5.0)
        assert "1234" in result

    def test_reports_not_running_when_no_pid(self, tmp_path: Path) -> None:
        with patch("adjutant.messaging.telegram.service._find_listener_pid", return_value=None):
            with patch("adjutant.messaging.telegram.service.find_by_cmdline", return_value=[]):
                result = listener_stop(tmp_path)
        assert result == "Not running"

    def test_kills_orphan_processes(self, tmp_path: Path) -> None:
        orphan = _make_proc(9999)
        with patch("adjutant.messaging.telegram.service._find_listener_pid", return_value=None):
            with patch(
                "adjutant.messaging.telegram.service.find_by_cmdline", return_value=[orphan]
            ):
                with patch("adjutant.messaging.telegram.service.kill_graceful") as mock_kill:
                    listener_stop(tmp_path)

        mock_kill.assert_called_once_with(9999, timeout=2.0)


# ---------------------------------------------------------------------------
# listener_start
# ---------------------------------------------------------------------------


class TestListenerStart:
    def test_returns_already_running_when_pid_found(self, tmp_path: Path) -> None:
        with patch("adjutant.messaging.telegram.service._find_listener_pid", return_value=42):
            with patch("adjutant.core.lockfiles.check_killed", return_value=True):
                result = listener_start(tmp_path)
        assert "Already running" in result
        assert "42" in result

    def test_returns_error_when_killed(self, tmp_path: Path) -> None:
        with patch("adjutant.core.lockfiles.check_killed", return_value=False):
            result = listener_start(tmp_path)
        assert "KILLED" in result

    def test_launches_subprocess_and_returns_started(self, tmp_path: Path) -> None:
        fake_proc = MagicMock()
        fake_proc.pid = 1111

        lockdir = tmp_path / "state" / "listener.lock"

        def _write_lockpid(*_args, **_kwargs):
            lockdir.mkdir(parents=True, exist_ok=True)
            (lockdir / "pid").write_text("1111")
            return fake_proc

        with patch("adjutant.core.lockfiles.check_killed", return_value=True):
            with patch("adjutant.messaging.telegram.service._find_listener_pid", return_value=None):
                with patch(
                    "adjutant.messaging.telegram.service.subprocess.Popen",
                    side_effect=_write_lockpid,
                ):
                    with patch(
                        "adjutant.messaging.telegram.service.pid_is_alive", return_value=True
                    ):
                        with patch("adjutant.messaging.telegram.service.time.sleep"):
                            result = listener_start(tmp_path)

        assert "Started" in result


# ---------------------------------------------------------------------------
# listener_restart
# ---------------------------------------------------------------------------


class TestListenerRestart:
    def test_combines_stop_and_start_messages(self, tmp_path: Path) -> None:
        with patch("adjutant.messaging.telegram.service.listener_stop", return_value="Not running"):
            with patch(
                "adjutant.messaging.telegram.service.listener_start",
                return_value="Started (PID 42)",
            ):
                with patch("adjutant.messaging.telegram.service.time.sleep"):
                    result = listener_restart(tmp_path)

        assert "Not running" in result
        assert "Started (PID 42)" in result


# ---------------------------------------------------------------------------
# main()
# ---------------------------------------------------------------------------


class TestMain:
    def test_returns_1_without_adj_dir(self, tmp_path: Path, capsys) -> None:
        with patch.dict("os.environ", {}, clear=True):
            # Make sure ADJ_DIR is not set
            import os

            os.environ.pop("ADJ_DIR", None)
            rc = main(["start"])
        assert rc == 1

    def test_returns_1_without_command(self, tmp_path: Path) -> None:
        with patch.dict("os.environ", {"ADJ_DIR": str(tmp_path)}):
            rc = main([])
        assert rc == 1

    def test_returns_1_for_unknown_command(self, tmp_path: Path) -> None:
        with patch.dict("os.environ", {"ADJ_DIR": str(tmp_path)}):
            rc = main(["unknown"])
        assert rc == 1

    def test_calls_listener_status(self, tmp_path: Path, capsys) -> None:
        with patch.dict("os.environ", {"ADJ_DIR": str(tmp_path)}):
            with patch(
                "adjutant.messaging.telegram.service.listener_status",
                return_value="Stopped",
            ) as mock_fn:
                rc = main(["status"])
        assert rc == 0
        mock_fn.assert_called_once_with(tmp_path)

    def test_calls_listener_start(self, tmp_path: Path, capsys) -> None:
        with patch.dict("os.environ", {"ADJ_DIR": str(tmp_path)}):
            with patch(
                "adjutant.messaging.telegram.service.listener_start",
                return_value="Started (PID 1)",
            ) as mock_fn:
                rc = main(["start"])
        assert rc == 0
        mock_fn.assert_called_once_with(tmp_path)

    def test_calls_listener_stop(self, tmp_path: Path, capsys) -> None:
        with patch.dict("os.environ", {"ADJ_DIR": str(tmp_path)}):
            with patch(
                "adjutant.messaging.telegram.service.listener_stop",
                return_value="Not running",
            ) as mock_fn:
                rc = main(["stop"])
        assert rc == 0
        mock_fn.assert_called_once_with(tmp_path)

    def test_calls_listener_restart(self, tmp_path: Path, capsys) -> None:
        with patch.dict("os.environ", {"ADJ_DIR": str(tmp_path)}):
            with patch(
                "adjutant.messaging.telegram.service.listener_restart",
                return_value="Not running; Started (PID 1)",
            ) as mock_fn:
                rc = main(["restart"])
        assert rc == 0
        mock_fn.assert_called_once_with(tmp_path)
