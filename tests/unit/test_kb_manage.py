"""Unit tests for adjutant.capabilities.kb.manage."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from adjutant.capabilities.kb.manage import (
    KBEntry,
    _load_registry,
    _write_registry,
    kb_count,
    kb_exists,
    kb_get_field,
    kb_get_operation_script,
    kb_info,
    kb_list,
    kb_register,
    kb_unregister,
    kb_scaffold,
    kb_detect_content,
    kb_create,
    kb_remove,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_registry_yaml(adj_dir: Path, entries: list[dict]) -> None:
    kb_dir = adj_dir / "knowledge_bases"
    kb_dir.mkdir(parents=True, exist_ok=True)
    lines = ["knowledge_bases:"]
    for e in entries:
        lines.append(f'  - name: "{e["name"]}"')
        if "path" in e:
            lines.append(f'    path: "{e["path"]}"')
        if "description" in e:
            lines.append(f'    description: "{e["description"]}"')
        if "model" in e:
            lines.append(f'    model: "{e["model"]}"')
        if "access" in e:
            lines.append(f'    access: "{e["access"]}"')
        if "created" in e:
            lines.append(f'    created: "{e["created"]}"')
    (kb_dir / "registry.yaml").write_text("\n".join(lines) + "\n")


def _registry_path(adj_dir: Path) -> Path:
    return adj_dir / "knowledge_bases" / "registry.yaml"


# ---------------------------------------------------------------------------
# _load_registry / _write_registry
# ---------------------------------------------------------------------------


class TestLoadRegistry:
    def test_returns_empty_list_when_no_file(self, tmp_path: Path) -> None:
        result = _load_registry(_registry_path(tmp_path))
        assert result == []

    def test_parses_single_entry(self, tmp_path: Path) -> None:
        _write_registry_yaml(tmp_path, [{"name": "notes", "path": "/kb/notes"}])
        entries = _load_registry(_registry_path(tmp_path))
        assert len(entries) == 1
        assert entries[0].name == "notes"
        assert entries[0].path == "/kb/notes"

    def test_parses_all_fields(self, tmp_path: Path) -> None:
        _write_registry_yaml(
            tmp_path,
            [
                {
                    "name": "finance",
                    "path": "/kb/finance",
                    "description": "Finance data",
                    "model": "gpt-4",
                    "access": "read-write",
                    "created": "2025-01-01",
                }
            ],
        )
        entry = _load_registry(_registry_path(tmp_path))[0]
        assert entry.description == "Finance data"
        assert entry.model == "gpt-4"
        assert entry.access == "read-write"
        assert entry.created == "2025-01-01"

    def test_parses_multiple_entries(self, tmp_path: Path) -> None:
        _write_registry_yaml(
            tmp_path,
            [
                {"name": "a", "path": "/kb/a"},
                {"name": "b", "path": "/kb/b"},
            ],
        )
        entries = _load_registry(_registry_path(tmp_path))
        assert len(entries) == 2
        assert {e.name for e in entries} == {"a", "b"}


class TestWriteRegistry:
    def test_writes_empty_registry(self, tmp_path: Path) -> None:
        path = _registry_path(tmp_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        _write_registry(path, [])
        assert path.read_text() == "knowledge_bases: []\n"

    def test_round_trips_entries(self, tmp_path: Path) -> None:
        path = _registry_path(tmp_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        entries = [
            KBEntry(
                name="mydb",
                path="/kb/mydb",
                description="My DB",
                model="inherit",
                access="read-only",
                created="2025-06-01",
            )
        ]
        _write_registry(path, entries)
        loaded = _load_registry(path)
        assert len(loaded) == 1
        assert loaded[0].name == "mydb"
        assert loaded[0].path == "/kb/mydb"
        assert loaded[0].description == "My DB"


# ---------------------------------------------------------------------------
# Query API
# ---------------------------------------------------------------------------


class TestKbCount:
    def test_zero_when_empty(self, tmp_path: Path) -> None:
        assert kb_count(tmp_path) == 0

    def test_counts_entries(self, tmp_path: Path) -> None:
        _write_registry_yaml(
            tmp_path,
            [{"name": "a", "path": "/a"}, {"name": "b", "path": "/b"}],
        )
        assert kb_count(tmp_path) == 2


class TestKbExists:
    def test_returns_false_when_not_found(self, tmp_path: Path) -> None:
        assert kb_exists(tmp_path, "ghost") is False

    def test_returns_true_when_found(self, tmp_path: Path) -> None:
        _write_registry_yaml(tmp_path, [{"name": "notes", "path": "/notes"}])
        assert kb_exists(tmp_path, "notes") is True

    def test_case_sensitive(self, tmp_path: Path) -> None:
        _write_registry_yaml(tmp_path, [{"name": "notes", "path": "/notes"}])
        assert kb_exists(tmp_path, "Notes") is False


class TestKbList:
    def test_empty_registry(self, tmp_path: Path) -> None:
        assert kb_list(tmp_path) == []

    def test_returns_all_entries(self, tmp_path: Path) -> None:
        _write_registry_yaml(
            tmp_path,
            [{"name": "a", "path": "/a"}, {"name": "b", "path": "/b"}],
        )
        entries = kb_list(tmp_path)
        assert len(entries) == 2


class TestKbInfo:
    def test_returns_entry(self, tmp_path: Path) -> None:
        _write_registry_yaml(tmp_path, [{"name": "finance", "path": "/fin"}])
        entry = kb_info(tmp_path, "finance")
        assert entry.name == "finance"
        assert entry.path == "/fin"

    def test_raises_value_error_when_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="ghost"):
            kb_info(tmp_path, "ghost")


class TestKbGetField:
    def test_returns_field_value(self, tmp_path: Path) -> None:
        _write_registry_yaml(
            tmp_path,
            [{"name": "kb1", "path": "/kb1", "description": "Some KB"}],
        )
        assert kb_get_field(tmp_path, "kb1", "description") == "Some KB"

    def test_returns_empty_string_when_kb_not_found(self, tmp_path: Path) -> None:
        assert kb_get_field(tmp_path, "ghost", "description") == ""

    def test_returns_empty_string_for_unknown_field(self, tmp_path: Path) -> None:
        _write_registry_yaml(tmp_path, [{"name": "kb1", "path": "/kb1"}])
        assert kb_get_field(tmp_path, "kb1", "nonexistent_field") == ""


class TestKbGetOperationScript:
    def test_raises_on_invalid_operation(self, tmp_path: Path) -> None:
        _write_registry_yaml(tmp_path, [{"name": "kb1", "path": str(tmp_path / "kb1")}])
        with pytest.raises(ValueError, match="Invalid"):
            kb_get_operation_script(tmp_path, "kb1", "../evil")

    def test_raises_when_kb_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="ghost"):
            kb_get_operation_script(tmp_path, "ghost", "fetch")

    def test_raises_when_kb_dir_missing(self, tmp_path: Path) -> None:
        _write_registry_yaml(tmp_path, [{"name": "kb1", "path": str(tmp_path / "nonexistent")}])
        with pytest.raises(ValueError, match="does not exist"):
            kb_get_operation_script(tmp_path, "kb1", "fetch")

    def test_raises_when_script_missing(self, tmp_path: Path) -> None:
        kb_path = tmp_path / "kb1"
        (kb_path / "scripts").mkdir(parents=True)
        _write_registry_yaml(tmp_path, [{"name": "kb1", "path": str(kb_path)}])
        with pytest.raises(ValueError, match="fetch"):
            kb_get_operation_script(tmp_path, "kb1", "fetch")

    def test_returns_script_path_when_exists(self, tmp_path: Path) -> None:
        kb_path = tmp_path / "kb1"
        scripts_dir = kb_path / "scripts"
        scripts_dir.mkdir(parents=True)
        script = scripts_dir / "fetch.sh"
        script.write_text("#!/bin/bash\necho done\n")
        script.chmod(0o755)
        _write_registry_yaml(tmp_path, [{"name": "kb1", "path": str(kb_path)}])
        result = kb_get_operation_script(tmp_path, "kb1", "fetch")
        assert result == script


# ---------------------------------------------------------------------------
# Registry mutations
# ---------------------------------------------------------------------------


class TestKbRegister:
    def test_registers_new_kb(self, tmp_path: Path) -> None:
        kb_register(tmp_path, "mydb", "/kb/mydb", "My DB")
        assert kb_exists(tmp_path, "mydb")

    def test_raises_if_already_registered(self, tmp_path: Path) -> None:
        kb_register(tmp_path, "mydb", "/kb/mydb", "My DB")
        with pytest.raises(ValueError, match="already registered"):
            kb_register(tmp_path, "mydb", "/kb/mydb", "My DB again")

    def test_stores_all_fields(self, tmp_path: Path) -> None:
        kb_register(
            tmp_path,
            "finance",
            "/kb/finance",
            "Finance data",
            model="gpt-4",
            access="read-write",
            created="2025-01-01",
        )
        entry = kb_info(tmp_path, "finance")
        assert entry.model == "gpt-4"
        assert entry.access == "read-write"
        assert entry.created == "2025-01-01"

    def test_auto_sets_created_if_not_given(self, tmp_path: Path) -> None:
        kb_register(tmp_path, "kb1", "/kb/kb1", "desc")
        entry = kb_info(tmp_path, "kb1")
        assert entry.created  # non-empty


class TestKbUnregister:
    def test_removes_registered_kb(self, tmp_path: Path) -> None:
        _write_registry_yaml(tmp_path, [{"name": "mydb", "path": "/mydb"}])
        kb_unregister(tmp_path, "mydb")
        assert not kb_exists(tmp_path, "mydb")

    def test_raises_when_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="not found"):
            kb_unregister(tmp_path, "ghost")

    def test_removes_only_target(self, tmp_path: Path) -> None:
        _write_registry_yaml(
            tmp_path,
            [{"name": "a", "path": "/a"}, {"name": "b", "path": "/b"}],
        )
        kb_unregister(tmp_path, "a")
        assert not kb_exists(tmp_path, "a")
        assert kb_exists(tmp_path, "b")


# ---------------------------------------------------------------------------
# kb_scaffold
# ---------------------------------------------------------------------------


class TestKbScaffold:
    def _make_templates(self, adj_dir: Path) -> None:
        """Create minimal template files."""
        tmpl = adj_dir / "templates" / "kb"
        (tmpl / "agents").mkdir(parents=True)
        (tmpl / "docs").mkdir(parents=True)
        (tmpl / "kb.yaml").write_text("name: {{KB_NAME}}\nmodel: {{KB_MODEL}}\n")
        (tmpl / "opencode.json").write_text('{"version": 1}\n')
        (tmpl / "agents" / "kb.md").write_text("# {{KB_NAME}}\n{{KB_DESCRIPTION}}\n")
        (tmpl / "docs" / "README.md").write_text("# {{KB_NAME}} README\n")

    def test_creates_directory_structure(self, tmp_path: Path) -> None:
        self._make_templates(tmp_path)
        kb_path = tmp_path / "kb1"
        kb_scaffold(tmp_path, "kb1", kb_path, "Test KB")
        assert (kb_path / "data").is_dir()
        assert (kb_path / "knowledge").is_dir()
        assert (kb_path / "history").is_dir()
        assert (kb_path / "state").is_dir()
        assert (kb_path / "templates").is_dir()

    def test_renders_template_variables(self, tmp_path: Path) -> None:
        self._make_templates(tmp_path)
        kb_path = tmp_path / "kb1"
        kb_scaffold(tmp_path, "kb1", kb_path, "My KB", model="gpt-4")
        content = (kb_path / "kb.yaml").read_text()
        assert "kb1" in content
        assert "gpt-4" in content
        assert "{{KB_NAME}}" not in content

    def test_creates_current_md_stub(self, tmp_path: Path) -> None:
        self._make_templates(tmp_path)
        kb_path = tmp_path / "kb1"
        kb_scaffold(tmp_path, "kb1", kb_path, "Test KB")
        current_md = kb_path / "data" / "current.md"
        assert current_md.is_file()
        assert "kb1" in current_md.read_text()

    def test_does_not_overwrite_existing_current_md(self, tmp_path: Path) -> None:
        self._make_templates(tmp_path)
        kb_path = tmp_path / "kb1"
        kb_path.mkdir(parents=True)
        (kb_path / "data").mkdir()
        existing = kb_path / "data" / "current.md"
        existing.write_text("# Existing content\n")
        kb_scaffold(tmp_path, "kb1", kb_path, "Test KB")
        assert existing.read_text() == "# Existing content\n"

    def test_does_not_create_readme_if_docs_md_exists(self, tmp_path: Path) -> None:
        self._make_templates(tmp_path)
        kb_path = tmp_path / "kb1"
        kb_path.mkdir(parents=True)
        (kb_path / "docs").mkdir(parents=True)
        (kb_path / "docs" / "EXISTING.md").write_text("existing doc\n")
        kb_scaffold(tmp_path, "kb1", kb_path, "Test KB")
        assert not (kb_path / "docs" / "README.md").exists()

    def test_works_without_template_files(self, tmp_path: Path) -> None:
        # No template dir — should not crash
        kb_path = tmp_path / "kb1"
        kb_scaffold(tmp_path, "kb1", kb_path, "Test KB")
        assert (kb_path / "data").is_dir()


# ---------------------------------------------------------------------------
# kb_detect_content
# ---------------------------------------------------------------------------


class TestKbDetectContent:
    def test_returns_empty_for_nonexistent_dir(self, tmp_path: Path) -> None:
        assert kb_detect_content(tmp_path / "nonexistent") == "empty"

    def test_detects_markdown(self, tmp_path: Path) -> None:
        kb = tmp_path / "kb"
        kb.mkdir()
        (kb / "notes.md").write_text("# Hello\n")
        result = kb_detect_content(kb)
        assert "markdown" in result

    def test_detects_code(self, tmp_path: Path) -> None:
        kb = tmp_path / "kb"
        kb.mkdir()
        (kb / "script.py").write_text("print('hi')\n")
        result = kb_detect_content(kb)
        assert "code" in result

    def test_detects_multiple_types(self, tmp_path: Path) -> None:
        kb = tmp_path / "kb"
        kb.mkdir()
        (kb / "a.md").write_text("# doc\n")
        (kb / "b.py").write_text("# code\n")
        result = kb_detect_content(kb)
        assert "markdown" in result
        assert "code" in result

    def test_returns_empty_for_empty_dir(self, tmp_path: Path) -> None:
        kb = tmp_path / "kb"
        kb.mkdir()
        assert kb_detect_content(kb) == "empty"


# ---------------------------------------------------------------------------
# kb_create / kb_remove
# ---------------------------------------------------------------------------


class TestKbCreate:
    def test_creates_and_registers(self, tmp_path: Path) -> None:
        kb_path = tmp_path / "kb1"
        kb_create(tmp_path, "kb1", kb_path, "Test KB")
        assert kb_exists(tmp_path, "kb1")
        assert (kb_path / "data").is_dir()

    def test_raises_on_invalid_name(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="lowercase"):
            kb_create(tmp_path, "My_KB!", tmp_path / "kb1", "Test KB")

    def test_raises_on_relative_path(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="absolute"):
            kb_create(tmp_path, "kb1", Path("relative/path"), "Test KB")

    def test_raises_if_name_already_registered(self, tmp_path: Path) -> None:
        kb_path = tmp_path / "kb1"
        kb_create(tmp_path, "kb1", kb_path, "First")
        with pytest.raises(ValueError, match="already registered"):
            kb_create(tmp_path, "kb1", tmp_path / "kb1b", "Second")

    def test_valid_name_with_hyphens(self, tmp_path: Path) -> None:
        kb_path = tmp_path / "my-kb"
        kb_create(tmp_path, "my-kb", kb_path, "Hyphen KB")
        assert kb_exists(tmp_path, "my-kb")


class TestKbRemove:
    def test_unregisters_kb(self, tmp_path: Path) -> None:
        _write_registry_yaml(tmp_path, [{"name": "notes", "path": "/notes"}])
        kb_remove(tmp_path, "notes")
        assert not kb_exists(tmp_path, "notes")

    def test_raises_if_not_registered(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="not found"):
            kb_remove(tmp_path, "ghost")

    def test_does_not_delete_files(self, tmp_path: Path) -> None:
        kb_path = tmp_path / "mydb"
        kb_path.mkdir()
        (kb_path / "data.txt").write_text("important\n")
        _write_registry_yaml(tmp_path, [{"name": "mydb", "path": str(kb_path)}])
        kb_remove(tmp_path, "mydb")
        assert (kb_path / "data.txt").exists()
