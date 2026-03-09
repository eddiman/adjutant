"""Tests for src/adjutant/setup/steps/autonomy.py"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

import adjutant.setup.steps.autonomy as autonomy_mod
from adjutant.setup.steps.autonomy import (
    _update_config,
    _update_quiet_hours,
    step_autonomy,
)


def _make_config(tmp_path: Path) -> Path:
    cfg = tmp_path / "adjutant.yaml"
    cfg.write_text("instance:\n  name: adjutant\n")
    return cfg


class TestUpdateConfig:
    def test_writes_autonomy_enabled(self, tmp_path: Path) -> None:
        _make_config(tmp_path)
        autonomy_mod.WIZARD_AUTONOMY_ENABLED = True
        autonomy_mod.WIZARD_AUTONOMY_MAX_PER_DAY = 5
        _update_config(tmp_path)
        with open(tmp_path / "adjutant.yaml") as f:
            data = yaml.safe_load(f)
        assert data["autonomy"]["enabled"] is True
        assert data["notifications"]["max_per_day"] == 5

    def test_dry_run_does_not_write(self, tmp_path: Path) -> None:
        _make_config(tmp_path)
        original = (tmp_path / "adjutant.yaml").read_text()
        autonomy_mod.WIZARD_AUTONOMY_ENABLED = True
        _update_config(tmp_path, dry_run=True)
        assert (tmp_path / "adjutant.yaml").read_text() == original

    def test_no_op_when_config_missing(self, tmp_path: Path) -> None:
        # Should not raise
        _update_config(tmp_path)


class TestUpdateQuietHours:
    def test_writes_quiet_hours(self, tmp_path: Path) -> None:
        _make_config(tmp_path)
        _update_quiet_hours(tmp_path, True, "22:00", "07:00")
        with open(tmp_path / "adjutant.yaml") as f:
            data = yaml.safe_load(f)
        qh = data["notifications"]["quiet_hours"]
        assert qh["enabled"] is True
        assert qh["start"] == "22:00"
        assert qh["end"] == "07:00"

    def test_dry_run_does_not_write(self, tmp_path: Path) -> None:
        _make_config(tmp_path)
        original = (tmp_path / "adjutant.yaml").read_text()
        _update_quiet_hours(tmp_path, True, "22:00", "07:00", dry_run=True)
        assert (tmp_path / "adjutant.yaml").read_text() == original


class TestStepAutonomy:
    def test_returns_true_when_declined(self, tmp_path: Path, capsys) -> None:
        _make_config(tmp_path)
        with patch("builtins.input", return_value="n"):
            result = step_autonomy(tmp_path)
        assert result is True
        assert autonomy_mod.WIZARD_AUTONOMY_ENABLED is False

    def test_enables_autonomy(self, tmp_path: Path, capsys) -> None:
        _make_config(tmp_path)
        # Y=enable, budget=3, N=quiet hours
        responses = iter(["y", "3", "n"])
        with patch("builtins.input", side_effect=lambda: next(responses)):
            with patch(
                "adjutant.setup.steps.autonomy._enable_schedules",
                return_value=None,
            ):
                result = step_autonomy(tmp_path)
        assert result is True
        assert autonomy_mod.WIZARD_AUTONOMY_ENABLED is True

    def test_sets_notification_budget(self, tmp_path: Path, capsys) -> None:
        _make_config(tmp_path)
        responses = iter(["y", "7", "n"])
        with patch("builtins.input", side_effect=lambda: next(responses)):
            with patch("adjutant.setup.steps.autonomy._enable_schedules"):
                step_autonomy(tmp_path)
        assert autonomy_mod.WIZARD_AUTONOMY_MAX_PER_DAY == 7

    def test_invalid_budget_defaults_to_three(self, tmp_path: Path, capsys) -> None:
        _make_config(tmp_path)
        responses = iter(["y", "notanumber", "n"])
        with patch("builtins.input", side_effect=lambda: next(responses)):
            with patch("adjutant.setup.steps.autonomy._enable_schedules"):
                step_autonomy(tmp_path)
        assert autonomy_mod.WIZARD_AUTONOMY_MAX_PER_DAY == 3

    def test_sets_quiet_hours(self, tmp_path: Path, capsys) -> None:
        _make_config(tmp_path)
        # Y=enable, 5 budget, Y=quiet, 23:00, 06:00
        responses = iter(["y", "5", "y", "23:00", "06:00"])
        with patch("builtins.input", side_effect=lambda: next(responses)):
            with patch("adjutant.setup.steps.autonomy._enable_schedules"):
                step_autonomy(tmp_path)
        with open(tmp_path / "adjutant.yaml") as f:
            data = yaml.safe_load(f)
        assert data["notifications"]["quiet_hours"]["start"] == "23:00"

    def test_dry_run_does_not_modify_config(self, tmp_path: Path, capsys) -> None:
        _make_config(tmp_path)
        original = (tmp_path / "adjutant.yaml").read_text()
        responses = iter(["y", "3", "n"])
        with patch("builtins.input", side_effect=lambda: next(responses)):
            with patch("adjutant.setup.steps.autonomy._enable_schedules"):
                step_autonomy(tmp_path, dry_run=True)
        assert (tmp_path / "adjutant.yaml").read_text() == original
