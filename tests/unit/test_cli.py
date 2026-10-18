"""Tests for src/adjutant/cli.py — Click CLI entry point.

Smoke-tests every top-level command and subcommand group to verify
that Click wiring, lazy imports, and --help output work correctly.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from adjutant.cli import _inline_termination_guard, main

if TYPE_CHECKING:
    from pathlib import Path


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
        assert result.exit_code == 0, result.output
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


class TestStartCommand:
    def test_start_uses_full_runtime_lifecycle(
        self, runner: CliRunner, adj_dir: Path, monkeypatch
    ) -> None:
        monkeypatch.setenv("ADJ_DIR", str(adj_dir))
        monkeypatch.setenv("ADJUTANT_HOME", str(adj_dir))
        with patch(
            "adjutant.lifecycle.control.start",
            return_value="Operation worker started\nTelegram listener started",
        ) as start_services:
            result = runner.invoke(main, ["start"])

        assert result.exit_code == 0, result.output
        start_services.assert_called_once_with(adj_dir)
        assert "Operation worker started" in result.output
        assert "Telegram listener started" in result.output


class TestDurableKbCli:
    def test_inline_sigterm_guard_restores_handler_after_unwind(self) -> None:
        previous = object()
        installed = []

        with (
            patch("adjutant.cli.signal.getsignal", return_value=previous),
            patch(
                "adjutant.cli.signal.signal",
                side_effect=lambda sig, handler: installed.append((sig, handler)),
            ),
            pytest.raises(KeyboardInterrupt, match="SIGTERM"),
            _inline_termination_guard(),
        ):
            installed[-1][1](None, None)

        assert installed[-1][1] is previous

    def test_query_flushes_acceptance_receipt_before_result(
        self, runner: CliRunner, adj_dir: Path, monkeypatch
    ) -> None:
        monkeypatch.setenv("ADJ_DIR", str(adj_dir))

        async def fake_query(_name, _query, _adj_dir, *, receipt_callback=None, **_kwargs):
            assert receipt_callback is not None
            receipt_callback(SimpleNamespace(id="op-child"))
            return "answer"

        with patch("adjutant.capabilities.kb.query.kb_query", side_effect=fake_query):
            result = runner.invoke(main, ["kb", "query", "notes", "Question?"])

        assert result.exit_code == 0
        assert result.output.index("accepted_operation_id") < result.output.index("answer")
        assert "op-child" in result.output

    def test_operation_context_returns_remaining_owned_budget(
        self, runner: CliRunner, adj_dir: Path, monkeypatch
    ) -> None:
        from adjutant.operations.models import OperationState
        from adjutant.operations.store import OperationStore

        monkeypatch.setenv("ADJ_DIR", str(adj_dir))
        monkeypatch.setenv("ADJUTANT_HOME", str(adj_dir))
        store = OperationStore(adj_dir)
        operation = store.create_operation(kind="prompt", source="test", payload={})
        claimed = store.claim_next("worker", lease_seconds=60)
        assert claimed is not None
        attempt = store.start_attempt(claimed, "worker", runtime_seconds=120)
        store.transition(
            operation.id,
            OperationState.RUNNING,
            worker_id="worker",
            lease_seconds=60,
            expected_attempt_id=attempt.id,
        )

        result = runner.invoke(main, ["operation-context", operation.id])

        assert result.exit_code == 0, f"{result.output}\n{result.exception!r}"
        payload = __import__("json").loads(result.output)
        assert payload["operation_id"] == operation.id
        assert payload["attempt_id"] == attempt.id
        assert 100_000 < payload["timeout_ms"] <= 120_000


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
