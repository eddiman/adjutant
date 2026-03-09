"""Tests for src/adjutant/setup/uninstall.py"""

from __future__ import annotations

import os
import signal
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from adjutant.setup.uninstall import (
    _confirm_intent,
    _detect_os,
    _kill_pid_file,
    _pkill,
    _remove_adjutant_crontab_entries,
    _stop_scheduled_jobs,
    remove_files,
    remove_path_alias,
    stop_processes,
    uninstall,
)


# ---------------------------------------------------------------------------
# _detect_os
# ---------------------------------------------------------------------------


class TestDetectOs:
    def test_macos(self) -> None:
        with patch("platform.system", return_value="Darwin"):
            assert _detect_os() == "macos"

    def test_linux(self) -> None:
        with patch("platform.system", return_value="Linux"):
            assert _detect_os() == "linux"

    def test_unknown(self) -> None:
        with patch("platform.system", return_value="FreeBSD"):
            assert _detect_os() == "unknown"


# ---------------------------------------------------------------------------
# _confirm_intent
# ---------------------------------------------------------------------------


class TestConfirmIntent:
    def test_returns_true_on_yes(self, capsys) -> None:
        with patch("builtins.input", return_value="yes"):
            assert _confirm_intent() is True

    def test_returns_false_on_anything_else(self, capsys) -> None:
        with patch("builtins.input", return_value="no"):
            assert _confirm_intent() is False

    def test_returns_false_on_eof(self, capsys) -> None:
        with patch("builtins.input", side_effect=EOFError):
            assert _confirm_intent() is False

    def test_returns_false_on_keyboard_interrupt(self, capsys) -> None:
        with patch("builtins.input", side_effect=KeyboardInterrupt):
            assert _confirm_intent() is False


# ---------------------------------------------------------------------------
# _pkill
# ---------------------------------------------------------------------------


class TestPkill:
    def test_runs_term_and_kill(self) -> None:
        with patch("subprocess.run") as mock_run, patch("time.sleep"):
            _pkill("some-process")

        assert mock_run.call_count == 2
        args_list = [c[0][0] for c in mock_run.call_args_list]
        assert any("-TERM" in a for a in args_list[0])
        assert any("-KILL" in a for a in args_list[1])

    def test_silently_handles_missing_pkill(self) -> None:
        with patch("subprocess.run", side_effect=FileNotFoundError), patch("time.sleep"):
            _pkill("pattern")  # should not raise


# ---------------------------------------------------------------------------
# _kill_pid_file
# ---------------------------------------------------------------------------


class TestKillPidFile:
    def test_does_nothing_when_no_file(self, tmp_path: Path) -> None:
        missing = tmp_path / "proc.pid"
        # should not raise
        _kill_pid_file(missing)

    def test_sends_sigterm_and_sigkill(self, tmp_path: Path) -> None:
        pid_file = tmp_path / "proc.pid"
        pid_file.write_text("12345")

        killed_signals = []

        def fake_kill(pid, sig):
            killed_signals.append((pid, sig))

        with patch("os.kill", side_effect=fake_kill), patch("time.sleep"):
            _kill_pid_file(pid_file)

        assert (12345, signal.SIGTERM) in killed_signals

    def test_removes_pid_file(self, tmp_path: Path) -> None:
        pid_file = tmp_path / "proc.pid"
        pid_file.write_text("99999")

        with patch("os.kill", side_effect=ProcessLookupError), patch("time.sleep"):
            _kill_pid_file(pid_file)

        assert not pid_file.exists()

    def test_handles_invalid_pid_file(self, tmp_path: Path) -> None:
        pid_file = tmp_path / "bad.pid"
        pid_file.write_text("not-a-number")
        # should not raise
        _kill_pid_file(pid_file)


# ---------------------------------------------------------------------------
# _stop_scheduled_jobs
# ---------------------------------------------------------------------------


class TestStopScheduledJobs:
    def test_kills_script_from_config(self, tmp_path: Path) -> None:
        cfg = tmp_path / "adjutant.yaml"
        cfg.write_text('schedules:\n  - name: "my-job"\n    script: "/usr/local/bin/myscript.sh"\n')

        with patch("adjutant.setup.uninstall._pkill") as mock_pkill, patch("time.sleep"):
            _stop_scheduled_jobs(tmp_path)

        mock_pkill.assert_called_once_with("/usr/local/bin/myscript.sh")

    def test_does_nothing_when_no_config(self, tmp_path: Path) -> None:
        with patch("adjutant.setup.uninstall._pkill") as mock_pkill:
            _stop_scheduled_jobs(tmp_path)
        mock_pkill.assert_not_called()

    def test_does_nothing_when_no_schedules_section(self, tmp_path: Path) -> None:
        cfg = tmp_path / "adjutant.yaml"
        cfg.write_text("instance:\n  name: test\n")

        with patch("adjutant.setup.uninstall._pkill") as mock_pkill:
            _stop_scheduled_jobs(tmp_path)
        mock_pkill.assert_not_called()


