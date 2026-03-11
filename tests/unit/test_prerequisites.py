"""Tests for src/adjutant/setup/steps/prerequisites.py"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from adjutant.setup.steps.prerequisites import (
    PrerequisiteResult,
    _check_playwright,
    _get_version,
    step_prerequisites,
)


class TestGetVersion:
    def test_returns_first_line(self) -> None:
        mock_result = MagicMock(stdout="bash 5.2.15\n", stderr="", returncode=0)
        with patch("subprocess.run", return_value=mock_result):
            v = _get_version("bash")
        assert "bash 5.2.15" in v

    def test_returns_found_on_exception(self) -> None:
        with patch("subprocess.run", side_effect=OSError("no such file")):
            assert _get_version("missing") == "found"

    def test_truncates_long_output(self) -> None:
        mock_result = MagicMock(stdout="x" * 100, stderr="", returncode=0)
        with patch("subprocess.run", return_value=mock_result):
            v = _get_version("bash")
        assert len(v) <= 60


class TestCheckPlaywright:
    def test_returns_false_when_npx_missing(self) -> None:
        with patch("shutil.which", return_value=None):
            assert _check_playwright() is False

    def test_returns_true_when_playwright_available(self) -> None:
        mock_result = MagicMock(returncode=0)
        with patch("shutil.which", return_value="/usr/bin/npx"):
            with patch("subprocess.run", return_value=mock_result):
                assert _check_playwright() is True

    def test_returns_false_on_nonzero_returncode(self) -> None:
        mock_result = MagicMock(returncode=1)
        with patch("shutil.which", return_value="/usr/bin/npx"):
            with patch("subprocess.run", return_value=mock_result):
                assert _check_playwright() is False

    def test_returns_false_on_subprocess_exception(self) -> None:
        with patch("shutil.which", return_value="/usr/bin/npx"):
            with patch("subprocess.run", side_effect=OSError("timeout")):
                assert _check_playwright() is False


class TestStepPrerequisites:
    def test_returns_true_when_all_required_found(self, capsys) -> None:
        mock_ver = MagicMock(stdout="1.0", stderr="", returncode=0)
        with patch("shutil.which", return_value="/usr/bin/cmd"):
            with patch("subprocess.run", return_value=mock_ver):
                result = step_prerequisites()
        assert result is True

    def test_returns_false_when_required_dep_missing(self, capsys) -> None:
        def which_side_effect(cmd):
            if cmd == "opencode":
                return None
            return f"/usr/bin/{cmd}"

        mock_ver = MagicMock(stdout="1.0", stderr="", returncode=0)
        with patch("shutil.which", side_effect=which_side_effect):
            with patch("subprocess.run", return_value=mock_ver):
                result = step_prerequisites()
        assert result is False

    def test_outputs_to_stderr(self, capsys) -> None:
        mock_ver = MagicMock(stdout="1.0", stderr="", returncode=0)
        with patch("shutil.which", return_value="/usr/bin/cmd"):
            with patch("subprocess.run", return_value=mock_ver):
                step_prerequisites()
        captured = capsys.readouterr()
        assert "Prerequisites" in captured.err

    def test_optional_dep_missing_does_not_fail(self, capsys) -> None:
        def which_side_effect(cmd):
            if cmd in ("npx", "bc", "bats"):
                return None
            return f"/usr/bin/{cmd}"

        mock_ver = MagicMock(stdout="1.0", stderr="", returncode=0)
        with patch("shutil.which", side_effect=which_side_effect):
            with patch("subprocess.run", return_value=mock_ver):
                result = step_prerequisites()
        # Required deps all present → should still pass
        assert result is True
