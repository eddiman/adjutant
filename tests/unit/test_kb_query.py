"""Tests for src/adjutant/capabilities/kb/query.py"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from adjutant.capabilities.kb.query import (
    KB_QUERY_TIMEOUT,
    KBQueryError,
    _read_kb_model_from_yaml,
    kb_query,
    kb_query_by_path,
    kb_write,
    kb_write_by_path,
    main,
)
from adjutant.core.backend import BackendNotFoundError, LLMResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_adj_dir(tmp_path: Path) -> Path:
    """Write a minimal adjutant.yaml and state/ dir."""
    cfg = tmp_path / "adjutant.yaml"
    cfg.write_text(
        "instance:\n  name: test\n"
        "llm:\n  models:\n    cheap: anthropic/claude-haiku-4-5\n"
        "    medium: anthropic/claude-sonnet-4-6\n"
        "    expensive: anthropic/claude-opus-4-6\n"
    )
    (tmp_path / "state").mkdir(exist_ok=True)
    return tmp_path


def _make_kb(tmp_path: Path, name: str, model: str = "inherit") -> Path:
    kb_path = tmp_path / name
    kb_path.mkdir()
    kb_yaml = kb_path / "kb.yaml"
    kb_yaml.write_text(f'name: "{name}"\nmodel: "{model}"\n')
    return kb_path


def _mock_backend(text="The answer.", session_id=None, error_type=None, returncode=0, timed_out=False):
    """Return a MagicMock backend whose ``run`` returns an ``LLMResult``."""
    result = LLMResult(
        text=text,
        session_id=session_id,
        error_type=error_type,
        returncode=returncode,
        timed_out=timed_out,
    )
    backend = MagicMock()
    backend.run = AsyncMock(return_value=result)
    backend.run_detached = MagicMock()
    backend.find_binary = MagicMock(return_value="/usr/bin/opencode")
    return backend


# ---------------------------------------------------------------------------
# _read_kb_model_from_yaml
# ---------------------------------------------------------------------------


class TestReadKbModelFromYaml:
    def test_reads_model_field(self, tmp_path: Path) -> None:
        kb_path = _make_kb(tmp_path, "notes", model="anthropic/claude-haiku-4-5")
        assert _read_kb_model_from_yaml(kb_path) == "anthropic/claude-haiku-4-5"

    def test_returns_inherit_when_no_yaml(self, tmp_path: Path) -> None:
        kb_path = tmp_path / "no-yaml-kb"
        kb_path.mkdir()
        assert _read_kb_model_from_yaml(kb_path) == "inherit"

    def test_returns_inherit_when_no_model_field(self, tmp_path: Path) -> None:
        kb_path = tmp_path / "no-model"
        kb_path.mkdir()
        (kb_path / "kb.yaml").write_text('name: "test"\n')
        assert _read_kb_model_from_yaml(kb_path) == "inherit"

    def test_strips_quotes(self, tmp_path: Path) -> None:
        kb_path = tmp_path / "quoted"
        kb_path.mkdir()
        (kb_path / "kb.yaml").write_text('model: "anthropic/claude-haiku-4-5"\n')
        assert _read_kb_model_from_yaml(kb_path) == "anthropic/claude-haiku-4-5"


# ---------------------------------------------------------------------------
# kb_query_by_path
# ---------------------------------------------------------------------------


class TestKbQueryByPath:
    def test_raises_when_kb_dir_missing(self, tmp_path: Path) -> None:
        adj_dir = _make_adj_dir(tmp_path)
        missing = tmp_path / "nonexistent"

        with pytest.raises(KBQueryError, match="does not exist"):
            import asyncio

            asyncio.run(kb_query_by_path(missing, "any question", adj_dir))

    def test_raises_when_query_empty(self, tmp_path: Path) -> None:
        adj_dir = _make_adj_dir(tmp_path)
        kb_path = _make_kb(tmp_path, "mydb")

        with pytest.raises(KBQueryError, match="empty"):
            import asyncio

            asyncio.run(kb_query_by_path(kb_path, "   ", adj_dir))

    def test_returns_parsed_reply(self, tmp_path: Path) -> None:
        adj_dir = _make_adj_dir(tmp_path)
        kb_path = _make_kb(tmp_path, "mydb")

        backend = _mock_backend(text="Portfolio value is $42k.")

        with patch(
            "adjutant.capabilities.kb.query.get_backend",
            return_value=backend,
        ):
            import asyncio

            reply = asyncio.run(kb_query_by_path(kb_path, "What is the value?", adj_dir))

        assert reply == "Portfolio value is $42k."

    def test_returns_fallback_on_empty_reply(self, tmp_path: Path) -> None:
        adj_dir = _make_adj_dir(tmp_path)
        kb_path = _make_kb(tmp_path, "mydb")

        backend = _mock_backend(text="")

        with patch(
            "adjutant.capabilities.kb.query.get_backend",
            return_value=backend,
        ):
            import asyncio

            reply = asyncio.run(kb_query_by_path(kb_path, "something", adj_dir))

        assert "did not return" in reply

    def test_uses_custom_timeout(self, tmp_path: Path) -> None:
        adj_dir = _make_adj_dir(tmp_path)
        kb_path = _make_kb(tmp_path, "mydb")
        backend = _mock_backend(text="ok")

        with patch("adjutant.capabilities.kb.query.get_backend", return_value=backend):
            import asyncio

            asyncio.run(kb_query_by_path(kb_path, "question?", adj_dir, timeout=30.0))

        call_kwargs = backend.run.call_args[1]
        assert call_kwargs["timeout"] == 30.0


# ---------------------------------------------------------------------------
# kb_query (by name)
# ---------------------------------------------------------------------------


class TestKbQuery:
    def _make_registry(self, adj_dir: Path, name: str, path: str) -> None:
        kb_dir = adj_dir / "knowledge_bases"
        kb_dir.mkdir(parents=True, exist_ok=True)
        (kb_dir / "registry.yaml").write_text(
            f'knowledge_bases:\n  - name: "{name}"\n    path: "{path}"\n'
        )

    def test_raises_kb_query_error_when_not_found(self, tmp_path: Path) -> None:
        adj_dir = _make_adj_dir(tmp_path)
        kb_dir = adj_dir / "knowledge_bases"
        kb_dir.mkdir(parents=True, exist_ok=True)
        (kb_dir / "registry.yaml").write_text("knowledge_bases:\n")

        with pytest.raises(KBQueryError):
            import asyncio

            asyncio.run(kb_query("ghost-kb", "question?", adj_dir))

    def test_delegates_to_query_by_path(self, tmp_path: Path) -> None:
        adj_dir = _make_adj_dir(tmp_path)
        kb_path = _make_kb(tmp_path, "notes")
        self._make_registry(adj_dir, "notes", str(kb_path))
        backend = _mock_backend(text="Here are my notes.")

        with patch(
            "adjutant.capabilities.kb.query.get_backend",
            return_value=backend,
        ):
            import asyncio

            reply = asyncio.run(kb_query("notes", "What notes?", adj_dir))

        assert reply == "Here are my notes."


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
            rc = main(["my-kb", "some question"])
        assert rc == 1

    def test_returns_0_on_success(self, tmp_path: Path) -> None:
        adj_dir = _make_adj_dir(tmp_path)
        kb_path = _make_kb(tmp_path, "notes")
        kb_dir = adj_dir / "knowledge_bases"
        kb_dir.mkdir(parents=True, exist_ok=True)
        (kb_dir / "registry.yaml").write_text(
            f'knowledge_bases:\n  - name: "notes"\n    path: "{kb_path}"\n'
        )
        backend = _mock_backend(text="The answer.")

        with (
            patch.dict(os.environ, {"ADJ_DIR": str(adj_dir)}),
            patch(
                "adjutant.capabilities.kb.query.get_backend",
                return_value=backend,
            ),
        ):
            rc = main(["notes", "What is this?"])

        assert rc == 0

    def test_path_flag_queries_by_path(self, tmp_path: Path) -> None:
        adj_dir = _make_adj_dir(tmp_path)
        kb_path = _make_kb(tmp_path, "notes")
        backend = _mock_backend(text="Direct path answer.")

        with (
            patch.dict(os.environ, {"ADJ_DIR": str(adj_dir)}),
            patch(
                "adjutant.capabilities.kb.query.get_backend",
                return_value=backend,
            ),
        ):
            rc = main(["--path", str(kb_path), "What?"])

        assert rc == 0

    def test_path_flag_requires_path_and_query(self, tmp_path: Path) -> None:
        adj_dir = _make_adj_dir(tmp_path)
        with patch.dict(os.environ, {"ADJ_DIR": str(adj_dir)}):
            rc = main(["--path"])
        assert rc == 1


# ---------------------------------------------------------------------------
# kb_write_by_path
# ---------------------------------------------------------------------------


class TestKbWriteByPath:
    def test_raises_when_kb_dir_missing(self, tmp_path: Path) -> None:
        adj_dir = _make_adj_dir(tmp_path)
        missing = tmp_path / "nonexistent"

        with pytest.raises(KBQueryError, match="does not exist"):
            kb_write_by_path(missing, "update something", adj_dir)

    def test_raises_when_instruction_empty(self, tmp_path: Path) -> None:
        adj_dir = _make_adj_dir(tmp_path)
        kb_path = _make_kb(tmp_path, "mydb")

        with pytest.raises(KBQueryError, match="empty"):
            kb_write_by_path(kb_path, "   ", adj_dir)

    def test_raises_when_backend_not_found(self, tmp_path: Path) -> None:
        adj_dir = _make_adj_dir(tmp_path)
        kb_path = _make_kb(tmp_path, "mydb")

        with patch("adjutant.capabilities.kb.query.get_backend", side_effect=BackendNotFoundError("not found")):
            with pytest.raises(BackendNotFoundError):
                kb_write_by_path(kb_path, "update issue #1", adj_dir)

    def test_returns_confirmation_message(self, tmp_path: Path) -> None:
        adj_dir = _make_adj_dir(tmp_path)
        kb_path = _make_kb(tmp_path, "mydb")

        backend = _mock_backend()

        with patch("adjutant.capabilities.kb.query.get_backend", return_value=backend):
            msg = kb_write_by_path(kb_path, "Update issue #12: mark complete", adj_dir)

        assert "Write dispatched" in msg
        assert "mydb" in msg
        assert "Update issue #12" in msg

    def test_calls_run_detached(self, tmp_path: Path) -> None:
        adj_dir = _make_adj_dir(tmp_path)
        kb_path = _make_kb(tmp_path, "mydb")

        backend = _mock_backend()

        with patch("adjutant.capabilities.kb.query.get_backend", return_value=backend):
            kb_write_by_path(kb_path, "Update issue #12", adj_dir)

        # Verify run_detached was called
        backend.run_detached.assert_called_once()
        call_kwargs = backend.run_detached.call_args[1]
        assert call_kwargs["agent"] == "kb"
        assert call_kwargs["workdir"] == kb_path

    def test_truncates_long_instruction_in_preview(self, tmp_path: Path) -> None:
        adj_dir = _make_adj_dir(tmp_path)
        kb_path = _make_kb(tmp_path, "mydb")

        long_instruction = "x" * 200

        backend = _mock_backend()

        with patch("adjutant.capabilities.kb.query.get_backend", return_value=backend):
            msg = kb_write_by_path(kb_path, long_instruction, adj_dir)

        assert msg.endswith("...")
        # Preview should be 120 chars + "..."
        assert "x" * 120 in msg


# ---------------------------------------------------------------------------
# kb_write (by name)
# ---------------------------------------------------------------------------


class TestKbWrite:
    def _make_registry(self, adj_dir: Path, name: str, path: str) -> None:
        kb_dir = adj_dir / "knowledge_bases"
        kb_dir.mkdir(parents=True, exist_ok=True)
        (kb_dir / "registry.yaml").write_text(
            f'knowledge_bases:\n  - name: "{name}"\n    path: "{path}"\n'
        )

    def test_raises_kb_query_error_when_not_found(self, tmp_path: Path) -> None:
        adj_dir = _make_adj_dir(tmp_path)
        kb_dir = adj_dir / "knowledge_bases"
        kb_dir.mkdir(parents=True, exist_ok=True)
        (kb_dir / "registry.yaml").write_text("knowledge_bases:\n")

        with pytest.raises(KBQueryError):
            kb_write("ghost-kb", "update something", adj_dir)

    def test_delegates_to_write_by_path(self, tmp_path: Path) -> None:
        adj_dir = _make_adj_dir(tmp_path)
        kb_path = _make_kb(tmp_path, "notes")
        self._make_registry(adj_dir, "notes", str(kb_path))

        backend = _mock_backend()

        with patch("adjutant.capabilities.kb.query.get_backend", return_value=backend):
            msg = kb_write("notes", "Add a new entry", adj_dir)

        assert "Write dispatched" in msg
        assert "notes" in msg

    def test_raises_when_no_path_in_registry(self, tmp_path: Path) -> None:
        adj_dir = _make_adj_dir(tmp_path)
        kb_dir = adj_dir / "knowledge_bases"
        kb_dir.mkdir(parents=True, exist_ok=True)
        (kb_dir / "registry.yaml").write_text(
            'knowledge_bases:\n  - name: "broken"\n    description: "no path"\n'
        )

        with pytest.raises(KBQueryError, match="no path"):
            kb_write("broken", "update something", adj_dir)
