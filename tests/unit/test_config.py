"""Tests for adjutant.core.config — YAML config loading."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from adjutant.core.config import get_config_value, is_feature_enabled, load_config


class TestLoadConfig:
    """Test load_config() — YAML file loading."""

    def test_load_valid_config(self, adj_dir: Path, adj_config: dict):
        config = load_config(adj_dir / "adjutant.yaml")
        assert config["instance"]["name"] == "test"

    def test_missing_file_returns_empty_dict(self, adj_dir: Path):
        config = load_config(adj_dir / "nonexistent.yaml")
        assert config == {}

    def test_empty_file_returns_empty_dict(self, adj_dir: Path):
        empty = adj_dir / "empty.yaml"
        empty.write_text("")
        config = load_config(empty)
        assert config == {}

    def test_invalid_yaml_returns_empty_dict(self, adj_dir: Path):
        bad = adj_dir / "bad.yaml"
        bad.write_text(": invalid: yaml: [broken")
        config = load_config(bad)
        assert config == {}

    def test_yaml_with_list_returns_empty_dict(self, adj_dir: Path):
        """YAML files that parse to a list (not dict) return empty dict."""
        list_yaml = adj_dir / "list.yaml"
        list_yaml.write_text("- item1\n- item2\n")
        config = load_config(list_yaml)
        assert config == {}

    def test_default_path_from_adj_dir(self, adj_dir: Path, adj_config: dict):
        """load_config() with no args uses $ADJ_DIR/adjutant.yaml."""
        config = load_config()
        assert config["instance"]["name"] == "test"

    def test_no_adj_dir_returns_empty(self, monkeypatch: pytest.MonkeyPatch):
        """load_config() returns empty dict when ADJ_DIR is not set."""
        monkeypatch.delenv("ADJ_DIR", raising=False)
        config = load_config()
        assert config == {}


class TestGetConfigValue:
    """Test get_config_value() — nested key access."""

    def test_nested_access(self, adj_config: dict):
        result = get_config_value(adj_config, "llm", "models", "cheap")
        assert result == "anthropic/claude-haiku-4-5"

    def test_missing_key_returns_default(self, adj_config: dict):
        result = get_config_value(adj_config, "nonexistent", "key", default="fallback")
        assert result == "fallback"

    def test_missing_nested_key(self, adj_config: dict):
        result = get_config_value(adj_config, "llm", "nonexistent", default=None)
        assert result is None

    def test_single_level_access(self, adj_config: dict):
        result = get_config_value(adj_config, "instance")
        assert result == {"name": "test"}

    def test_deep_access(self, adj_config: dict):
        result = get_config_value(
            adj_config, "messaging", "telegram", "rate_limit", "messages_per_minute"
        )
        assert result == 10

    def test_none_value_returns_default(self):
        """If a key exists but value is None, return default."""
        config = {"key": None}
        result = get_config_value(config, "key", default="fallback")
        assert result == "fallback"


class TestIsFeatureEnabled:
    """Test is_feature_enabled() — feature flag checking."""

    def test_disabled_feature(self, adj_config: dict):
        assert is_feature_enabled(adj_config, "news") is False

    def test_enabled_feature(self, adj_config: dict):
        adj_config["features"]["news"]["enabled"] = True
        assert is_feature_enabled(adj_config, "news") is True

    def test_missing_feature(self, adj_config: dict):
        assert is_feature_enabled(adj_config, "nonexistent") is False

    def test_empty_config(self):
        assert is_feature_enabled({}, "news") is False