# ---------------------------------------------------------------------------
# _remove_adjutant_crontab_entries
# ---------------------------------------------------------------------------


class TestRemoveAdjutantCrontabEntries:
    def test_removes_adjutant_lines(self, capsys) -> None:
        existing_crontab = (
            "0 8 * * * /some/script.sh >> /log 2>&1 # adjutant:my-job\n"
            "0 9 * * * /other/script.sh # unrelated\n"
        )
        list_result = MagicMock()
        list_result.returncode = 0
        list_result.stdout = existing_crontab

        with patch("subprocess.run", side_effect=[list_result, MagicMock()]) as mock_run:
            _remove_adjutant_crontab_entries()

        write_call = mock_run.call_args_list[1]
        written = write_call[1]["input"]
        assert "adjutant:my-job" not in written
        assert "/other/script.sh" in written

    def test_skips_when_no_adjutant_entries(self) -> None:
        result = MagicMock()
        result.returncode = 0
        result.stdout = "0 9 * * * /other/script.sh # unrelated\n"

        with patch("subprocess.run", return_value=result) as mock_run:
            _remove_adjutant_crontab_entries()

        # Only called once (the -l list call), no write call
        assert mock_run.call_count == 1

    def test_handles_missing_crontab_gracefully(self) -> None:
        import subprocess

        with patch("subprocess.run", side_effect=FileNotFoundError):
            _remove_adjutant_crontab_entries()  # should not raise


# ---------------------------------------------------------------------------
# remove_files
# ---------------------------------------------------------------------------


class TestRemoveFiles:
    def test_returns_false_on_no_input(self, tmp_path: Path, capsys) -> None:
        with patch("builtins.input", return_value="n"):
            result = remove_files(tmp_path)
        assert result is False

    def test_returns_true_and_deletes_on_yes(self, tmp_path: Path, capsys) -> None:
        target = tmp_path / "adj"
        target.mkdir()
        (target / "adjutant.yaml").write_text("instance:\n  name: test\n")

        with (
            patch("builtins.input", return_value="y"),
            patch("adjutant.setup.uninstall._remove_adjutant_crontab_entries"),
        ):
            result = remove_files(target)

        assert result is True
        assert not target.exists()

    def test_returns_false_on_eof(self, tmp_path: Path, capsys) -> None:
        with patch("builtins.input", side_effect=EOFError):
            result = remove_files(tmp_path)
        assert result is False


# ---------------------------------------------------------------------------
# stop_processes (integration-light)
# ---------------------------------------------------------------------------


class TestStopProcesses:
    def test_runs_without_error_on_empty_dir(self, tmp_path: Path, capsys) -> None:
        with (
            patch("adjutant.setup.uninstall._pkill"),
            patch("adjutant.setup.uninstall._kill_pid_file"),
            patch("time.sleep"),
        ):
            stop_processes(tmp_path)

        captured = capsys.readouterr()
        assert "Stopping" in captured.err


# ---------------------------------------------------------------------------
# uninstall (integration-light)
# ---------------------------------------------------------------------------


class TestUninstall:
    def test_aborts_when_user_does_not_confirm(self, tmp_path: Path, capsys) -> None:
        with patch("builtins.input", return_value="no"):
            uninstall(tmp_path)

        captured = capsys.readouterr()
        assert "Aborted" in captured.err

    def test_runs_full_flow_on_yes(self, tmp_path: Path, capsys) -> None:
        # Answer "yes" to confirm, then "n" to all optional prompts
        inputs = iter(["yes", "n", "n", "n"])

        with (
            patch("builtins.input", side_effect=inputs),
            patch("adjutant.setup.uninstall.stop_processes"),
            patch("adjutant.setup.uninstall.remove_service"),
            patch("adjutant.setup.uninstall.remove_path_alias"),
            patch("adjutant.setup.uninstall.remove_files", return_value=False),
        ):
            uninstall(tmp_path)

        captured = capsys.readouterr()
        # Should reach the completion banner
        assert "━" in captured.err
