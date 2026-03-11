"""Tests for adjutant.core.lockfiles — KILLED/PAUSED state management."""

from __future__ import annotations

from pathlib import Path

import pytest

from adjutant.core.lockfiles import (
    check_killed,
    check_operational,
    check_paused,
    clear_killed,
    clear_paused,
    is_killed,
    is_operational,
    is_paused,
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
