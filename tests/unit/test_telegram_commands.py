"""Tests for src/adjutant/messaging/telegram/commands.py"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from adjutant.core.backend import LLMResult
from adjutant.messaging.telegram.commands import (
    _journal_append,
    _run_opencode_prompt,
    cmd_help,
    cmd_kb,
    cmd_kill,
    cmd_model,
    cmd_pause,
    cmd_reflect_confirm,
    cmd_reflect_request,
    cmd_restart,
    cmd_resume,
    cmd_schedule,
    cmd_screenshot,
    cmd_search,
    cmd_status,
)

if TYPE_CHECKING:
    from pathlib import Path


BOT = "123:testtoken"
CHAT = "999"

# ---------------------------------------------------------------------------
# Helper — captures msg_send_text calls
# ---------------------------------------------------------------------------


def _capture_send():
    """Return a mock and a list of sent messages."""
    sent = []

    def _fake_send(msg, reply_to=None, *, bot_token, chat_id):
        sent.append(msg)

    mock = MagicMock(side_effect=_fake_send)
    return mock, sent


# ---------------------------------------------------------------------------
# _run_opencode_prompt
# ---------------------------------------------------------------------------


class TestRunOpencodePrompt:
    @pytest.mark.asyncio
    async def test_runs_standalone_prompt_without_agent_wrapper(self, tmp_path: Path) -> None:
        prompt = tmp_path / "prompts" / "self_assess.md"
        prompt.parent.mkdir(parents=True)
        prompt.write_text("Standalone prompt text")

        backend = MagicMock()
        backend.run = AsyncMock(return_value=LLMResult(text="Done"))
        backend.reap = AsyncMock(return_value=0)
        backend.capabilities = SimpleNamespace(reaping=False)

        resolved = SimpleNamespace(model="anthropic/claude-sonnet-4-6", variant="high")

        with (
            patch("adjutant.core.backend.get_backend", return_value=backend),
            patch("adjutant.core.config.load_config", return_value={}),
            patch("adjutant.messaging.telegram.commands.resolve_model_spec", return_value=resolved),
        ):
            result = await _run_opencode_prompt(prompt, 30.0, tmp_path, "medium")

        assert result == "Done"
        backend.run.assert_awaited_once()
        assert backend.run.await_args.args == ("Standalone prompt text",)
        assert backend.run.await_args.kwargs == {
            "workdir": tmp_path,
            "model": "anthropic/claude-sonnet-4-6",
            "variant": "high",
            "timeout": 30.0,
        }


# ---------------------------------------------------------------------------
# _journal_append
# ---------------------------------------------------------------------------


class TestJournalAppend:
    def test_creates_journal_file(self, tmp_path: Path) -> None:
        _journal_append(tmp_path, "Test entry")
        today_files = list((tmp_path / "journal").glob("*.md"))
        assert len(today_files) == 1
        content = today_files[0].read_text()
        assert "Test entry" in content

    def test_appends_to_existing_file(self, tmp_path: Path) -> None:
        _journal_append(tmp_path, "First entry")
        _journal_append(tmp_path, "Second entry")
        today_files = list((tmp_path / "journal").glob("*.md"))
        content = today_files[0].read_text()
        assert "First entry" in content
        assert "Second entry" in content


# ---------------------------------------------------------------------------
# cmd_status
# ---------------------------------------------------------------------------


class TestCmdStatus:
    @pytest.mark.asyncio
    async def test_calls_get_status_and_sends(self, tmp_path: Path) -> None:
        mock_send, sent = _capture_send()
        with patch("adjutant.messaging.telegram.send.msg_send_text", mock_send):
            with patch(
                "adjutant.observability.status.get_status",
                return_value="Status: OK",
            ):
                await cmd_status(1, tmp_path, bot_token=BOT, chat_id=CHAT)
        assert any("OK" in m for m in sent)

    @pytest.mark.asyncio
    async def test_handles_get_status_exception(self, tmp_path: Path) -> None:
        mock_send, sent = _capture_send()
        with patch("adjutant.messaging.telegram.send.msg_send_text", mock_send):
            with patch(
                "adjutant.observability.status.get_status",
                side_effect=Exception("oops"),
            ):
                await cmd_status(1, tmp_path, bot_token=BOT, chat_id=CHAT)
        assert len(sent) == 1


# ---------------------------------------------------------------------------
# cmd_pause / cmd_resume
# ---------------------------------------------------------------------------


class TestCmdPause:
    @pytest.mark.asyncio
    async def test_sets_paused_and_responds(self, tmp_path: Path) -> None:
        mock_send, sent = _capture_send()
        with patch("adjutant.messaging.telegram.send.msg_send_text", mock_send):
            with patch("adjutant.core.lockfiles.set_paused") as mock_pause:
                await cmd_pause(1, tmp_path, bot_token=BOT, chat_id=CHAT)
        mock_pause.assert_called_once_with(tmp_path)
        assert len(sent) == 1
        assert "paused" in sent[0].lower()


class TestCmdResume:
    @pytest.mark.asyncio
    async def test_clears_paused_and_responds(self, tmp_path: Path) -> None:
        mock_send, sent = _capture_send()
        with patch("adjutant.messaging.telegram.send.msg_send_text", mock_send):
            with patch("adjutant.core.lockfiles.clear_paused") as mock_clear:
                await cmd_resume(1, tmp_path, bot_token=BOT, chat_id=CHAT)
        mock_clear.assert_called_once_with(tmp_path)
        assert len(sent) == 1
        assert "online" in sent[0].lower() or "back" in sent[0].lower()


class TestCmdRestart:
    @pytest.mark.asyncio
    async def test_persists_pending_restart_reply_before_spawning(self, tmp_path: Path) -> None:
        mock_send, sent = _capture_send()

        with (
            patch("adjutant.messaging.telegram.send.msg_send_text", mock_send),
            patch("adjutant.messaging.telegram.commands.adj_log") as mock_log,
            patch("asyncio.sleep", new=AsyncMock()),
            patch("subprocess.Popen") as mock_popen,
        ):
            await cmd_restart(7, tmp_path, bot_token=BOT, chat_id=CHAT)

        pending = tmp_path / "state" / "restart_notify.json"
        assert pending.exists()
        assert '"reply_to_message_id": 7' in pending.read_text()
        mock_popen.assert_called_once()
        assert any(
            "Wrote restart reply marker" in str(call.args[1]) for call in mock_log.call_args_list
        )
        assert any("restarting" in m.lower() for m in sent)

    @pytest.mark.asyncio
    async def test_cleans_pending_file_when_spawn_fails(self, tmp_path: Path) -> None:
        mock_send, sent = _capture_send()

        with (
            patch("adjutant.messaging.telegram.send.msg_send_text", mock_send),
            patch("asyncio.sleep", new=AsyncMock()),
            patch("subprocess.Popen", side_effect=OSError("boom")),
        ):
            await cmd_restart(7, tmp_path, bot_token=BOT, chat_id=CHAT)

        assert not (tmp_path / "state" / "restart_notify.json").exists()
        assert any("restart failed" in m.lower() for m in sent)


# ---------------------------------------------------------------------------
# cmd_kill
# ---------------------------------------------------------------------------


class TestCmdKill:
    @pytest.mark.asyncio
    async def test_sends_confirmation_and_starts_kill(self, tmp_path: Path) -> None:
        mock_send, sent = _capture_send()
        with patch("adjutant.messaging.telegram.send.msg_send_text", mock_send):
            with patch("adjutant.lifecycle.control.emergency_kill"):
                await cmd_kill(1, tmp_path, bot_token=BOT, chat_id=CHAT)
                import time

                time.sleep(0.05)

        assert len(sent) >= 1
        assert "kill" in sent[0].lower() or "shut" in sent[0].lower()


# ---------------------------------------------------------------------------
# cmd_reflect_request / cmd_reflect_confirm
# ---------------------------------------------------------------------------


class TestCmdReflect:
    @pytest.mark.asyncio
    async def test_reflect_request_creates_pending_file(self, tmp_path: Path) -> None:
        mock_send, sent = _capture_send()
        with patch("adjutant.messaging.telegram.send.msg_send_text", mock_send):
            await cmd_reflect_request(1, tmp_path, bot_token=BOT, chat_id=CHAT)
        assert (tmp_path / "state" / "pending_reflect").exists()
        assert len(sent) == 1

    @pytest.mark.asyncio
    async def test_reflect_confirm_without_opencode(self, tmp_path: Path) -> None:
        mock_send, sent = _capture_send()
        # Create pending file first
        state = tmp_path / "state"
        state.mkdir(parents=True, exist_ok=True)
        (state / "pending_reflect").touch()

        with patch("adjutant.messaging.telegram.send.msg_send_text", mock_send):
            with patch("shutil.which", return_value=None):
                await cmd_reflect_confirm(1, tmp_path, bot_token=BOT, chat_id=CHAT)

        assert not (state / "pending_reflect").exists()
        assert any("can't find" in m.lower() or "opencode" in m.lower() for m in sent)


# ---------------------------------------------------------------------------
# cmd_help
# ---------------------------------------------------------------------------


class TestCmdHelp:
    @pytest.mark.asyncio
    async def test_sends_help_text(self, tmp_path: Path) -> None:
        mock_send, sent = _capture_send()
        with patch("adjutant.messaging.telegram.send.msg_send_text", mock_send):
            await cmd_help(1, tmp_path, bot_token=BOT, chat_id=CHAT)
        assert len(sent) == 1
        assert "/status" in sent[0]
        assert "/pause" in sent[0]
        assert "/help" in sent[0]


# ---------------------------------------------------------------------------
# cmd_model
# ---------------------------------------------------------------------------


class TestCmdModel:
    @pytest.mark.asyncio
    async def test_switches_model(self, tmp_path: Path) -> None:
        mock_send, sent = _capture_send()
        state = tmp_path / "state"
        state.mkdir()

        with patch("adjutant.messaging.telegram.send.msg_send_text", mock_send):
            await cmd_model("expensive", 1, tmp_path, bot_token=BOT, chat_id=CHAT)

        model_file = state / "telegram_model.txt"
        assert model_file.is_file()
        assert model_file.read_text().strip() == "expensive"
        assert any("switched" in m.lower() or "expensive" in m.lower() for m in sent)

    @pytest.mark.asyncio
    async def test_shows_current_model_when_no_arg(self, tmp_path: Path) -> None:
        mock_send, sent = _capture_send()
        state = tmp_path / "state"
        state.mkdir()
        (state / "telegram_model.txt").write_text("medium")

        with patch("adjutant.messaging.telegram.send.msg_send_text", mock_send):
            await cmd_model("", 1, tmp_path, bot_token=BOT, chat_id=CHAT)

        assert len(sent) == 1
        assert "current tier" in sent[0].lower()
        assert "available tiers" in sent[0].lower()
        assert "reasoning" in sent[0].lower()
        assert "`cheap`" in sent[0]
        assert "`medium`" in sent[0]
        assert "`expensive`" in sent[0]

    @pytest.mark.asyncio
    async def test_switches_to_tier_name_without_model_lookup(self, tmp_path: Path) -> None:
        mock_send, sent = _capture_send()
        state = tmp_path / "state"
        state.mkdir()

        with patch("adjutant.messaging.telegram.send.msg_send_text", mock_send):
            await cmd_model("medium", 1, tmp_path, bot_token=BOT, chat_id=CHAT)

        model_file = state / "telegram_model.txt"
        assert model_file.read_text().strip() == "medium"
        assert any("tier" in m.lower() for m in sent)

    @pytest.mark.asyncio
    async def test_rejects_non_tier_model_name(self, tmp_path: Path) -> None:
        mock_send, sent = _capture_send()
        state = tmp_path / "state"
        state.mkdir()

        with patch("adjutant.messaging.telegram.send.msg_send_text", mock_send):
            await cmd_model("anthropic/claude-opus-4-6", 1, tmp_path, bot_token=BOT, chat_id=CHAT)

        assert not (state / "telegram_model.txt").exists()
        assert any("only the configured tiers are allowed" in m.lower() for m in sent)


# ---------------------------------------------------------------------------
# cmd_screenshot
# ---------------------------------------------------------------------------


class TestCmdScreenshot:
    @pytest.mark.asyncio
    async def test_sends_error_on_failure(self, tmp_path: Path) -> None:
        mock_send, sent = _capture_send()
        mock_react = MagicMock()
        mock_typing_start = MagicMock()
        mock_typing_stop = MagicMock()

        with patch("adjutant.messaging.telegram.send.msg_send_text", mock_send):
            with patch("adjutant.messaging.telegram.send.msg_react", mock_react):
                with patch("adjutant.messaging.telegram.send.msg_typing_start", mock_typing_start):
                    with patch(
                        "adjutant.messaging.telegram.send.msg_typing_stop", mock_typing_stop
                    ):
                        with patch(
                            "adjutant.capabilities.screenshot.screenshot.run_screenshot",
                            return_value="ERROR:Something failed",
                        ):
                            await cmd_screenshot(
                                "https://example.com", 1, tmp_path, bot_token=BOT, chat_id=CHAT
                            )

        assert any("failed" in m.lower() or "error" in m.lower() for m in sent)


# ---------------------------------------------------------------------------
# cmd_search
# ---------------------------------------------------------------------------


class TestCmdSearch:
    @pytest.mark.asyncio
    async def test_sends_results_on_success(self, tmp_path: Path) -> None:
        mock_send, sent = _capture_send()

        with patch("adjutant.messaging.telegram.send.msg_send_text", mock_send):
            with patch("adjutant.messaging.telegram.send.msg_react", MagicMock()):
                with patch("adjutant.messaging.telegram.send.msg_typing_start", MagicMock()):
                    with patch("adjutant.messaging.telegram.send.msg_typing_stop", MagicMock()):
                        with patch(
                            "adjutant.capabilities.search.search.run_search",
                            return_value="OK:Result text",
                        ):
                            await cmd_search("test query", 1, tmp_path, bot_token=BOT, chat_id=CHAT)

        assert any("result" in m.lower() for m in sent)

    @pytest.mark.asyncio
    async def test_sends_error_on_failure(self, tmp_path: Path) -> None:
        mock_send, sent = _capture_send()

        with patch("adjutant.messaging.telegram.send.msg_send_text", mock_send):
            with patch("adjutant.messaging.telegram.send.msg_react", MagicMock()):
                with patch("adjutant.messaging.telegram.send.msg_typing_start", MagicMock()):
                    with patch("adjutant.messaging.telegram.send.msg_typing_stop", MagicMock()):
                        with patch(
                            "adjutant.capabilities.search.search.run_search",
                            return_value="ERROR:API key missing",
                        ):
                            await cmd_search("test query", 1, tmp_path, bot_token=BOT, chat_id=CHAT)

        assert any("failed" in m.lower() or "error" in m.lower() for m in sent)


# ---------------------------------------------------------------------------
# cmd_kb
# ---------------------------------------------------------------------------


class TestCmdKb:
    @pytest.mark.asyncio
    async def test_list_empty(self, tmp_path: Path) -> None:
        mock_send, sent = _capture_send()

        with patch("adjutant.messaging.telegram.send.msg_send_text", mock_send):
            with patch("adjutant.capabilities.kb.manage.kb_count", return_value=0):
                await cmd_kb("list", 1, tmp_path, bot_token=BOT, chat_id=CHAT)

        assert any("no knowledge" in m.lower() for m in sent)

    @pytest.mark.asyncio
    async def test_query_requires_name_and_question(self, tmp_path: Path) -> None:
        mock_send, sent = _capture_send()

        with patch("adjutant.messaging.telegram.send.msg_send_text", mock_send):
            await cmd_kb("query", 1, tmp_path, bot_token=BOT, chat_id=CHAT)

        assert any("usage" in m.lower() or "/kb" in m for m in sent)

    @pytest.mark.asyncio
    async def test_query_kb_not_found(self, tmp_path: Path) -> None:
        mock_send, sent = _capture_send()

        with patch("adjutant.messaging.telegram.send.msg_send_text", mock_send):
            with patch("adjutant.capabilities.kb.manage.kb_exists", return_value=False):
                await cmd_kb("query myrepo what is this", 1, tmp_path, bot_token=BOT, chat_id=CHAT)

        assert any("not found" in m.lower() for m in sent)


# ---------------------------------------------------------------------------
# cmd_schedule
# ---------------------------------------------------------------------------


class TestCmdSchedule:
    @pytest.mark.asyncio
    async def test_list_empty(self, tmp_path: Path) -> None:
        mock_send, sent = _capture_send()
        config = tmp_path / "adjutant.yaml"
        config.write_text("schedules: []\n")

        with patch("adjutant.messaging.telegram.send.msg_send_text", mock_send):
            with patch("adjutant.capabilities.schedule.manage.schedule_count", return_value=0):
                await cmd_schedule("list", 1, tmp_path, bot_token=BOT, chat_id=CHAT)

        assert any("no scheduled" in m.lower() for m in sent)

    @pytest.mark.asyncio
    async def test_enable_unknown_job(self, tmp_path: Path) -> None:
        mock_send, sent = _capture_send()
        config = tmp_path / "adjutant.yaml"
        config.write_text("schedules: []\n")

        with patch("adjutant.messaging.telegram.send.msg_send_text", mock_send):
            with patch("adjutant.capabilities.schedule.manage.schedule_exists", return_value=False):
                await cmd_schedule("enable unknownjob", 1, tmp_path, bot_token=BOT, chat_id=CHAT)

        assert any("not found" in m.lower() for m in sent)

    @pytest.mark.asyncio
    async def test_unknown_subcommand(self, tmp_path: Path) -> None:
        mock_send, sent = _capture_send()

        with patch("adjutant.messaging.telegram.send.msg_send_text", mock_send):
            await cmd_schedule("badcmd", 1, tmp_path, bot_token=BOT, chat_id=CHAT)

        assert any("usage" in m.lower() for m in sent)
