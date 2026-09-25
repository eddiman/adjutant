"""Tests for src/adjutant/capabilities/kb/query.py"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from adjutant.capabilities.kb.query import (
    KBQueryError,
    _read_kb_model_from_yaml,
    kb_cross_query,
    kb_operation_result,
    kb_operation_status,
    kb_query,
    kb_query_all,
    kb_query_by_path,
    kb_submit_query,
    kb_submit_query_by_path,
    kb_submit_write,
    kb_write,
    kb_write_by_path,
    main,
)
from adjutant.core.backend import (
    BackendNotFoundError,
    ExecutionEvent,
    ExecutionEventType,
    LLMResult,
)
from adjutant.operations.models import OperationState, SideEffectClass
from adjutant.operations.store import OperationStore

if TYPE_CHECKING:
    from pathlib import Path


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


def _mock_backend(
    text="The answer.", session_id=None, error_type=None, returncode=0, timed_out=False
):
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
        assert call_kwargs["variant"] is None


# ---------------------------------------------------------------------------
# kb_query (by name)
# ---------------------------------------------------------------------------


class TestKbQuery:
    def _make_registry(self, adj_dir: Path, name: str, path: str) -> None:
        kb_dir = adj_dir / "knowledge_bases"
        kb_dir.mkdir(parents=True, exist_ok=True)
        (kb_dir / "registry.yaml").write_text(
            f'knowledge_bases:\n  - name: "{name}"\n    path: "{path}"\n    access: "read-write"\n'
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

        with (
            patch(
                "adjutant.capabilities.kb.query.get_backend",
                side_effect=BackendNotFoundError("not found"),
            ),
            pytest.raises(BackendNotFoundError),
        ):
            kb_write_by_path(kb_path, "update issue #1", adj_dir)

    def test_returns_dispatch_acknowledgement(self, tmp_path: Path) -> None:
        adj_dir = _make_adj_dir(tmp_path)
        kb_path = _make_kb(tmp_path, "mydb")

        backend = _mock_backend()

        with patch("adjutant.capabilities.kb.query.get_backend", return_value=backend):
            msg = kb_write_by_path(kb_path, "Update issue #12: mark complete", adj_dir)

        assert "Write dispatched" in msg
        assert "completion not verified" in msg
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
        assert "variant" in call_kwargs

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
            f'knowledge_bases:\n  - name: "{name}"\n    path: "{path}"\n    access: "read-write"\n'
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


class TestTrackedKbOperations:
    def _enable_operations(self, adj_dir: Path) -> None:
        (adj_dir / "adjutant.yaml").write_text(
            "operations:\n  enabled: true\n"
            "llm:\n  backend: opencode\n  models:\n"
            "    cheap: anthropic/claude-haiku-4-5\n"
            "    medium: anthropic/claude-sonnet-4-6\n"
            "    expensive: anthropic/claude-opus-4-6\n"
        )

    def _registry(self, adj_dir: Path, kb_path: Path) -> None:
        registry = adj_dir / "knowledge_bases" / "registry.yaml"
        registry.parent.mkdir(parents=True, exist_ok=True)
        registry.write_text(
            "knowledge_bases:\n"
            '  - name: "notes"\n'
            f'    path: "{kb_path}"\n'
            '    model: "inherit"\n'
            '    access: "read-write"\n'
        )

    def test_query_and_write_freeze_kb_boundary_and_parent(self, tmp_path: Path) -> None:
        adj_dir = _make_adj_dir(tmp_path)
        self._enable_operations(adj_dir)
        kb_path = _make_kb(tmp_path, "notes")
        self._registry(adj_dir, kb_path)
        store = OperationStore(adj_dir)
        parent = store.create_operation(
            kind="telegram_chat",
            source="test",
            payload={},
        )
        parent = store.claim_operation(parent.id, "parent-worker", lease_seconds=60)
        assert parent is not None
        store.start_attempt(parent, "parent-worker", runtime_seconds=1800)
        parent = store.transition(
            parent.id,
            OperationState.RUNNING,
            worker_id="parent-worker",
            lease_seconds=60,
        )

        query = kb_submit_query("notes", "What changed?", adj_dir, parent_id=parent.id)
        write = kb_submit_write("notes", "Update item 1", adj_dir, parent_id=parent.id)

        assert query.parent_id == parent.id
        assert query.execution_mode == "inline"
        assert query.parent_attempt_id == parent.current_attempt_id
        assert query.current_attempt_id is not None
        assert query.deadline_at is not None
        assert query.deadline_at < parent.deadline_at
        assert query.kind == "kb_query"
        assert query.side_effect_class is SideEffectClass.READ_ONLY
        assert query.workdir == str(kb_path)
        assert query.agent == "kb"
        assert write.parent_id == parent.id
        assert write.kind == "kb_write"
        assert write.side_effect_class is SideEffectClass.MUTATING
        assert "authoritative target" in write.payload["prompt"]
        assert "verification" not in query.payload["prompt"].lower()

    def test_enabled_write_uses_durable_submission_not_detached_backend(
        self, tmp_path: Path
    ) -> None:
        adj_dir = _make_adj_dir(tmp_path)
        self._enable_operations(adj_dir)
        kb_path = _make_kb(tmp_path, "notes")
        self._registry(adj_dir, kb_path)

        with patch(
            "adjutant.operations.process.worker_start",
            return_value="Operation worker already running",
        ):
            message = kb_write("notes", "Update item 1", adj_dir)

        assert "Write accepted as `op-" in message
        operations = OperationStore(adj_dir).list_operations()
        assert len(operations) == 1
        assert operations[0].kind == "kb_write"

    def test_enabled_standalone_query_stays_on_daemon_queue(self, tmp_path: Path) -> None:
        import asyncio

        adj_dir = _make_adj_dir(tmp_path)
        self._enable_operations(adj_dir)
        kb_path = _make_kb(tmp_path, "notes")

        with patch(
            "adjutant.operations.process.worker_start",
            return_value="Operation worker already running",
        ):
            message = asyncio.run(kb_query_by_path(kb_path, "Question", adj_dir))

        assert "Query accepted as `op-" in message
        operation = OperationStore(adj_dir).list_operations()[0]
        assert operation.state is OperationState.QUEUED
        assert operation.execution_mode == "daemon"
        assert operation.current_attempt_id is None

    def test_status_and_result_read_persisted_kb_operation(self, tmp_path: Path) -> None:
        adj_dir = _make_adj_dir(tmp_path)
        self._enable_operations(adj_dir)
        kb_path = _make_kb(tmp_path, "notes")
        self._registry(adj_dir, kb_path)
        operation = kb_submit_query("notes", "Question", adj_dir)
        store = OperationStore(adj_dir)

        assert "queued" in kb_operation_status(operation.id, adj_dir)
        with pytest.raises(KBQueryError, match="still queued"):
            kb_operation_result(operation.id, adj_dir)

        store.claim_operation(operation.id, "worker")
        store.transition(operation.id, OperationState.RUNNING, worker_id="worker")
        store.complete_with_deliveries(
            operation.id,
            OperationState.SUCCEEDED,
            result_text="Verified answer",
        )

        assert kb_operation_result(operation.id, adj_dir) == "Verified answer"

    def test_parent_executes_child_inline_without_worker_pool_wait(self, tmp_path: Path) -> None:
        import asyncio

        adj_dir = _make_adj_dir(tmp_path)
        self._enable_operations(adj_dir)
        kb_path = _make_kb(tmp_path, "notes")
        store = OperationStore(adj_dir)
        parent = store.create_operation(
            kind="telegram_chat",
            source="test",
            payload={},
        )
        parent = store.claim_operation(parent.id, "parent-worker", lease_seconds=60)
        assert parent is not None
        store.start_attempt(parent, "parent-worker", runtime_seconds=1800)
        parent = store.transition(
            parent.id,
            OperationState.RUNNING,
            worker_id="parent-worker",
            lease_seconds=60,
        )

        class FakeBackend:
            async def execute(self, request):
                yield ExecutionEvent(type=ExecutionEventType.STARTED)
                yield ExecutionEvent(
                    type=ExecutionEventType.COMPLETED,
                    result=LLMResult(text="Child answer", correlation_id=request.correlation_id),
                )

        with (
            patch.dict(os.environ, {"ADJUTANT_PARENT_OPERATION_ID": parent.id}),
            patch("adjutant.operations.worker.get_backend", return_value=FakeBackend()),
        ):
            result = asyncio.run(kb_query_by_path(kb_path, "Question", adj_dir))

        assert result == "Child answer"
        children = [
            operation
            for operation in OperationStore(adj_dir).list_operations()
            if operation.parent_id == parent.id
        ]
        assert len(children) == 1
        assert children[0].state is OperationState.SUCCEEDED
        parent_status = kb_operation_status(parent.id, adj_dir)
        assert "attached KB children" in parent_status
        assert children[0].id in parent_status

    def test_attached_claude_child_is_gated_until_owned_process_fixture_passes(
        self, tmp_path: Path
    ) -> None:
        adj_dir = _make_adj_dir(tmp_path)
        self._enable_operations(adj_dir)
        (adj_dir / "adjutant.yaml").write_text(
            "operations:\n  enabled: true\n"
            "llm:\n  backend: claude-cli\n  models:\n"
            "    cheap: haiku\n    medium: sonnet\n    expensive: opus\n"
        )
        kb_path = _make_kb(tmp_path, "notes")
        store = OperationStore(adj_dir)
        parent = store.create_operation(kind="telegram_chat", source="test", payload={})
        claimed = store.claim_next("parent", lease_seconds=60)
        assert claimed is not None
        attempt = store.start_attempt(claimed, "parent", runtime_seconds=1800)
        parent = store.transition(
            parent.id,
            OperationState.RUNNING,
            worker_id="parent",
            lease_seconds=60,
            expected_attempt_id=attempt.id,
        )

        with pytest.raises(KBQueryError, match="Claude CLI support remains disabled"):
            kb_submit_query_by_path(
                kb_path,
                "Question",
                adj_dir,
                parent_id=parent.id,
            )


# ---------------------------------------------------------------------------
# kb_query_all
# ---------------------------------------------------------------------------


def _make_registry_multi(adj_dir: Path, kbs: list[tuple[str, str, str]]) -> None:
    """Write a registry with multiple KBs. Each tuple: (name, path, query_hint)."""
    kb_dir = adj_dir / "knowledge_bases"
    kb_dir.mkdir(parents=True, exist_ok=True)
    lines = ["knowledge_bases:"]
    for name, path, hint in kbs:
        lines.append(f'  - name: "{name}"')
        lines.append(f'    path: "{path}"')
        lines.append('    description: "test kb"')
        lines.append('    model: "inherit"')
        lines.append('    access: "read-only"')
        if hint:
            lines.append(f'    query_hint: "{hint}"')
    (kb_dir / "registry.yaml").write_text("\n".join(lines) + "\n")


class TestKbQueryAll:
    def test_queries_all_kbs_in_parallel(self, tmp_path: Path) -> None:
        adj_dir = _make_adj_dir(tmp_path)
        kb1 = _make_kb(tmp_path, "alpha")
        kb2 = _make_kb(tmp_path, "beta")
        _make_registry_multi(
            adj_dir,
            [
                ("alpha", str(kb1), ""),
                ("beta", str(kb2), "Ask about deadlines"),
            ],
        )

        backend = _mock_backend(text="Status OK.")
        with patch("adjutant.capabilities.kb.query.get_backend", return_value=backend):
            import asyncio

            result = asyncio.run(kb_query_all(adj_dir))

        assert "### alpha" in result
        assert "### beta" in result
        assert "Status OK." in result
        # Should have been called twice (once per KB)
        assert backend.run.call_count == 2

    def test_returns_message_when_no_kbs(self, tmp_path: Path) -> None:
        adj_dir = _make_adj_dir(tmp_path)
        kb_dir = adj_dir / "knowledge_bases"
        kb_dir.mkdir(parents=True, exist_ok=True)
        (kb_dir / "registry.yaml").write_text("knowledge_bases: []\n")

        import asyncio

        result = asyncio.run(kb_query_all(adj_dir))
        assert "No knowledge bases" in result

    def test_handles_partial_failure(self, tmp_path: Path) -> None:
        adj_dir = _make_adj_dir(tmp_path)
        kb1 = _make_kb(tmp_path, "good")
        kb2 = tmp_path / "bad"  # Don't create — will cause error
        _make_registry_multi(
            adj_dir,
            [
                ("good", str(kb1), ""),
                ("bad", str(kb2), ""),
            ],
        )

        backend = _mock_backend(text="Working fine.")
        with patch("adjutant.capabilities.kb.query.get_backend", return_value=backend):
            import asyncio

            result = asyncio.run(kb_query_all(adj_dir))

        assert "### good" in result
        assert "### bad" in result
        assert "[error:" in result

    def test_uses_custom_query(self, tmp_path: Path) -> None:
        adj_dir = _make_adj_dir(tmp_path)
        kb1 = _make_kb(tmp_path, "alpha")
        _make_registry_multi(adj_dir, [("alpha", str(kb1), "ignored hint")])

        backend = _mock_backend(text="Custom answer.")
        with patch("adjutant.capabilities.kb.query.get_backend", return_value=backend):
            import asyncio

            asyncio.run(kb_query_all(adj_dir, query="My custom question"))

        # Should have used custom query, not the hint
        call_args = backend.run.call_args
        assert "My custom question" in call_args[0][0]


# ---------------------------------------------------------------------------
# kb_cross_query
# ---------------------------------------------------------------------------


class TestKbCrossQuery:
    def _make_registry(self, adj_dir: Path, name: str, path: str) -> None:
        kb_dir = adj_dir / "knowledge_bases"
        kb_dir.mkdir(parents=True, exist_ok=True)
        (kb_dir / "registry.yaml").write_text(
            f'knowledge_bases:\n  - name: "{name}"\n    path: "{path}"\n'
        )

    def test_raises_on_empty_names(self, tmp_path: Path) -> None:
        adj_dir = _make_adj_dir(tmp_path)
        with pytest.raises(KBQueryError, match="No KB names"):
            import asyncio

            asyncio.run(kb_cross_query([], "question?", adj_dir))

    def test_raises_on_empty_question(self, tmp_path: Path) -> None:
        adj_dir = _make_adj_dir(tmp_path)
        with pytest.raises(KBQueryError, match="empty"):
            import asyncio

            asyncio.run(kb_cross_query(["kb1"], "  ", adj_dir))

    def test_queries_and_synthesizes(self, tmp_path: Path) -> None:
        adj_dir = _make_adj_dir(tmp_path)
        kb1 = _make_kb(tmp_path, "alpha")
        kb2 = _make_kb(tmp_path, "beta")
        _make_registry_multi(
            adj_dir,
            [
                ("alpha", str(kb1), ""),
                ("beta", str(kb2), ""),
            ],
        )

        # First 2 calls return KB results, 3rd call returns synthesis
        call_count = 0
        results = [
            LLMResult(text="Alpha says: yes"),
            LLMResult(text="Beta says: no"),
            LLMResult(text="Synthesized: alpha says yes, beta says no"),
        ]

        async def mock_run(prompt, **kwargs):
            nonlocal call_count
            r = results[min(call_count, len(results) - 1)]
            call_count += 1
            return r

        backend = MagicMock()
        backend.run = AsyncMock(side_effect=mock_run)
        backend.find_binary = MagicMock(return_value="/usr/bin/opencode")

        with patch("adjutant.capabilities.kb.query.get_backend", return_value=backend):
            import asyncio

            result = asyncio.run(kb_cross_query(["alpha", "beta"], "conflict?", adj_dir))

        assert "Synthesized" in result
        # 2 KB queries + 1 synthesis = 3 calls
        assert backend.run.call_count == 3
