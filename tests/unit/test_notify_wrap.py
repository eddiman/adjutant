"""Unit tests for adjutant.capabilities.schedule.notify_wrap."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from adjutant.capabilities.schedule.notify_wrap import (
    notify_wrap,
    _extract_kb_notify_message,
    main,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_proc(returncode=0, stdout="", stderr=""):
    m = MagicMock()
    m.returncode = returncode
    m.stdout = stdout
    m.stderr = stderr
    return m


def _kb_event(message: str) -> str:
    """Return a JSON line as emitted by kb_notify()."""
    return json.dumps({"type": "notification", "ts": "2026-03-12T10:00:00Z", "message": message})


# ---------------------------------------------------------------------------
# _extract_kb_notify_message
# ---------------------------------------------------------------------------


class TestExtractKbNotifyMessage:
    def test_returns_none_for_empty_output(self):
        assert _extract_kb_notify_message("") is None

    def test_returns_none_for_plain_text(self):
        assert _extract_kb_notify_message("OK:fetched 2 positions\n") is None

    def test_returns_message_from_single_event(self):
        stderr = _kb_event("Portfolio snapshot updated — 2 positions, 94,500 NOK")
        result = _extract_kb_notify_message(stderr)
        assert result == "Portfolio snapshot updated — 2 positions, 94,500 NOK"

    def test_returns_last_message_when_multiple_events(self):
        """Pipelines emit fill events before the final summary — last wins."""
        first = _kb_event("[MOCK] 1 order filled")
        last = _kb_event("Portfolio snapshot updated — 3 positions")
        stderr = first + "\n" + last + "\n"
        result = _extract_kb_notify_message(stderr)
        assert result == "Portfolio snapshot updated — 3 positions"

    def test_ignores_non_notification_json(self):
        other = json.dumps({"type": "log", "message": "should be ignored"})
        event = _kb_event("real message")
        result = _extract_kb_notify_message(other + "\n" + event)
        assert result == "real message"

    def test_ignores_json_without_type(self):
        bad = json.dumps({"message": "no type field"})
        event = _kb_event("good message")
        result = _extract_kb_notify_message(bad + "\n" + event)
        assert result == "good message"

    def test_ignores_malformed_json_lines(self):
        stderr = "not json\n{broken}\n" + _kb_event("valid message")
        result = _extract_kb_notify_message(stderr)
        assert result == "valid message"

    def test_handles_mixed_output(self):
        """Real output mixes plain text and JSON events."""
        stderr = (
            "some log line\n"
            + _kb_event("Mock fills: 1 order filled")
            + "\n"
            + "another log line\n"
            + _kb_event("Portfolio snapshot updated — 3 positions, 85,000 NOK")
            + "\n"
        )
        result = _extract_kb_notify_message(stderr)
        assert result == "Portfolio snapshot updated — 3 positions, 85,000 NOK"

    def test_returns_none_when_no_message_key(self):
        bad = json.dumps({"type": "notification", "ts": "2026-03-12T10:00:00Z"})
        assert _extract_kb_notify_message(bad) is None


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
            patch("subprocess.run", return_value=_make_proc(1, "", "something broke\n")),
            patch("adjutant.core.logging.adj_log"),
            patch("adjutant.messaging.telegram.notify.send_notify"),
        ):
            rc = notify_wrap("my-job", "/scripts/run.sh", tmp_path)
        assert rc == 0

    def test_uses_kb_notify_message_when_present(self, tmp_path: Path) -> None:
        """Rich kb_notify message from stderr takes priority over terse stdout."""
        rich = "Portfolio snapshot updated — 2 positions, 94,500 NOK cash\nTotal: 98,200 NOK"
        stderr = _kb_event(rich)
        stdout = "OK:fetched 2 positions\n"
        log_calls = []

        with (
            patch("subprocess.run", return_value=_make_proc(0, stdout, stderr)),
            patch("adjutant.core.logging.adj_log", side_effect=lambda c, m: log_calls.append(m)),
            patch("adjutant.messaging.telegram.notify.send_notify"),
        ):
            notify_wrap("portfolio-fetch", "/run.sh", tmp_path)

        assert log_calls
        assert "Portfolio snapshot updated" in log_calls[0]
        assert "OK:fetched" not in log_calls[0]

    def test_falls_back_to_stdout_when_no_json_event(self, tmp_path: Path) -> None:
        """Fall back to first stdout line when no kb_notify event on stderr."""
        stdout = "Data fetched OK\n"
        log_calls = []

        with (
            patch("subprocess.run", return_value=_make_proc(0, stdout, "")),
            patch("adjutant.core.logging.adj_log", side_effect=lambda c, m: log_calls.append(m)),
            patch("adjutant.messaging.telegram.notify.send_notify"),
        ):
            notify_wrap("portfolio-fetch", "/run.sh", tmp_path)

        assert log_calls
        assert "Data fetched OK" in log_calls[0]
        assert "ERROR" not in log_calls[0]

    def test_uses_last_kb_notify_message_not_first(self, tmp_path: Path) -> None:
        """When multiple kb_notify events exist, use the last (the summary)."""
        stderr = (
            _kb_event("[MOCK] 1 order(s) filled at market prices")
            + "\n"
            + _kb_event("Portfolio snapshot updated — 3 positions, 85,000 NOK")
            + "\n"
        )
        log_calls = []

        with (
            patch("subprocess.run", return_value=_make_proc(0, "OK:fetched 3 positions\n", stderr)),
            patch("adjutant.core.logging.adj_log", side_effect=lambda c, m: log_calls.append(m)),
            patch("adjutant.messaging.telegram.notify.send_notify"),
        ):
            notify_wrap("portfolio-fetch", "/run.sh", tmp_path)

        assert log_calls
        assert "Portfolio snapshot updated" in log_calls[0]
        assert "filled" not in log_calls[0]

    def test_success_message_includes_job_name(self, tmp_path: Path) -> None:
        log_calls = []
        with (
            patch("subprocess.run", return_value=_make_proc(0, "ok\n")),
            patch("adjutant.core.logging.adj_log", side_effect=lambda c, m: log_calls.append(m)),
            patch("adjutant.messaging.telegram.notify.send_notify"),
        ):
            notify_wrap("portfolio-fetch", "/run.sh", tmp_path)
        assert "[portfolio-fetch]" in log_calls[0]

    def test_failure_message_includes_rc(self, tmp_path: Path) -> None:
        log_calls = []
        with (
            patch("subprocess.run", return_value=_make_proc(2, "", "Script failed badly\n")),
            patch("adjutant.core.logging.adj_log", side_effect=lambda c, m: log_calls.append(m)),
            patch("adjutant.messaging.telegram.notify.send_notify"),
        ):
            notify_wrap("daily-sync", "/run.sh", tmp_path)
        assert "[daily-sync]" in log_calls[0]
        assert "ERROR" in log_calls[0]
        assert "rc=2" in log_calls[0]

    def test_failure_does_not_use_kb_notify_message(self, tmp_path: Path) -> None:
        """On failure, use combined output first line — don't trust partial JSON."""
        stderr = "Script crashed\n" + _kb_event("partial success message")
        log_calls = []
        with (
            patch("subprocess.run", return_value=_make_proc(1, "", stderr)),
            patch("adjutant.core.logging.adj_log", side_effect=lambda c, m: log_calls.append(m)),
            patch("adjutant.messaging.telegram.notify.send_notify"),
        ):
            notify_wrap("my-job", "/run.sh", tmp_path)
        assert "ERROR" in log_calls[0]
        assert "Script crashed" in log_calls[0]

    def test_handles_no_output(self, tmp_path: Path) -> None:
        log_calls = []
        with (
            patch("subprocess.run", return_value=_make_proc(0, "", "")),
            patch("adjutant.core.logging.adj_log", side_effect=lambda c, m: log_calls.append(m)),
            patch("adjutant.messaging.telegram.notify.send_notify"),
        ):
            notify_wrap("empty-job", "/run.sh", tmp_path)
        assert "(no output)" in log_calls[0]

    def test_handles_subprocess_oserror(self, tmp_path: Path) -> None:
        log_calls = []
        with (
            patch("subprocess.run", side_effect=OSError("not found")),
            patch("adjutant.core.logging.adj_log", side_effect=lambda c, m: log_calls.append(m)),
            patch("adjutant.messaging.telegram.notify.send_notify"),
        ):
            rc = notify_wrap("bad-job", "/missing.sh", tmp_path)
        assert rc == 0
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

    def test_falls_back_to_first_non_empty_stdout_line(self, tmp_path: Path) -> None:
        """When no JSON event, skip blank lines and use first non-empty stdout line."""
        stdout = "\n\n  \nFirst actual line\nSecond line\n"
        log_calls = []
        with (
            patch("subprocess.run", return_value=_make_proc(0, stdout, "")),
            patch("adjutant.core.logging.adj_log", side_effect=lambda c, m: log_calls.append(m)),
            patch("adjutant.messaging.telegram.notify.send_notify"),
        ):
            notify_wrap("job1", "/run.sh", tmp_path)
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
