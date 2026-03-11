"""Unit tests for adjutant.capabilities.schedule.notify_wrap."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from adjutant.capabilities.schedule.notify_wrap import notify_wrap, main


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_proc(returncode=0, stdout="", stderr=""):
    m = MagicMock()
    m.returncode = returncode
    m.stdout = stdout
    m.stderr = stderr
    return m


# ---------------------------------------------------------------------------
# notify_wrap
# ---------------------------------------------------------------------------


class TestNotifyWrap:
    def test_returns_zero_on_success(self, tmp_path: Path) -> None:
        with (
            patch("subprocess.run", return_value=_make_proc(0, "All good\n")),
            patch("adjutant.core.logging.adj_log"),
            patch("adjutant.messaging.telegram.notify.send_notify"),
        ):
            rc = notify_wrap("my-job", "/scripts/run.sh", tmp_path)
        assert rc == 0

    def test_returns_zero_on_failure(self, tmp_path: Path) -> None:
        """Always returns 0 — cron must not see failure exit codes."""
        with (
            patch("subprocess.run", return_value=_make_proc(1, "something broke\n")),
            patch("adjutant.core.logging.adj_log"),
            patch("adjutant.messaging.telegram.notify.send_notify"),
        ):
            rc = notify_wrap("my-job", "/scripts/run.sh", tmp_path)
        assert rc == 0

    def test_success_message_format(self, tmp_path: Path) -> None:
        log_calls = []

        def capture_log(component, msg):
            log_calls.append(msg)

        with (
            patch("subprocess.run", return_value=_make_proc(0, "Data fetched OK\n")),
            patch("adjutant.core.logging.adj_log", side_effect=capture_log),
            patch("adjutant.messaging.telegram.notify.send_notify"),
        ):
            notify_wrap("portfolio-fetch", "/run.sh", tmp_path)

        assert log_calls, "adj_log should have been called"
        log_msg = log_calls[0]
        assert "[portfolio-fetch]" in log_msg
        assert "Data fetched OK" in log_msg
        assert "ERROR" not in log_msg

    def test_failure_message_includes_rc(self, tmp_path: Path) -> None:
        log_calls = []

        def capture_log(component, msg):
            log_calls.append(msg)

        with (
            patch("subprocess.run", return_value=_make_proc(2, "", "Script failed badly\n")),
            patch("adjutant.core.logging.adj_log", side_effect=capture_log),
            patch("adjutant.messaging.telegram.notify.send_notify"),
        ):
            notify_wrap("daily-sync", "/run.sh", tmp_path)

        assert log_calls
        log_msg = log_calls[0]
        assert "[daily-sync]" in log_msg
        assert "ERROR" in log_msg
        assert "rc=2" in log_msg

    def test_handles_no_output(self, tmp_path: Path) -> None:
        log_calls = []

        def capture_log(component, msg):
            log_calls.append(msg)

        with (
            patch("subprocess.run", return_value=_make_proc(0, "", "")),
            patch("adjutant.core.logging.adj_log", side_effect=capture_log),
            patch("adjutant.messaging.telegram.notify.send_notify"),
        ):
            notify_wrap("empty-job", "/run.sh", tmp_path)

        assert log_calls
        assert "(no output)" in log_calls[0]

    def test_handles_subprocess_oserror(self, tmp_path: Path) -> None:
        log_calls = []

        def capture_log(component, msg):
            log_calls.append(msg)

        with (
            patch("subprocess.run", side_effect=OSError("not found")),
            patch("adjutant.core.logging.adj_log", side_effect=capture_log),
            patch("adjutant.messaging.telegram.notify.send_notify"),
        ):
            rc = notify_wrap("bad-job", "/missing.sh", tmp_path)

        assert rc == 0
        assert log_calls
        assert "ERROR" in log_calls[0]

    def test_notify_failure_does_not_crash(self, tmp_path: Path) -> None:
        """If send_notify raises, notify_wrap still returns 0."""
        with (
            patch("subprocess.run", return_value=_make_proc(0, "ok\n")),
            patch("adjutant.core.logging.adj_log"),
            patch(
                "adjutant.messaging.telegram.notify.send_notify",
                side_effect=RuntimeError("telegram down"),
            ),
        ):
            rc = notify_wrap("job1", "/run.sh", tmp_path)
        assert rc == 0

    def test_uses_first_non_empty_line_as_summary(self, tmp_path: Path) -> None:
        output = "\n\n  \nFirst actual line\nSecond line\n"
        log_calls = []

        def capture_log(component, msg):
            log_calls.append(msg)

        with (
            patch("subprocess.run", return_value=_make_proc(0, output)),
            patch("adjutant.core.logging.adj_log", side_effect=capture_log),
            patch("adjutant.messaging.telegram.notify.send_notify"),
        ):
            notify_wrap("job1", "/run.sh", tmp_path)

        assert log_calls
        assert "First actual line" in log_calls[0]
        assert "Second line" not in log_calls[0]


# ---------------------------------------------------------------------------
# main (CLI)
# ---------------------------------------------------------------------------


class TestMain:
    def test_returns_1_on_missing_args(self) -> None:
        rc = main(["only-one"])
        assert rc == 1

    def test_returns_1_when_adj_dir_not_set(self) -> None:
        env = {k: v for k, v in os.environ.items() if k != "ADJ_DIR"}
        with patch.dict(os.environ, env, clear=True):
            rc = main(["job1", "/scripts/run.sh"])
        assert rc == 1

    def test_returns_0_on_success(self, tmp_path: Path) -> None:
        with (
            patch.dict(os.environ, {"ADJ_DIR": str(tmp_path)}),
            patch(
                "adjutant.capabilities.schedule.notify_wrap.notify_wrap",
                return_value=0,
            ) as mock_wrap,
        ):
            rc = main(["job1", "/scripts/run.sh"])
        assert rc == 0
        mock_wrap.assert_called_once_with("job1", "/scripts/run.sh", tmp_path)
