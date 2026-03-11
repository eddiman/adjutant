"""Tests for src/adjutant/setup/steps/identity.py"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from adjutant.setup.steps.identity import (
    _estimate_tokens,
    _extract_opencode_text,
    _heart_template,
    _write_templates,
    step_identity,
)


class TestEstimateTokens:
    def test_basic(self) -> None:
        assert _estimate_tokens("hello world") == max(1, len("hello world") // 4)

    def test_empty_string_returns_one(self) -> None:
        assert _estimate_tokens("") == 1

    def test_long_text(self) -> None:
        text = "a" * 400
        assert _estimate_tokens(text) == 100


class TestExtractOpencodeText:
    def test_extracts_text_parts(self) -> None:
        lines = [
            json.dumps({"part": {"text": "Hello "}}),
            json.dumps({"part": {"text": "world"}}),
        ]
        result = _extract_opencode_text("\n".join(lines))
        assert result == "Hello world"

    def test_skips_non_text_parts(self) -> None:
        lines = [
            json.dumps({"part": {"type": "tool_call"}}),
            json.dumps({"part": {"text": "Answer"}}),
        ]
        result = _extract_opencode_text("\n".join(lines))
        assert result == "Answer"

    def test_handles_invalid_json(self) -> None:
        result = _extract_opencode_text("not json\n{bad}")
        assert result == ""

    def test_empty_input(self) -> None:
        assert _extract_opencode_text("") == ""


class TestHeartTemplate:
    def test_contains_date(self) -> None:
        result = _heart_template("2026-03-10")
        assert "2026-03-10" in result

    def test_contains_expected_sections(self) -> None:
        result = _heart_template("2026-01-01")
        assert "Current Priorities" in result
        assert "Active Concerns" in result


class TestWriteTemplates:
    def test_creates_soul_heart_registry(self, tmp_path: Path) -> None:
        _write_templates(tmp_path)
        identity_dir = tmp_path / "identity"
        assert (identity_dir / "soul.md").is_file()
        assert (identity_dir / "heart.md").is_file()
        assert (identity_dir / "registry.md").is_file()

    def test_dry_run_does_not_write(self, tmp_path: Path) -> None:
        _write_templates(tmp_path, dry_run=True)
        assert not (tmp_path / "identity" / "soul.md").is_file()

    def test_does_not_overwrite_existing_registry(self, tmp_path: Path) -> None:
        identity_dir = tmp_path / "identity"
        identity_dir.mkdir()
        existing = identity_dir / "registry.md"
        existing.write_text("custom registry")
        _write_templates(tmp_path)
        assert existing.read_text() == "custom registry"


class TestStepIdentity:
    def test_uses_templates_when_no_opencode(self, tmp_path: Path, capsys) -> None:
        with patch("shutil.which", return_value=None):
            with patch("builtins.input", side_effect=["adjutant", "I need monitoring\n"]):
                result = step_identity(tmp_path)
        assert result is True
        assert (tmp_path / "identity" / "soul.md").is_file()

    def test_skips_regen_when_files_exist_and_user_declines(self, tmp_path: Path, capsys) -> None:
        identity_dir = tmp_path / "identity"
        identity_dir.mkdir()
        (identity_dir / "soul.md").write_text("existing soul")
        (identity_dir / "heart.md").write_text("existing heart")

        # User says N to regenerate
        with patch("builtins.input", return_value="n"):
            result = step_identity(tmp_path)
        assert result is True
        assert (identity_dir / "soul.md").read_text() == "existing soul"

    def test_regenerates_and_backs_up_when_confirmed(self, tmp_path: Path, capsys) -> None:
        identity_dir = tmp_path / "identity"
        identity_dir.mkdir()
        (identity_dir / "soul.md").write_text("old soul")
        (identity_dir / "heart.md").write_text("old heart")

        # user says y to regen, then provides name and description (two blank lines terminate
        # _wiz_multiline), then N to LLM cost confirm
        responses = iter(["y", "myagent", "I do stuff", "", "", "n"])
        with patch("builtins.input", side_effect=lambda: next(responses)):
            with patch("shutil.which", return_value="/usr/bin/opencode"):
                result = step_identity(tmp_path)
        assert result is True
        # Backup files should exist
        backups = list(identity_dir.glob("soul.md.backup.*"))
        assert len(backups) == 1

    def test_writes_templates_on_empty_description(self, tmp_path: Path, capsys) -> None:
        # User provides empty description → templates (two blank lines to terminate _wiz_multiline)
        responses = iter(["adjutant", "", ""])
        with patch("builtins.input", side_effect=lambda: next(responses)):
            with patch("shutil.which", return_value="/usr/bin/opencode"):
                result = step_identity(tmp_path)
        assert result is True
        assert (tmp_path / "identity" / "soul.md").is_file()
