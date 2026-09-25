"""Tests for the OpenCode backend wrapper."""

from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from adjutant.core.backend import ExecutionEventType, ExecutionRequest, LLMResult
from adjutant.core.backend_opencode import OpenCodeBackend, _managed_server, _normalize_record
from adjutant.core.opencode import OpenCodeResult
from adjutant.core.opencode_server import OpenCodeServerDrainingError, OpenCodeServerEndpoint


@pytest.mark.backend_opencode
class TestOpenCodeBackend:
    def test_raw_error_event_is_not_published_as_terminal_status(self) -> None:
        events = _normalize_record({"type": "error", "error": {"name": "ServerError"}})

        assert len(events) == 1
        assert events[0].type is ExecutionEventType.FAILED
        assert events[0].public_message is None

    def test_persistent_transport_is_gated_off_for_kb_operations(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        (tmp_path / "adjutant.yaml").write_text(
            "operations:\n"
            "  enabled: true\n"
            "  persistent_opencode:\n"
            "    enabled: true\n"
        )
        kb_dir = tmp_path / "fixture-kb"
        kb_dir.mkdir()
        monkeypatch.setenv("ADJ_DIR", str(tmp_path))

        manager = _managed_server(
            ExecutionRequest(
                prompt="query",
                workdir=kb_dir,
                env={"ADJUTANT_OPERATION_KIND": "kb_query"},
            )
        )

        assert manager is None

    @pytest.mark.asyncio
    async def test_kb_fixture_workdirs_do_not_attach_or_share_sessions(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        (tmp_path / "adjutant.yaml").write_text(
            "operations:\n"
            "  enabled: true\n"
            "  persistent_opencode:\n"
            "    enabled: true\n"
        )
        alpha = tmp_path / "alpha-kb"
        beta = tmp_path / "beta-kb"
        alpha.mkdir()
        beta.mkdir()
        monkeypatch.setenv("ADJ_DIR", str(tmp_path))
        calls: list[list[str]] = []

        async def fake_run(
            args,
            timeout=None,
            startup_timeout=None,
            env=None,
            on_stdout_line=None,
            on_spawn=None,
        ):
            calls.append(args)
            workdir = args[args.index("--dir") + 1]
            session = "alpha-session" if workdir == str(alpha) else "beta-session"
            assert on_stdout_line is not None
            await on_stdout_line(f'{{"type":"session.create","sessionID":"{session}"}}')
            await on_stdout_line(
                f'{{"type":"text","part":{{"text":"{Path(workdir).name}"}}}}'
            )
            return OpenCodeResult(stdout="", stderr="", returncode=0)

        backend = OpenCodeBackend()

        async def execute(workdir: Path) -> LLMResult:
            result: LLMResult | None = None
            async for event in backend.execute(
                ExecutionRequest(
                    prompt="fixture query",
                    workdir=workdir,
                    env={"ADJUTANT_OPERATION_KIND": "kb_query"},
                )
            ):
                result = event.result or result
            assert result is not None
            return result

        with patch("adjutant.core.backend_opencode.opencode_run", side_effect=fake_run):
            alpha_result, beta_result = await asyncio.gather(execute(alpha), execute(beta))

        assert len(calls) == 2
        assert all("--attach" not in args for args in calls)
        assert {args[args.index("--dir") + 1] for args in calls} == {str(alpha), str(beta)}
        assert {alpha_result.session_id, beta_result.session_id} == {
            "alpha-session",
            "beta-session",
        }

    @pytest.mark.asyncio
    async def test_draining_server_falls_back_to_isolated_cli(self) -> None:
        manager = AsyncMock()
        manager.ensure_ready.side_effect = OpenCodeServerDrainingError("draining")
        calls: list[list[str]] = []

        async def fake_run(
            args,
            timeout=None,
            startup_timeout=None,
            env=None,
            on_stdout_line=None,
            on_spawn=None,
        ):
            calls.append(args)
            assert on_stdout_line is not None
            await on_stdout_line('{"type":"text","part":{"text":"OK"}}')
            return OpenCodeResult(stdout="", stderr="", returncode=0)

        backend = OpenCodeBackend()
        with (
            patch("adjutant.core.backend_opencode._managed_server", return_value=manager),
            patch("adjutant.core.backend_opencode.opencode_run", side_effect=fake_run),
        ):
            result = await backend.run("hello")

        assert result.text == "OK"
        assert len(calls) == 1
        assert "--attach" not in calls[0]

    @pytest.mark.asyncio
    async def test_run_passes_variant_to_opencode(self) -> None:
        backend = OpenCodeBackend()
        with patch(
            "adjutant.core.backend_opencode.opencode_run",
            new=AsyncMock(
                return_value=OpenCodeResult(
                    stdout='{"type":"text","part":{"text":"OK"}}', stderr="", returncode=0
                )
            ),
        ) as mock_run:
            result = await backend.run(
                "hello",
                model="github-copilot/gpt-5.4",
                variant="xhigh",
                correlation_id="op-123",
            )

        assert isinstance(result, LLMResult)
        args = mock_run.await_args.args[0]
        assert "--variant" in args
        assert "xhigh" in args
        assert result.correlation_id == "op-123"
        assert result.timings is not None
        assert result.timings.total_seconds >= 0
        assert mock_run.await_args.kwargs["env"]["ADJUTANT_CORRELATION_ID"] == "op-123"

    @pytest.mark.asyncio
    async def test_run_places_prompt_before_file_attachments(self) -> None:
        backend = OpenCodeBackend()
        with patch(
            "adjutant.core.backend_opencode.opencode_run",
            new=AsyncMock(
                return_value=OpenCodeResult(
                    stdout='{"type":"text","part":{"text":"OK"}}', stderr="", returncode=0
                )
            ),
        ) as mock_run:
            await backend.run(
                "describe this image",
                model="github-copilot/gpt-5.4",
                variant="medium",
                files=[Path("/tmp/photo.jpg")],
            )

        args = mock_run.await_args.args[0]
        prompt_index = args.index("describe this image")
        file_flag_index = args.index("-f")
        assert prompt_index < file_flag_index
        assert args[file_flag_index + 1] == "/tmp/photo.jpg"

    @pytest.mark.asyncio
    async def test_run_preserves_partial_text_on_timeout(self) -> None:
        backend = OpenCodeBackend()
        with patch(
            "adjutant.core.backend_opencode.opencode_run",
            new=AsyncMock(
                return_value=OpenCodeResult(
                    stdout='{"type":"text","part":{"text":"partial answer"}}',
                    stderr="",
                    returncode=-15,
                    timed_out=True,
                )
            ),
        ):
            result = await backend.run("hello", timeout=1)

        assert result.timed_out is True
        assert result.error_type == "timeout"
        assert result.text == "partial answer"

    def test_run_detached_passes_variant_to_opencode(self, tmp_path: Path) -> None:
        backend = OpenCodeBackend()
        with (
            patch(
                "adjutant.core.backend_opencode._find_opencode", return_value="/usr/bin/opencode"
            ),
            patch("subprocess.Popen") as mock_popen,
        ):
            backend.run_detached(
                "hello",
                workdir=tmp_path,
                model="github-copilot/gpt-5.4",
                variant="medium",
            )

        args = mock_popen.call_args.args[0]
        assert "--variant" in args
        assert "medium" in args

    @pytest.mark.asyncio
    async def test_execute_yields_incremental_normalized_events(self) -> None:
        backend = OpenCodeBackend()

        async def fake_run(
            args,
            timeout=None,
            startup_timeout=None,
            env=None,
            on_stdout_line=None,
            on_spawn=None,
        ):
            assert on_stdout_line is not None
            await on_stdout_line('{"type":"session.create","sessionID":"s1"}')
            await on_stdout_line('{"type":"tool.start","part":{"name":"secret"}}')
            await on_stdout_line('{"type":"text","part":{"text":"answer"}}')
            return OpenCodeResult(stdout="", stderr="", returncode=0)

        with patch("adjutant.core.backend_opencode.opencode_run", side_effect=fake_run):
            events = [
                event
                async for event in backend.execute(
                    ExecutionRequest(prompt="hello", correlation_id="op-stream")
                )
            ]

        assert [event.type for event in events] == [
            ExecutionEventType.STARTED,
            ExecutionEventType.SESSION_STARTED,
            ExecutionEventType.TOOL_STARTED,
            ExecutionEventType.TEXT_DELTA,
            ExecutionEventType.COMPLETED,
        ]
        assert events[2].public_message == "A tool step started"
        assert events[2].data == {}
        assert events[3].text == "answer"
        assert events[-1].result is not None
        assert events[-1].result.text == "answer"

    @pytest.mark.asyncio
    async def test_execute_attaches_to_managed_server(self) -> None:
        backend = OpenCodeBackend()
        endpoint = OpenCodeServerEndpoint(
            url="http://127.0.0.1:4567",
            username="opencode",
            password="secret",
            instance_id="ocs-1",
            pid=123,
            version="1.18.0",
            reused=True,
            startup_seconds=0.0,
            rss_bytes=1024,
        )
        manager = AsyncMock()
        manager.ensure_ready.return_value = endpoint
        fake_result = OpenCodeResult(
            stdout='{"type":"text","part":{"text":"attached"}}',
            stderr="",
            returncode=0,
        )
        with (
            patch("adjutant.core.backend_opencode._managed_server", return_value=manager),
            patch(
                "adjutant.core.backend_opencode.opencode_run",
                new=AsyncMock(return_value=fake_result),
            ) as mock_run,
        ):
            result = await backend.run("hello")

        args = mock_run.await_args.args[0]
        assert args[:3] == ["run", "--attach", endpoint.url]
        assert mock_run.await_args.kwargs["env"]["OPENCODE_SERVER_PASSWORD"] == "secret"
        assert result.server_instance_id == "ocs-1"
        assert result.text == "attached"

    @pytest.mark.asyncio
    async def test_attached_cancellation_uses_native_session_abort(self) -> None:
        backend = OpenCodeBackend()
        client = MagicMock()
        endpoint = MagicMock(
            url="http://127.0.0.1:4567",
            username="opencode",
            password="secret",
            instance_id="ocs-1",
            reused=True,
            rss_bytes=1024,
        )
        endpoint.client.return_value = client
        manager = AsyncMock()
        manager.ensure_ready.return_value = endpoint
        session_seen = asyncio.Event()

        async def fake_run(
            args,
            timeout=None,
            startup_timeout=None,
            env=None,
            on_stdout_line=None,
            on_spawn=None,
        ):
            assert on_stdout_line is not None
            await on_stdout_line('{"type":"session.create","sessionID":"ses-cancel"}')
            session_seen.set()
            await asyncio.sleep(10)
            raise AssertionError("cancel should interrupt the CLI")

        async def consume() -> None:
            async for _event in backend.execute(ExecutionRequest(prompt="hello")):
                pass

        with (
            patch("adjutant.core.backend_opencode._managed_server", return_value=manager),
            patch("adjutant.core.backend_opencode.opencode_run", side_effect=fake_run),
        ):
            task = asyncio.create_task(consume())
            await session_seen.wait()
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

        client.abort_session.assert_called_once_with("ses-cancel", workdir=None)

    @pytest.mark.asyncio
    async def test_attached_disconnect_is_reconciled_without_replay(self) -> None:
        backend = OpenCodeBackend()
        client = MagicMock()
        client.session_status.return_value = {"ses-uncertain": {"type": "busy"}}
        endpoint = MagicMock(
            url="http://127.0.0.1:4567",
            username="opencode",
            password="secret",
            instance_id="ocs-1",
            reused=True,
            rss_bytes=1024,
        )
        endpoint.client.return_value = client
        manager = AsyncMock()
        manager.ensure_ready.return_value = endpoint

        async def fake_run(
            args,
            timeout=None,
            startup_timeout=None,
            env=None,
            on_stdout_line=None,
            on_spawn=None,
        ):
            assert on_stdout_line is not None
            await on_stdout_line('{"type":"session.create","sessionID":"ses-uncertain"}')
            return OpenCodeResult(stdout="", stderr="connection lost", returncode=1)

        with (
            patch("adjutant.core.backend_opencode._managed_server", return_value=manager),
            patch("adjutant.core.backend_opencode.opencode_run", side_effect=fake_run) as run,
        ):
            result = await backend.run("hello")

        assert run.await_count == 1
        assert result.error_type == "reconciliation_required"
        assert result.reconciliation_status == '{"type": "busy"}'
        client.session_status.assert_called_once_with(workdir=None)

    @pytest.mark.asyncio
    async def test_attached_connection_timeout_is_distinct(self) -> None:
        backend = OpenCodeBackend()
        endpoint = MagicMock(
            url="http://127.0.0.1:4567",
            username="opencode",
            password="secret",
            instance_id="ocs-1",
            reused=True,
            rss_bytes=1024,
        )
        manager = AsyncMock()
        manager.ensure_ready.return_value = endpoint

        async def fake_run(*_args, **_kwargs):
            await asyncio.sleep(10)
            raise AssertionError("connection timeout should cancel the CLI")

        request = ExecutionRequest(prompt="hello", connection_timeout=0.01, timeout=30)
        with (
            patch("adjutant.core.backend_opencode._managed_server", return_value=manager),
            patch("adjutant.core.backend_opencode.opencode_run", side_effect=fake_run),
        ):
            terminal = None
            async for event in backend.execute(request):
                terminal = event.result or terminal

        assert terminal is not None
        assert terminal.error_type == "timeout"
        assert terminal.timeout_phase == "connection"
