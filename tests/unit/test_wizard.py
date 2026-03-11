"""Tests for src/adjutant/setup/wizard.py"""

from __future__ import annotations

import platform
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest

from adjutant.setup.wizard import (
    DEFAULT_CONFIG_YAML,
    detect_os,
    ensure_config,
    expand_path,
    wiz_choose,
    wiz_confirm,
    wiz_fail,
    wiz_header,
    wiz_info,
    wiz_input,
    wiz_ok,
    wiz_step,
    wiz_warn,
)


# ---------------------------------------------------------------------------
# detect_os
# ---------------------------------------------------------------------------


class TestDetectOs:
    def test_macos(self) -> None:
        with patch("platform.system", return_value="Darwin"):
            assert detect_os() == "macos"

    def test_linux(self) -> None:
        with patch("platform.system", return_value="Linux"):
            assert detect_os() == "linux"

    def test_unknown(self) -> None:
        with patch("platform.system", return_value="Windows"):
            assert detect_os() == "unknown"


# ---------------------------------------------------------------------------
# expand_path
# ---------------------------------------------------------------------------


class TestExpandPath:
    def test_expands_tilde(self) -> None:
        result = expand_path("~/foo")
        assert not result.startswith("~")
        assert result.endswith("/foo")

    def test_absolute_unchanged(self) -> None:
        assert expand_path("/tmp/foo") == "/tmp/foo"


# ---------------------------------------------------------------------------
# UI primitives (output goes to stderr — patch sys.stderr)
# ---------------------------------------------------------------------------


class TestWizOk:
    def test_prints_checkmark(self, capsys) -> None:
        wiz_ok("All good")
        captured = capsys.readouterr()
        assert "All good" in captured.err


class TestWizFail:
    def test_prints_cross(self, capsys) -> None:
        wiz_fail("Something broke")
        captured = capsys.readouterr()
        assert "Something broke" in captured.err


class TestWizWarn:
    def test_prints_bang(self, capsys) -> None:
        wiz_warn("Be careful")
        captured = capsys.readouterr()
        assert "Be careful" in captured.err


class TestWizInfo:
    def test_prints_message(self, capsys) -> None:
        wiz_info("Information here")
        captured = capsys.readouterr()
        assert "Information here" in captured.err


class TestWizHeader:
    def test_prints_title(self, capsys) -> None:
        wiz_header("My Title")
        captured = capsys.readouterr()
        assert "My Title" in captured.err


class TestWizStep:
    def test_prints_step_info(self, capsys) -> None:
        wiz_step(2, 5, "Identity")
        captured = capsys.readouterr()
        assert "2 of 5" in captured.err
        assert "Identity" in captured.err


# ---------------------------------------------------------------------------
# wiz_confirm
# ---------------------------------------------------------------------------


class TestWizConfirm:
    def test_yes_input_returns_true(self, capsys) -> None:
        with patch("builtins.input", return_value="y"):
            assert wiz_confirm("Continue?") is True

    def test_no_input_returns_false(self, capsys) -> None:
        with patch("builtins.input", return_value="n"):
            assert wiz_confirm("Continue?") is False

    def test_default_yes_on_empty(self, capsys) -> None:
        with patch("builtins.input", return_value=""):
            assert wiz_confirm("Continue?", default="Y") is True

    def test_default_no_on_empty(self, capsys) -> None:
        with patch("builtins.input", return_value=""):
            assert wiz_confirm("Continue?", default="N") is False

    def test_eof_returns_false(self, capsys) -> None:
        with patch("builtins.input", side_effect=EOFError):
            assert wiz_confirm("Continue?") is False

    def test_full_word_yes(self, capsys) -> None:
        with patch("builtins.input", return_value="yes"):
            assert wiz_confirm("Continue?") is True

    def test_full_word_no(self, capsys) -> None:
        with patch("builtins.input", return_value="no"):
            assert wiz_confirm("Continue?") is False


# ---------------------------------------------------------------------------
# wiz_choose
# ---------------------------------------------------------------------------


class TestWizChoose:
    def test_valid_choice_returned(self, capsys) -> None:
        with patch("builtins.input", return_value="2"):
            result = wiz_choose("Pick one", "Alpha", "Beta", "Gamma")
        assert result == 2

    def test_first_option_on_eof(self, capsys) -> None:
        with patch("builtins.input", side_effect=EOFError):
            result = wiz_choose("Pick one", "Alpha", "Beta")
        assert result == 1

    def test_invalid_then_valid(self, capsys) -> None:
        responses = iter(["99", "abc", "1"])
        with patch("builtins.input", side_effect=responses):
            result = wiz_choose("Pick", "Only option")
        assert result == 1


# ---------------------------------------------------------------------------
# wiz_input
# ---------------------------------------------------------------------------


class TestWizInput:
    def test_returns_user_input(self, capsys) -> None:
        with patch("builtins.input", return_value="  my answer  "):
            result = wiz_input("Enter value")
        assert result == "my answer"

    def test_returns_default_on_empty(self, capsys) -> None:
        with patch("builtins.input", return_value=""):
            result = wiz_input("Enter value", default="fallback")
        assert result == "fallback"

    def test_returns_default_on_eof(self, capsys) -> None:
        with patch("builtins.input", side_effect=EOFError):
            result = wiz_input("Enter value", default="safe")
        assert result == "safe"


# ---------------------------------------------------------------------------
# ensure_config
# ---------------------------------------------------------------------------


class TestEnsureConfig:
    def test_creates_config_when_missing(self, tmp_path: Path, capsys) -> None:
        ensure_config(tmp_path)
        cfg = tmp_path / "adjutant.yaml"
        assert cfg.is_file()
        content = cfg.read_text()
        assert "adjutant.yaml" in content or "instance:" in content

    def test_skips_if_config_exists(self, tmp_path: Path) -> None:
        cfg = tmp_path / "adjutant.yaml"
        cfg.write_text("instance:\n  name: existing\n")
        ensure_config(tmp_path)
        # Should not overwrite
        assert "existing" in cfg.read_text()

    def test_dry_run_does_not_write(self, tmp_path: Path) -> None:
        ensure_config(tmp_path, dry_run=True)
        assert not (tmp_path / "adjutant.yaml").exists()

    def test_written_config_contains_default_models(self, tmp_path: Path) -> None:
        ensure_config(tmp_path)
        content = (tmp_path / "adjutant.yaml").read_text()
        assert "claude" in content
        assert "notifications" in content


# ---------------------------------------------------------------------------
# DEFAULT_CONFIG_YAML
# ---------------------------------------------------------------------------


class TestDefaultConfigYaml:
    def test_contains_required_sections(self) -> None:
        for section in ["instance:", "messaging:", "llm:", "features:", "notifications:"]:
            assert section in DEFAULT_CONFIG_YAML

    def test_default_max_per_day_is_3(self) -> None:
        assert "max_per_day: 3" in DEFAULT_CONFIG_YAML
