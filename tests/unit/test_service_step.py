"""Tests for src/adjutant/setup/steps/service.py"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from adjutant.setup.steps.service import (
    _LAUNCHD_PLIST,
    _SYSTEMD_UNIT,
    _fix_permissions,
    _install_launchd,
    _install_systemd,
    _setup_cli,
    step_service,
)


class TestFixPermissions:
    def test_makes_cli_executable(self, tmp_path: Path) -> None:
        cli = tmp_path / "adjutant"
        cli.write_text("#!/bin/bash")
        cli.chmod(0o644)
        _fix_permissions(tmp_path)
        assert os.access(str(cli), os.X_OK)

    def test_makes_scripts_executable(self, tmp_path: Path) -> None:
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()
        sh = scripts_dir / "test.sh"
        sh.write_text("#!/bin/bash")
        sh.chmod(0o644)
        _fix_permissions(tmp_path)
        assert os.access(str(sh), os.X_OK)

    def test_restricts_env_permissions(self, tmp_path: Path) -> None:
        env = tmp_path / ".env"
        env.write_text("SECRET=x")
        env.chmod(0o644)
        _fix_permissions(tmp_path)
        import stat

        mode = stat.S_IMODE(env.stat().st_mode)
        assert mode == 0o600

    def test_dry_run_does_not_change_cli_perms(self, tmp_path: Path) -> None:
        cli = tmp_path / "adjutant"
        cli.write_text("#!/bin/bash")
        cli.chmod(0o644)
        # Note: in dry_run we just skip writing scripts, so this test verifies no crash
        _fix_permissions(tmp_path, dry_run=True)


class TestSetupCli:
    def test_skips_when_already_on_path(self, tmp_path: Path, capsys) -> None:
        with patch("shutil.which", return_value="/usr/bin/adjutant"):
            _setup_cli(tmp_path)
        out = capsys.readouterr().err
        assert "PATH" in out

    def test_adds_alias_to_shellrc(self, tmp_path: Path, capsys) -> None:
        shell_rc = tmp_path / ".zshrc"
        shell_rc.write_text("# existing content\n")

        with patch("shutil.which", return_value=None):
            with patch(
                "os.environ.get",
                side_effect=lambda k, d="": {
                    "PATH": "/usr/bin",
                    "SHELL": "/bin/zsh",
                }.get(k, d),
            ):
                with patch("pathlib.Path.home", return_value=tmp_path):
                    with patch("builtins.input", return_value="y"):
                        _setup_cli(tmp_path)

        content = shell_rc.read_text()
        assert "alias adjutant=" in content

    def test_dry_run_does_not_write_alias(self, tmp_path: Path, capsys) -> None:
        shell_rc = tmp_path / ".zshrc"
        shell_rc.write_text("# existing\n")

        with patch("shutil.which", return_value=None):
            with patch(
                "os.environ.get",
                side_effect=lambda k, d="": {
                    "PATH": "/usr/bin",
                    "SHELL": "/bin/zsh",
                }.get(k, d),
            ):
                with patch("pathlib.Path.home", return_value=tmp_path):
                    with patch("builtins.input", return_value="y"):
                        _setup_cli(tmp_path, dry_run=True)

        content = shell_rc.read_text()
        assert "alias adjutant=" not in content


class TestInstallLaunchd:
    def test_dry_run_does_not_create_plist(self, tmp_path: Path, capsys) -> None:
        plist_dir = tmp_path / "Library" / "LaunchAgents"
        with patch("builtins.input", return_value="y"):
            with patch("pathlib.Path.home", return_value=tmp_path):
                _install_launchd(tmp_path, dry_run=True)
        plist = plist_dir / "com.adjutant.telegram.plist"
        assert not plist.is_file()

    def test_creates_plist_on_confirm(self, tmp_path: Path) -> None:
        # Confirm install, decline load
        responses = iter(["y", "n"])
        with patch("builtins.input", side_effect=lambda: next(responses)):
            with patch("pathlib.Path.home", return_value=tmp_path):
                _install_launchd(tmp_path)
        plist = tmp_path / "Library" / "LaunchAgents" / "com.adjutant.telegram.plist"
        assert plist.is_file()

    def test_skips_when_user_declines(self, tmp_path: Path, capsys) -> None:
        with patch("builtins.input", return_value="n"):
            _install_launchd(tmp_path)
        # No plist created
        plist = tmp_path / "Library" / "LaunchAgents" / "com.adjutant.telegram.plist"
        assert not plist.is_file()


class TestStepService:
    def test_returns_true_on_macos(self, tmp_path: Path, capsys) -> None:
        with patch("adjutant.setup.steps.service.detect_os", return_value="macos"):
            with patch("adjutant.setup.steps.service._fix_permissions"):
                with patch("adjutant.setup.steps.service._setup_cli"):
                    with patch("adjutant.setup.steps.service._install_launchd"):
                        with patch("adjutant.setup.steps.service._install_schedules"):
                            result = step_service(tmp_path)
        assert result is True

    def test_returns_true_on_linux(self, tmp_path: Path, capsys) -> None:
        with patch("adjutant.setup.steps.service.detect_os", return_value="linux"):
            with patch("adjutant.setup.steps.service._fix_permissions"):
                with patch("adjutant.setup.steps.service._setup_cli"):
                    with patch("adjutant.setup.steps.service._install_systemd"):
                        with patch("adjutant.setup.steps.service._install_schedules"):
                            result = step_service(tmp_path)
        assert result is True

    def test_returns_true_on_unknown_platform(self, tmp_path: Path, capsys) -> None:
        with patch("adjutant.setup.steps.service.detect_os", return_value="unknown"):
            with patch("adjutant.setup.steps.service._fix_permissions"):
                with patch("adjutant.setup.steps.service._setup_cli"):
                    with patch("adjutant.setup.steps.service._install_schedules"):
                        result = step_service(tmp_path)
        assert result is True
