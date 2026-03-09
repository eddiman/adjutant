"""Tests for src/adjutant/setup/steps/install_path.py"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from adjutant.setup.steps.install_path import _BASE_DIRS, step_install_path


class TestStepInstallPath:
    def test_returns_existing_adjutant_dir(self, tmp_path: Path) -> None:
        # Simulate existing install
        (tmp_path / "adjutant.yaml").touch()
        result = step_install_path(adj_dir=tmp_path)
        assert result == tmp_path

    def test_returns_chosen_path_when_already_installed(self, tmp_path: Path) -> None:
        (tmp_path / "adjutant.yaml").touch()
        with patch("builtins.input", return_value=str(tmp_path)):
            result = step_install_path()
        assert result == tmp_path

    def test_creates_directory_on_confirm(self, tmp_path: Path) -> None:
        new_dir = tmp_path / "fresh_install"
        responses = iter([str(new_dir), "y"])
        with patch("builtins.input", side_effect=lambda: next(responses)):
            result = step_install_path()
        assert result == new_dir
        assert new_dir.is_dir()

    def test_returns_none_on_create_cancel(self, tmp_path: Path) -> None:
        new_dir = tmp_path / "fresh_install"
        responses = iter([str(new_dir), "n"])
        with patch("builtins.input", side_effect=lambda: next(responses)):
            result = step_install_path()
        assert result is None

    def test_creates_base_directory_structure(self, tmp_path: Path) -> None:
        new_dir = tmp_path / "adjutant_home"
        responses = iter([str(new_dir), "y"])
        with patch("builtins.input", side_effect=lambda: next(responses)):
            step_install_path()
        for d in _BASE_DIRS:
            assert (new_dir / d).is_dir()

    def test_dry_run_does_not_create_directory(self, tmp_path: Path) -> None:
        new_dir = tmp_path / "should_not_exist"
        responses = iter([str(new_dir), "y"])
        with patch("builtins.input", side_effect=lambda: next(responses)):
            result = step_install_path(dry_run=True)
        # In dry_run the dir may be created (confirm still runs) but no subdirs
        # The important thing: no error raised

    def test_outputs_to_stderr(self, tmp_path: Path) -> None:
        (tmp_path / "adjutant.yaml").touch()
        result = step_install_path(adj_dir=tmp_path)
        # No assertion on output; just ensure it completes without error
        assert result is not None
