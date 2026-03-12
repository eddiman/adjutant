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
    _read_kb_cli_flags,
    _read_kb_cli_module,
    _resolve_kb_python,
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


def _make_kb(
    tmp_path: Path,
    name: str,
    operations: list[str] | None = None,
    cli_module: str = "",
    cli_flags: str = "",
) -> Path:
    """Create a minimal KB directory with optional operation scripts or kb.yaml."""
    kb_path = tmp_path / f"kb_{name}"
    scripts_dir = kb_path / "scripts"
    scripts_dir.mkdir(parents=True)
    for op in operations or []:
        script = scripts_dir / f"{op}.sh"
        script.write_text(f"#!/bin/bash\necho 'ran {op}'\n")
        script.chmod(0o755)
    if cli_module or cli_flags:
        yaml_content = f'name: "{name}"\n'
        if cli_module:
            yaml_content += f'cli_module: "{cli_module}"\n'
        if cli_flags:
            yaml_content += f'cli_flags: "{cli_flags}"\n'
        (kb_path / "kb.yaml").write_text(yaml_content)
    return kb_path


def _make_venv_python(kb_path: Path) -> Path:
    """Create a fake .venv/bin/python file so _resolve_kb_python succeeds."""
    venv_bin = kb_path / ".venv" / "bin"
    venv_bin.mkdir(parents=True)
    python = venv_bin / "python"
    python.write_text('#!/bin/sh\nexec python3 "$@"\n')
    python.chmod(0o755)
    return python


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
# _read_kb_cli_module
# ---------------------------------------------------------------------------


class TestReadKbCliModule:
    def test_returns_empty_when_no_kb_yaml(self, tmp_path: Path) -> None:
        kb_path = tmp_path / "kb"
        kb_path.mkdir()
        assert _read_kb_cli_module(kb_path) == ""

    def test_returns_empty_when_no_cli_module_field(self, tmp_path: Path) -> None:
        kb_path = tmp_path / "kb"
        kb_path.mkdir()
        (kb_path / "kb.yaml").write_text('name: "mydb"\nmodel: "cheap"\n')
        assert _read_kb_cli_module(kb_path) == ""

    def test_returns_cli_module_value(self, tmp_path: Path) -> None:
        kb_path = tmp_path / "kb"
        kb_path.mkdir()
        (kb_path / "kb.yaml").write_text('name: "mydb"\ncli_module: "src.cli"\n')
        assert _read_kb_cli_module(kb_path) == "src.cli"

    def test_returns_cli_module_without_quotes(self, tmp_path: Path) -> None:
        kb_path = tmp_path / "kb"
        kb_path.mkdir()
        (kb_path / "kb.yaml").write_text("name: mydb\ncli_module: src.cli\n")
        assert _read_kb_cli_module(kb_path) == "src.cli"

    def test_returns_empty_when_cli_module_is_blank(self, tmp_path: Path) -> None:
        kb_path = tmp_path / "kb"
        kb_path.mkdir()
        (kb_path / "kb.yaml").write_text('name: "mydb"\ncli_module: ""\n')
        assert _read_kb_cli_module(kb_path) == ""

    def test_ignores_commented_out_cli_module(self, tmp_path: Path) -> None:
        kb_path = tmp_path / "kb"
        kb_path.mkdir()
        (kb_path / "kb.yaml").write_text('name: "mydb"\n# cli_module: "src.cli"\n')
        assert _read_kb_cli_module(kb_path) == ""


# ---------------------------------------------------------------------------
# _read_kb_cli_flags
# ---------------------------------------------------------------------------


