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
        with patch("adjutant.capabilities.schedule.install.uninstall_all") as uninstall_all:
            result = pause(adj)
        assert (adj / "PAUSED").exists()
        uninstall_all.assert_called_once_with(adj)
        assert "paused" in result.lower()
        assert "resume" in result.lower()

    def test_removes_only_managed_cron_entries(self, adj):
        with patch("adjutant.capabilities.schedule.install.uninstall_all") as uninstall_all:
            pause(adj)
        uninstall_all.assert_called_once_with(adj)

    def test_idempotent(self, adj):
        with patch("adjutant.capabilities.schedule.install.uninstall_all") as uninstall_all:
            pause(adj)
            pause(adj)
        assert (adj / "PAUSED").exists()
        assert uninstall_all.call_count == 2

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
        with patch("adjutant.capabilities.schedule.install.install_all") as install_all:
            result = resume(adj)
        assert not (adj / "PAUSED").exists()
        install_all.assert_called_once_with(adj)
        assert "resumed" in result.lower()

    def test_idempotent_when_not_paused(self, adj):
        with patch("adjutant.capabilities.schedule.install.install_all") as install_all:
            result = resume(adj)  # file doesn't exist — should not raise
        install_all.assert_called_once_with(adj)
        assert "resumed" in result.lower()

    def test_does_not_restore_schedules_when_killed(self, adj):
        (adj / "PAUSED").touch()
        (adj / "KILLED").touch()
        with patch("adjutant.capabilities.schedule.install.install_all") as install_all:
            result = resume(adj)
        assert not (adj / "PAUSED").exists()
        install_all.assert_not_called()
        assert "killed" in result.lower()

    def test_missing_adj_dir(self, monkeypatch):
        monkeypatch.delenv("ADJ_DIR", raising=False)
        with pytest.raises(RuntimeError):
            resume()


# ---------------------------------------------------------------------------
# emergency_kill
# ---------------------------------------------------------------------------


@pytest.mark.skip(
    reason="DEFERRED: emergency_kill tests kill real opencode web processes. "
    "Needs full subprocess isolation before re-enabling. "
    "See docs/reference/backend-migration-log.md."
)
class TestEmergencyKill:
    def _run(self, adj, monkeypatch):
        monkeypatch.setattr("adjutant.lifecycle.control._send_notify", lambda d, t: None)
        monkeypatch.setattr(
            "adjutant.lifecycle.control._kill_by_pattern", lambda p, s=signal.SIGTERM: None
        )
        monkeypatch.setattr(
            "adjutant.lifecycle.control._kill_pidfile", lambda p, s=signal.SIGTERM: None
        )
        monkeypatch.setattr("time.sleep", lambda s: None)
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
        monkeypatch.setattr("time.sleep", lambda s: None)
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
        with patch("adjutant.capabilities.schedule.install.uninstall_all") as uninstall_all:
            result = self._patched_startup(adj, monkeypatch)
        uninstall_all.assert_called_once_with(adj)
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
        monkeypatch.setattr("adjutant.lifecycle.control._pgrep_first", lambda p: None)
        monkeypatch.setattr(
            "adjutant.lifecycle.control._kill_by_pattern", lambda p, s=signal.SIGTERM: None
        )
        monkeypatch.setattr("time.sleep", lambda s: None)
        result = restart(adj)
        assert "Restart complete" in result
        assert "Startup complete" in result

    def test_startup_sends_post_restart_reply_when_pending_file_exists(self, adj, monkeypatch):
        sent: list[tuple[str, int | None]] = []
        (adj / "state" / "restart_notify.json").write_text('{"reply_to_message_id": 42}')

        monkeypatch.setattr("adjutant.lifecycle.control._send_notify", lambda d, t: None)
        monkeypatch.setattr(
            "adjutant.lifecycle.control._start_telegram_service",
            lambda d: "Telegram listener started (PID 12345)",
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

        def _fake_require(path):
            return ("bot-token", "999")

        def _fake_send(message, reply_to=None, *, bot_token, chat_id):
            sent.append((message, reply_to))

        with (
            patch("adjutant.core.env.require_telegram_credentials", side_effect=_fake_require),
            patch("adjutant.messaging.telegram.send.msg_send_text", side_effect=_fake_send),
        ):
            result = startup(adj, interactive=False)

        assert (adj / "state" / "restart_notify.json").exists() is False
        assert sent == [("I'm back online and keeping an eye on things.", 42)]
        assert "Post-restart Telegram reply sent" in result

    def test_startup_reports_invalid_post_restart_marker(self, adj, monkeypatch):
        (adj / "state" / "restart_notify.json").write_text("not-json")

        monkeypatch.setattr("adjutant.lifecycle.control._send_notify", lambda d, t: None)
        monkeypatch.setattr(
            "adjutant.lifecycle.control._start_telegram_service",
            lambda d: "Telegram listener started (PID 12345)",
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

        result = startup(adj, interactive=False)

        assert (adj / "state" / "restart_notify.json").exists() is False
        assert "Post-restart Telegram reply not sent (invalid_marker)" in result

    def test_startup_reports_failed_post_restart_send(self, adj, monkeypatch):
        (adj / "state" / "restart_notify.json").write_text('{"reply_to_message_id": 42}')

        monkeypatch.setattr("adjutant.lifecycle.control._send_notify", lambda d, t: None)
        monkeypatch.setattr(
            "adjutant.lifecycle.control._start_telegram_service",
            lambda d: "Telegram listener started (PID 12345)",
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

        with patch(
            "adjutant.core.env.require_telegram_credentials",
            side_effect=RuntimeError("missing creds"),
        ):
            result = startup(adj, interactive=False)

        assert (adj / "state" / "restart_notify.json").exists() is False
        assert "Post-restart Telegram reply not sent (send_failed)" in result

    def test_missing_adj_dir(self, monkeypatch):
        monkeypatch.delenv("ADJ_DIR", raising=False)
        with pytest.raises(RuntimeError):
            restart()


# ---------------------------------------------------------------------------
# Direct function calls — error paths
# ---------------------------------------------------------------------------


class TestDirectFunctionErrors:
    def test_pause_returns_message(self, adj, monkeypatch):
        monkeypatch.setenv("ADJ_DIR", str(adj))
        result = pause(adj)
        assert "paused" in result.lower()

    def test_resume_returns_message(self, adj, monkeypatch):
        monkeypatch.setenv("ADJ_DIR", str(adj))
        result = resume(adj)
        assert "resumed" in result.lower()

    def test_pause_no_adj_dir_raises(self, monkeypatch):
        monkeypatch.delenv("ADJ_DIR", raising=False)
        with pytest.raises(RuntimeError):
            pause()

    def test_resume_no_adj_dir_raises(self, monkeypatch):
        monkeypatch.delenv("ADJ_DIR", raising=False)
        with pytest.raises(RuntimeError):
            resume()

    def test_restart_no_adj_dir_raises(self, monkeypatch):
        monkeypatch.delenv("ADJ_DIR", raising=False)
        with pytest.raises(RuntimeError):
            restart()

    def test_emergency_kill_no_adj_dir_raises(self, monkeypatch):
        monkeypatch.delenv("ADJ_DIR", raising=False)
        with pytest.raises(RuntimeError):
            emergency_kill()

    def test_startup_no_adj_dir_raises(self, monkeypatch):
        monkeypatch.delenv("ADJ_DIR", raising=False)
        with pytest.raises(RuntimeError):
            startup()
