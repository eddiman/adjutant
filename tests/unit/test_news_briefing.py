"""Unit tests for adjutant.news.briefing."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from adjutant.news.briefing import run_briefing, _prune_old_files, main


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_adj_dir(tmp_path: Path, config: dict | None = None) -> Path:
    if config is None:
        config = {
            "delivery": {"journal": False, "telegram": False},
            "deduplication": {"window_days": 30},
            "cleanup": {"raw_retention_days": 7, "analyzed_retention_days": 7},
        }
    (tmp_path / "news_config.json").write_text(json.dumps(config))
    state = tmp_path / "state"
    (state / "news_raw").mkdir(parents=True, exist_ok=True)
    (state / "news_analyzed").mkdir(parents=True, exist_ok=True)
    (state / "news_seen_urls.json").write_text('{"urls":[]}')
    return tmp_path


def _write_analyzed(adj_dir: Path, items: list[dict]) -> Path:
    today = datetime.now().strftime("%Y-%m-%d")
    analyzed_file = adj_dir / "state" / "news_analyzed" / f"{today}.json"
    analyzed_file.write_text(json.dumps(items))
    return analyzed_file


def _write_raw(adj_dir: Path, items: list[dict]) -> Path:
    today = datetime.now().strftime("%Y-%m-%d")
    raw_file = adj_dir / "state" / "news_raw" / f"{today}.json"
    raw_file.write_text(json.dumps(items))
    return raw_file


# ---------------------------------------------------------------------------
# run_briefing
# ---------------------------------------------------------------------------


class TestRunBriefing:
    def test_returns_error_when_not_operational(self, tmp_path: Path):
        _make_adj_dir(tmp_path)
        with patch("adjutant.core.lockfiles.check_operational", return_value=False):
            result = run_briefing(tmp_path)
        assert result.startswith("ERROR")
        assert "operational" in result

    def test_returns_error_when_fetch_fails(self, tmp_path: Path):
        _make_adj_dir(tmp_path)
        with (
            patch("adjutant.core.lockfiles.check_operational", return_value=True),
            patch("adjutant.core.logging.adj_log"),
            patch("adjutant.news.fetch.fetch_news", return_value="ERROR: fetch broke"),
        ):
            result = run_briefing(tmp_path)
        assert result.startswith("ERROR")
        assert "fetch" in result

    def test_returns_error_when_analyze_fails(self, tmp_path: Path):
        _make_adj_dir(tmp_path)
        with (
            patch("adjutant.core.lockfiles.check_operational", return_value=True),
            patch("adjutant.core.logging.adj_log"),
            patch("adjutant.news.fetch.fetch_news", return_value="OK:/some/path"),
            patch("adjutant.news.analyze.analyze_news", return_value="ERROR: analysis broke"),
        ):
            result = run_briefing(tmp_path)
        assert result.startswith("ERROR")
        assert "analyze" in result

    def test_returns_ok_when_no_analyzed_file(self, tmp_path: Path):
        _make_adj_dir(tmp_path)
        # Don't write an analyzed file
        with (
            patch("adjutant.core.lockfiles.check_operational", return_value=True),
            patch("adjutant.core.logging.adj_log"),
            patch("adjutant.news.fetch.fetch_news", return_value="OK:/some/path"),
            patch("adjutant.news.analyze.analyze_news", return_value="OK:/some/path"),
        ):
            result = run_briefing(tmp_path)
        assert result.startswith("OK:")
        assert "no analysis" in result

    def test_returns_ok_when_no_items(self, tmp_path: Path):
        _make_adj_dir(tmp_path)
        _write_analyzed(tmp_path, [])
        _write_raw(tmp_path, [])
        with (
            patch("adjutant.core.lockfiles.check_operational", return_value=True),
            patch("adjutant.core.logging.adj_log"),
            patch("adjutant.news.fetch.fetch_news", return_value="OK:/some/path"),
            patch("adjutant.news.analyze.analyze_news", return_value="OK:/some/path"),
        ):
            result = run_briefing(tmp_path)
        assert result.startswith("OK:")
        assert "no interesting" in result

    def test_returns_ok_with_items_no_delivery(self, tmp_path: Path):
        _make_adj_dir(tmp_path)
        items = [{"rank": 1, "title": "Test", "url": "https://t.com", "summary": "ok"}]
        _write_analyzed(tmp_path, items)
        _write_raw(
            tmp_path,
            [
                {
                    "title": "Test",
                    "url": "https://t.com",
                    "score": 5,
                    "source": "hn",
                    "timestamp": "",
                }
            ],
        )

        with (
            patch("adjutant.core.lockfiles.check_operational", return_value=True),
            patch("adjutant.core.logging.adj_log"),
            patch("adjutant.news.fetch.fetch_news", return_value="OK:/some/path"),
            patch("adjutant.news.analyze.analyze_news", return_value="OK:/some/path"),
        ):
            result = run_briefing(tmp_path)

        assert result == "OK:briefing complete"

    def test_writes_journal_when_enabled(self, tmp_path: Path):
        config = {
            "delivery": {"journal": True, "telegram": False},
            "deduplication": {"window_days": 30},
            "cleanup": {"raw_retention_days": 7, "analyzed_retention_days": 7},
        }
        _make_adj_dir(tmp_path, config)
        items = [{"rank": 1, "title": "J", "url": "https://j.com", "summary": "journal"}]
        _write_analyzed(tmp_path, items)
        _write_raw(
            tmp_path,
            [{"title": "J", "url": "https://j.com", "score": 1, "source": "hn", "timestamp": ""}],
        )

        with (
            patch("adjutant.core.lockfiles.check_operational", return_value=True),
            patch("adjutant.core.logging.adj_log"),
            patch("adjutant.news.fetch.fetch_news", return_value="OK:/some/path"),
            patch("adjutant.news.analyze.analyze_news", return_value="OK:/some/path"),
        ):
            run_briefing(tmp_path)

        today = datetime.now().strftime("%Y-%m-%d")
        journal_file = tmp_path / "journal" / "news" / f"{today}.md"
        assert journal_file.exists()
        assert "Agentic AI News" in journal_file.read_text()

    def test_sends_telegram_when_enabled(self, tmp_path: Path):
        config = {
            "delivery": {"journal": False, "telegram": True},
            "deduplication": {"window_days": 30},
            "cleanup": {"raw_retention_days": 7, "analyzed_retention_days": 7},
        }
        _make_adj_dir(tmp_path, config)
        items = [{"rank": 1, "title": "T", "url": "https://t.com", "summary": "tg"}]
        _write_analyzed(tmp_path, items)
        _write_raw(
            tmp_path,
            [{"title": "T", "url": "https://t.com", "score": 1, "source": "hn", "timestamp": ""}],
        )

        mock_send = MagicMock()
        with (
            patch("adjutant.core.lockfiles.check_operational", return_value=True),
            patch("adjutant.core.logging.adj_log"),
            patch("adjutant.news.fetch.fetch_news", return_value="OK:/some/path"),
            patch("adjutant.news.analyze.analyze_news", return_value="OK:/some/path"),
            patch("adjutant.messaging.telegram.notify.send_notify", mock_send),
        ):
            run_briefing(tmp_path)

        mock_send.assert_called_once()

    def test_updates_dedup_cache(self, tmp_path: Path):
        _make_adj_dir(tmp_path)
        items = [{"rank": 1, "title": "D", "url": "https://d.com", "summary": "dedup"}]
        _write_analyzed(tmp_path, items)
        _write_raw(
            tmp_path,
            [{"title": "D", "url": "https://d.com", "score": 1, "source": "hn", "timestamp": ""}],
        )

        with (
            patch("adjutant.core.lockfiles.check_operational", return_value=True),
            patch("adjutant.core.logging.adj_log"),
            patch("adjutant.news.fetch.fetch_news", return_value="OK:/some/path"),
            patch("adjutant.news.analyze.analyze_news", return_value="OK:/some/path"),
        ):
            run_briefing(tmp_path)

        dedup = json.loads((tmp_path / "state" / "news_seen_urls.json").read_text())
        urls = [e["url"] for e in dedup["urls"]]
        assert "https://d.com" in urls


# ---------------------------------------------------------------------------
# _prune_old_files
# ---------------------------------------------------------------------------


class TestPruneOldFiles:
    def test_deletes_old_files(self, tmp_path: Path):
        import time

        old_file = tmp_path / "old.json"
        old_file.write_text("{}")
        # Backdate mtime by 10 days
        old_mtime = time.time() - 10 * 86400
        import os

        os.utime(old_file, (old_mtime, old_mtime))

        _prune_old_files(tmp_path, retention_days=7)
        assert not old_file.exists()

    def test_keeps_recent_files(self, tmp_path: Path):
        recent_file = tmp_path / "recent.json"
        recent_file.write_text("{}")

        _prune_old_files(tmp_path, retention_days=7)
        assert recent_file.exists()

    def test_does_nothing_when_dir_missing(self, tmp_path: Path):
        # Should not raise
        _prune_old_files(tmp_path / "nonexistent", retention_days=7)


# ---------------------------------------------------------------------------
# main (CLI)
# ---------------------------------------------------------------------------


class TestMain:
    def test_returns_1_when_adj_dir_not_set(self, monkeypatch):
        monkeypatch.delenv("ADJ_DIR", raising=False)
        rc = main([])
        assert rc == 1

    def test_returns_0_on_success(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("ADJ_DIR", str(tmp_path))
        with patch("adjutant.news.briefing.run_briefing", return_value="OK:done"):
            rc = main([])
        assert rc == 0

    def test_returns_1_on_error(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("ADJ_DIR", str(tmp_path))
        with patch("adjutant.news.briefing.run_briefing", return_value="ERROR: bad"):
            rc = main([])
        assert rc == 1
