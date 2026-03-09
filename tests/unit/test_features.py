"""Tests for src/adjutant/setup/steps/features.py"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

import adjutant.setup.steps.features as features_mod
from adjutant.setup.steps.features import (
    _read_env_key,
    _playwright_available,
    _update_feature_in_yaml,
    _write_brave_key,
    step_features,
)


class TestReadEnvKey:
    def test_returns_value(self, tmp_path: Path) -> None:
        env = tmp_path / ".env"
        env.write_text("BRAVE_API_KEY=mykey\n")
        assert _read_env_key(env, "BRAVE_API_KEY") == "mykey"

    def test_returns_empty_when_missing(self, tmp_path: Path) -> None:
        env = tmp_path / ".env"
        env.write_text("OTHER=val\n")
        assert _read_env_key(env, "BRAVE_API_KEY") == ""

    def test_returns_empty_when_no_file(self, tmp_path: Path) -> None:
        assert _read_env_key(tmp_path / ".env", "BRAVE_API_KEY") == ""


class TestPlaywrightAvailable:
    def test_false_when_npx_missing(self) -> None:
        with patch("shutil.which", return_value=None):
            assert _playwright_available() is False

    def test_true_when_available(self) -> None:
        mock_r = MagicMock(returncode=0)
        with patch("shutil.which", return_value="/usr/bin/npx"):
            with patch("subprocess.run", return_value=mock_r):
                assert _playwright_available() is True


class TestUpdateFeatureInYaml:
    def test_sets_feature_enabled(self, tmp_path: Path) -> None:
        cfg = tmp_path / "adjutant.yaml"
        cfg.write_text("features:\n  news:\n    enabled: false\n")
        _update_feature_in_yaml(tmp_path, "news", True)
        with open(cfg) as f:
            data = yaml.safe_load(f)
        assert data["features"]["news"]["enabled"] is True

    def test_creates_feature_block_if_missing(self, tmp_path: Path) -> None:
        cfg = tmp_path / "adjutant.yaml"
        cfg.write_text("features: {}\n")
        _update_feature_in_yaml(tmp_path, "vision", True)
        with open(cfg) as f:
            data = yaml.safe_load(f)
        assert data["features"]["vision"]["enabled"] is True

    def test_no_op_when_no_config(self, tmp_path: Path) -> None:
        # Should not raise
        _update_feature_in_yaml(tmp_path, "vision", True)


class TestWriteBraveKey:
    def test_creates_env_with_key(self, tmp_path: Path) -> None:
        _write_brave_key(tmp_path, "my-brave-key")
        env = tmp_path / ".env"
        assert env.is_file()
        assert "my-brave-key" in env.read_text()

    def test_updates_existing_key(self, tmp_path: Path) -> None:
        env = tmp_path / ".env"
        env.write_text("BRAVE_API_KEY=old-key\n")
        _write_brave_key(tmp_path, "new-key")
        assert "new-key" in env.read_text()
        assert "old-key" not in env.read_text()

    def test_sets_permissions_600(self, tmp_path: Path) -> None:
        _write_brave_key(tmp_path, "mykey")
        env = tmp_path / ".env"
        import stat

        mode = stat.S_IMODE(env.stat().st_mode)
        assert mode == 0o600


class TestStepFeatures:
    def _make_config(self, tmp_path: Path) -> Path:
        cfg = tmp_path / "adjutant.yaml"
        cfg.write_text("features:\n  news:\n    enabled: false\n")
        return tmp_path

    def test_returns_true(self, tmp_path: Path, capsys) -> None:
        self._make_config(tmp_path)
        # All N responses → disable everything
        with patch("builtins.input", return_value="n"):
            with patch("shutil.which", return_value=None):
                result = step_features(tmp_path)
        assert result is True

    def test_enables_news(self, tmp_path: Path, capsys) -> None:
        self._make_config(tmp_path)
        # Y=news, N=screenshot, N=vision, N=search, Y=usage
        responses = iter(["y", "n", "n", "n", "y"])
        with patch("builtins.input", side_effect=lambda: next(responses)):
            with patch("shutil.which", return_value=None):
                result = step_features(tmp_path)
        assert result is True
        assert features_mod.WIZARD_FEATURES_NEWS is True

    def test_news_config_written(self, tmp_path: Path, capsys) -> None:
        self._make_config(tmp_path)
        responses = iter(["y", "n", "n", "n", "n"])
        with patch("builtins.input", side_effect=lambda: next(responses)):
            with patch("shutil.which", return_value=None):
                step_features(tmp_path)
        assert (tmp_path / "news_config.json").is_file()

    def test_dry_run_does_not_write_config(self, tmp_path: Path, capsys) -> None:
        self._make_config(tmp_path)
        responses = iter(["y", "n", "n", "n", "n"])
        with patch("builtins.input", side_effect=lambda: next(responses)):
            with patch("shutil.which", return_value=None):
                step_features(tmp_path, dry_run=True)
        assert not (tmp_path / "news_config.json").is_file()

    def test_search_enabled_with_key(self, tmp_path: Path, capsys) -> None:
        self._make_config(tmp_path)
        # Force telegram_enabled=False so screenshot/vision are auto-disabled (no input consumed).
        # Sequence: N=news, Y=search, N=usage
        # The Brave key is collected via getpass.getpass (wiz_secret), not input()
        import sys

        mock_messaging = MagicMock()
        mock_messaging.WIZARD_TELEGRAM_ENABLED = False
        responses = iter(["n", "y", "n"])
        with patch.dict(sys.modules, {"adjutant.setup.steps.messaging": mock_messaging}):
            with patch("builtins.input", side_effect=lambda: next(responses)):
                with patch("shutil.which", return_value=None):
                    with patch("getpass.getpass", return_value="brave-test-key"):
                        step_features(tmp_path)
        assert features_mod.WIZARD_FEATURES_SEARCH is True
