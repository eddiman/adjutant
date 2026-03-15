"""Unit tests for adjutant.news.fetch."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from adjutant.news.fetch import (
    fetch_news,
    main,
    _fetch_hackernews,
    _fetch_reddit,
    _fetch_blogs,
    _parse_rss,
    _epoch_lookback,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_adj_dir(tmp_path: Path) -> Path:
    """Create a minimal adj_dir with a news_config.json."""
    config = {
        "keywords": ["agentic", "LLM"],
        "sources": {
            "hackernews": {"enabled": True, "max_items": 5, "lookback_hours": 24},
            "reddit": {
                "enabled": True,
                "subreddits": ["MachineLearning"],
                "max_items": 5,
            },
            "blogs": {"enabled": False, "feeds": []},
        },
        "analysis": {},
    }
    (tmp_path / "news_config.json").write_text(json.dumps(config))
    (tmp_path / "state").mkdir(exist_ok=True)
    return tmp_path


def _mock_hn_response() -> dict:
    return {
        "hits": [
            {
                "title": "Agentic AI breakthrough",
                "url": "https://example.com/agentic",
                "points": 100,
                "objectID": "12345",
                "created_at": "2026-01-01T10:00:00.000Z",
            }
        ]
    }


# ---------------------------------------------------------------------------
# _epoch_lookback
# ---------------------------------------------------------------------------


class TestEpochLookback:
    def test_returns_int(self):
        ts = _epoch_lookback(24)
        assert isinstance(ts, int)

    def test_is_in_the_past(self):
        now = int(datetime.now(timezone.utc).timestamp())
        ts = _epoch_lookback(1)
        assert ts < now

    def test_24h_is_approximately_right(self):
        now = int(datetime.now(timezone.utc).timestamp())
        ts = _epoch_lookback(24)
        diff = now - ts
        assert 86390 < diff < 86410  # ~86400s = 24h


# ---------------------------------------------------------------------------
# _fetch_hackernews
# ---------------------------------------------------------------------------


class TestFetchHackerNews:
    def test_returns_empty_when_disabled(self):
        config = {"sources": {"hackernews": {"enabled": False}}, "keywords": []}
        items = _fetch_hackernews(config, lambda url, **kw: {})
        assert items == []

    def test_returns_items(self):
        config = {
            "sources": {"hackernews": {"enabled": True, "max_items": 5, "lookback_hours": 24}},
            "keywords": ["agentic"],
        }
        items = _fetch_hackernews(config, lambda url, **kw: _mock_hn_response())
        assert len(items) == 1
        assert items[0]["title"] == "Agentic AI breakthrough"
        assert items[0]["source"] == "hackernews"
        assert items[0]["score"] == 100

    def test_uses_fallback_url_when_missing(self):
        config = {
            "sources": {"hackernews": {"enabled": True, "max_items": 5, "lookback_hours": 24}},
            "keywords": ["ai"],
        }
        response = {
            "hits": [
                {
                    "title": "No URL item",
                    "url": None,
                    "points": 10,
                    "objectID": "99",
                    "created_at": "",
                }
            ]
        }
        items = _fetch_hackernews(config, lambda url, **kw: response)
        assert "news.ycombinator.com" in items[0]["url"]

    def test_handles_empty_hits(self):
        config = {
            "sources": {"hackernews": {"enabled": True, "max_items": 5, "lookback_hours": 24}},
            "keywords": ["ai"],
        }
        items = _fetch_hackernews(config, lambda url, **kw: {"hits": []})
        assert items == []


# ---------------------------------------------------------------------------
# _fetch_reddit
# ---------------------------------------------------------------------------


class TestFetchReddit:
    def test_returns_empty_when_disabled(self):
        config = {"sources": {"reddit": {"enabled": False}}, "keywords": []}
        items = _fetch_reddit(config, lambda url, **kw: {})
        assert items == []

    def test_returns_items(self):
        config = {
            "sources": {"reddit": {"enabled": True, "subreddits": ["ML"], "max_items": 5}},
            "keywords": ["llm"],
        }
        response = {
            "data": {
                "children": [
                    {
                        "data": {
                            "title": "LLM paper",
                            "url": "https://reddit.com/r/ML/1",
                            "ups": 50,
                            "created_utc": 1700000000,
                        }
                    }
                ]
            }
        }
        items = _fetch_reddit(config, lambda url, **kw: response)
        assert len(items) == 1
        assert items[0]["title"] == "LLM paper"
        assert items[0]["source"] == "reddit"

    def test_skips_subreddit_on_exception(self):
        config = {
            "sources": {"reddit": {"enabled": True, "subreddits": ["ML"], "max_items": 5}},
            "keywords": ["llm"],
        }

        def raise_error(url, **kw):
            raise RuntimeError("connection refused")

        items = _fetch_reddit(config, raise_error)
        assert items == []


# ---------------------------------------------------------------------------
# _parse_rss
# ---------------------------------------------------------------------------


class TestParseRss:
    def test_parses_rss2(self):
        xml = """<?xml version="1.0"?>
