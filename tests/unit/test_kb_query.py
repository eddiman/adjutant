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
    main,
)


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
        "    expensive: anthropic/claude-opus-4-5\n"
    )
    (tmp_path / "state").mkdir(exist_ok=True)
    return tmp_path


def _make_kb(tmp_path: Path, name: str, model: str = "inherit") -> Path:
    kb_path = tmp_path / name
    kb_path.mkdir()
    kb_yaml = kb_path / "kb.yaml"
    kb_yaml.write_text(f'name: "{name}"\nmodel: "{model}"\n')
    return kb_path


def _fake_opencode_result(text: str = "The answer.", returncode: int = 0, timed_out: bool = False):
    """Return a fake OpenCodeResult-like object with correct NDJSON format.

    parse_ndjson accumulates text from events with type="text" and part.text.
    """
    import json

    ndjson = json.dumps({"type": "text", "part": {"text": text}}) + "\n"
    return type(
        "R",
        (),
        {"returncode": returncode, "stdout": ndjson, "stderr": "", "timed_out": timed_out},
    )()


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

        fake_result = _fake_opencode_result("Portfolio value is $42k.")

        with patch(
            "adjutant.capabilities.kb.query.opencode_run",
            new=AsyncMock(return_value=fake_result),
        ):
            import asyncio

            reply = asyncio.run(kb_query_by_path(kb_path, "What is the value?", adj_dir))

        assert reply == "Portfolio value is $42k."

    def test_returns_fallback_on_empty_reply(self, tmp_path: Path) -> None:
        adj_dir = _make_adj_dir(tmp_path)
        kb_path = _make_kb(tmp_path, "mydb")

        # Empty stdout → parse_ndjson returns empty text
        fake_result = type(
            "R", (), {"returncode": 0, "stdout": "", "stderr": "", "timed_out": False}
        )()

        with patch(
            "adjutant.capabilities.kb.query.opencode_run",
            new=AsyncMock(return_value=fake_result),
        ):
            import asyncio

            reply = asyncio.run(kb_query_by_path(kb_path, "something", adj_dir))

        assert "did not return" in reply

    def test_uses_custom_timeout(self, tmp_path: Path) -> None:
        adj_dir = _make_adj_dir(tmp_path)
        kb_path = _make_kb(tmp_path, "mydb")
        fake_result = _fake_opencode_result("ok")

        mock_run = AsyncMock(return_value=fake_result)
        with patch("adjutant.capabilities.kb.query.opencode_run", new=mock_run):
            import asyncio

            asyncio.run(kb_query_by_path(kb_path, "question?", adj_dir, timeout=30.0))

        call_kwargs = mock_run.call_args[1]
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
        fake_result = _fake_opencode_result("Here are my notes.")

        with patch(
            "adjutant.capabilities.kb.query.opencode_run",
            new=AsyncMock(return_value=fake_result),
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
        fake_result = _fake_opencode_result("The answer.")

        with (
            patch.dict(os.environ, {"ADJ_DIR": str(adj_dir)}),
            patch(
                "adjutant.capabilities.kb.query.opencode_run",
                new=AsyncMock(return_value=fake_result),
            ),
        ):
            rc = main(["notes", "What is this?"])

        assert rc == 0

    def test_path_flag_queries_by_path(self, tmp_path: Path) -> None:
        adj_dir = _make_adj_dir(tmp_path)
        kb_path = _make_kb(tmp_path, "notes")
        fake_result = _fake_opencode_result("Direct path answer.")

        with (
            patch.dict(os.environ, {"ADJ_DIR": str(adj_dir)}),
            patch(
                "adjutant.capabilities.kb.query.opencode_run",
                new=AsyncMock(return_value=fake_result),
            ),
        ):
            rc = main(["--path", str(kb_path), "What?"])

        assert rc == 0

    def test_path_flag_requires_path_and_query(self, tmp_path: Path) -> None:
        adj_dir = _make_adj_dir(tmp_path)
        with patch.dict(os.environ, {"ADJ_DIR": str(adj_dir)}):
            rc = main(["--path"])
        assert rc == 1
