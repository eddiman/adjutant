"""Tests for src/adjutant/setup/repair.py"""

from __future__ import annotations

import os
import stat
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from adjutant.setup.repair import (
    _check_cli_executable,
    _check_config,
    _check_credentials,
    _check_dependencies,
    _check_env_permissions,
    _check_path,
    _check_required_dirs,
    _check_script_permissions,
    _file_octal_perms,
    _read_env_cred,
    run_repair,
)


class TestReadEnvCred:
    def test_returns_value(self, tmp_path: Path) -> None:
        env = tmp_path / ".env"
        env.write_text("TELEGRAM_BOT_TOKEN=12345:abc\n")
        assert _read_env_cred(env, "TELEGRAM_BOT_TOKEN") == "12345:abc"

    def test_strips_quotes(self, tmp_path: Path) -> None:
        env = tmp_path / ".env"
        env.write_text("TELEGRAM_BOT_TOKEN='12345:abc'\n")
        assert _read_env_cred(env, "TELEGRAM_BOT_TOKEN") == "12345:abc"

    def test_empty_when_missing(self, tmp_path: Path) -> None:
        env = tmp_path / ".env"
        env.write_text("OTHER=x\n")
        assert _read_env_cred(env, "TELEGRAM_BOT_TOKEN") == ""

    def test_empty_when_no_file(self, tmp_path: Path) -> None:
        assert _read_env_cred(tmp_path / ".env", "KEY") == ""


class TestFileOctalPerms:
    def test_returns_600(self, tmp_path: Path) -> None:
        f = tmp_path / "secret"
        f.write_text("x")
        f.chmod(0o600)
        assert _file_octal_perms(f) == "600"

    def test_returns_644(self, tmp_path: Path) -> None:
        f = tmp_path / "normal"
        f.write_text("x")
        f.chmod(0o644)
        assert _file_octal_perms(f) == "644"


class TestCheckConfig:
    def test_ok_when_config_exists(self, tmp_path: Path, capsys) -> None:
        (tmp_path / "adjutant.yaml").write_text("instance:\n  name: adj\n")
        found, fixed = _check_config(tmp_path, False, 0, 0)
        assert found == 0

    def test_increments_found_when_missing(self, tmp_path: Path, capsys) -> None:
        with patch("builtins.input", return_value="n"):
            found, fixed = _check_config(tmp_path, False, 0, 0)
        assert found == 1

    def test_creates_config_when_confirmed(self, tmp_path: Path, capsys) -> None:
        with patch("builtins.input", return_value="y"):
            found, fixed = _check_config(tmp_path, False, 0, 0)
        assert (tmp_path / "adjutant.yaml").is_file()
        assert fixed == 1

    def test_dry_run_does_not_create(self, tmp_path: Path, capsys) -> None:
        with patch("builtins.input", return_value="y"):
            _check_config(tmp_path, True, 0, 0)
        assert not (tmp_path / "adjutant.yaml").is_file()


class TestCheckCredentials:
    def test_ok_when_valid_creds(self, tmp_path: Path, capsys) -> None:
        env = tmp_path / ".env"
        env.write_text("TELEGRAM_BOT_TOKEN=12345:tok\nTELEGRAM_CHAT_ID=999\n")
        found, fixed = _check_credentials(tmp_path, False, 0, 0)
        assert found == 0

    def test_fail_when_no_env(self, tmp_path: Path, capsys) -> None:
        with patch("builtins.input", return_value="n"):
            found, fixed = _check_credentials(tmp_path, False, 0, 0)
        assert found == 1

    def test_fail_when_placeholder_values(self, tmp_path: Path, capsys) -> None:
        env = tmp_path / ".env"
        env.write_text(
            "TELEGRAM_BOT_TOKEN=your-bot-token-here\nTELEGRAM_CHAT_ID=your-chat-id-here\n"
        )
        with patch("builtins.input", return_value="n"):
            found, fixed = _check_credentials(tmp_path, False, 0, 0)
        assert found == 1


