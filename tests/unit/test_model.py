"""Tests for adjutant.core.model — model tier resolution."""

from __future__ import annotations

from pathlib import Path

from adjutant.core.model import (
    DEFAULT_MODEL,
    TIER_DEFAULTS,
    get_chat_model,
    resolve_kb_model,
)


class TestGetChatModel:
    """Test get_chat_model() — simple two-step chain."""

    def test_returns_default_when_no_file(self, adj_dir: Path):
        result = get_chat_model(adj_dir / "state")
        assert result == DEFAULT_MODEL

    def test_reads_model_from_file(self, adj_dir: Path):
        (adj_dir / "state" / "telegram_model.txt").write_text("anthropic/claude-sonnet-4-6\n")
        result = get_chat_model(adj_dir / "state")
        assert result == "anthropic/claude-sonnet-4-6"

    def test_ignores_empty_file(self, adj_dir: Path):
        (adj_dir / "state" / "telegram_model.txt").write_text("  \n")
        result = get_chat_model(adj_dir / "state")
        assert result == DEFAULT_MODEL

    def test_strips_whitespace(self, adj_dir: Path):
        (adj_dir / "state" / "telegram_model.txt").write_text("  some/model  \n")
        result = get_chat_model(adj_dir / "state")
        assert result == "some/model"


class TestResolveKbModel:
    """Test resolve_kb_model() — full tier chain."""

    # --- inherit / empty ---

    def test_inherit_with_model_file(self, adj_dir: Path):
        (adj_dir / "state" / "telegram_model.txt").write_text("anthropic/claude-sonnet-4-6\n")
        result = resolve_kb_model("inherit", adj_dir / "state")
        assert result == "anthropic/claude-sonnet-4-6"

    def test_empty_string_treated_as_inherit(self, adj_dir: Path):
        (adj_dir / "state" / "telegram_model.txt").write_text("some/model\n")
        result = resolve_kb_model("", adj_dir / "state")
        assert result == "some/model"

    def test_inherit_falls_back_to_cheap_default(self, adj_dir: Path):
        """No model file → cheap tier → hardcoded default."""
        result = resolve_kb_model("inherit", adj_dir / "state")
        assert result == TIER_DEFAULTS["cheap"]

    def test_inherit_falls_back_to_config_cheap(self, adj_dir: Path):
        """No model file → check config cheap tier."""
        config = {"llm": {"models": {"cheap": "custom/cheap-model"}}}
        result = resolve_kb_model("inherit", adj_dir / "state", config=config)
        assert result == "custom/cheap-model"

    # --- tier names ---

    def test_cheap_tier_default(self, adj_dir: Path):
        result = resolve_kb_model("cheap", adj_dir / "state")
        assert result == TIER_DEFAULTS["cheap"]

    def test_medium_tier_default(self, adj_dir: Path):
        result = resolve_kb_model("medium", adj_dir / "state")
        assert result == TIER_DEFAULTS["medium"]

    def test_expensive_tier_default(self, adj_dir: Path):
        result = resolve_kb_model("expensive", adj_dir / "state")
        assert result == TIER_DEFAULTS["expensive"]

    def test_tier_with_config_override(self, adj_dir: Path):
        config = {"llm": {"models": {"medium": "custom/medium-model"}}}
        result = resolve_kb_model("medium", adj_dir / "state", config=config)
        assert result == "custom/medium-model"

    def test_tier_with_empty_config(self, adj_dir: Path):
        """Config exists but tier not set → hardcoded default."""
        config = {"llm": {"models": {}}}
        result = resolve_kb_model("cheap", adj_dir / "state", config=config)
        assert result == TIER_DEFAULTS["cheap"]

    def test_tier_with_none_config(self, adj_dir: Path):
        result = resolve_kb_model("cheap", adj_dir / "state", config=None)
        assert result == TIER_DEFAULTS["cheap"]

    # --- explicit model ID ---

    def test_explicit_model_passthrough(self, adj_dir: Path):
        result = resolve_kb_model("openai/gpt-4o", adj_dir / "state")
        assert result == "openai/gpt-4o"

    def test_explicit_model_not_affected_by_config(self, adj_dir: Path):
        config = {"llm": {"models": {"cheap": "custom/cheap"}}}
        result = resolve_kb_model("openai/gpt-4o", adj_dir / "state", config=config)
        assert result == "openai/gpt-4o"
