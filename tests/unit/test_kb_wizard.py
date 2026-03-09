"""Tests for src/adjutant/setup/steps/kb_wizard.py"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from adjutant.setup.steps.kb_wizard import (
    _VALID_KB_NAME,
    _detect_content,
    _kb_create_simple,
    _kb_exists,
    kb_quick_create,
    main,
)


# ---------------------------------------------------------------------------
# _VALID_KB_NAME regex
# ---------------------------------------------------------------------------


class TestValidKbNameRegex:
    def test_valid_simple(self) -> None:
        assert _VALID_KB_NAME.match("notes") is not None

    def test_valid_with_hyphens(self) -> None:
        assert _VALID_KB_NAME.match("ml-papers") is not None

    def test_valid_with_digits(self) -> None:
        assert _VALID_KB_NAME.match("kb1") is not None

    def test_rejects_uppercase(self) -> None:
        assert _VALID_KB_NAME.match("MyKB") is None

    def test_rejects_leading_hyphen(self) -> None:
        assert _VALID_KB_NAME.match("-bad") is None

    def test_rejects_trailing_hyphen(self) -> None:
        assert _VALID_KB_NAME.match("bad-") is None

    def test_rejects_underscores(self) -> None:
        # underscores are NOT in the KB name pattern (unlike schedule wizard)
        assert _VALID_KB_NAME.match("my_kb") is None

    def test_rejects_empty(self) -> None:
        assert _VALID_KB_NAME.match("") is None


# ---------------------------------------------------------------------------
# _kb_exists
# ---------------------------------------------------------------------------


class TestKbExists:
    def _make_registry(self, adj_dir: Path, name: str) -> None:
        kb_dir = adj_dir / "knowledge_bases"
        kb_dir.mkdir(parents=True, exist_ok=True)
        (kb_dir / "registry.yaml").write_text(
            f'knowledge_bases:\n  - name: "{name}"\n    path: "/some/path"\n'
        )

    def test_returns_true_when_kb_registered(self, tmp_path: Path) -> None:
        self._make_registry(tmp_path, "notes")
        assert _kb_exists(tmp_path, "notes") is True

    def test_returns_false_when_kb_not_registered(self, tmp_path: Path) -> None:
        self._make_registry(tmp_path, "other")
        assert _kb_exists(tmp_path, "notes") is False

    def test_returns_false_when_no_registry(self, tmp_path: Path) -> None:
        assert _kb_exists(tmp_path, "notes") is False


# ---------------------------------------------------------------------------
# _detect_content
# ---------------------------------------------------------------------------


class TestDetectContent:
    def test_returns_empty_for_missing_dir(self, tmp_path: Path) -> None:
        missing = tmp_path / "nonexistent"
        assert _detect_content(missing) == "empty"

    def test_returns_empty_for_empty_dir(self, tmp_path: Path) -> None:
        d = tmp_path / "emptydir"
        d.mkdir()
        assert _detect_content(d) == "empty"

    def test_lists_contents(self, tmp_path: Path) -> None:
        d = tmp_path / "contents"
        d.mkdir()
        (d / "alpha.md").touch()
        (d / "beta.txt").touch()
        result = _detect_content(d)
        assert "alpha.md" in result
        assert "beta.txt" in result

    def test_caps_at_six_items(self, tmp_path: Path) -> None:
        d = tmp_path / "many"
        d.mkdir()
        for i in range(10):
            (d / f"file{i:02d}.txt").touch()
        result = _detect_content(d)
        # At most 6 items shown, joined by ", "
        assert len(result.split(", ")) <= 6


# ---------------------------------------------------------------------------
# _kb_create_simple
# ---------------------------------------------------------------------------


class TestKbCreateSimple:
    def test_creates_directory_structure(self, tmp_path: Path) -> None:
        adj_dir = tmp_path / "adj"
        adj_dir.mkdir()
        kb_path = tmp_path / "my-kb"

        _kb_create_simple(adj_dir, "my-kb", kb_path, "My KB", "inherit", "read-only")

        for subdir in ["data", "knowledge", "history", "templates", "scripts"]:
            assert (kb_path / subdir).is_dir()

    def test_writes_kb_yaml(self, tmp_path: Path) -> None:
        adj_dir = tmp_path / "adj"
        adj_dir.mkdir()
        kb_path = tmp_path / "my-kb"

        _kb_create_simple(adj_dir, "my-kb", kb_path, "My KB", "cheap", "read-write")

        kb_yaml = kb_path / "kb.yaml"
        assert kb_yaml.is_file()
        content = kb_yaml.read_text()
        assert 'name: "my-kb"' in content
        assert 'model: "cheap"' in content
        assert 'access: "read-write"' in content

    def test_writes_current_md(self, tmp_path: Path) -> None:
        adj_dir = tmp_path / "adj"
        adj_dir.mkdir()
        kb_path = tmp_path / "my-kb"

        _kb_create_simple(adj_dir, "my-kb", kb_path, "My KB", "inherit", "read-only")

        current_md = kb_path / "data" / "current.md"
        assert current_md.is_file()
        assert "my-kb" in current_md.read_text()

    def test_registers_in_registry(self, tmp_path: Path) -> None:
        adj_dir = tmp_path / "adj"
        adj_dir.mkdir()
        kb_path = tmp_path / "my-kb"

        _kb_create_simple(adj_dir, "my-kb", kb_path, "My KB", "inherit", "read-only")

        registry = adj_dir / "knowledge_bases" / "registry.yaml"
        assert registry.is_file()
        content = registry.read_text()
        assert 'name: "my-kb"' in content
        assert str(kb_path) in content

    def test_appends_to_existing_registry(self, tmp_path: Path) -> None:
        adj_dir = tmp_path / "adj"
        adj_dir.mkdir()
        kb_dir = adj_dir / "knowledge_bases"
        kb_dir.mkdir()
        registry = kb_dir / "registry.yaml"
        registry.write_text('knowledge_bases:\n  - name: "existing"\n    path: "/old"\n')

        kb_path = tmp_path / "new-kb"
        _kb_create_simple(adj_dir, "new-kb", kb_path, "New KB", "inherit", "read-only")

        content = registry.read_text()
        assert 'name: "existing"' in content
        assert 'name: "new-kb"' in content

    def test_does_not_overwrite_existing_current_md(self, tmp_path: Path) -> None:
        adj_dir = tmp_path / "adj"
        adj_dir.mkdir()
        kb_path = tmp_path / "my-kb"
        (kb_path / "data").mkdir(parents=True)
        (kb_path / "data" / "current.md").write_text("# Existing content\n")

        _kb_create_simple(adj_dir, "my-kb", kb_path, "My KB", "inherit", "read-only")

        assert "Existing content" in (kb_path / "data" / "current.md").read_text()


# ---------------------------------------------------------------------------
# kb_quick_create
# ---------------------------------------------------------------------------


class TestKbQuickCreate:
    def test_creates_kb_with_defaults(self, tmp_path: Path, capsys) -> None:
        adj_dir = tmp_path / "adj"
        adj_dir.mkdir()
        kb_path = str(tmp_path / "my-kb")

        kb_quick_create(adj_dir, "my-kb", kb_path)

        captured = capsys.readouterr()
        assert "OK" in captured.out
        assert "my-kb" in captured.out

    def test_raises_on_missing_name(self, tmp_path: Path) -> None:
        adj_dir = tmp_path / "adj"
        adj_dir.mkdir()
        with pytest.raises(ValueError, match="required"):
            kb_quick_create(adj_dir, "", "/some/path")

    def test_raises_on_missing_path(self, tmp_path: Path) -> None:
        adj_dir = tmp_path / "adj"
        adj_dir.mkdir()
        with pytest.raises(ValueError, match="required"):
            kb_quick_create(adj_dir, "my-kb", "")

    def test_uses_default_description(self, tmp_path: Path, capsys) -> None:
        adj_dir = tmp_path / "adj"
        adj_dir.mkdir()
        kb_path = str(tmp_path / "auto-kb")

        kb_quick_create(adj_dir, "auto-kb", kb_path)

        registry = adj_dir / "knowledge_bases" / "registry.yaml"
        content = registry.read_text()
        assert "Knowledge base: auto-kb" in content


# ---------------------------------------------------------------------------
# main (CLI)
# ---------------------------------------------------------------------------


class TestMain:
    def test_returns_1_when_adj_dir_not_set(self) -> None:
        env = {k: v for k, v in os.environ.items() if k != "ADJ_DIR"}
        with patch.dict(os.environ, env, clear=True):
            rc = main([])
        assert rc == 1

    def test_quick_mode_returns_0_on_success(self, tmp_path: Path) -> None:
        adj_dir = tmp_path / "adj"
        adj_dir.mkdir()
        kb_path = str(tmp_path / "quick-kb")

        with patch.dict(os.environ, {"ADJ_DIR": str(adj_dir)}):
            rc = main(["--quick", "--name", "quick-kb", "--path", kb_path])

        assert rc == 0

    def test_quick_mode_returns_1_on_missing_name(self, tmp_path: Path) -> None:
        adj_dir = tmp_path / "adj"
        adj_dir.mkdir()

        with patch.dict(os.environ, {"ADJ_DIR": str(adj_dir)}):
            rc = main(["--quick", "--path", "/some/path"])

        assert rc == 1

    def test_interactive_mode_returns_1_on_keyboard_interrupt(self, tmp_path: Path) -> None:
        adj_dir = tmp_path / "adj"
        adj_dir.mkdir()

        with (
            patch.dict(os.environ, {"ADJ_DIR": str(adj_dir)}),
            patch(
                "adjutant.setup.steps.kb_wizard.kb_wizard_interactive",
                side_effect=KeyboardInterrupt,
            ),
        ):
            rc = main([])

        assert rc == 1
