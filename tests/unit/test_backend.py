"""Tests for the backend abstraction layer (factory, LLMResult, BackendCapabilities)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from adjutant.core.backend import (
    BackendCapabilities,
    BackendNotFoundError,
    LLMResult,
    get_backend,
)


class TestLLMResult:
    def test_defaults(self):
        r = LLMResult(text="hello")
        assert r.text == "hello"
        assert r.session_id is None
        assert r.error_type is None
        assert r.returncode == 0
        assert r.timed_out is False
        assert r.cost_usd is None

    def test_all_fields(self):
        r = LLMResult(
            text="ok",
            session_id="abc",
            error_type="model_not_found",
            returncode=1,
            timed_out=True,
            cost_usd=0.005,
        )
        assert r.session_id == "abc"
        assert r.error_type == "model_not_found"
        assert r.returncode == 1
        assert r.timed_out is True
        assert r.cost_usd == 0.005


class TestBackendCapabilities:
    def test_defaults_all_false(self):
        caps = BackendCapabilities()
        assert caps.vision is False
        assert caps.model_listing is False
        assert caps.reaping is False
        assert caps.web_server is False
        assert caps.remote_session is False
        assert caps.streaming is False
        assert caps.cost_tracking is False

    def test_frozen(self):
        caps = BackendCapabilities(vision=True)
        with pytest.raises(AttributeError):
            caps.vision = False  # type: ignore[misc]


class TestGetBackend:
    def test_opencode_backend(self):
        backend = get_backend("opencode")
        assert backend.name == "opencode"

    def test_claude_cli_backend(self):
        backend = get_backend("claude-cli")
        assert backend.name == "claude-cli"

    def test_unknown_backend_raises(self):
        with pytest.raises(ValueError, match="Unknown LLM backend"):
            get_backend("nonexistent")

    def test_default_reads_config(self, adj_dir, adj_config):
        backend = get_backend()
        assert backend.name == "opencode"


class TestOpenCodeCapabilities:
    def test_capabilities(self):
        backend = get_backend("opencode")
        caps = backend.capabilities
        assert caps.vision is True
        assert caps.model_listing is True
        assert caps.reaping is True
        assert caps.web_server is True
        assert caps.remote_session is False
        assert caps.streaming is True
        assert caps.cost_tracking is False


class TestClaudeCLICapabilities:
    def test_capabilities(self):
        backend = get_backend("claude-cli")
        caps = backend.capabilities
        assert caps.vision is False
        assert caps.model_listing is False
        assert caps.reaping is False
        assert caps.web_server is True
        assert caps.remote_session is False
        assert caps.streaming is False
        assert caps.cost_tracking is True


class TestOpenCodeAliases:
    def test_resolve_alias_known(self):
        backend = get_backend("opencode")
        assert backend.resolve_alias("haiku") == "anthropic/claude-haiku-4-5"
        assert backend.resolve_alias("sonnet") == "anthropic/claude-sonnet-4-6"
        assert backend.resolve_alias("opus") == "anthropic/claude-opus-4-6"

    def test_resolve_alias_passthrough(self):
        backend = get_backend("opencode")
        assert backend.resolve_alias("some/custom-model") == "some/custom-model"

    def test_translate_model_id(self):
        """translate_model_id converts FROM other backend's format TO this backend's."""
        backend = get_backend("opencode")
        # Claude CLI "sonnet" → OpenCode full ID
        assert backend.translate_model_id("sonnet") == "anthropic/claude-sonnet-4-6"
        assert backend.translate_model_id("haiku") == "anthropic/claude-haiku-4-5"
        assert backend.translate_model_id("unknown-model") == "unknown-model"


class TestClaudeCLIAliases:
    def test_resolve_alias_known(self):
        backend = get_backend("claude-cli")
        assert backend.resolve_alias("haiku") == "haiku"
        assert backend.resolve_alias("sonnet") == "sonnet"
        assert backend.resolve_alias("opus") == "opus"

    def test_resolve_opencode_format(self):
        backend = get_backend("claude-cli")
        assert backend.resolve_alias("anthropic/claude-sonnet-4-6") == "sonnet"

    def test_resolve_alias_passthrough(self):
        backend = get_backend("claude-cli")
        assert backend.resolve_alias("custom-model") == "custom-model"

    def test_translate_model_id(self):
        """translate_model_id converts FROM other backend's format TO this backend's."""
        backend = get_backend("claude-cli")
        # OpenCode full ID → Claude CLI short name
        assert backend.translate_model_id("anthropic/claude-sonnet-4-6") == "sonnet"
        assert backend.translate_model_id("anthropic/claude-opus-4-6") == "opus"
        assert backend.translate_model_id("unknown") == "unknown"
