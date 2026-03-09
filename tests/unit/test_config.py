"""Tests for adjutant.core.config — YAML config loading."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from adjutant.core.config import (
    AdjutantConfig,
    get_config_value,
    is_feature_enabled,
    load_config,
    load_typed_config,
)


# ---------------------------------------------------------------------------
# Dict-based API
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Typed model API
# ---------------------------------------------------------------------------


class TestAdjutantConfig:
    """Tests for AdjutantConfig typed model."""

    def test_default_config(self) -> None:
        config = AdjutantConfig()
        assert config.instance.name == "adjutant"
        assert config.messaging.backend == "telegram"
        assert config.llm.backend == "opencode"

    def test_load_from_file(self, tmp_path: Path) -> None:
        config_file = tmp_path / "adjutant.yaml"
        config_file.write_text(
            "instance:\n  name: test-instance\n\nllm:\n  models:\n    cheap: test-model\n"
        )
        config = AdjutantConfig.load(config_file)
        assert config.instance.name == "test-instance"
        assert config.llm.models.cheap == "test-model"

    def test_load_missing_file_returns_defaults(self, tmp_path: Path) -> None:
        config = AdjutantConfig.load(tmp_path / "nonexistent.yaml")
        assert config.instance.name == "adjutant"

    def test_get_model_tiers(self) -> None:
        config = AdjutantConfig()
        assert config.get_model("cheap") == "anthropic/claude-haiku-4-5"
        assert config.get_model("medium") == "anthropic/claude-sonnet-4-6"
        assert config.get_model("expensive") == "anthropic/claude-opus-4-5"

    def test_get_model_unknown_tier_falls_back_to_cheap(self) -> None:
        config = AdjutantConfig()
        assert config.get_model("unknown") == "anthropic/claude-haiku-4-5"

    def test_is_feature_enabled_defaults_false(self) -> None:
        config = AdjutantConfig()
        assert config.is_feature_enabled("news") is False
        assert config.is_feature_enabled("screenshot") is False

    def test_is_feature_enabled_from_file(self, tmp_path: Path) -> None:
        config_file = tmp_path / "adjutant.yaml"
        config_file.write_text("features:\n  news:\n    enabled: true\n")
        config = AdjutantConfig.load(config_file)
        assert config.is_feature_enabled("news") is True

    def test_is_feature_enabled_unknown_returns_false(self) -> None:
        config = AdjutantConfig()
        assert config.is_feature_enabled("nonexistent") is False

    def test_get_schedule_found(self, tmp_path: Path) -> None:
        config_file = tmp_path / "adjutant.yaml"
        config_file.write_text(
            "schedules:\n  - name: daily_news\n    schedule: '0 8 * * *'\n    enabled: true\n"
        )
        config = AdjutantConfig.load(config_file)
        schedule = config.get_schedule("daily_news")
        assert schedule is not None
        assert schedule.name == "daily_news"
        assert schedule.schedule == "0 8 * * *"

    def test_get_schedule_not_found(self) -> None:
        config = AdjutantConfig()
        assert config.get_schedule("nonexistent") is None

    def test_nested_defaults_populated(self) -> None:
        config = AdjutantConfig()
        assert config.messaging.telegram.rate_limit.messages_per_minute == 10
        assert config.llm.models.medium == "anthropic/claude-sonnet-4-6"
        assert config.journal.retention_days == 30
        assert config.security.prompt_injection_guard is True


class TestLoadTypedConfig:
    """Tests for load_typed_config() convenience function."""

    def test_load_with_explicit_path(self, tmp_path: Path) -> None:
        config_file = tmp_path / "adjutant.yaml"
        config_file.write_text("instance:\n  name: explicit\n")
        config = load_typed_config(config_file)
        assert config.instance.name == "explicit"

    def test_load_from_adjutant_home_env(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        config_file = tmp_path / "adjutant.yaml"
        config_file.write_text("instance:\n  name: from-env\n")
        monkeypatch.setenv("ADJUTANT_HOME", str(tmp_path))
        monkeypatch.delenv("ADJ_DIR", raising=False)
        config = load_typed_config()
        assert config.instance.name == "from-env"

    def test_load_no_env_returns_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ADJUTANT_HOME", raising=False)
        monkeypatch.delenv("ADJ_DIR", raising=False)
        config = load_typed_config()
        assert config.instance.name == "adjutant"
