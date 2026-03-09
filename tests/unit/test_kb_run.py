"""Tests for src/adjutant/capabilities/kb/run.py"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from adjutant.capabilities.kb.run import (
    KBNotFoundError,
    KBOperationNotFoundError,
    KBRunError,
    _load_registry,
    get_operation_script,
    kb_run,
    main,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_registry(adj_dir: Path, entries: list[dict[str, str]]) -> None:
    """Write a minimal registry.yaml."""
    kb_dir = adj_dir / "knowledge_bases"
    kb_dir.mkdir(parents=True, exist_ok=True)
    lines = ["knowledge_bases:"]
    for e in entries:
        lines.append(f'  - name: "{e["name"]}"')
        lines.append(f'    path: "{e["path"]}"')
        if "description" in e:
            lines.append(f'    description: "{e["description"]}"')
        if "model" in e:
            lines.append(f'    model: "{e["model"]}"')
        if "access" in e:
            lines.append(f'    access: "{e["access"]}"')
    (kb_dir / "registry.yaml").write_text("\n".join(lines) + "\n")


def _make_kb(tmp_path: Path, name: str, operations: list[str] | None = None) -> Path:
    """Create a minimal KB directory with optional operation scripts."""
    kb_path = tmp_path / f"kb_{name}"
    scripts_dir = kb_path / "scripts"
    scripts_dir.mkdir(parents=True)
    for op in operations or []:
        script = scripts_dir / f"{op}.sh"
        script.write_text(f"#!/bin/bash\necho 'ran {op}'\n")
        script.chmod(0o755)
    return kb_path


# ---------------------------------------------------------------------------
# _load_registry
# ---------------------------------------------------------------------------


class TestLoadRegistry:
    def test_returns_empty_list_when_no_registry(self, tmp_path: Path) -> None:
        assert _load_registry(tmp_path) == []

    def test_parses_single_entry(self, tmp_path: Path) -> None:
        kb_path = _make_kb(tmp_path, "notes")
        _make_registry(tmp_path, [{"name": "notes", "path": str(kb_path)}])
        entries = _load_registry(tmp_path)
        assert len(entries) == 1
        assert entries[0]["name"] == "notes"
        assert entries[0]["path"] == str(kb_path)

    def test_parses_multiple_entries(self, tmp_path: Path) -> None:
        kb1 = _make_kb(tmp_path, "kb1")
        kb2 = _make_kb(tmp_path, "kb2")
        _make_registry(
            tmp_path,
            [
                {"name": "kb1", "path": str(kb1)},
                {"name": "kb2", "path": str(kb2)},
            ],
        )
        entries = _load_registry(tmp_path)
        assert len(entries) == 2
        assert {e["name"] for e in entries} == {"kb1", "kb2"}

    def test_parses_optional_fields(self, tmp_path: Path) -> None:
        kb_path = _make_kb(tmp_path, "notes")
        _make_registry(
            tmp_path,
            [
                {
                    "name": "notes",
                    "path": str(kb_path),
                    "description": "My notes",
                    "model": "inherit",
                    "access": "read-only",
                }
            ],
        )
        entry = _load_registry(tmp_path)[0]
        assert entry["description"] == "My notes"
        assert entry["model"] == "inherit"
        assert entry["access"] == "read-only"


# ---------------------------------------------------------------------------
# get_operation_script
# ---------------------------------------------------------------------------


class TestGetOperationScript:
    def test_returns_script_path_when_exists(self, tmp_path: Path) -> None:
        kb_path = _make_kb(tmp_path, "mydb", ["fetch"])
        _make_registry(tmp_path, [{"name": "mydb", "path": str(kb_path)}])
        script = get_operation_script(tmp_path, "mydb", "fetch")
        assert script == kb_path / "scripts" / "fetch.sh"
        assert script.is_file()

    def test_raises_kb_not_found(self, tmp_path: Path) -> None:
        _make_registry(tmp_path, [])
        with pytest.raises(KBNotFoundError, match="ghost"):
            get_operation_script(tmp_path, "ghost", "fetch")

    def test_raises_operation_not_found(self, tmp_path: Path) -> None:
        kb_path = _make_kb(tmp_path, "mydb")  # no operations
        _make_registry(tmp_path, [{"name": "mydb", "path": str(kb_path)}])
        with pytest.raises(KBOperationNotFoundError, match="analyze"):
            get_operation_script(tmp_path, "mydb", "analyze")

    def test_raises_on_invalid_operation_name(self, tmp_path: Path) -> None:
        kb_path = _make_kb(tmp_path, "mydb")
        _make_registry(tmp_path, [{"name": "mydb", "path": str(kb_path)}])
        with pytest.raises(ValueError, match="Invalid"):
            get_operation_script(tmp_path, "mydb", "../etc/passwd")

    def test_raises_on_missing_kb_directory(self, tmp_path: Path) -> None:
        _make_registry(tmp_path, [{"name": "ghost", "path": str(tmp_path / "nonexistent")}])
        with pytest.raises(KBNotFoundError, match="does not exist"):
            get_operation_script(tmp_path, "ghost", "fetch")

    def test_valid_operation_name_with_hyphens_and_digits(self, tmp_path: Path) -> None:
        kb_path = _make_kb(tmp_path, "mydb", ["sync-data2"])
        _make_registry(tmp_path, [{"name": "mydb", "path": str(kb_path)}])
        script = get_operation_script(tmp_path, "mydb", "sync-data2")
        assert script.name == "sync-data2.sh"


# ---------------------------------------------------------------------------
# kb_run
# ---------------------------------------------------------------------------


class TestKbRun:
    def test_runs_operation_and_returns_output(self, tmp_path: Path) -> None:
        kb_path = _make_kb(tmp_path, "mydb", ["fetch"])
        _make_registry(tmp_path, [{"name": "mydb", "path": str(kb_path)}])

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = type(
                "R", (), {"returncode": 0, "stdout": "OK:fetched\n", "stderr": ""}
            )()
            result = kb_run(tmp_path, "mydb", "fetch")

        assert result == "OK:fetched\n"

    def test_raises_kb_run_error_on_nonzero_exit(self, tmp_path: Path) -> None:
        kb_path = _make_kb(tmp_path, "mydb", ["fetch"])
        _make_registry(tmp_path, [{"name": "mydb", "path": str(kb_path)}])

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = type(
                "R", (), {"returncode": 1, "stdout": "", "stderr": "Something broke"}
            )()
            with pytest.raises(KBRunError, match="Something broke"):
                kb_run(tmp_path, "mydb", "fetch")

    def test_passes_extra_args(self, tmp_path: Path) -> None:
        kb_path = _make_kb(tmp_path, "mydb", ["sync"])
        _make_registry(tmp_path, [{"name": "mydb", "path": str(kb_path)}])

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = type(
                "R", (), {"returncode": 0, "stdout": "done\n", "stderr": ""}
            )()
            kb_run(tmp_path, "mydb", "sync", ["--force", "arg1"])

        cmd = mock_run.call_args[0][0]
        assert "--force" in cmd
        assert "arg1" in cmd


# ---------------------------------------------------------------------------
# main (CLI)
# ---------------------------------------------------------------------------


class TestMain:
    def test_returns_1_on_insufficient_args(self) -> None:
        rc = main(["only-one"])
        assert rc == 1

    def test_returns_1_when_adj_dir_not_set(self) -> None:
        env = {k: v for k, v in os.environ.items() if k != "ADJ_DIR"}
        with patch.dict(os.environ, env, clear=True):
            rc = main(["mydb", "fetch"])
        assert rc == 1

    def test_returns_0_on_success(self, tmp_path: Path) -> None:
        kb_path = _make_kb(tmp_path, "mydb", ["fetch"])
        _make_registry(tmp_path, [{"name": "mydb", "path": str(kb_path)}])

        with (
            patch.dict(os.environ, {"ADJ_DIR": str(tmp_path)}),
            patch("adjutant.capabilities.kb.run.kb_run", return_value="output\n") as mock_run,
        ):
            rc = main(["mydb", "fetch"])

        assert rc == 0
        mock_run.assert_called_once()

    def test_returns_1_on_kb_not_found(self, tmp_path: Path) -> None:
        _make_registry(tmp_path, [])
        with patch.dict(os.environ, {"ADJ_DIR": str(tmp_path)}):
            rc = main(["ghost", "fetch"])
        assert rc == 1
