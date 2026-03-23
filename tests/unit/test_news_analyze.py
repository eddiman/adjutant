"""Unit tests for adjutant.news.analyze."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from adjutant.core.backend import LLMResult
from adjutant.news.analyze import analyze_news, main


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config() -> dict:
    return {
        "keywords": ["agentic", "LLM"],
        "analysis": {
            "prefilter_limit": 10,
            "top_n": 3,
            "model": "anthropic/claude-haiku-4-5",
        },
    }


def _write_config(adj_dir: Path, config: dict | None = None) -> None:
    (adj_dir / "news_config.json").write_text(json.dumps(config or _make_config()))


def _write_raw(adj_dir: Path, items: list[dict]) -> Path:
    from datetime import datetime

    today = datetime.now().strftime("%Y-%m-%d")
    raw_dir = adj_dir / "state" / "news_raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_file = raw_dir / f"{today}.json"
    raw_file.write_text(json.dumps(items))
    return raw_file


def _make_raw_items(n: int = 3) -> list[dict]:
    return [
        {
            "title": f"Agentic AI story {i}",
            "url": f"https://example.com/{i}",
            "score": 10 * i,
            "source": "hackernews",
            "timestamp": "2026-01-01T00:00:00Z",
        }
        for i in range(n)
    ]


def _llm_result(text: str = "OK", error_type: str | None = None) -> LLMResult:
    return LLMResult(text=text, error_type=error_type)


def _mock_backend(text: str = "OK") -> MagicMock:
    backend = MagicMock()
    backend.run = AsyncMock(return_value=_llm_result(text=text))
    return backend


# ---------------------------------------------------------------------------
# analyze_news
# ---------------------------------------------------------------------------


class TestAnalyzeNews:
    def test_returns_error_when_killed(self, tmp_path: Path):
        _write_config(tmp_path)
        with patch("adjutant.core.lockfiles.check_killed", return_value=False):
            result = analyze_news(tmp_path)
        assert result.startswith("ERROR")
        assert "killed" in result

    def test_returns_error_when_config_missing(self, tmp_path: Path):
        result = analyze_news(tmp_path)
        assert result.startswith("ERROR")
        assert "news_config.json" in result

    def test_returns_error_when_raw_file_missing(self, tmp_path: Path):
        _write_config(tmp_path)
        with patch("adjutant.core.lockfiles.check_killed", return_value=True):
            result = analyze_news(tmp_path)
        assert result.startswith("ERROR")
        assert "Raw news file" in result

    def test_returns_ok_with_empty_when_all_seen(self, tmp_path: Path):
        _write_config(tmp_path)
        raw_items = _make_raw_items(2)
        _write_raw(tmp_path, raw_items)

        dedup = {
            "urls": [
                {"url": item["url"], "first_seen": "2026-01-01T00:00:00+00:00"}
                for item in raw_items
            ]
        }
        (tmp_path / "state" / "news_seen_urls.json").write_text(json.dumps(dedup))

        with (
            patch("adjutant.core.lockfiles.check_killed", return_value=True),
            patch("adjutant.core.logging.adj_log"),
        ):
            result = analyze_news(tmp_path)

        assert result.startswith("OK:")
        from datetime import datetime

        today = datetime.now().strftime("%Y-%m-%d")
        output = tmp_path / "state" / "news_analyzed" / f"{today}.json"
        assert json.loads(output.read_text()) == []

    def test_returns_ok_on_success(self, tmp_path: Path):
        _write_config(tmp_path)
        _write_raw(tmp_path, _make_raw_items(5))

        llm_json = '[{"rank":1,"title":"Best","url":"https://best.com","summary":"Great"}]'
        backend = _mock_backend(text=llm_json)

        with (
            patch("adjutant.core.lockfiles.check_killed", return_value=True),
            patch("adjutant.core.logging.adj_log"),
            patch("adjutant.core.backend.get_backend", return_value=backend),
        ):
            result = analyze_news(tmp_path)

        assert result.startswith("OK:")
        from datetime import datetime

        today = datetime.now().strftime("%Y-%m-%d")
        output = tmp_path / "state" / "news_analyzed" / f"{today}.json"
        items = json.loads(output.read_text())
        assert len(items) == 1
        assert items[0]["title"] == "Best"

    def test_returns_error_when_llm_returns_no_json(self, tmp_path: Path):
        _write_config(tmp_path)
        _write_raw(tmp_path, _make_raw_items(3))

        backend = _mock_backend(text="no json array here")

        with (
            patch("adjutant.core.lockfiles.check_killed", return_value=True),
            patch("adjutant.core.logging.adj_log"),
            patch("adjutant.core.backend.get_backend", return_value=backend),
        ):
            result = analyze_news(tmp_path)

        assert result.startswith("ERROR")
        assert "JSON" in result

    def test_falls_back_to_top_scored_when_no_keyword_match(self, tmp_path: Path):
        """When no items match keywords, we fall back to top-scored items."""
        config = {
            "keywords": ["zzz_no_match"],
            "analysis": {"prefilter_limit": 10, "top_n": 2, "model": "haiku"},
        }
        _write_config(tmp_path, config)
        _write_raw(tmp_path, _make_raw_items(3))

        llm_json = '[{"rank":1,"title":"Fallback","url":"https://f.com","summary":"ok"}]'
        backend = _mock_backend(text=llm_json)

        with (
            patch("adjutant.core.lockfiles.check_killed", return_value=True),
            patch("adjutant.core.logging.adj_log"),
            patch("adjutant.core.backend.get_backend", return_value=backend),
        ):
            result = analyze_news(tmp_path)

        assert result.startswith("OK:")

    def test_initialises_dedup_file_when_missing(self, tmp_path: Path):
        _write_config(tmp_path)
        _write_raw(tmp_path, _make_raw_items(1))

        llm_json = '[{"rank":1,"title":"T","url":"https://t.com","summary":"s"}]'
        backend = _mock_backend(text=llm_json)

        with (
            patch("adjutant.core.lockfiles.check_killed", return_value=True),
            patch("adjutant.core.logging.adj_log"),
            patch("adjutant.core.backend.get_backend", return_value=backend),
        ):
            analyze_news(tmp_path)

        dedup_file = tmp_path / "state" / "news_seen_urls.json"
        assert dedup_file.exists()

    def test_returns_error_when_llm_call_raises(self, tmp_path: Path):
        _write_config(tmp_path)
        _write_raw(tmp_path, _make_raw_items(2))

        backend = MagicMock()
        backend.run = AsyncMock(side_effect=RuntimeError("backend crashed"))

        with (
            patch("adjutant.core.lockfiles.check_killed", return_value=True),
            patch("adjutant.core.logging.adj_log"),
            patch("adjutant.core.backend.get_backend", return_value=backend),
        ):
            result = analyze_news(tmp_path)

        assert result.startswith("ERROR")
        assert "backend crashed" in result


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
        with patch("adjutant.news.analyze.analyze_news", return_value=f"OK:{tmp_path}"):
            rc = main([])
        assert rc == 0

    def test_returns_1_on_error(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("ADJ_DIR", str(tmp_path))
        with patch("adjutant.news.analyze.analyze_news", return_value="ERROR: bad"):
            rc = main([])
        assert rc == 1
