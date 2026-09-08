"""Tests for src/adjutant/cli.py — Click CLI entry point.

Smoke-tests every top-level command and subcommand group to verify
that Click wiring, lazy imports, and --help output work correctly.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from adjutant.cli import main


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture()
def adj_dir(tmp_path: Path) -> Path:
    """Create a minimal adj_dir with required files."""
    d = tmp_path / "adj"
    d.mkdir()
    (d / ".adjutant-root").touch()
    (d / "adjutant.yaml").write_text("instance:\n  name: test\n")
    (d / ".env").write_text("TELEGRAM_BOT_TOKEN=test\nTELEGRAM_CHAT_ID=123\n")
    (d / "state").mkdir()
    return d


# ---------------------------------------------------------------------------
# Version and help
# ---------------------------------------------------------------------------


class TestVersionAndHelp:
    def test_version(self, runner: CliRunner) -> None:
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert "0.2.0" in result.output

    def test_help(self, runner: CliRunner) -> None:
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "adjutant" in result.output.lower()


# ---------------------------------------------------------------------------
# Top-level command --help smoke tests
# ---------------------------------------------------------------------------


class TestCommandHelp:
    """Verify every top-level command responds to --help without crashing."""

    @pytest.mark.parametrize(
        "cmd",
        [
            "status",
            "pulse",
            "review",
            "rotate",
            "reply",
            "notify",
            "update",
            "setup",
            "uninstall",
            "start",
            "stop",
            "restart",
            "pause",
            "resume",
            "kill",
            "startup",
            "screenshot",
            "search",
            "news",
            "logs",
            "doctor",
        ],
    )
    def test_command_help(self, runner: CliRunner, cmd: str) -> None:
        result = runner.invoke(main, [cmd, "--help"])
        assert result.exit_code == 0, f"{cmd} --help failed: {result.output}"


# ---------------------------------------------------------------------------
# Subcommand group --help smoke tests
# ---------------------------------------------------------------------------


class TestSubcommandGroupHelp:
    """Verify subcommand groups respond to --help."""

    @pytest.mark.parametrize(
        "group,subcmd",
        [
            ("kb", "list"),
            ("kb", "create"),
            ("kb", "remove"),
            ("kb", "info"),
            ("kb", "query"),
            ("kb", "run"),
            ("schedule", "add"),
            ("schedule", "list"),
            ("schedule", "enable"),
            ("schedule", "disable"),
            ("schedule", "remove"),
            ("schedule", "sync"),
            ("schedule", "run"),
        ],
    )
    def test_subcommand_help(self, runner: CliRunner, group: str, subcmd: str) -> None:
        result = runner.invoke(main, [group, subcmd, "--help"])
        assert result.exit_code == 0, f"{group} {subcmd} --help failed: {result.output}"


# ---------------------------------------------------------------------------
# Status command (functional test with mock adj_dir)
# ---------------------------------------------------------------------------


class TestStatusCommand:
    def test_status_runs(self, runner: CliRunner, adj_dir: Path, monkeypatch) -> None:
        monkeypatch.setenv("ADJ_DIR", str(adj_dir))
        monkeypatch.setenv("ADJUTANT_HOME", str(adj_dir))
        result = runner.invoke(main, ["status"])
        # Should succeed or show operational status
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Schedule commands
# ---------------------------------------------------------------------------


class TestScheduleCommands:
    @staticmethod
    def _write_schedule(adj_dir: Path, *, enabled: bool = False) -> None:
        (adj_dir / "adjutant.yaml").write_text(
            "schedules:\n"
            "  - name: job1\n"
            "    schedule: '* * * * *'\n"
            "    script: /run.sh\n"
            f"    enabled: {str(enabled).lower()}\n"
        )

    def test_enable_passes_adj_dir_for_crontab_install(
        self, runner: CliRunner, adj_dir: Path, monkeypatch
    ) -> None:
        monkeypatch.setenv("ADJ_DIR", str(adj_dir))
        monkeypatch.chdir(adj_dir)
        self._write_schedule(adj_dir)
        with patch("adjutant.capabilities.schedule.install.install_one") as install_one:
            result = runner.invoke(main, ["schedule", "enable", "job1"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "enabled: true" in (adj_dir / "adjutant.yaml").read_text()
        install_one.assert_called_once_with(adj_dir, "job1")

    def test_enable_while_paused_defers_crontab_install(
        self, runner: CliRunner, adj_dir: Path, monkeypatch
    ) -> None:
        monkeypatch.setenv("ADJ_DIR", str(adj_dir))
        monkeypatch.chdir(adj_dir)
        self._write_schedule(adj_dir)
        (adj_dir / "PAUSED").touch()
        with patch("adjutant.capabilities.schedule.install.uninstall_one") as uninstall_one:
            result = runner.invoke(main, ["schedule", "enable", "job1"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "will be restored on resume" in result.output
        uninstall_one.assert_called_once_with(adj_dir, "job1")

    def test_disable_passes_adj_dir_for_crontab_removal(
        self, runner: CliRunner, adj_dir: Path, monkeypatch
    ) -> None:
        monkeypatch.setenv("ADJ_DIR", str(adj_dir))
        monkeypatch.chdir(adj_dir)
        self._write_schedule(adj_dir, enabled=True)
        with patch("adjutant.capabilities.schedule.install.uninstall_one") as uninstall_one:
            result = runner.invoke(main, ["schedule", "disable", "job1"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "enabled: false" in (adj_dir / "adjutant.yaml").read_text()
        uninstall_one.assert_called_once_with(adj_dir, "job1")

    def test_remove_passes_adj_dir_for_crontab_removal(
        self, runner: CliRunner, adj_dir: Path, monkeypatch
    ) -> None:
        monkeypatch.setenv("ADJ_DIR", str(adj_dir))
        monkeypatch.chdir(adj_dir)
        self._write_schedule(adj_dir, enabled=True)
        with patch("adjutant.capabilities.schedule.install.uninstall_one") as uninstall_one:
            result = runner.invoke(main, ["schedule", "remove", "job1"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "job1" not in (adj_dir / "adjutant.yaml").read_text()
        uninstall_one.assert_called_once_with(adj_dir, "job1")

    def test_sync_while_paused_reports_managed_entries_disabled(
        self, runner: CliRunner, adj_dir: Path, monkeypatch
    ) -> None:
        monkeypatch.setenv("ADJ_DIR", str(adj_dir))
        monkeypatch.chdir(adj_dir)
        (adj_dir / "PAUSED").touch()
        with patch("adjutant.capabilities.schedule.install.install_all") as install_all:
            result = runner.invoke(main, ["schedule", "sync"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "managed crontab entries remain disabled" in result.output
        install_all.assert_called_once_with(adj_dir)


# ---------------------------------------------------------------------------
# Doctor command (functional test)
# ---------------------------------------------------------------------------


class TestDoctorCommand:
    def test_doctor_runs(self, runner: CliRunner, adj_dir: Path, monkeypatch) -> None:
        monkeypatch.setenv("ADJ_DIR", str(adj_dir))
        monkeypatch.setenv("ADJUTANT_HOME", str(adj_dir))
        result = runner.invoke(main, ["doctor"])
        # Doctor should run without crashing (may report issues)
        assert result.exit_code in (0, 1)
