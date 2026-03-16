"""Unit tests for adjutant.lifecycle.control."""

from __future__ import annotations

import json
import os
import signal
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from adjutant.lifecycle.control import (
    pause,
    resume,
    restart,
    emergency_kill,
    startup,
    main_pause,
    main_resume,
    main_restart,
    main_emergency_kill,
    main_startup,
    _adj_dir,
    _timestamp,
    _kill_by_pattern,
    _kill_pidfile,
    _pid_alive,
    _pgrep_first,
    _read_pid,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


@pytest.fixture()
def adj(tmp_path):
    """Return a minimal adj_dir with state/ and journal/ dirs."""
    (tmp_path / "state").mkdir()
    (tmp_path / "journal").mkdir()
    return tmp_path


# ---------------------------------------------------------------------------
# _adj_dir
# ---------------------------------------------------------------------------


class TestAdjDir:
    def test_reads_env(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ADJ_DIR", str(tmp_path))
        assert _adj_dir() == tmp_path

    def test_missing_raises(self, monkeypatch):
        monkeypatch.delenv("ADJ_DIR", raising=False)
        with pytest.raises(RuntimeError):
            _adj_dir()


# ---------------------------------------------------------------------------
# _read_pid
# ---------------------------------------------------------------------------


class TestReadPid:
    def test_valid(self, tmp_path):
        f = tmp_path / "test.pid"
        f.write_text("1234\n")
        assert _read_pid(f) == 1234

    def test_missing(self, tmp_path):
        assert _read_pid(tmp_path / "no.pid") is None

    def test_bad_content(self, tmp_path):
        f = tmp_path / "bad.pid"
        f.write_text("not-a-number")
        assert _read_pid(f) is None


# ---------------------------------------------------------------------------
# _pid_alive
# ---------------------------------------------------------------------------


class TestPidAlive:
    def test_own_process(self):
        assert _pid_alive(os.getpid()) is True

    def test_dead_pid(self):
        # PID 0 is never a user process; sending signal 0 to it raises PermissionError
        # on macOS/Linux — which _pid_alive treats as False
        # Use a PID that almost certainly doesn't exist
        assert _pid_alive(999_999_999) is False


# ---------------------------------------------------------------------------
# _pgrep_first
# ---------------------------------------------------------------------------


class TestPgrepFirst:
    def test_no_match(self):
        result = _pgrep_first("adjutant_very_unlikely_process_xyz_12345")
        assert result is None

    def test_returns_int_or_none(self):
        result = _pgrep_first("python")
        assert result is None or isinstance(result, int)


# ---------------------------------------------------------------------------
# _kill_by_pattern / _kill_pidfile
# ---------------------------------------------------------------------------


class TestKillHelpers:
    def test_kill_by_pattern_no_match(self):
        # Should not raise even when no process matches
        _kill_by_pattern("adjutant_very_unlikely_process_xyz_12345")

    def test_kill_pidfile_missing(self, tmp_path):
        # Should not raise for missing file
        _kill_pidfile(tmp_path / "nonexistent.pid")

    def test_kill_pidfile_bad_content(self, tmp_path):
        f = tmp_path / "bad.pid"
        f.write_text("not-a-pid")
        _kill_pidfile(f)  # should not raise


# ---------------------------------------------------------------------------
# pause
# ---------------------------------------------------------------------------


class TestPause:
    def test_creates_paused_lockfile(self, adj):
        result = pause(adj)
        assert (adj / "PAUSED").exists()
        assert "paused" in result.lower()
        assert "resume" in result.lower()

    def test_missing_adj_dir(self, monkeypatch):
        monkeypatch.delenv("ADJ_DIR", raising=False)
        with pytest.raises(RuntimeError):
            pause()


# ---------------------------------------------------------------------------
# resume
# ---------------------------------------------------------------------------


class TestResume:
    def test_removes_paused_lockfile(self, adj):
        (adj / "PAUSED").touch()
        result = resume(adj)
        assert not (adj / "PAUSED").exists()
        assert "resumed" in result.lower()

    def test_idempotent_when_not_paused(self, adj):
        result = resume(adj)  # file doesn't exist — should not raise
        assert "resumed" in result.lower()

    def test_missing_adj_dir(self, monkeypatch):
        monkeypatch.delenv("ADJ_DIR", raising=False)
        with pytest.raises(RuntimeError):
            resume()


# ---------------------------------------------------------------------------
# emergency_kill
# ---------------------------------------------------------------------------


class TestEmergencyKill:
    def _run(self, adj, monkeypatch):
        monkeypatch.setattr("adjutant.lifecycle.control._send_notify", lambda d, t: None)
        monkeypatch.setattr(
            "adjutant.lifecycle.control._kill_by_pattern", lambda p, s=signal.SIGTERM: None
        )
        monkeypatch.setattr(
            "adjutant.lifecycle.control._kill_pidfile", lambda p, s=signal.SIGTERM: None
        )
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="")
            result = emergency_kill(adj)
        return result

    def test_creates_killed_lockfile(self, adj, monkeypatch):
        self._run(adj, monkeypatch)
        assert (adj / "KILLED").exists()

    def test_output_contains_completion(self, adj, monkeypatch):
        result = self._run(adj, monkeypatch)
        assert "shutdown complete" in result.lower() or "KILLED" in result

    def test_backs_up_crontab(self, adj, monkeypatch):
        monkeypatch.setattr("adjutant.lifecycle.control._send_notify", lambda d, t: None)
        monkeypatch.setattr(
            "adjutant.lifecycle.control._kill_by_pattern", lambda p, s=signal.SIGTERM: None
        )
        monkeypatch.setattr(
            "adjutant.lifecycle.control._kill_pidfile", lambda p, s=signal.SIGTERM: None
        )
        with patch("subprocess.run") as mock_run:
            # Simulate crontab -l returning some content
            mock_run.return_value = MagicMock(returncode=0, stdout="0 8 * * * echo test\n")
            emergency_kill(adj)
        backup = adj / "state" / "crontab.backup"
        assert backup.exists()

    def test_logs_to_journal(self, adj, monkeypatch):
        self._run(adj, monkeypatch)
        from datetime import datetime

        today = datetime.now().strftime("%Y-%m-%d")
        log = adj / "journal" / f"{today}.md"
        assert log.exists()
        assert "EMERGENCY" in log.read_text()

    def test_missing_adj_dir(self, monkeypatch):
        monkeypatch.delenv("ADJ_DIR", raising=False)
        with pytest.raises(RuntimeError):
            emergency_kill()


# ---------------------------------------------------------------------------
# startup
# ---------------------------------------------------------------------------


class TestStartup:
    def _patched_startup(self, adj, monkeypatch, recovery=False):
        if recovery:
            (adj / "KILLED").touch()

        monkeypatch.setattr("adjutant.lifecycle.control._send_notify", lambda d, t: None)
        monkeypatch.setattr(
            "adjutant.lifecycle.control._start_telegram_service",
            lambda d: "Telegram listener started (PID 12345)",
        )
        monkeypatch.setattr(
            "adjutant.lifecycle.control.start_opencode_web",
            lambda d: "OpenCode web server started (PID 99999)",
        )
        monkeypatch.setattr(
            "adjutant.lifecycle.control._sync_schedule_crontab",
            lambda d: "Crontab synced (0 jobs)",
        )
        monkeypatch.setattr("adjutant.lifecycle.control._pgrep_first", lambda p: None)
        monkeypatch.setattr(
            "adjutant.observability.status.get_status",
            lambda d: "Adjutant is up and running.",
        )
        return startup(adj, interactive=False)

    def test_normal_startup(self, adj, monkeypatch):
        result = self._patched_startup(adj, monkeypatch)
        assert "Startup complete" in result
        assert "Telegram listener started" in result

    def test_recovery_mode_removes_killed(self, adj, monkeypatch):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="")
            result = self._patched_startup(adj, monkeypatch, recovery=True)
        assert not (adj / "KILLED").exists()
        assert "RECOVERY" in result or "recovered" in result.lower()

    def test_recovery_restores_crontab_backup(self, adj, monkeypatch):
        (adj / "KILLED").touch()
        backup = adj / "state" / "crontab.backup"
        backup.write_text("0 8 * * * echo test\n")

        monkeypatch.setattr("adjutant.lifecycle.control._send_notify", lambda d, t: None)
        monkeypatch.setattr(
            "adjutant.lifecycle.control._start_telegram_service",
            lambda d: "started",
        )
        monkeypatch.setattr(
            "adjutant.lifecycle.control.start_opencode_web",
            lambda d: "started",
        )
        monkeypatch.setattr(
            "adjutant.lifecycle.control._sync_schedule_crontab",
            lambda d: "synced",
        )
        monkeypatch.setattr("adjutant.lifecycle.control._pgrep_first", lambda p: None)

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="")
            result = startup(adj, interactive=False)

        assert "Crontab restored" in result

    def test_startup_paused_message(self, adj, monkeypatch):
        (adj / "PAUSED").touch()
        result = self._patched_startup(adj, monkeypatch)
        assert "PAUSED" in result or "paused" in result.lower()

    def test_missing_adj_dir(self, monkeypatch):
        monkeypatch.delenv("ADJ_DIR", raising=False)
        with pytest.raises(RuntimeError):
            startup()


