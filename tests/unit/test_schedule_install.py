"""Unit tests for adjutant.capabilities.schedule.install."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from adjutant.capabilities.schedule.install import (
    _marker,
    _resolve_path,
    _resolve_command,
    _read_crontab,
    _write_crontab,
    install_all,
    install_one,
    uninstall_one,
    run_now,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_adjutant_yaml(adj_dir: Path, schedules: list[dict]) -> None:
    import yaml

    (adj_dir / "adjutant.yaml").parent.mkdir(parents=True, exist_ok=True)
    data = {"schedules": schedules}
    with open(adj_dir / "adjutant.yaml", "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)


def _make_proc(returncode=0, stdout="", stderr=""):
    m = MagicMock()
    m.returncode = returncode
    m.stdout = stdout
    m.stderr = stderr
    return m


# ---------------------------------------------------------------------------
# _marker
# ---------------------------------------------------------------------------


class TestMarker:
    def test_format(self) -> None:
        assert _marker("myjob") == "# adjutant:myjob"

    def test_job_name_in_marker(self) -> None:
        assert "daily-fetch" in _marker("daily-fetch")


# ---------------------------------------------------------------------------
# _resolve_path
# ---------------------------------------------------------------------------


class TestResolvePath:
    def test_absolute_unchanged(self, tmp_path: Path) -> None:
        assert _resolve_path("/abs/path", tmp_path) == "/abs/path"

    def test_relative_prepended(self, tmp_path: Path) -> None:
        assert _resolve_path("scripts/run.sh", tmp_path) == str(tmp_path / "scripts/run.sh")


# ---------------------------------------------------------------------------
# _resolve_command
# ---------------------------------------------------------------------------


class TestResolveCommand:
    def test_kb_command(self, tmp_path: Path) -> None:
        entry = {"kb_name": "mydb", "kb_operation": "fetch"}
        result = _resolve_command(entry, tmp_path)
        assert "run.sh" in result
        assert "mydb" in result
        assert "fetch" in result

    def test_script_command(self, tmp_path: Path) -> None:
        entry = {"script": "/scripts/run.sh"}
        assert _resolve_command(entry, tmp_path) == "/scripts/run.sh"

    def test_empty_when_no_command(self, tmp_path: Path) -> None:
        assert _resolve_command({}, tmp_path) == ""


# ---------------------------------------------------------------------------
# _read_crontab / _write_crontab
# ---------------------------------------------------------------------------


class TestReadCrontab:
    def test_returns_stdout_on_success(self) -> None:
        with patch("subprocess.run", return_value=_make_proc(0, "* * * * * /cmd\n")):
            assert _read_crontab() == "* * * * * /cmd\n"

    def test_returns_empty_on_failure(self) -> None:
        with patch("subprocess.run", return_value=_make_proc(1)):
            assert _read_crontab() == ""


class TestWriteCrontab:
    def test_calls_crontab_dash(self) -> None:
        with patch("subprocess.run", return_value=_make_proc(0)) as mock_run:
            _write_crontab("* * * * * /cmd\n")
        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert args == ["crontab", "-"]

    def test_clears_crontab_when_empty(self) -> None:
        with patch("subprocess.run", return_value=_make_proc(0)) as mock_run:
            _write_crontab("   \n  ")
        args = mock_run.call_args[0][0]
        assert args == ["crontab", "-r"]

    def test_raises_on_write_failure(self) -> None:
        with patch("subprocess.run", return_value=_make_proc(1, stderr="no permission")):
            with pytest.raises(RuntimeError, match="no permission"):
                _write_crontab("* * * * * /cmd\n")


# ---------------------------------------------------------------------------
# install_all
# ---------------------------------------------------------------------------


class TestInstallAll:
    def test_installs_enabled_jobs(self, tmp_path: Path) -> None:
        _write_adjutant_yaml(
            tmp_path,
            [{"name": "job1", "schedule": "* * * * *", "enabled": True, "script": "/run.sh"}],
        )
        with (
            patch("adjutant.capabilities.schedule.install._read_crontab", return_value=""),
            patch("adjutant.capabilities.schedule.install._write_crontab") as mock_write,
        ):
            install_all(tmp_path)
        mock_write.assert_called_once()
        written = mock_write.call_args[0][0]
        assert "# adjutant:job1" in written

    def test_uninstalls_disabled_jobs(self, tmp_path: Path) -> None:
        _write_adjutant_yaml(
            tmp_path,
            [{"name": "job1", "schedule": "* * * * *", "enabled": False, "script": "/run.sh"}],
        )
        existing = "* * * * * /other  # adjutant:job1\n"
        with (
            patch(
                "adjutant.capabilities.schedule.install._read_crontab",
                return_value=existing,
            ),
            patch("adjutant.capabilities.schedule.install._write_crontab") as mock_write,
        ):
            install_all(tmp_path)
        written = mock_write.call_args[0][0]
        assert "# adjutant:job1" not in written

    def test_skips_entries_without_name(self, tmp_path: Path) -> None:
        _write_adjutant_yaml(
            tmp_path,
            [{"schedule": "* * * * *", "enabled": True, "script": "/run.sh"}],
        )
        # Should not crash
        with (
            patch("adjutant.capabilities.schedule.install._read_crontab", return_value=""),
            patch("adjutant.capabilities.schedule.install._write_crontab"),
        ):
            install_all(tmp_path)


# ---------------------------------------------------------------------------
# install_one
# ---------------------------------------------------------------------------


class TestInstallOne:
    def test_installs_job(self, tmp_path: Path) -> None:
        _write_adjutant_yaml(
            tmp_path,
            [
                {
                    "name": "job1",
                    "schedule": "0 9 * * *",
                    "enabled": True,
                    "script": "/scripts/run.sh",
                    "log": "state/job1.log",
                }
            ],
        )
        with (
            patch("adjutant.capabilities.schedule.install._read_crontab", return_value=""),
            patch("adjutant.capabilities.schedule.install._write_crontab") as mock_write,
        ):
            install_one(tmp_path, "job1")
        written = mock_write.call_args[0][0]
        assert "# adjutant:job1" in written
        assert "0 9 * * *" in written
        assert "/scripts/run.sh" in written

    def test_replaces_existing_entry(self, tmp_path: Path) -> None:
        _write_adjutant_yaml(
            tmp_path,
            [
                {
                    "name": "job1",
                    "schedule": "0 10 * * *",
                    "script": "/new_script.sh",
                    "log": "state/job1.log",
                    "enabled": True,
                }
            ],
        )
        existing = "0 9 * * * /old_script.sh >> state/job1.log 2>&1  # adjutant:job1\n"
        with (
            patch(
                "adjutant.capabilities.schedule.install._read_crontab",
                return_value=existing,
            ),
            patch("adjutant.capabilities.schedule.install._write_crontab") as mock_write,
        ):
            install_one(tmp_path, "job1")
        written = mock_write.call_args[0][0]
        assert "0 10 * * *" in written
        assert "0 9 * * *" not in written

    def test_raises_when_job_not_found(self, tmp_path: Path) -> None:
        _write_adjutant_yaml(tmp_path, [])
        with pytest.raises(ValueError, match="ghost"):
            install_one(tmp_path, "ghost")

    def test_raises_when_no_command(self, tmp_path: Path) -> None:
        _write_adjutant_yaml(
            tmp_path,
            [{"name": "job1", "schedule": "* * * * *", "enabled": True}],
        )
        with (
            patch("adjutant.capabilities.schedule.install._read_crontab", return_value=""),
            patch("adjutant.capabilities.schedule.install._write_crontab"),
        ):
            with pytest.raises(ValueError, match="no runnable"):
                install_one(tmp_path, "job1")

    def test_notify_wraps_command(self, tmp_path: Path) -> None:
        _write_adjutant_yaml(
            tmp_path,
            [
                {
                    "name": "job1",
                    "schedule": "0 9 * * *",
                    "script": "/run.sh",
                    "notify": True,
                    "log": "state/job1.log",
                    "enabled": True,
                }
            ],
        )
        with (
            patch("adjutant.capabilities.schedule.install._read_crontab", return_value=""),
            patch("adjutant.capabilities.schedule.install._write_crontab") as mock_write,
        ):
            install_one(tmp_path, "job1")
        written = mock_write.call_args[0][0]
        assert "notify_wrap.py" in written
        assert "python3" in written


# ---------------------------------------------------------------------------
# uninstall_one
# ---------------------------------------------------------------------------


class TestUninstallOne:
    def test_removes_existing_entry(self, tmp_path: Path) -> None:
        existing = "0 9 * * * /run.sh  # adjutant:job1\n30 * * * * /other.sh  # adjutant:job2\n"
        with (
            patch(
                "adjutant.capabilities.schedule.install._read_crontab",
                return_value=existing,
            ),
            patch("adjutant.capabilities.schedule.install._write_crontab") as mock_write,
        ):
            uninstall_one(tmp_path, "job1")
        written = mock_write.call_args[0][0]
        assert "# adjutant:job1" not in written
        assert "# adjutant:job2" in written

    def test_noop_when_not_present(self, tmp_path: Path) -> None:
        existing = "0 9 * * * /run.sh  # adjutant:other\n"
        with (
            patch(
                "adjutant.capabilities.schedule.install._read_crontab",
                return_value=existing,
            ),
            patch("adjutant.capabilities.schedule.install._write_crontab") as mock_write,
        ):
            uninstall_one(tmp_path, "ghost")
        mock_write.assert_not_called()

    def test_clears_crontab_when_last_entry_removed(self, tmp_path: Path) -> None:
        existing = "0 9 * * * /run.sh  # adjutant:job1\n"
        with (
            patch(
                "adjutant.capabilities.schedule.install._read_crontab",
                return_value=existing,
            ),
            patch("adjutant.capabilities.schedule.install._write_crontab") as mock_write,
        ):
            uninstall_one(tmp_path, "job1")
        written = mock_write.call_args[0][0]
        assert written == ""


# ---------------------------------------------------------------------------
# run_now
# ---------------------------------------------------------------------------


class TestRunNow:
    def test_raises_when_not_found(self, tmp_path: Path) -> None:
        _write_adjutant_yaml(tmp_path, [])
        with pytest.raises(ValueError, match="ghost"):
            run_now(tmp_path, "ghost")

    def test_raises_when_no_command(self, tmp_path: Path) -> None:
        _write_adjutant_yaml(tmp_path, [{"name": "job1", "schedule": "* * * * *"}])
        with pytest.raises(ValueError, match="no runnable"):
            run_now(tmp_path, "job1")

    def test_runs_script_and_returns_rc(self, tmp_path: Path) -> None:
        script = tmp_path / "run.sh"
        script.write_text("#!/bin/bash\nexit 0\n")
        script.chmod(0o755)
        _write_adjutant_yaml(
            tmp_path,
            [{"name": "job1", "schedule": "* * * * *", "script": str(script)}],
        )
        with patch("subprocess.run", return_value=_make_proc(0)) as mock_run:
            rc = run_now(tmp_path, "job1")
        assert rc == 0
        mock_run.assert_called_once()

    def test_raises_when_script_not_found(self, tmp_path: Path) -> None:
        _write_adjutant_yaml(
            tmp_path,
            [{"name": "job1", "schedule": "* * * * *", "script": "/nonexistent/run.sh"}],
        )
        with pytest.raises(ValueError, match="not found"):
            run_now(tmp_path, "job1")

    def test_runs_kb_command_via_shell(self, tmp_path: Path) -> None:
        _write_adjutant_yaml(
            tmp_path,
            [
                {
                    "name": "job1",
                    "schedule": "* * * * *",
                    "kb_name": "mydb",
                    "kb_operation": "fetch",
                }
            ],
        )
        with patch("subprocess.run", return_value=_make_proc(0)) as mock_run:
            rc = run_now(tmp_path, "job1")
        assert rc == 0
        # shell=True for kb commands
        kwargs = mock_run.call_args[1]
        assert kwargs.get("shell") is True

    def test_raises_when_script_not_executable(self, tmp_path: Path) -> None:
        script = tmp_path / "run.sh"
        script.write_text("#!/bin/bash\n")
        script.chmod(0o644)  # not executable
        _write_adjutant_yaml(
            tmp_path,
            [{"name": "job1", "schedule": "* * * * *", "script": str(script)}],
        )
        with pytest.raises(ValueError, match="not executable"):
            run_now(tmp_path, "job1")
