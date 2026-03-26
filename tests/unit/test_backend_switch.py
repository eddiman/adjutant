"""Tests for backend switch detection and side effects."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from adjutant.lifecycle.control import (
    _detect_backend_change,
    _handle_backend_switch,
    _warn_nested_opencode_dependencies,
)


class TestDetectBackendChange:
    def test_no_change_when_state_matches_config(self, adj_dir: Path) -> None:
        # Write config with opencode backend
        config = {"llm": {"backend": "opencode"}}
        (adj_dir / "adjutant.yaml").write_text(yaml.dump(config))
        # Write matching state
        (adj_dir / "state" / "backend.txt").write_text("opencode")

        result = _detect_backend_change(adj_dir)
        assert result is None

    def test_detects_change_from_opencode_to_claude(self, adj_dir: Path) -> None:
        config = {"llm": {"backend": "claude-cli"}}
        (adj_dir / "adjutant.yaml").write_text(yaml.dump(config))
        (adj_dir / "state" / "backend.txt").write_text("opencode")

        result = _detect_backend_change(adj_dir)
        assert result == "opencode"

    def test_detects_change_from_claude_to_opencode(self, adj_dir: Path) -> None:
        config = {"llm": {"backend": "opencode"}}
        (adj_dir / "adjutant.yaml").write_text(yaml.dump(config))
        (adj_dir / "state" / "backend.txt").write_text("claude-cli")

        result = _detect_backend_change(adj_dir)
        assert result == "claude-cli"

    def test_creates_state_file_on_first_run(self, adj_dir: Path) -> None:
        config = {"llm": {"backend": "opencode"}}
        (adj_dir / "adjutant.yaml").write_text(yaml.dump(config))

        result = _detect_backend_change(adj_dir)
        assert result is None
        assert (adj_dir / "state" / "backend.txt").read_text() == "opencode"

    def test_defaults_to_opencode_when_no_config(self, adj_dir: Path) -> None:
        result = _detect_backend_change(adj_dir)
        assert result is None
        assert (adj_dir / "state" / "backend.txt").read_text() == "opencode"


class TestHandleBackendSwitch:
    def test_clears_session_file(self, adj_dir: Path) -> None:
        session = adj_dir / "state" / "telegram_session.json"
        session.write_text(json.dumps({"session_id": "old-sid"}))

        with patch("adjutant.lifecycle.control._kill_by_pattern"):
            lines = _handle_backend_switch(adj_dir, "opencode", "claude-cli")

        assert not session.exists()
        assert any("session" in l.lower() for l in lines)

    def test_translates_model_id(self, adj_dir: Path) -> None:
        model_file = adj_dir / "state" / "telegram_model.txt"
        model_file.write_text("anthropic/claude-sonnet-4-6")

        with patch("adjutant.lifecycle.control._kill_by_pattern"):
            _handle_backend_switch(adj_dir, "opencode", "claude-cli")

        # Claude CLI backend translates full ID → short alias
        assert model_file.read_text() == "sonnet"

    def test_records_new_backend(self, adj_dir: Path) -> None:
        with patch("adjutant.lifecycle.control._kill_by_pattern"):
            _handle_backend_switch(adj_dir, "opencode", "claude-cli")

        assert (adj_dir / "state" / "backend.txt").read_text() == "claude-cli"

    def test_stops_opencode_web_when_switching_away(self, adj_dir: Path) -> None:
        (adj_dir / "state" / "opencode_web.pid").write_text("12345")

        with patch("adjutant.lifecycle.control._kill_by_pattern") as mock_kill:
            _handle_backend_switch(adj_dir, "opencode", "claude-cli")

        mock_kill.assert_called()
        assert not (adj_dir / "state" / "opencode_web.pid").exists()

    def test_stops_cloudcli_when_switching_away(self, adj_dir: Path) -> None:
        (adj_dir / "state" / "cloudcli_web.pid").write_text("12345")

        with patch("adjutant.lifecycle.control._kill_by_pattern") as mock_kill:
            _handle_backend_switch(adj_dir, "claude-cli", "opencode")

        mock_kill.assert_called()
        assert not (adj_dir / "state" / "cloudcli_web.pid").exists()

    def test_no_crash_when_no_session_or_model(self, adj_dir: Path) -> None:
        """Switch works even when there's no session or model file."""
        with patch("adjutant.lifecycle.control._kill_by_pattern"):
            lines = _handle_backend_switch(adj_dir, "opencode", "claude-cli")

        assert any("switched" in l.lower() for l in lines)

    def test_warns_nested_opencode_deps_on_switch_to_claude(self, adj_dir: Path) -> None:
        """Switching to claude-cli warns about KBs that internally use opencode."""
        from adjutant.capabilities.kb.manage import KBEntry

        fake_kbs = [
            KBEntry(name="portfolio", path="/vol/portfolio-kb"),
            KBEntry(name="ixda", path="/vol/ixda"),
        ]
        with (
            patch("adjutant.lifecycle.control._kill_by_pattern"),
            patch("adjutant.capabilities.kb.manage.kb_list", return_value=fake_kbs),
        ):
            lines = _handle_backend_switch(adj_dir, "opencode", "claude-cli")

        assert any("portfolio" in l and "OpenCode" in l for l in lines)

    def test_no_nested_warning_on_switch_to_opencode(self, adj_dir: Path) -> None:
        """Switching to opencode does not warn about nested deps."""
        with patch("adjutant.lifecycle.control._kill_by_pattern"):
            lines = _handle_backend_switch(adj_dir, "claude-cli", "opencode")

        assert not any("internally use OpenCode" in l for l in lines)


class TestWarnNestedDependencies:
    def test_warns_for_portfolio_kb(self, adj_dir: Path) -> None:
        from adjutant.capabilities.kb.manage import KBEntry

        fake_kbs = [
            KBEntry(name="portfolio", path="/vol/portfolio-kb"),
            KBEntry(name="hopen", path="/vol/hopen"),
        ]
        with patch("adjutant.capabilities.kb.manage.kb_list", return_value=fake_kbs):
            warnings = _warn_nested_opencode_dependencies(adj_dir)

        assert len(warnings) == 1
        assert "portfolio" in warnings[0]

    def test_no_warning_without_portfolio(self, adj_dir: Path) -> None:
        from adjutant.capabilities.kb.manage import KBEntry

        fake_kbs = [
            KBEntry(name="ixda", path="/vol/ixda"),
            KBEntry(name="hopen", path="/vol/hopen"),
        ]
        with patch("adjutant.capabilities.kb.manage.kb_list", return_value=fake_kbs):
            warnings = _warn_nested_opencode_dependencies(adj_dir)

        assert warnings == []

    def test_handles_missing_registry(self, adj_dir: Path) -> None:
        """No crash when registry is unavailable."""
        warnings = _warn_nested_opencode_dependencies(adj_dir)
        assert warnings == []