class TestReadKbCliFlags:
    def test_defaults_to_real_when_no_kb_yaml(self, tmp_path: Path) -> None:
        kb_path = tmp_path / "kb"
        kb_path.mkdir()
        assert _read_kb_cli_flags(kb_path) == ["--real"]

    def test_defaults_to_real_when_no_cli_flags_field(self, tmp_path: Path) -> None:
        kb_path = tmp_path / "kb"
        kb_path.mkdir()
        (kb_path / "kb.yaml").write_text('name: "mydb"\ncli_module: "src.cli"\n')
        assert _read_kb_cli_flags(kb_path) == ["--real"]

    def test_returns_mock_flag(self, tmp_path: Path) -> None:
        kb_path = tmp_path / "kb"
        kb_path.mkdir()
        (kb_path / "kb.yaml").write_text('name: "mydb"\ncli_flags: "--mock"\n')
        assert _read_kb_cli_flags(kb_path) == ["--mock"]

    def test_returns_real_flag_explicit(self, tmp_path: Path) -> None:
        kb_path = tmp_path / "kb"
        kb_path.mkdir()
        (kb_path / "kb.yaml").write_text('name: "mydb"\ncli_flags: "--real"\n')
        assert _read_kb_cli_flags(kb_path) == ["--real"]

    def test_returns_multiple_flags(self, tmp_path: Path) -> None:
        kb_path = tmp_path / "kb"
        kb_path.mkdir()
        (kb_path / "kb.yaml").write_text('name: "mydb"\ncli_flags: "--mock --verbose"\n')
        assert _read_kb_cli_flags(kb_path) == ["--mock", "--verbose"]

    def test_defaults_to_real_when_field_is_empty(self, tmp_path: Path) -> None:
        kb_path = tmp_path / "kb"
        kb_path.mkdir()
        (kb_path / "kb.yaml").write_text('name: "mydb"\ncli_flags: ""\n')
        assert _read_kb_cli_flags(kb_path) == ["--real"]

    def test_ignores_commented_out_cli_flags(self, tmp_path: Path) -> None:
        kb_path = tmp_path / "kb"
        kb_path.mkdir()
        (kb_path / "kb.yaml").write_text('name: "mydb"\n# cli_flags: "--mock"\n')
        assert _read_kb_cli_flags(kb_path) == ["--real"]


# ---------------------------------------------------------------------------
# _resolve_kb_python
# ---------------------------------------------------------------------------


class TestResolveKbPython:
    def test_returns_venv_python_when_exists(self, tmp_path: Path) -> None:
        kb_path = tmp_path / "kb"
        python = _make_venv_python(kb_path)
        assert _resolve_kb_python(kb_path) == python

    def test_raises_when_venv_missing(self, tmp_path: Path) -> None:
        kb_path = tmp_path / "kb"
        kb_path.mkdir()
        with pytest.raises(KBRunError, match=".venv/bin/python"):
            _resolve_kb_python(kb_path)


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
# kb_run — bash fallback path
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

    def test_invokes_bash_for_sh_script(self, tmp_path: Path) -> None:
        kb_path = _make_kb(tmp_path, "mydb", ["fetch"])
        _make_registry(tmp_path, [{"name": "mydb", "path": str(kb_path)}])

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = type(
                "R", (), {"returncode": 0, "stdout": "ok\n", "stderr": ""}
            )()
            kb_run(tmp_path, "mydb", "fetch")

        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "bash"
        assert cmd[1].endswith("fetch.sh")

    def test_injects_env_vars(self, tmp_path: Path) -> None:
        kb_path = _make_kb(tmp_path, "mydb", ["fetch"])
        _make_registry(tmp_path, [{"name": "mydb", "path": str(kb_path)}])

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = type(
                "R", (), {"returncode": 0, "stdout": "ok\n", "stderr": ""}
            )()
            kb_run(tmp_path, "mydb", "fetch")

        env = mock_run.call_args[1]["env"]
        assert env["ADJ_DIR"] == str(tmp_path)
        assert env["ADJUTANT_HOME"] == str(tmp_path)
        assert env["KB_DIR"] == str(kb_path)


# ---------------------------------------------------------------------------
# kb_run — Python CLI path
# ---------------------------------------------------------------------------


