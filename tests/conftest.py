"""Shared test fixtures for the Adjutant Python test suite."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml


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
                "expensive": "anthropic/claude-opus-4-5",
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
def sample_kb(adj_dir: Path) -> Path:
    """Create a sample KB for testing."""
    kb_dir = adj_dir / "knowledge_bases" / "test-kb"
    kb_dir.mkdir(parents=True)
    (kb_dir / "kb.yaml").write_text(
        'name: "test-kb"\ndescription: "Test KB"\nmodel: "inherit"\naccess: "read-only"\n'
    )
    return kb_dir
