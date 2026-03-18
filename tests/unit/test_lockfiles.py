"""Tests for adjutant.core.lockfiles — KILLED/PAUSED state and active operation tracking."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from adjutant.core.lockfiles import (
    check_killed,
    check_operational,
    check_paused,
    clear_active_operation,
    clear_killed,
    clear_paused,
    get_active_operation,
    is_killed,
    is_operational,
    is_paused,
    set_active_operation,
    set_killed,
    set_paused,
)


class TestSetAndClear:
    """Test state mutation functions."""

    def test_set_paused_creates_file(self, adj_dir: Path):
        assert not (adj_dir / "PAUSED").exists()
        set_paused(adj_dir)
        assert (adj_dir / "PAUSED").exists()

    def test_clear_paused_removes_file(self, adj_dir: Path):
        set_paused(adj_dir)
        clear_paused(adj_dir)
        assert not (adj_dir / "PAUSED").exists()

    def test_clear_paused_no_error_if_missing(self, adj_dir: Path):
        """clear_paused doesn't raise if file doesn't exist."""
        clear_paused(adj_dir)  # Should not raise

    def test_set_killed_creates_file(self, adj_dir: Path):
        assert not (adj_dir / "KILLED").exists()
        set_killed(adj_dir)
        assert (adj_dir / "KILLED").exists()

    def test_clear_killed_removes_file(self, adj_dir: Path):
        set_killed(adj_dir)
        clear_killed(adj_dir)
        assert not (adj_dir / "KILLED").exists()

    def test_clear_killed_no_error_if_missing(self, adj_dir: Path):
        clear_killed(adj_dir)  # Should not raise


class TestSilentBooleanQueries:
    """Test is_* functions — silent, no stderr output."""

    def test_is_killed_false_by_default(self, adj_dir: Path):
        assert is_killed(adj_dir) is False

    def test_is_killed_true_when_set(self, adj_dir: Path):
        set_killed(adj_dir)
        assert is_killed(adj_dir) is True

    def test_is_paused_false_by_default(self, adj_dir: Path):
        assert is_paused(adj_dir) is False

    def test_is_paused_true_when_set(self, adj_dir: Path):
        set_paused(adj_dir)
        assert is_paused(adj_dir) is True

    def test_is_operational_true_by_default(self, adj_dir: Path):
        assert is_operational(adj_dir) is True

    def test_is_operational_false_when_killed(self, adj_dir: Path):
        set_killed(adj_dir)
        assert is_operational(adj_dir) is False

    def test_is_operational_false_when_paused(self, adj_dir: Path):
        set_paused(adj_dir)
        assert is_operational(adj_dir) is False

    def test_is_operational_false_when_both(self, adj_dir: Path):
        set_killed(adj_dir)
        set_paused(adj_dir)
        assert is_operational(adj_dir) is False

    def test_is_queries_are_silent(self, adj_dir: Path, capsys):
        """is_* functions produce no stderr output."""
        set_killed(adj_dir)
        set_paused(adj_dir)
        is_killed(adj_dir)
        is_paused(adj_dir)
        is_operational(adj_dir)
        captured = capsys.readouterr()
        assert captured.err == ""
        assert captured.out == ""


class TestVerboseCheckFunctions:
    """Test check_* functions — emit stderr messages."""

    def test_check_killed_returns_true_when_not_killed(self, adj_dir: Path):
        assert check_killed(adj_dir) is True

    def test_check_killed_returns_false_with_stderr(self, adj_dir: Path, capsys):
        set_killed(adj_dir)
        assert check_killed(adj_dir) is False
        captured = capsys.readouterr()
        assert "KILLED lockfile exists" in captured.err
        assert "startup.sh" in captured.err

    def test_check_paused_returns_true_when_not_paused(self, adj_dir: Path):
        assert check_paused(adj_dir) is True

    def test_check_paused_returns_false_with_stderr(self, adj_dir: Path, capsys):
        set_paused(adj_dir)
        assert check_paused(adj_dir) is False
        captured = capsys.readouterr()
        assert "paused" in captured.err.lower()

    def test_check_operational_true_when_clean(self, adj_dir: Path):
        assert check_operational(adj_dir) is True

    def test_check_operational_false_when_killed(self, adj_dir: Path):
        set_killed(adj_dir)
        assert check_operational(adj_dir) is False

    def test_check_operational_false_when_paused(self, adj_dir: Path):
        set_paused(adj_dir)
        assert check_operational(adj_dir) is False

    def test_check_operational_killed_checked_before_paused(self, adj_dir: Path, capsys):
        """When both killed and paused, killed message appears (checked first)."""
        set_killed(adj_dir)
        set_paused(adj_dir)
        assert check_operational(adj_dir) is False
        captured = capsys.readouterr()
        assert "KILLED" in captured.err
        # Paused message should NOT appear because killed check fails first
        assert "paused" not in captured.err.lower()


class TestFullLifecycle:
    """Test complete state transitions."""

    def test_lifecycle(self, adj_dir: Path):
        """Full lifecycle: operational → paused → operational → killed → operational."""
        assert is_operational(adj_dir)

        set_paused(adj_dir)
        assert not is_operational(adj_dir)
        assert is_paused(adj_dir)

        clear_paused(adj_dir)
        assert is_operational(adj_dir)

        set_killed(adj_dir)
        assert not is_operational(adj_dir)
        assert is_killed(adj_dir)

        clear_killed(adj_dir)
        assert is_operational(adj_dir)

    def test_both_lockfiles_independent(self, adj_dir: Path):
        """Clearing one lockfile doesn't affect the other."""
        set_killed(adj_dir)
        set_paused(adj_dir)

        clear_paused(adj_dir)
        assert is_killed(adj_dir) is True
        assert is_paused(adj_dir) is False

    def test_uses_adj_dir_from_env(self, adj_dir: Path):
        """Functions work with default adj_dir from environment."""
        # adj_dir fixture sets ADJUTANT_HOME and ADJ_DIR
        set_paused()
        assert is_paused()
        clear_paused()
        assert not is_paused()


