"""Tests for the Claude CLI backend (ClaudeCLIBackend)."""

from __future__ import annotations

import asyncio
import json
import os
import textwrap
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from adjutant.core.backend import BackendNotFoundError, LLMResult, get_backend
from adjutant.core.backend_claude_cli import (
    ClaudeCLIBackend,
    _extract_prompt_body,
    _find_claude,
    _get_permission_args,
    _resolve_agent_file,
)

pytestmark = pytest.mark.backend_claude_cli


# ---------------------------------------------------------------------------
# Binary resolution
# ---------------------------------------------------------------------------


class TestFindClaude:
    def test_finds_on_path(self, mock_claude: Path) -> None:
        assert _find_claude() == str(mock_claude)

    def test_uses_env_var(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        script = tmp_path / "my-claude"
        script.write_text("#!/bin/bash\necho ok")
        script.chmod(0o755)
        monkeypatch.setenv("CLAUDE_CODE_BIN", str(script))
        assert _find_claude() == str(script)

    def test_env_var_nonexistent_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CLAUDE_CODE_BIN", "/nonexistent/claude")
        with pytest.raises(BackendNotFoundError, match="not an executable"):
            _find_claude()

    def test_not_found_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PATH", "/empty")
        monkeypatch.delenv("CLAUDE_CODE_BIN", raising=False)
        with pytest.raises(BackendNotFoundError, match="not found on PATH"):
            _find_claude()

    def test_find_binary_returns_none_when_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PATH", "/empty")
        monkeypatch.delenv("CLAUDE_CODE_BIN", raising=False)
        backend = ClaudeCLIBackend()
        assert backend.find_binary() is None


# ---------------------------------------------------------------------------
# Agent prompt handling
# ---------------------------------------------------------------------------


class TestExtractPromptBody:
    def test_strips_frontmatter(self, tmp_path: Path) -> None:
        f = tmp_path / "agent.md"
        f.write_text("---\nmodel: sonnet\n---\n\n# System prompt\nDo things.\n")
        assert _extract_prompt_body(f) == "# System prompt\nDo things."

    def test_no_frontmatter(self, tmp_path: Path) -> None:
        f = tmp_path / "agent.md"
        f.write_text("# Just markdown\nNo frontmatter here.\n")
        assert _extract_prompt_body(f) == "# Just markdown\nNo frontmatter here."

    def test_incomplete_frontmatter(self, tmp_path: Path) -> None:
        f = tmp_path / "agent.md"
        f.write_text("---\nmodel: sonnet\nNo closing delimiter.\n")
        # Only one "---" → treated as plain content
        assert "model: sonnet" in _extract_prompt_body(f)


class TestResolveAgentFile:
    def test_finds_agent(self, tmp_path: Path) -> None:
        agent_file = tmp_path / ".opencode" / "agents" / "adjutant.md"
        agent_file.parent.mkdir(parents=True)
        agent_file.write_text("prompt")
        assert _resolve_agent_file("adjutant", tmp_path) == agent_file

    def test_returns_none_when_missing(self, tmp_path: Path) -> None:
        assert _resolve_agent_file("adjutant", tmp_path) is None

    def test_returns_none_when_no_workdir(self) -> None:
        assert _resolve_agent_file("adjutant", None) is None


# ---------------------------------------------------------------------------
# Permission args
# ---------------------------------------------------------------------------


class TestPermissionArgs:
    def test_default_skip(self) -> None:
        with patch(
            "adjutant.core.backend_claude_cli.load_typed_config",
            side_effect=Exception("no config"),
        ):
            assert _get_permission_args() == ["--dangerously-skip-permissions"]

    def test_allowlist_mode(self) -> None:
        mock_config = MagicMock()
        mock_config.llm.permission_mode = "allowlist"
        mock_config.llm.allowed_tools = "Read,Write"
        with patch(
            "adjutant.core.backend_claude_cli.load_typed_config",
            return_value=mock_config,
        ):
            assert _get_permission_args() == ["--allowedTools", "Read,Write"]


# ---------------------------------------------------------------------------
# Vision (image path injection)
# ---------------------------------------------------------------------------


class TestVisionPathInjection:
    @pytest.mark.asyncio
    async def test_injects_image_paths_into_prompt(self, mock_claude: Path) -> None:
        backend = ClaudeCLIBackend()
        result = await backend.run(
            "describe this",
            files=[Path("/tmp/photo.jpg")],
        )
        # Should succeed (not rejected) — image path gets injected into prompt
        assert result.error_type != "vision_unsupported"

    @pytest.mark.asyncio
    async def test_allows_non_image_files(self, mock_claude: Path) -> None:
        backend = ClaudeCLIBackend()
        # Non-image file should proceed (will hit mock claude binary)
        result = await backend.run(
            "analyze this",
            files=[Path("data.csv")],
        )
        assert result.error_type != "vision_unsupported"


# ---------------------------------------------------------------------------
# run() integration
# ---------------------------------------------------------------------------


class TestRun:
    @pytest.mark.asyncio
    async def test_basic_run(self, mock_claude: Path) -> None:
        backend = ClaudeCLIBackend()
        result = await backend.run("hello")
        assert isinstance(result, LLMResult)
        assert result.text == "OK"
        assert result.session_id == "test-uuid-123"
        assert result.returncode == 0
        assert result.timed_out is False

    @pytest.mark.asyncio
    async def test_timeout(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        # Create a claude binary that sleeps forever
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir()
        script = mock_bin / "claude"
        script.write_text("#!/bin/bash\nsleep 60")
        script.chmod(0o755)
        monkeypatch.setenv("PATH", f"{mock_bin}:{os.environ['PATH']}")

        backend = ClaudeCLIBackend()
        result = await backend.run("hello", timeout=0.5)
        assert result.timed_out is True
        assert result.error_type == "timeout"

    @pytest.mark.asyncio
    async def test_passes_model(self, mock_claude: Path) -> None:
        backend = ClaudeCLIBackend()
        # Should resolve alias and pass to CLI
        result = await backend.run("hello", model="opus")
        assert result.returncode == 0

    @pytest.mark.asyncio
    async def test_passes_session_id(self, mock_claude: Path) -> None:
        backend = ClaudeCLIBackend()
        result = await backend.run("hello", session_id="uuid-456")
        assert result.returncode == 0


# ---------------------------------------------------------------------------
# run_detached()
# ---------------------------------------------------------------------------


class TestRunDetached:
    def test_runs_without_error(self, mock_claude: Path, tmp_path: Path) -> None:
        backend = ClaudeCLIBackend()
        # Should not raise
        backend.run_detached("do something", workdir=tmp_path)

    def test_logs_to_file(self, mock_claude: Path, tmp_path: Path) -> None:
        log = tmp_path / "detached.log"
        backend = ClaudeCLIBackend()
        backend.run_detached("do something", workdir=tmp_path, log_path=log)
        # Log file should be created (may be empty if process hasn't flushed)
        assert log.exists()


# ---------------------------------------------------------------------------
# run_sync()
# ---------------------------------------------------------------------------


class TestRunSync:
    def test_returns_returncode(self, mock_claude: Path) -> None:
        backend = ClaudeCLIBackend()
        rc = backend.run_sync("hello")
        assert rc == 0


# ---------------------------------------------------------------------------
# reap() and health_check()
# ---------------------------------------------------------------------------


class TestReap:
    @pytest.mark.asyncio
    async def test_reap_is_noop(self, tmp_path: Path) -> None:
        backend = ClaudeCLIBackend()
        count = await backend.reap(tmp_path)
        assert count == 0


class TestHealthCheck:
    """health_check just verifies the claude binary is available.

    Previously it also probed the CloudCLI web server's /health endpoint;
    that native web server has been retired in favor of adjutant's own
    web/app, so the check is now a pure binary availability check.
    """

    @pytest.mark.asyncio
    async def test_healthy_when_binary_found(
        self, mock_claude: Path, tmp_path: Path
    ) -> None:
        backend = ClaudeCLIBackend()
        assert await backend.health_check(tmp_path) is True

    @pytest.mark.asyncio
    async def test_unhealthy_when_binary_missing(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("PATH", "/empty")
        monkeypatch.delenv("CLAUDE_CODE_BIN", raising=False)
        backend = ClaudeCLIBackend()
        assert await backend.health_check(tmp_path) is False


# ---------------------------------------------------------------------------
# list_models()
# ---------------------------------------------------------------------------


class TestListModels:
    @pytest.mark.asyncio
    async def test_returns_static_list(self) -> None:
        backend = ClaudeCLIBackend()
        models = await backend.list_models()
        assert "haiku" in models
        assert "sonnet" in models
        assert "opus" in models