# ---------------------------------------------------------------------------
# restart
# ---------------------------------------------------------------------------


class TestRestart:
    def test_restart_calls_startup(self, adj, monkeypatch):
        monkeypatch.setattr(
            "adjutant.lifecycle.control.startup",
            lambda d, interactive=True: "Startup complete",
        )
        monkeypatch.setattr("adjutant.lifecycle.control._read_pid", lambda p: None)
        result = restart(adj)
        assert "Restart complete" in result
        assert "Startup complete" in result

    def test_missing_adj_dir(self, monkeypatch):
        monkeypatch.delenv("ADJ_DIR", raising=False)
        with pytest.raises(RuntimeError):
            restart()


# ---------------------------------------------------------------------------
# main_* entrypoints
# ---------------------------------------------------------------------------


class TestMainEntrypoints:
    def test_main_pause(self, adj, monkeypatch, capsys):
        monkeypatch.setenv("ADJ_DIR", str(adj))
        rc = main_pause()
        assert rc == 0
        assert "paused" in capsys.readouterr().out.lower()

    def test_main_resume(self, adj, monkeypatch, capsys):
        monkeypatch.setenv("ADJ_DIR", str(adj))
        rc = main_resume()
        assert rc == 0
        assert "resumed" in capsys.readouterr().out.lower()

    def test_main_pause_no_adj_dir(self, monkeypatch, capsys):
        monkeypatch.delenv("ADJ_DIR", raising=False)
        rc = main_pause()
        assert rc == 1

    def test_main_resume_no_adj_dir(self, monkeypatch, capsys):
        monkeypatch.delenv("ADJ_DIR", raising=False)
        rc = main_resume()
        assert rc == 1

    def test_main_restart_no_adj_dir(self, monkeypatch):
        monkeypatch.delenv("ADJ_DIR", raising=False)
        rc = main_restart()
        assert rc == 1

    def test_main_emergency_kill_no_adj_dir(self, monkeypatch):
        monkeypatch.delenv("ADJ_DIR", raising=False)
        rc = main_emergency_kill()
        assert rc == 1

    def test_main_startup_no_adj_dir(self, monkeypatch):
        monkeypatch.delenv("ADJ_DIR", raising=False)
        rc = main_startup()
        assert rc == 1
