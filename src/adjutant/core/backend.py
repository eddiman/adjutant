"""LLM backend abstraction — protocol, result types, factory.

All LLM interactions go through this module. Call sites import get_backend()
and use the returned backend's run/run_detached/run_sync methods. Never import
backend implementations (backend_opencode, backend_claude_cli) directly.

Two backends:
- opencode: Anthropic API key via OpenCode CLI
- claude-cli: Claude subscription via Claude Code CLI
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class ResolvedModel:
    """Concrete model selection after tier resolution."""

    model: str
    variant: str | None = None
    source: str = "explicit"


@dataclass
class LLMResult:
    """Unified result from any LLM backend invocation."""

    text: str
    session_id: str | None = None
    error_type: str | None = None
    returncode: int = 0
    timed_out: bool = False
    cost_usd: float | None = None


@dataclass(frozen=True)
class BackendCapabilities:
    """Declares which optional features a backend supports.

    Call sites MUST check capabilities before calling optional methods.
    This prevents silent no-ops and makes capability gaps explicit.
    """

    vision: bool = False
    model_listing: bool = False
    reaping: bool = False
    web_server: bool = False
    remote_session: bool = False
    streaming: bool = False
    cost_tracking: bool = False


class LLMBackend(Protocol):
    """Protocol all LLM backends must implement."""

    @property
    def name(self) -> str: ...

    @property
    def capabilities(self) -> BackendCapabilities: ...

    async def run(
        self,
        prompt: str,
        *,
        agent: str | None = None,
        workdir: Path | None = None,
        model: str | None = None,
        variant: str | None = None,
        session_id: str | None = None,
        timeout: float | None = None,
        env: dict[str, str] | None = None,
        files: list[Path] | None = None,
    ) -> LLMResult: ...

    def run_detached(
        self,
        prompt: str,
        *,
        agent: str | None = None,
        workdir: Path | None = None,
        model: str | None = None,
        variant: str | None = None,
        log_path: Path | None = None,
    ) -> None: ...

    def run_sync(
        self,
        prompt: str,
        *,
        workdir: Path | None = None,
        timeout: float | None = None,
    ) -> int: ...

    async def reap(self, adj_dir: Path) -> int: ...

    async def health_check(self, adj_dir: Path) -> bool: ...

    async def list_models(self) -> str: ...

    def find_binary(self) -> str | None: ...

    def resolve_alias(self, alias: str) -> str: ...

    def translate_model_id(self, model_id: str) -> str: ...


class BackendNotFoundError(Exception):
    """Raised when the backend binary is not available."""


def get_backend(backend_name: str | None = None) -> LLMBackend:
    """Factory: return the configured LLM backend.

    Args:
        backend_name: Explicit backend name. If None, reads from config.
    """
    if backend_name is None:
        from adjutant.core.config import load_typed_config

        backend_name = load_typed_config().llm.backend
    if backend_name == "opencode":
        from adjutant.core.backend_opencode import OpenCodeBackend

        return OpenCodeBackend()
    elif backend_name == "claude-cli":
        from adjutant.core.backend_claude_cli import ClaudeCLIBackend

        return ClaudeCLIBackend()
    raise ValueError(f"Unknown LLM backend: {backend_name!r}")