<rss version="2.0">
  <channel>
    <item>
      <title>RSS Item 1</title>
      <link>https://example.com/1</link>
      <pubDate>Mon, 01 Jan 2024 00:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>"""
        items = _parse_rss(xml, "testblog")
        assert len(items) == 1
        assert items[0]["title"] == "RSS Item 1"
        assert items[0]["url"] == "https://example.com/1"
        assert items[0]["source"] == "rss:testblog"

    def test_parses_atom(self):
        xml = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>Atom Entry 1</title>
    <link href="https://atom.example.com/1"/>
    <published>2024-01-01T00:00:00Z</published>
  </entry>
</feed>"""
        items = _parse_rss(xml, "atomblog")
        assert len(items) == 1
        assert items[0]["title"] == "Atom Entry 1"
        assert items[0]["source"] == "rss:atomblog"

    def test_returns_empty_on_invalid_xml(self):
        items = _parse_rss("this is not xml", "blog")
        assert items == []

    def test_limits_to_10_items(self):
        items_xml = "".join(
            f"<item><title>Item {i}</title><link>https://example.com/{i}</link></item>"
            for i in range(15)
        )
        xml = f"<?xml version='1.0'?><rss><channel>{items_xml}</channel></rss>"
        items = _parse_rss(xml, "blog")
        assert len(items) == 10


# ---------------------------------------------------------------------------
# fetch_news (integration-style, mocked HTTP)
# ---------------------------------------------------------------------------


class TestFetchNews:
    def test_returns_error_when_adj_dir_not_set(self, tmp_path: Path):
        with patch("os.environ.get", return_value=""):
            # No config file in empty path → returns error
            result = fetch_news(tmp_path)
        assert result.startswith("ERROR")

    def test_returns_error_when_config_missing(self, tmp_path: Path):
        result = fetch_news(tmp_path)
        assert result.startswith("ERROR")
        assert "news_config.json" in result

    def test_returns_error_when_killed(self, tmp_path: Path):
        _make_adj_dir(tmp_path)
        with patch("adjutant.core.lockfiles.check_killed", return_value=False):
            result = fetch_news(tmp_path)
        assert result.startswith("ERROR")
        assert "killed" in result

    def test_writes_output_file_on_success(self, tmp_path: Path):
        _make_adj_dir(tmp_path)
        mock_client = MagicMock()
        mock_client.get.side_effect = [
            _mock_hn_response(),  # HN call
            {"data": {"children": []}},  # Reddit call
        ]
        with (
            patch("adjutant.core.lockfiles.check_killed", return_value=True),
            patch("adjutant.core.logging.adj_log"),
            patch("adjutant.lib.http.get_client", return_value=mock_client),
        ):
            result = fetch_news(tmp_path)

        assert result.startswith("OK:")
        output_path = Path(result[3:])
        assert output_path.exists()
        items = json.loads(output_path.read_text())
        assert isinstance(items, list)

    def test_returns_ok_with_zero_items_when_all_fail(self, tmp_path: Path):
        _make_adj_dir(tmp_path)
        mock_client = MagicMock()
        mock_client.get.side_effect = RuntimeError("network error")
        with (
            patch("adjutant.core.lockfiles.check_killed", return_value=True),
            patch("adjutant.core.logging.adj_log"),
            patch("adjutant.lib.http.get_client", return_value=mock_client),
        ):
            result = fetch_news(tmp_path)

        # Should still succeed — just with empty list
        assert result.startswith("OK:")
        items = json.loads(Path(result[3:]).read_text())
        assert items == []

    def test_blog_raw_fetch_uses_get_text(self, tmp_path: Path):
        """RSS/blog feeds must use get_text(), not get()."""
        rss_xml = """<?xml version="1.0"?>
<rss version="2.0"><channel>
  <item><title>AI News</title><link>https://blog.example.com/ai</link></item>
</channel></rss>"""
        config = {
            "keywords": ["AI"],
            "sources": {
                "hackernews": {"enabled": False},
                "reddit": {"enabled": False},
                "blogs": {
                    "enabled": True,
                    "feeds": [
                        {"name": "TestBlog", "url": "https://blog.example.com/feed", "type": "rss"}
                    ],
                },
            },
            "analysis": {},
        }
        (tmp_path / "news_config.json").write_text(json.dumps(config))
        (tmp_path / "state").mkdir(exist_ok=True)

        mock_client = MagicMock()
        mock_client.get_text.return_value = rss_xml

        with (
            patch("adjutant.core.lockfiles.check_killed", return_value=True),
            patch("adjutant.core.logging.adj_log"),
            patch("adjutant.lib.http.get_client", return_value=mock_client),
        ):
            result = fetch_news(tmp_path)

        assert result.startswith("OK:")
        mock_client.get_text.assert_called_once()
        mock_client.get.assert_not_called()
        items = json.loads(Path(result[3:]).read_text())
        assert any(i["title"] == "AI News" for i in items)


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
        with patch(
            "adjutant.news.fetch.fetch_news",
            return_value=f"OK:{tmp_path}/result.json",
        ):
            rc = main([])
        assert rc == 0

    def test_returns_1_on_error(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("ADJ_DIR", str(tmp_path))
        with patch("adjutant.news.fetch.fetch_news", return_value="ERROR: bad"):
            rc = main([])
        assert rc == 1
