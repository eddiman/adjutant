"""Tests for src/adjutant/messaging/telegram/commands.py"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from adjutant.messaging.telegram.commands import (
    _journal_append,
    cmd_help,
    cmd_kb,
    cmd_kill,
    cmd_model,
    cmd_pause,
    cmd_reflect_confirm,
    cmd_reflect_request,
    cmd_resume,
    cmd_schedule,
    cmd_search,
    cmd_screenshot,
    cmd_status,
)


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


# ---------------------------------------------------------------------------
# cmd_kill
# ---------------------------------------------------------------------------


class TestCmdKill:
    @pytest.mark.asyncio
    async def test_sends_confirmation_and_starts_kill(self, tmp_path: Path) -> None:
        mock_send, sent = _capture_send()
        with patch("adjutant.messaging.telegram.send.msg_send_text", mock_send):
            with patch("adjutant.lifecycle.control.emergency_kill") as mock_kill:
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

        # Mock opencode models to include the target model
        fake_proc = AsyncMock()
        fake_proc.communicate = AsyncMock(
            return_value=(b"anthropic/claude-opus-4-5\nanthropicmodel2\n", b"")
        )
        fake_proc.returncode = 0

        with patch("adjutant.messaging.telegram.send.msg_send_text", mock_send):
            with patch("asyncio.create_subprocess_exec", return_value=fake_proc):
                await cmd_model(
                    "anthropic/claude-opus-4-5", 1, tmp_path, bot_token=BOT, chat_id=CHAT
                )

        model_file = state / "telegram_model.txt"
        assert model_file.is_file()
        assert model_file.read_text().strip() == "anthropic/claude-opus-4-5"
        assert any("switched" in m.lower() or "claude-opus" in m for m in sent)

    @pytest.mark.asyncio
    async def test_shows_current_model_when_no_arg(self, tmp_path: Path) -> None:
        mock_send, sent = _capture_send()
        state = tmp_path / "state"
        state.mkdir()
        (state / "telegram_model.txt").write_text("anthropic/claude-haiku-4-5")

        fake_proc = AsyncMock()
        fake_proc.communicate = AsyncMock(return_value=(b"model1\nmodel2\n", b""))
        fake_proc.returncode = 0

        with patch("adjutant.messaging.telegram.send.msg_send_text", mock_send):
            with patch("asyncio.create_subprocess_exec", return_value=fake_proc):
                await cmd_model("", 1, tmp_path, bot_token=BOT, chat_id=CHAT)

        assert len(sent) == 1
        assert "current model" in sent[0].lower()


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
                with patch(
                    "adjutant.messaging.telegram.send.msg_typing_start", mock_typing_start
                ):
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
