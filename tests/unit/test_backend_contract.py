"""Cross-backend contract tests.

Verifies that both backends satisfy the same behavioral contracts.
These tests are parametrized over both backends and marked @pytest.mark.slow
because they require actual binaries (or mocks of them).

Run with: .venv/bin/pytest tests/unit/test_backend_contract.py --run-all-backends
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from adjutant.core.backend import (
    BackendCapabilities,
    BackendNotFoundError,
    LLMResult,
    get_backend,
)

pytestmark = pytest.mark.slow

BACKENDS = ["opencode", "claude-cli"]


class TestProtocolCompliance:
    """Both backends must expose all protocol methods and properties."""

    @pytest.mark.parametrize("backend_name", BACKENDS)
    def test_has_name_property(self, backend_name: str) -> None:
        backend = get_backend(backend_name)
        assert isinstance(backend.name, str)
        assert backend.name == backend_name

    @pytest.mark.parametrize("backend_name", BACKENDS)
    def test_has_capabilities_property(self, backend_name: str) -> None:
        backend = get_backend(backend_name)
        caps = backend.capabilities
        assert isinstance(caps, BackendCapabilities)

    @pytest.mark.parametrize("backend_name", BACKENDS)
    def test_has_run_method(self, backend_name: str) -> None:
        backend = get_backend(backend_name)
        assert callable(backend.run)

    @pytest.mark.parametrize("backend_name", BACKENDS)
    def test_has_run_detached_method(self, backend_name: str) -> None:
        backend = get_backend(backend_name)
        assert callable(backend.run_detached)

    @pytest.mark.parametrize("backend_name", BACKENDS)
    def test_has_run_sync_method(self, backend_name: str) -> None:
        backend = get_backend(backend_name)
        assert callable(backend.run_sync)

    @pytest.mark.parametrize("backend_name", BACKENDS)
    def test_has_reap_method(self, backend_name: str) -> None:
        backend = get_backend(backend_name)
        assert callable(backend.reap)

    @pytest.mark.parametrize("backend_name", BACKENDS)
    def test_has_health_check_method(self, backend_name: str) -> None:
        backend = get_backend(backend_name)
        assert callable(backend.health_check)

    @pytest.mark.parametrize("backend_name", BACKENDS)
    def test_has_list_models_method(self, backend_name: str) -> None:
        backend = get_backend(backend_name)
        assert callable(backend.list_models)

    @pytest.mark.parametrize("backend_name", BACKENDS)
    def test_has_find_binary_method(self, backend_name: str) -> None:
        backend = get_backend(backend_name)
        assert callable(backend.find_binary)
        # find_binary returns str or None
        result = backend.find_binary()
        assert result is None or isinstance(result, str)

    @pytest.mark.parametrize("backend_name", BACKENDS)
    def test_has_resolve_alias_method(self, backend_name: str) -> None:
        backend = get_backend(backend_name)
        assert callable(backend.resolve_alias)

    @pytest.mark.parametrize("backend_name", BACKENDS)
    def test_has_translate_model_id_method(self, backend_name: str) -> None:
        backend = get_backend(backend_name)
        assert callable(backend.translate_model_id)


class TestAliasConsistency:
    """Both backends must resolve the same set of aliases."""

    STANDARD_ALIASES = ["haiku", "sonnet", "opus"]

    @pytest.mark.parametrize("backend_name", BACKENDS)
    def test_all_standard_aliases_resolve(self, backend_name: str) -> None:
        backend = get_backend(backend_name)
        for alias in self.STANDARD_ALIASES:
            result = backend.resolve_alias(alias)
            assert result is not None
            assert isinstance(result, str)
            assert len(result) > 0

    @pytest.mark.parametrize("backend_name", BACKENDS)
    def test_unknown_alias_passes_through(self, backend_name: str) -> None:
        backend = get_backend(backend_name)
        result = backend.resolve_alias("totally-custom-model-xyz")
        assert result == "totally-custom-model-xyz"


class TestTranslateRoundTrip:
    """Model IDs should survive a round-trip translation between backends."""

    def test_opencode_to_claude_to_opencode(self) -> None:
        oc = get_backend("opencode")
        cc = get_backend("claude-cli")

        for alias in ["haiku", "sonnet", "opus"]:
            oc_id = oc.resolve_alias(alias)  # e.g. "anthropic/claude-sonnet-4-6"
            cc_id = cc.translate_model_id(oc_id)  # e.g. "sonnet"
            back = oc.translate_model_id(cc_id)  # e.g. "anthropic/claude-sonnet-4-6"
            assert back == oc_id, f"Round-trip failed for {alias}: {oc_id} -> {cc_id} -> {back}"

    def test_claude_to_opencode_to_claude(self) -> None:
        oc = get_backend("opencode")
        cc = get_backend("claude-cli")

        for alias in ["haiku", "sonnet", "opus"]:
            cc_id = cc.resolve_alias(alias)  # e.g. "haiku"
            oc_id = oc.translate_model_id(cc_id)  # e.g. "anthropic/claude-haiku-4-5"
            back = cc.translate_model_id(oc_id)  # e.g. "haiku"
            assert back == cc_id, f"Round-trip failed for {alias}: {cc_id} -> {oc_id} -> {back}"


class TestCapabilitiesContract:
    """Capabilities must be consistent with documented behavior."""

    def test_opencode_has_vision(self) -> None:
        assert get_backend("opencode").capabilities.vision is True

    def test_claude_cli_no_vision(self) -> None:
        assert get_backend("claude-cli").capabilities.vision is False

    def test_opencode_has_reaping(self) -> None:
        assert get_backend("opencode").capabilities.reaping is True

    def test_claude_cli_no_reaping(self) -> None:
        assert get_backend("claude-cli").capabilities.reaping is False

    def test_claude_cli_has_cost_tracking(self) -> None:
        assert get_backend("claude-cli").capabilities.cost_tracking is True

    def test_opencode_no_cost_tracking(self) -> None:
        assert get_backend("opencode").capabilities.cost_tracking is False

    def test_opencode_web_server(self) -> None:
        assert get_backend("opencode").capabilities.web_server is True

    def test_claude_cli_web_server(self) -> None:
        assert get_backend("claude-cli").capabilities.web_server is True
        assert get_backend("claude-cli").capabilities.remote_session is False

    @pytest.mark.parametrize("backend_name", BACKENDS)
    def test_capabilities_are_frozen(self, backend_name: str) -> None:
        caps = get_backend(backend_name).capabilities
        with pytest.raises(AttributeError):
            caps.vision = True  # type: ignore[misc]


class TestVisionGuard:
    """Claude CLI must return vision_unsupported for image files."""

    def test_claude_cli_rejects_images(self, mock_claude: Path) -> None:
        backend = get_backend("claude-cli")
        result = asyncio.run(backend.run("describe this", files=[Path("photo.jpg")]))
        assert result.error_type == "vision_unsupported"
        assert "not supported" in result.text.lower()

    def test_claude_cli_rejects_png(self, mock_claude: Path) -> None:
        backend = get_backend("claude-cli")
        result = asyncio.run(backend.run("analyze", files=[Path("screenshot.png")]))
        assert result.error_type == "vision_unsupported"

    def test_claude_cli_rejects_webp(self, mock_claude: Path) -> None:
        backend = get_backend("claude-cli")
        result = asyncio.run(backend.run("analyze", files=[Path("image.webp")]))
        assert result.error_type == "vision_unsupported"


class TestReapContract:
    """Reap must return int (number of processes cleaned up) on both backends."""

    @pytest.mark.parametrize("backend_name", BACKENDS)
    def test_reap_returns_int(self, backend_name: str, adj_dir: Path) -> None:
        backend = get_backend(backend_name)
        if backend_name == "opencode":
            # Mock opencode_reap to avoid actual process management
            with patch(
                "adjutant.core.backend_opencode.opencode_reap",
                new_callable=AsyncMock,
                return_value=0,
            ):
                result = asyncio.run(backend.reap(adj_dir))
        else:
            result = asyncio.run(backend.reap(adj_dir))
        assert isinstance(result, int)
        assert result >= 0


class TestErrorTaxonomy:
    """Both backends must use the same error type strings."""

    VALID_ERROR_TYPES = {
        "model_not_found",
        "auth_failure",
        "rate_limited",
        "context_overflow",
        "permission_denied",
        "vision_unsupported",
        "timeout",
        "parse_error",
        "error",
        None,  # no error
    }

    def test_claude_json_error_types_are_valid(self) -> None:
        from adjutant.lib.claude_json import _classify_claude_error

        # All classified errors must be in the shared taxonomy
        test_messages = [
            "Model not found: bad-model",
            "Not authenticated",
            "Rate limit exceeded",
            "Context length exceeded",
            "Permission denied",
            "Something unexpected",
        ]
        for msg in test_messages:
            error_type = _classify_claude_error(msg)
            assert error_type in self.VALID_ERROR_TYPES, (
                f"Error type {error_type!r} not in shared taxonomy"
            )

    def test_vision_unsupported_is_valid_error(self) -> None:
        result = LLMResult(text="not supported", error_type="vision_unsupported")
        assert result.error_type in self.VALID_ERROR_TYPES

    def test_llm_result_accepts_all_error_types(self) -> None:
        for error_type in self.VALID_ERROR_TYPES:
            result = LLMResult(text="test", error_type=error_type)
            assert result.error_type == error_type
