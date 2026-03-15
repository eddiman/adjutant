"""Integration tests for Telegram listener lifecycle.

Tests process spawning, PID lock acquisition, and clean shutdown.
External services (Telegram API, opencode) are mocked.
"""

from __future__ import annotations

import os
import signal
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


pytestmark = pytest.mark.integration


class TestPidLock:
    """Test PID lock file management."""

    def test_lock_created_on_acquire(self, adj_dir: Path) -> None:
        from adjutant.core.process import PidLock

        lock_dir = adj_dir / "state" / "listener.lock"
        lock = PidLock(lock_dir)
        assert lock.acquire()
        assert lock_dir.is_dir()
        assert (lock_dir / "pid").is_file()
        pid = int((lock_dir / "pid").read_text().strip())
        assert pid == os.getpid()
        lock.release()

    def test_lock_released_on_release(self, adj_dir: Path) -> None:
        from adjutant.core.process import PidLock

        lock_dir = adj_dir / "state" / "listener.lock"
        lock = PidLock(lock_dir)
        lock.acquire()
        lock.release()
        assert not lock_dir.is_dir()

    def test_second_acquire_fails_when_held(self, adj_dir: Path) -> None:
        from adjutant.core.process import PidLock

        lock_dir = adj_dir / "state" / "listener.lock"
        lock1 = PidLock(lock_dir)
        lock2 = PidLock(lock_dir)
        assert lock1.acquire()
        assert not lock2.acquire()
        lock1.release()

    def test_stale_lock_from_dead_pid_is_reclaimed(self, adj_dir: Path) -> None:
        from adjutant.core.process import PidLock

        lock_dir = adj_dir / "state" / "listener.lock"
        lock_dir.mkdir(parents=True, exist_ok=True)
        # Write a PID that definitely doesn't exist
        (lock_dir / "pid").write_text("999999999\n")

        lock = PidLock(lock_dir)
        assert lock.acquire()
        lock.release()


class TestKilledLockfile:
    """Test KILLED lockfile behaviour."""

    def test_is_killed_returns_false_by_default(self, adj_dir: Path) -> None:
        from adjutant.core.lockfiles import is_killed

        assert not is_killed(adj_dir)

    def test_is_killed_returns_true_when_file_exists(self, adj_dir: Path) -> None:
        from adjutant.core.lockfiles import is_killed

        (adj_dir / "KILLED").touch()
        assert is_killed(adj_dir)

    def test_check_killed_returns_false_when_killed(self, adj_dir: Path) -> None:
        from adjutant.core.lockfiles import check_killed

        (adj_dir / "KILLED").touch()
        assert check_killed(adj_dir) is False

    def test_check_killed_returns_true_when_not_killed(self, adj_dir: Path) -> None:
        from adjutant.core.lockfiles import check_killed

        assert check_killed(adj_dir) is True


class TestListenerStartup:
    """Test listener startup sequence without actually polling Telegram."""

    def test_exits_when_killed(self, adj_dir: Path) -> None:
        """Listener should exit immediately if KILLED lockfile is present."""
        (adj_dir / "KILLED").touch()

        with patch.dict(os.environ, {"ADJ_DIR": str(adj_dir)}):
            from adjutant.messaging.telegram.listener import main

            with pytest.raises(SystemExit):
                import asyncio

                asyncio.run(main())

    def test_exits_when_no_credentials(self, adj_dir: Path) -> None:
        """Listener should exit if .env is missing credentials."""
        (adj_dir / ".env").write_text("")  # empty .env

        with patch.dict(os.environ, {"ADJ_DIR": str(adj_dir)}):
            from adjutant.messaging.telegram.listener import main

            with pytest.raises(SystemExit):
                import asyncio

                asyncio.run(main())


class TestServicePlist:
    """Test plist generation content."""

    def test_plist_has_unconditional_keepalive(self, adj_dir: Path) -> None:
        from adjutant.setup.steps.service import _LAUNCHD_PLIST

        plist = _LAUNCHD_PLIST.format(python="/usr/bin/python3", adj_dir=str(adj_dir))
        assert "<key>KeepAlive</key>" in plist
        assert "<true/>" in plist.split("<key>KeepAlive</key>")[1].split("</dict>")[0]
        # Ensure SuccessfulExit is NOT present
        assert "SuccessfulExit" not in plist

    def test_plist_has_throttle_interval(self, adj_dir: Path) -> None:
        from adjutant.setup.steps.service import _LAUNCHD_PLIST

        plist = _LAUNCHD_PLIST.format(python="/usr/bin/python3", adj_dir=str(adj_dir))
        assert "<key>ThrottleInterval</key>" in plist
        assert "<integer>30</integer>" in plist

    def test_plist_sets_adj_dir_not_adjutant_home(self, adj_dir: Path) -> None:
        from adjutant.setup.steps.service import _LAUNCHD_PLIST

        plist = _LAUNCHD_PLIST.format(python="/usr/bin/python3", adj_dir=str(adj_dir))
        assert "<key>ADJ_DIR</key>" in plist
        assert "ADJUTANT_HOME" not in plist

    def test_plist_has_working_directory(self, adj_dir: Path) -> None:
        from adjutant.setup.steps.service import _LAUNCHD_PLIST

        plist = _LAUNCHD_PLIST.format(python="/usr/bin/python3", adj_dir=str(adj_dir))
        assert "<key>WorkingDirectory</key>" in plist

    def test_plist_uses_python_not_bash(self, adj_dir: Path) -> None:
        from adjutant.setup.steps.service import _LAUNCHD_PLIST

        plist = _LAUNCHD_PLIST.format(python="/usr/bin/python3", adj_dir=str(adj_dir))
        assert "listener.sh" not in plist
        assert "adjutant.messaging.telegram.listener" in plist
