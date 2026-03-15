"""Shared fixtures for integration tests.

Integration tests exercise real process spawning, file I/O, and locking
but mock external services (Telegram API, opencode, crontab).

Run with: .venv/bin/pytest tests/integration/ -m integration
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.fixture()
def adj_dir(tmp_path: Path) -> Path:
    """Create a full adj_dir structure with all required files."""
    d = tmp_path / "adjutant"
    d.mkdir()

    # Root marker
    (d / ".adjutant-root").touch()

    # Config
    (d / "adjutant.yaml").write_text(
        "instance:\n"
        "  name: test-instance\n"
        "messaging:\n"
        "  backend: telegram\n"
        "  telegram:\n"
        "    session_timeout_seconds: 7200\n"
        "    chat_timeout_seconds: 240\n"
        "    rate_limit:\n"
        "      messages_per_minute: 10\n"
        "      window_seconds: 60\n"
        "features:\n"
        "  news:\n"
        "    enabled: false\n"
        "  screenshot:\n"
        "    enabled: false\n"
        "  vision:\n"
        "    enabled: true\n"
        "  search:\n"
        "    enabled: false\n"
        "  usage_tracking:\n"
        "    enabled: false\n"
    )

    # Secrets
    (d / ".env").write_text("TELEGRAM_BOT_TOKEN=test-token-12345\nTELEGRAM_CHAT_ID=99999\n")

    # State directory
    (d / "state").mkdir()

    # Journal directory
    (d / "journal").mkdir()

    # Identity stubs
    identity = d / "identity"
    identity.mkdir()
    (identity / "soul.md").write_text("Test soul.\n")
    (identity / "heart.md").write_text("Test heart.\n")
    (identity / "registry.md").write_text("Test registry.\n")

    # Knowledge bases directory
    kb_dir = d / "knowledge_bases"
    kb_dir.mkdir()
    (kb_dir / "registry.yaml").write_text("knowledge_bases: []\n")

    # Prompts
    prompts = d / "prompts"
    prompts.mkdir()
    (prompts / "pulse.md").write_text("Test pulse prompt.\n")
    (prompts / "review.md").write_text("Test review prompt.\n")

    return d
