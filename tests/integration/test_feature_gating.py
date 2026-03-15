"""Integration tests for runtime feature gating in dispatch.

Verifies that disabled features are rejected at the dispatch layer
before reaching command handlers.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


pytestmark = pytest.mark.integration


class TestFeatureGating:
    """Test that dispatch.py gates feature-flagged commands."""

    @pytest.fixture()
    def _setup_config(self, adj_dir: Path):
        """Write config with screenshot disabled and search disabled."""
        (adj_dir / "adjutant.yaml").write_text(
            "instance:\n"
            "  name: test\n"
            "messaging:\n"
            "  backend: telegram\n"
            "features:\n"
            "  news:\n"
            "    enabled: false\n"
            "  screenshot:\n"
            "    enabled: false\n"
            "  vision:\n"
            "    enabled: true\n"
            "  search:\n"
            "    enabled: false\n"
            "  usage_tracking:\n"
            "    enabled: false\n"
        )

    @pytest.mark.usefixtures("_setup_config")
    def test_disabled_screenshot_is_rejected(self, adj_dir: Path) -> None:
        from adjutant.messaging.dispatch import dispatch_message

        with (
            patch("adjutant.messaging.telegram.send.msg_send_text") as mock_send,
            patch("adjutant.messaging.dispatch._check_rate_limit", return_value=True),
        ):
            asyncio.run(
                dispatch_message(
                    "/screenshot https://example.com",
                    1,
                    "99999",
                    adj_dir,
                    bot_token="test-token",
                    chat_id="99999",
                )
            )

            mock_send.assert_called_once()
            sent_text = mock_send.call_args[0][0]
            assert "not enabled" in sent_text.lower()

    @pytest.mark.usefixtures("_setup_config")
    def test_disabled_search_is_rejected(self, adj_dir: Path) -> None:
        from adjutant.messaging.dispatch import dispatch_message

        with (
            patch("adjutant.messaging.telegram.send.msg_send_text") as mock_send,
            patch("adjutant.messaging.dispatch._check_rate_limit", return_value=True),
        ):
            asyncio.run(
                dispatch_message(
                    "/search test query",
                    1,
                    "99999",
                    adj_dir,
                    bot_token="test-token",
                    chat_id="99999",
                )
            )

            mock_send.assert_called_once()
            sent_text = mock_send.call_args[0][0]
            assert "not enabled" in sent_text.lower()

    def test_enabled_feature_is_allowed(self, adj_dir: Path) -> None:
        """When a feature is enabled, the command should reach the handler."""
        (adj_dir / "adjutant.yaml").write_text(
            "instance:\n"
            "  name: test\n"
            "features:\n"
            "  screenshot:\n"
            "    enabled: true\n"
            "  search:\n"
            "    enabled: true\n"
            "  news:\n"
            "    enabled: false\n"
            "  vision:\n"
            "    enabled: false\n"
            "  usage_tracking:\n"
            "    enabled: false\n"
        )

        from adjutant.messaging.dispatch import dispatch_message

        with (
            patch(
                "adjutant.messaging.telegram.commands.cmd_screenshot", new_callable=AsyncMock
            ) as mock_cmd,
            patch("adjutant.messaging.telegram.send.msg_send_text"),
            patch("adjutant.messaging.dispatch._check_rate_limit", return_value=True),
        ):
            asyncio.run(
                dispatch_message(
                    "/screenshot https://example.com",
                    1,
                    "99999",
                    adj_dir,
                    bot_token="test-token",
                    chat_id="99999",
                )
            )

            mock_cmd.assert_called_once()

    def test_ungated_command_always_works(self, adj_dir: Path) -> None:
        """Commands without feature gates (like /status) should always work."""
        from adjutant.messaging.dispatch import dispatch_message

        with (
            patch(
                "adjutant.messaging.telegram.commands.cmd_status", new_callable=AsyncMock
            ) as mock_cmd,
            patch("adjutant.messaging.dispatch._check_rate_limit", return_value=True),
        ):
            asyncio.run(
                dispatch_message(
                    "/status",
                    1,
                    "99999",
                    adj_dir,
                    bot_token="test-token",
                    chat_id="99999",
                )
            )

            mock_cmd.assert_called_once()