class TestCheckCliExecutable:
    def test_ok_when_executable(self, tmp_path: Path, capsys) -> None:
        cli = tmp_path / "adjutant"
        cli.write_text("#!/bin/bash")
        cli.chmod(0o755)
        found, fixed = _check_cli_executable(tmp_path, False, 0, 0)
        assert found == 0

    def test_fix_when_not_executable(self, tmp_path: Path, capsys) -> None:
        cli = tmp_path / "adjutant"
        cli.write_text("#!/bin/bash")
        cli.chmod(0o644)
        with patch("builtins.input", return_value="y"):
            found, fixed = _check_cli_executable(tmp_path, False, 0, 0)
        assert found == 1 and fixed == 1
        assert os.access(str(cli), os.X_OK)


class TestCheckRequiredDirs:
    def test_ok_when_all_exist(self, tmp_path: Path, capsys) -> None:
        for d in ["state", "journal", "identity", "prompts", "photos", "screenshots"]:
            (tmp_path / d).mkdir()
        found, fixed = _check_required_dirs(tmp_path, False, 0, 0)
        assert found == 0

    def test_creates_missing_dirs(self, tmp_path: Path, capsys) -> None:
        # Only create some
        (tmp_path / "state").mkdir()
        with patch("builtins.input", return_value="y"):
            found, fixed = _check_required_dirs(tmp_path, False, 0, 0)
        assert found > 0
        assert (tmp_path / "journal").is_dir()


class TestCheckDependencies:
    def test_ok_when_all_found(self) -> None:
        with patch("shutil.which", return_value="/usr/bin/cmd"):
            found = _check_dependencies(0)
        assert found == 0

    def test_increments_found_when_missing(self) -> None:
        def which_side(cmd):
            if cmd == "opencode":
                return None
            return f"/usr/bin/{cmd}"

        with patch("shutil.which", side_effect=which_side):
            found = _check_dependencies(0)
        assert found == 1


class TestCheckEnvPermissions:
    def test_ok_when_600(self, tmp_path: Path, capsys) -> None:
        env = tmp_path / ".env"
        env.write_text("SECRET=x")
        env.chmod(0o600)
        found, fixed = _check_env_permissions(tmp_path, False, 0, 0)
        assert found == 0

    def test_fix_when_not_600(self, tmp_path: Path, capsys) -> None:
        env = tmp_path / ".env"
        env.write_text("SECRET=x")
        env.chmod(0o644)
        with patch("builtins.input", return_value="y"):
            found, fixed = _check_env_permissions(tmp_path, False, 0, 0)
        assert found == 1 and fixed == 1
        assert stat.S_IMODE(env.stat().st_mode) == 0o600


class TestRunRepair:
    def test_runs_without_error_on_healthy_install(self, tmp_path: Path, capsys) -> None:
        # Create minimal healthy layout
        (tmp_path / "adjutant.yaml").write_text("instance:\n  name: adj\n")
        env = tmp_path / ".env"
        env.write_text("TELEGRAM_BOT_TOKEN=12345:tok\nTELEGRAM_CHAT_ID=999\n")
        env.chmod(0o600)
        for d in ["state", "journal", "identity", "prompts", "photos", "screenshots"]:
            (tmp_path / d).mkdir()
        cli = tmp_path / "adjutant"
        cli.write_text("#!/bin/bash")
        cli.chmod(0o755)

        with patch("shutil.which", return_value="/usr/bin/cmd"):
            with patch("adjutant.setup.repair._check_listener", return_value=(0, 0)):
                with patch(
                    "adjutant.setup.repair._check_scheduled_jobs",
                    return_value=(0, 0),
                ):
                    run_repair(tmp_path)

        out = capsys.readouterr().err
        assert "health" in out.lower() or "check" in out.lower()

    def test_dry_run_reports_without_changes(self, tmp_path: Path, capsys) -> None:
        with patch("builtins.input", return_value="y"):
            with patch("shutil.which", return_value=None):
                with patch("adjutant.setup.repair._check_listener", return_value=(0, 0)):
                    with patch(
                        "adjutant.setup.repair._check_scheduled_jobs",
                        return_value=(0, 0),
                    ):
                        run_repair(tmp_path, dry_run=True)
        # In dry_run, adjutant.yaml should NOT be created even with Y
        assert not (tmp_path / "adjutant.yaml").is_file()
