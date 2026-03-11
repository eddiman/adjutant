"""Unit tests for adjutant.capabilities.screenshot.screenshot."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from adjutant.capabilities.screenshot.screenshot import (
    _normalise_url,
    _domain_from_url,
    take_and_send,
    main,
)


# ---------------------------------------------------------------------------
# _normalise_url
# ---------------------------------------------------------------------------


class TestNormaliseUrl:
    def test_adds_https_when_missing(self) -> None:
        assert _normalise_url("example.com") == "https://example.com"

    def test_preserves_https(self) -> None:
        assert _normalise_url("https://example.com") == "https://example.com"

    def test_preserves_http(self) -> None:
        assert _normalise_url("http://example.com") == "http://example.com"

    def test_adds_https_to_bare_path(self) -> None:
        assert _normalise_url("news.bbc.co.uk/article") == "https://news.bbc.co.uk/article"


# ---------------------------------------------------------------------------
# _domain_from_url
# ---------------------------------------------------------------------------


class TestDomainFromUrl:
    def test_extracts_domain(self) -> None:
        assert _domain_from_url("https://example.com/page") == "example.com"

    def test_strips_www(self) -> None:
        assert _domain_from_url("https://www.example.com") == "example.com"

    def test_truncates_long_domain(self) -> None:
        long_url = "https://" + "a" * 50 + ".com"
        result = _domain_from_url(long_url)
        assert len(result) <= 40

    def test_returns_page_on_bad_url(self) -> None:
        assert _domain_from_url("not_a_url") == "page"

    def test_replaces_port_colon(self) -> None:
        result = _domain_from_url("http://localhost:8080/page")
        assert ":" not in result


# ---------------------------------------------------------------------------
# take_and_send
# ---------------------------------------------------------------------------


class TestTakeAndSend:
    def test_returns_error_when_no_url(self, tmp_path: Path) -> None:
        result = take_and_send("", tmp_path)
        assert result.startswith("ERROR")

    def test_returns_error_when_credentials_missing(self, tmp_path: Path) -> None:
        with patch(
            "adjutant.core.env.require_telegram_credentials",
            side_effect=RuntimeError("missing token"),
        ):
            result = take_and_send("https://example.com", tmp_path)
        assert result.startswith("ERROR")
        assert "missing token" in result

    def test_returns_error_when_screenshot_fails(self, tmp_path: Path) -> None:
        with (
            patch(
                "adjutant.core.env.require_telegram_credentials",
                return_value=("token123", "chat456"),
            ),
            patch(
                "adjutant.capabilities.screenshot.screenshot._take_screenshot",
                return_value=(False, "Playwright failed"),
            ),
            patch("adjutant.core.logging.adj_log"),
        ):
            result = take_and_send("https://example.com", tmp_path)
        assert result.startswith("ERROR")
        assert "Playwright failed" in result

    def test_returns_ok_when_photo_sent(self, tmp_path: Path) -> None:
        screenshots_dir = tmp_path / "screenshots"
        screenshots_dir.mkdir()

        def fake_take_screenshot(url, outfile):
            outfile.write_bytes(b"fake png data")
            return True, ""

        with (
            patch(
                "adjutant.core.env.require_telegram_credentials",
                return_value=("token123", "chat456"),
            ),
            patch(
                "adjutant.capabilities.screenshot.screenshot._take_screenshot",
                side_effect=fake_take_screenshot,
            ),
            patch(
                "adjutant.capabilities.screenshot.screenshot._generate_vision_caption",
                return_value="A news website",
            ),
            patch(
                "adjutant.capabilities.screenshot.screenshot._send_photo",
                return_value=(True, ""),
            ),
            patch("adjutant.core.logging.adj_log"),
            patch("adjutant.capabilities.screenshot.screenshot.datetime") as mock_dt,
        ):
            mock_dt.now.return_value.strftime.return_value = "2025-01-01_12-00-00"
            result = take_and_send("https://example.com", tmp_path, caption="Custom caption")

        assert result.startswith("OK:")

    def test_falls_back_to_document_when_photo_fails(self, tmp_path: Path) -> None:
        screenshots_dir = tmp_path / "screenshots"
        screenshots_dir.mkdir()

        def fake_take_screenshot(url, outfile):
            outfile.write_bytes(b"fake png data")
            return True, ""

        with (
            patch(
                "adjutant.core.env.require_telegram_credentials",
                return_value=("token123", "chat456"),
            ),
            patch(
                "adjutant.capabilities.screenshot.screenshot._take_screenshot",
                side_effect=fake_take_screenshot,
            ),
            patch(
                "adjutant.capabilities.screenshot.screenshot._generate_vision_caption",
                return_value="",
            ),
            patch(
                "adjutant.capabilities.screenshot.screenshot._send_photo",
                return_value=(False, "photo too large"),
            ),
            patch(
                "adjutant.capabilities.screenshot.screenshot._send_document",
                return_value=(True, ""),
            ),
            patch("adjutant.core.logging.adj_log"),
            patch("adjutant.capabilities.screenshot.screenshot.datetime") as mock_dt,
        ):
            mock_dt.now.return_value.strftime.return_value = "2025-01-01_12-00-00"
            result = take_and_send("https://example.com", tmp_path)

        assert result.startswith("OK:")

    def test_returns_error_when_both_send_methods_fail(self, tmp_path: Path) -> None:
        screenshots_dir = tmp_path / "screenshots"
        screenshots_dir.mkdir()

        def fake_take_screenshot(url, outfile):
            outfile.write_bytes(b"fake png data")
            return True, ""

        with (
            patch(
                "adjutant.core.env.require_telegram_credentials",
                return_value=("token123", "chat456"),
            ),
            patch(
                "adjutant.capabilities.screenshot.screenshot._take_screenshot",
                side_effect=fake_take_screenshot,
            ),
            patch(
                "adjutant.capabilities.screenshot.screenshot._generate_vision_caption",
                return_value="",
            ),
            patch(
                "adjutant.capabilities.screenshot.screenshot._send_photo",
                return_value=(False, "err1"),
            ),
            patch(
                "adjutant.capabilities.screenshot.screenshot._send_document",
                return_value=(False, "err2"),
            ),
            patch("adjutant.core.logging.adj_log"),
            patch("adjutant.capabilities.screenshot.screenshot.datetime") as mock_dt,
        ):
            mock_dt.now.return_value.strftime.return_value = "2025-01-01_12-00-00"
            result = take_and_send("https://example.com", tmp_path)

        assert result.startswith("ERROR")
        assert "err1" in result
        assert "err2" in result

    def test_uses_url_as_fallback_caption(self, tmp_path: Path) -> None:
        screenshots_dir = tmp_path / "screenshots"
        screenshots_dir.mkdir()
        captured_caption = {}

        def fake_take_screenshot(url, outfile):
            outfile.write_bytes(b"fake png")
            return True, ""

        def mock_send_photo(token, chat, outfile, caption):
            captured_caption["caption"] = caption
            return True, ""

        with (
            patch(
                "adjutant.core.env.require_telegram_credentials",
                return_value=("t", "c"),
            ),
            patch(
                "adjutant.capabilities.screenshot.screenshot._take_screenshot",
                side_effect=fake_take_screenshot,
            ),
            patch(
                "adjutant.capabilities.screenshot.screenshot._generate_vision_caption",
                return_value="",
            ),
            patch(
                "adjutant.capabilities.screenshot.screenshot._send_photo",
                side_effect=mock_send_photo,
            ),
            patch("adjutant.core.logging.adj_log"),
            patch("adjutant.capabilities.screenshot.screenshot.datetime") as mock_dt,
        ):
            mock_dt.now.return_value.strftime.return_value = "2025-01-01_12-00-00"
            take_and_send("https://example.com", tmp_path)

        assert captured_caption["caption"] == "https://example.com"

    def test_clamps_caption_to_1024_chars(self, tmp_path: Path) -> None:
        long_caption = "A" * 2000
        captured = {}
        screenshots_dir = tmp_path / "screenshots"
        screenshots_dir.mkdir()

        def fake_take_screenshot(url, outfile):
            outfile.write_bytes(b"fake png")
            return True, ""

        def mock_send_photo(token, chat, outfile, caption):
            captured["caption"] = caption
            return True, ""

        with (
            patch(
                "adjutant.core.env.require_telegram_credentials",
                return_value=("t", "c"),
            ),
            patch(
                "adjutant.capabilities.screenshot.screenshot._take_screenshot",
                side_effect=fake_take_screenshot,
            ),
            patch(
                "adjutant.capabilities.screenshot.screenshot._send_photo",
                side_effect=mock_send_photo,
            ),
            patch("adjutant.core.logging.adj_log"),
            patch("adjutant.capabilities.screenshot.screenshot.datetime") as mock_dt,
        ):
            mock_dt.now.return_value.strftime.return_value = "2025-01-01_12-00-00"
            take_and_send("https://example.com", tmp_path, caption=long_caption)

        assert len(captured["caption"]) <= 1024


# ---------------------------------------------------------------------------
# main (CLI)
# ---------------------------------------------------------------------------


class TestMain:
    def test_returns_1_on_no_args(self) -> None:
        rc = main([])
        assert rc == 1

    def test_returns_1_when_adj_dir_not_set(self) -> None:
        env = {k: v for k, v in os.environ.items() if k != "ADJ_DIR"}
        with patch.dict(os.environ, env, clear=True):
            rc = main(["https://example.com"])
        assert rc == 1

    def test_returns_0_on_success(self, tmp_path: Path) -> None:
        with (
            patch.dict(os.environ, {"ADJ_DIR": str(tmp_path)}),
            patch(
                "adjutant.capabilities.screenshot.screenshot.take_and_send",
                return_value="OK:/path/to/file.png:::caption",
            ),
        ):
            rc = main(["https://example.com"])
        assert rc == 0

    def test_returns_1_on_error(self, tmp_path: Path) -> None:
        with (
            patch.dict(os.environ, {"ADJ_DIR": str(tmp_path)}),
            patch(
                "adjutant.capabilities.screenshot.screenshot.take_and_send",
                return_value="ERROR: something failed",
            ),
        ):
            rc = main(["https://example.com"])
        assert rc == 1
