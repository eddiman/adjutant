"""Tests for adjutant.core.process — PidLock, kill_graceful, pid_is_alive, read_pid_file."""

from __future__ import annotations

import os
import signal
import subprocess
from pathlib import Path
from unittest.mock import patch

import psutil
import pytest

from adjutant.core.process import (
    PidLock,
    find_by_cmdline,
    kill_graceful,
    kill_process_tree,
    pid_is_alive,
    read_pid_file,
)


class TestPidLock:
    """Test PidLock — mkdir-based atomic locking."""

    def test_acquire_and_release(self, tmp_path: Path):
        lock = PidLock(tmp_path / "test.lock")
        assert lock.acquire() is True
        assert lock.lock_dir.exists()
        assert lock.pid_file.read_text().strip() == str(os.getpid())
        lock.release()
        assert not lock.lock_dir.exists()

    def test_double_acquire_same_process(self, tmp_path: Path):
        """Second acquire from same process (PID alive) returns False."""
        lock = PidLock(tmp_path / "test.lock")
        assert lock.acquire() is True
        lock2 = PidLock(tmp_path / "test.lock")
        assert lock2.acquire() is False
        lock.release()

    def test_stale_lock_recovery(self, tmp_path: Path):
        """If lock holder PID is dead, recover the lock."""
        lock_dir = tmp_path / "test.lock"
        lock_dir.mkdir()
        (lock_dir / "pid").write_text("99999999")  # Non-existent PID
        lock = PidLock(lock_dir)
        assert lock.acquire() is True
        assert lock.pid_file.read_text().strip() == str(os.getpid())
        lock.release()

    def test_held_pid_returns_current(self, tmp_path: Path):
        lock = PidLock(tmp_path / "test.lock")
        lock.acquire()
        assert lock.held_pid == os.getpid()
        lock.release()

    def test_held_pid_returns_none_when_not_locked(self, tmp_path: Path):
        lock = PidLock(tmp_path / "test.lock")
        assert lock.held_pid is None

    def test_held_pid_returns_none_for_stale(self, tmp_path: Path):
        lock_dir = tmp_path / "test.lock"
        lock_dir.mkdir()
        (lock_dir / "pid").write_text("99999999")
        lock = PidLock(lock_dir)
        assert lock.held_pid is None

    def test_release_nonexistent_is_safe(self, tmp_path: Path):
        lock = PidLock(tmp_path / "test.lock")
        lock.release()  # Should not raise


class TestPidIsAlive:
    """Test pid_is_alive() — kill -0 replacement."""

    def test_current_process_is_alive(self):
        assert pid_is_alive(os.getpid()) is True

    def test_nonexistent_pid_is_not_alive(self):
        assert pid_is_alive(99999999) is False

    def test_permission_error_means_alive(self):
        """PermissionError from kill(pid, 0) means process exists."""
        with patch("adjutant.core.process.os.kill", side_effect=PermissionError):
            assert pid_is_alive(1) is True


class TestReadPidFile:
    """Test read_pid_file() — PID file reading with liveness check."""

    def test_valid_pid_file_alive(self, tmp_path: Path):
        pid_file = tmp_path / "test.pid"
        pid_file.write_text(str(os.getpid()))
        assert read_pid_file(pid_file) == os.getpid()

    def test_stale_pid_returns_none(self, tmp_path: Path):
        pid_file = tmp_path / "test.pid"
        pid_file.write_text("99999999")
        assert read_pid_file(pid_file) is None

    def test_missing_file_returns_none(self, tmp_path: Path):
        assert read_pid_file(tmp_path / "nonexistent.pid") is None

    def test_invalid_content_returns_none(self, tmp_path: Path):
        pid_file = tmp_path / "test.pid"
        pid_file.write_text("not-a-number")
        assert read_pid_file(pid_file) is None

    def test_empty_file_returns_none(self, tmp_path: Path):
        pid_file = tmp_path / "test.pid"
        pid_file.write_text("")
        assert read_pid_file(pid_file) is None


class TestKillGraceful:
    """Test kill_graceful() — TERM→KILL two-phase shutdown."""

    def test_kill_nonexistent_returns_false(self):
        assert kill_graceful(99999999) is False

    def test_kill_real_process(self):
        """Spawn a sleep process and kill it gracefully."""
        proc = subprocess.Popen(["sleep", "60"])
        result = kill_graceful(proc.pid)
        assert result is True
        # Process should be gone
        assert not pid_is_alive(proc.pid)
        # Clean up zombie
        proc.wait()


class TestKillProcessTree:
    """Test kill_process_tree() — parent + children termination."""

    def test_kill_nonexistent_is_safe(self):
        """kill_process_tree on non-existent PID should not raise."""
        kill_process_tree(99999999)

    def test_kill_tree_with_child(self):
        """Spawn a parent with a child and kill the tree."""
        parent = subprocess.Popen(
            ["bash", "-c", "sleep 60 & wait"],
        )
        # Give child time to spawn
        import time

        time.sleep(0.3)
        kill_process_tree(parent.pid)
        parent.wait()
        assert not pid_is_alive(parent.pid)


class TestFindByCmdline:
    """Test find_by_cmdline() — pgrep -f replacement."""

    def test_excludes_current_process(self):
        """Should not find itself."""
        results = find_by_cmdline("python")
        pids = [p.pid for p in results]
        assert os.getpid() not in pids

    def test_no_match(self):
        results = find_by_cmdline("this_process_definitely_does_not_exist_xyz_123")
        assert results == []
