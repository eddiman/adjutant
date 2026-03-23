"""Shared test fixtures for the Adjutant Python test suite."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml


# ---------------------------------------------------------------------------
# Backend-aware auto-skip
# ---------------------------------------------------------------------------


def _get_active_backend() -> str:
    """Read active backend from adjutant.yaml if it exists."""
    for candidate in [
        Path.home() / ".adjutant" / "adjutant.yaml",
        Path(__file__).parent.parent / "adjutant.yaml",
    ]:
        if candidate.exists():
            try:
                from adjutant.core.config import AdjutantConfig

                config = AdjutantConfig.load(candidate)
                return config.llm.backend
            except Exception:  # noqa: BLE001
                pass
    return "opencode"


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-all-backends",
        action="store_true",
        default=False,
        help="Run tests for ALL backends, not just the active one",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Auto-skip backend-specific tests when that backend is not active."""
    if config.getoption("--run-all-backends", default=False):
        return
    markexpr = config.getoption("-m", default="")
    if "backend_opencode" in markexpr or "backend_claude_cli" in markexpr:
        return

    active = _get_active_backend()
    skip_oc = pytest.mark.skip(reason="opencode backend not active")
    skip_cc = pytest.mark.skip(reason="claude-cli backend not active")

    for item in items:
        if "backend_opencode" in item.keywords and active != "opencode":
            item.add_marker(skip_oc)
        if "backend_claude_cli" in item.keywords and active != "claude-cli":
            item.add_marker(skip_cc)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def adj_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create isolated adjutant directory with standard subdirectories."""
    adj = tmp_path / ".adjutant"
    adj.mkdir()
    (adj / "state").mkdir()
    (adj / "knowledge_bases").mkdir()
    (adj / "identity").mkdir()
    (adj / "scripts" / "lifecycle").mkdir(parents=True)
    monkeypatch.setenv("ADJUTANT_HOME", str(adj))
    monkeypatch.setenv("ADJ_DIR", str(adj))
    monkeypatch.setenv("ADJUTANT_DIR", str(adj))
    return adj


@pytest.fixture
def adj_env(adj_dir: Path) -> Path:
    """Create .env file with test credentials. Returns path to .env."""
    env_file = adj_dir / ".env"
    env_file.write_text(
        "TELEGRAM_BOT_TOKEN=test-token-123\n"
        "TELEGRAM_CHAT_ID=12345678\n"
        "BRAVE_API_KEY=test-brave-key\n"
    )
    return env_file


@pytest.fixture
def adj_config(adj_dir: Path) -> dict:
    """Create adjutant.yaml with standard config for testing."""
    config = {
        "instance": {"name": "test"},
        "messaging": {
            "backend": "telegram",
            "telegram": {
                "session_timeout_seconds": 7200,
                "default_model": "anthropic/claude-haiku-4-5",
                "rate_limit": {"messages_per_minute": 10},
            },
        },
        "llm": {
            "models": {
                "cheap": "anthropic/claude-haiku-4-5",
                "medium": "anthropic/claude-sonnet-4-6",
                "expensive": "anthropic/claude-opus-4-6",
            }
        },
        "features": {
            "news": {"enabled": False},
            "screenshot": {"enabled": False},
            "vision": {"enabled": False},
            "search": {"enabled": False},
        },
        "notifications": {"max_per_day": 3, "quiet_hours": {"enabled": False}},
        "debug": {"dry_run": False, "verbose_logging": False},
    }
    (adj_dir / "adjutant.yaml").write_text(yaml.dump(config))
    return config


@pytest.fixture
def mock_opencode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Mock opencode binary returning NDJSON."""
    mock_bin = tmp_path / "bin"
    mock_bin.mkdir()
    script = mock_bin / "opencode"
    script.write_text('#!/bin/bash\necho \'{"type":"text","part":{"text":"OK"}}\'')
    script.chmod(0o755)
    monkeypatch.setenv("PATH", f"{mock_bin}:{os.environ['PATH']}")
    return script


@pytest.fixture
def mock_claude(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Mock claude binary returning valid JSON response."""
    mock_bin = tmp_path / "bin"
    mock_bin.mkdir(exist_ok=True)
    script = mock_bin / "claude"
    script.write_text(
        '#!/bin/bash\n'
        'echo \'{"result":"OK","session_id":"test-uuid-123","is_error":false}\'\n'
    )
    script.chmod(0o755)
    monkeypatch.setenv("PATH", f"{mock_bin}:{os.environ['PATH']}")
    return script


@pytest.fixture
def sample_kb(adj_dir: Path) -> Path:
    """Create a sample KB for testing."""
    kb_dir = adj_dir / "knowledge_bases" / "test-kb"
    kb_dir.mkdir(parents=True)
    (kb_dir / "kb.yaml").write_text(
        'name: "test-kb"\ndescription: "Test KB"\nmodel: "inherit"\naccess: "read-only"\n'
    )
    return kb_dir