class TestKbRunPython:
    def test_invokes_venv_python_when_cli_module_set(self, tmp_path: Path) -> None:
        kb_path = _make_kb(tmp_path, "mydb", cli_module="src.cli")
        _make_venv_python(kb_path)
        _make_registry(tmp_path, [{"name": "mydb", "path": str(kb_path)}])

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = type(
                "R", (), {"returncode": 0, "stdout": "OK:fetched\n", "stderr": ""}
            )()
            result = kb_run(tmp_path, "mydb", "fetch")

        assert result == "OK:fetched\n"
        cmd = mock_run.call_args[0][0]
        # Must use venv Python, not bash
        assert "python" in cmd[0]
        assert "bash" not in cmd[0]
        assert "-m" in cmd
        assert "src.cli" in cmd

    def test_passes_real_flag_by_default(self, tmp_path: Path) -> None:
        """--real is the default when kb.yaml has no cli_flags field."""
        kb_path = _make_kb(tmp_path, "mydb", cli_module="src.cli")
        _make_venv_python(kb_path)
        _make_registry(tmp_path, [{"name": "mydb", "path": str(kb_path)}])

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = type(
                "R", (), {"returncode": 0, "stdout": "ok\n", "stderr": ""}
            )()
            kb_run(tmp_path, "mydb", "fetch")

        cmd = mock_run.call_args[0][0]
        assert "--real" in cmd
        assert "--kb-dir" in cmd
        assert str(kb_path) in cmd

    def test_passes_mock_flag_when_cli_flags_set(self, tmp_path: Path) -> None:
        """cli_flags: --mock in kb.yaml replaces the default --real."""
        kb_path = _make_kb(tmp_path, "mydb", cli_module="src.cli", cli_flags="--mock")
        _make_venv_python(kb_path)
        _make_registry(tmp_path, [{"name": "mydb", "path": str(kb_path)}])

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = type(
                "R", (), {"returncode": 0, "stdout": "ok\n", "stderr": ""}
            )()
            kb_run(tmp_path, "mydb", "fetch")

        cmd = mock_run.call_args[0][0]
        assert "--mock" in cmd
        assert "--real" not in cmd

    def test_passes_operation_and_extra_args(self, tmp_path: Path) -> None:
        kb_path = _make_kb(tmp_path, "mydb", cli_module="src.cli")
        _make_venv_python(kb_path)
        _make_registry(tmp_path, [{"name": "mydb", "path": str(kb_path)}])

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = type(
                "R", (), {"returncode": 0, "stdout": "ok\n", "stderr": ""}
            )()
            kb_run(tmp_path, "mydb", "analyze", ["--days", "7"])

        cmd = mock_run.call_args[0][0]
        assert "analyze" in cmd
        assert "--days" in cmd
        assert "7" in cmd

    def test_sets_cwd_to_kb_path(self, tmp_path: Path) -> None:
        kb_path = _make_kb(tmp_path, "mydb", cli_module="src.cli")
        _make_venv_python(kb_path)
        _make_registry(tmp_path, [{"name": "mydb", "path": str(kb_path)}])

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = type(
                "R", (), {"returncode": 0, "stdout": "ok\n", "stderr": ""}
            )()
            kb_run(tmp_path, "mydb", "fetch")

        kwargs = mock_run.call_args[1]
        assert kwargs["cwd"] == str(kb_path)

    def test_raises_kb_run_error_when_venv_missing(self, tmp_path: Path) -> None:
        kb_path = _make_kb(tmp_path, "mydb", cli_module="src.cli")
        # No venv created
        _make_registry(tmp_path, [{"name": "mydb", "path": str(kb_path)}])

        with pytest.raises(KBRunError, match=".venv/bin/python"):
            kb_run(tmp_path, "mydb", "fetch")

    def test_raises_kb_run_error_on_nonzero_exit(self, tmp_path: Path) -> None:
        kb_path = _make_kb(tmp_path, "mydb", cli_module="src.cli")
        _make_venv_python(kb_path)
        _make_registry(tmp_path, [{"name": "mydb", "path": str(kb_path)}])

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = type(
                "R", (), {"returncode": 1, "stdout": "", "stderr": "ERROR:fetch: auth failed"}
            )()
            with pytest.raises(KBRunError, match="auth failed"):
                kb_run(tmp_path, "mydb", "fetch")

    def test_injects_env_vars(self, tmp_path: Path) -> None:
        kb_path = _make_kb(tmp_path, "mydb", cli_module="src.cli")
        _make_venv_python(kb_path)
        _make_registry(tmp_path, [{"name": "mydb", "path": str(kb_path)}])

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = type(
                "R", (), {"returncode": 0, "stdout": "ok\n", "stderr": ""}
            )()
            kb_run(tmp_path, "mydb", "fetch")

        env = mock_run.call_args[1]["env"]
        assert env["ADJ_DIR"] == str(tmp_path)
        assert env["ADJUTANT_HOME"] == str(tmp_path)
        assert env["KB_DIR"] == str(kb_path)

    def test_raises_invalid_operation_name(self, tmp_path: Path) -> None:
        kb_path = _make_kb(tmp_path, "mydb", cli_module="src.cli")
        _make_venv_python(kb_path)
        _make_registry(tmp_path, [{"name": "mydb", "path": str(kb_path)}])

        with pytest.raises(ValueError, match="Invalid"):
            kb_run(tmp_path, "mydb", "../etc/passwd")


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