class TestActiveOperation:
    """Test active operation marker (state/active_operation.json)."""

    def test_set_creates_json_file(self, adj_dir: Path) -> None:
        set_active_operation("pulse", "cron", adj_dir=adj_dir)
        op_file = adj_dir / "state" / "active_operation.json"
        assert op_file.is_file()

        data = json.loads(op_file.read_text())
        assert data["action"] == "pulse"
        assert data["source"] == "cron"
        assert "started_at" in data
        assert data["pid"] == os.getpid()

    def test_get_returns_data_when_present(self, adj_dir: Path) -> None:
        set_active_operation("review", "telegram", adj_dir=adj_dir)
        data = get_active_operation(adj_dir=adj_dir)
        assert data is not None
        assert data["action"] == "review"
        assert data["source"] == "telegram"

    def test_get_returns_none_when_missing(self, adj_dir: Path) -> None:
        assert get_active_operation(adj_dir=adj_dir) is None

    def test_clear_removes_file(self, adj_dir: Path) -> None:
        set_active_operation("pulse", "mariposa", adj_dir=adj_dir)
        clear_active_operation(adj_dir=adj_dir)
        assert not (adj_dir / "state" / "active_operation.json").exists()

    def test_clear_no_error_if_missing(self, adj_dir: Path) -> None:
        clear_active_operation(adj_dir=adj_dir)  # Should not raise

    def test_get_returns_none_for_stale_marker_dead_pid(self, adj_dir: Path) -> None:
        """Marker older than 30 min with a dead PID should be cleaned up."""
        op_file = adj_dir / "state" / "active_operation.json"
        old_time = (datetime.now(UTC) - timedelta(minutes=45)).isoformat()
        op_file.write_text(
            json.dumps(
                {
                    "action": "pulse",
                    "started_at": old_time,
                    "pid": 999999999,  # Almost certainly not a running process
                    "source": "cron",
                }
            )
        )

        result = get_active_operation(adj_dir=adj_dir)
        assert result is None
        assert not op_file.exists(), "Stale marker should be deleted"

    def test_get_keeps_stale_marker_if_pid_alive(self, adj_dir: Path) -> None:
        """Marker older than 30 min but with alive PID should be kept."""
        op_file = adj_dir / "state" / "active_operation.json"
        old_time = (datetime.now(UTC) - timedelta(minutes=45)).isoformat()
        op_file.write_text(
            json.dumps(
                {
                    "action": "pulse",
                    "started_at": old_time,
                    "pid": os.getpid(),  # This process IS alive
                    "source": "cron",
                }
            )
        )

        result = get_active_operation(adj_dir=adj_dir)
        assert result is not None
        assert result["action"] == "pulse"

    def test_get_keeps_recent_marker(self, adj_dir: Path) -> None:
        """Marker less than 30 min old should always be kept."""
        set_active_operation("review", "telegram", adj_dir=adj_dir)
        result = get_active_operation(adj_dir=adj_dir)
        assert result is not None
        assert result["action"] == "review"

    def test_get_returns_none_for_corrupt_json(self, adj_dir: Path) -> None:
        """Corrupt JSON should return None."""
        op_file = adj_dir / "state" / "active_operation.json"
        op_file.write_text("not valid json {{{")
        assert get_active_operation(adj_dir=adj_dir) is None

    def test_set_overwrites_existing(self, adj_dir: Path) -> None:
        """Second set_active_operation should overwrite the first."""
        set_active_operation("pulse", "cron", adj_dir=adj_dir)
        set_active_operation("review", "telegram", adj_dir=adj_dir)
        data = get_active_operation(adj_dir=adj_dir)
        assert data is not None
        assert data["action"] == "review"
        assert data["source"] == "telegram"

    def test_set_creates_state_dir_if_missing(self, tmp_path: Path) -> None:
        """set_active_operation should create state/ if it doesn't exist."""
        bare_dir = tmp_path / "bare"
        bare_dir.mkdir()
        set_active_operation("pulse", "cron", adj_dir=bare_dir)
        assert (bare_dir / "state" / "active_operation.json").is_file()

    def test_uses_adj_dir_from_env(self, adj_dir: Path) -> None:
        """Functions work with default adj_dir from ADJ_DIR env var."""
        set_active_operation("pulse", "cron")
        data = get_active_operation()
        assert data is not None
        assert data["action"] == "pulse"
        clear_active_operation()
        assert get_active_operation() is None
