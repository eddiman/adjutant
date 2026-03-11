"""Unit tests for adjutant.capabilities.search.search."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from adjutant.capabilities.search.search import (
    _DEFAULT_COUNT,
    web_search,
    main,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_brave_response(results: list[dict]) -> dict:
    return {"web": {"results": results}}


def _make_result(title="Title", url="https://example.com", description="Desc"):
    return {"title": title, "url": url, "description": description}


def _mock_client(return_value):
    client = MagicMock()
    client.get.return_value = return_value
    return client


# ---------------------------------------------------------------------------
# web_search
# ---------------------------------------------------------------------------


class TestWebSearch:
    def test_returns_error_on_empty_query(self, tmp_path: Path) -> None:
        result = web_search("", adj_dir=tmp_path)
        assert result.startswith("ERROR")
        assert "No query" in result

    def test_returns_error_when_api_key_missing(self, tmp_path: Path) -> None:
        with patch("adjutant.core.env.get_credential", return_value=""):
            result = web_search("python async", adj_dir=tmp_path)
        assert result.startswith("ERROR")
        assert "BRAVE_API_KEY" in result

    def test_returns_formatted_results(self, tmp_path: Path) -> None:
        response = _make_brave_response(
            [
                _make_result("Python Docs", "https://docs.python.org", "Official docs"),
                _make_result("RealPython", "https://realpython.com", "Tutorials"),
            ]
        )
        with (
            patch("adjutant.core.env.get_credential", return_value="test-key"),
            patch("adjutant.core.logging.adj_log"),
            patch(
                "adjutant.lib.http.get_client",
                return_value=_mock_client(response),
            ),
        ):
            result = web_search("python async", adj_dir=tmp_path)

        assert result.startswith("OK:")
        assert "Python Docs" in result
        assert "https://docs.python.org" in result
        assert "Official docs" in result
        assert "[1]" in result
        assert "[2]" in result

    def test_returns_no_results_message(self, tmp_path: Path) -> None:
        response = _make_brave_response([])
        with (
            patch("adjutant.core.env.get_credential", return_value="test-key"),
            patch("adjutant.core.logging.adj_log"),
            patch(
                "adjutant.lib.http.get_client",
                return_value=_mock_client(response),
            ),
        ):
            result = web_search("obscure query xyz123", adj_dir=tmp_path)

        assert result.startswith("OK:")
        assert "No results" in result

    def test_returns_error_on_api_exception(self, tmp_path: Path) -> None:
        client = MagicMock()
        client.get.side_effect = RuntimeError("connection refused")
        with (
            patch("adjutant.core.env.get_credential", return_value="test-key"),
            patch("adjutant.core.logging.adj_log"),
            patch("adjutant.lib.http.get_client", return_value=client),
        ):
            result = web_search("anything", adj_dir=tmp_path)

        assert result.startswith("ERROR")
        assert "connection refused" in result

    def test_clamps_count_to_max(self, tmp_path: Path) -> None:
        captured = {}

        def mock_get(url, params, headers):
            captured["count"] = params["count"]
            return _make_brave_response([])

        client = MagicMock()
        client.get.side_effect = mock_get
        with (
            patch("adjutant.core.env.get_credential", return_value="test-key"),
            patch("adjutant.core.logging.adj_log"),
            patch("adjutant.lib.http.get_client", return_value=client),
        ):
            web_search("query", count=99, adj_dir=tmp_path)

        assert captured["count"] == "10"

    def test_clamps_count_to_min(self, tmp_path: Path) -> None:
        captured = {}

        def mock_get(url, params, headers):
            captured["count"] = params["count"]
            return _make_brave_response([])

        client = MagicMock()
        client.get.side_effect = mock_get
        with (
            patch("adjutant.core.env.get_credential", return_value="test-key"),
            patch("adjutant.core.logging.adj_log"),
            patch("adjutant.lib.http.get_client", return_value=client),
        ):
            web_search("query", count=0, adj_dir=tmp_path)

        assert captured["count"] == "1"

    def test_resolves_env_path_from_adj_dir(self, tmp_path: Path) -> None:
        """env_path should default to adj_dir / '.env'."""
        captured = {}

        def mock_get_credential(key, env_path):
            captured["env_path"] = env_path
            return "fake-key"

        response = _make_brave_response([])
        with (
            patch("adjutant.core.env.get_credential", side_effect=mock_get_credential),
            patch("adjutant.core.logging.adj_log"),
            patch(
                "adjutant.lib.http.get_client",
                return_value=_mock_client(response),
            ),
        ):
            web_search("query", adj_dir=tmp_path)

        assert captured["env_path"] == tmp_path / ".env"

    def test_uses_explicit_env_path(self, tmp_path: Path) -> None:
        custom_env = tmp_path / "custom" / ".env"
        captured = {}

        def mock_get_credential(key, env_path):
            captured["env_path"] = env_path
            return "fake-key"

        response = _make_brave_response([])
        with (
            patch("adjutant.core.env.get_credential", side_effect=mock_get_credential),
            patch("adjutant.core.logging.adj_log"),
            patch(
                "adjutant.lib.http.get_client",
                return_value=_mock_client(response),
            ),
        ):
            web_search("query", env_path=custom_env)

        assert captured["env_path"] == custom_env

    def test_handles_missing_description(self, tmp_path: Path) -> None:
        response = _make_brave_response(
            [{"title": "No Desc", "url": "https://example.com", "description": None}]
        )
        with (
            patch("adjutant.core.env.get_credential", return_value="test-key"),
            patch("adjutant.core.logging.adj_log"),
            patch(
                "adjutant.lib.http.get_client",
                return_value=_mock_client(response),
            ),
        ):
            result = web_search("query", adj_dir=tmp_path)

        assert "No description" in result

    def test_includes_result_count_in_header(self, tmp_path: Path) -> None:
        response = _make_brave_response([_make_result(f"Result {i}") for i in range(3)])
        with (
            patch("adjutant.core.env.get_credential", return_value="test-key"),
            patch("adjutant.core.logging.adj_log"),
            patch(
                "adjutant.lib.http.get_client",
                return_value=_mock_client(response),
            ),
        ):
            result = web_search("python", adj_dir=tmp_path)

        assert "3 results" in result


# ---------------------------------------------------------------------------
# main (CLI)
# ---------------------------------------------------------------------------


class TestMain:
    def test_returns_1_on_no_args(self) -> None:
        rc = main([])
        assert rc == 1

    def test_returns_1_on_invalid_count(self) -> None:
        rc = main(["query", "not-a-number"])
        assert rc == 1

    def test_returns_0_on_success(self, tmp_path: Path) -> None:
        with (
            patch.dict(os.environ, {"ADJ_DIR": str(tmp_path)}),
            patch(
                "adjutant.capabilities.search.search.web_search",
                return_value="OK:results",
            ),
        ):
            rc = main(["python async"])
        assert rc == 0

    def test_returns_1_on_error(self, tmp_path: Path) -> None:
        with (
            patch.dict(os.environ, {"ADJ_DIR": str(tmp_path)}),
            patch(
                "adjutant.capabilities.search.search.web_search",
                return_value="ERROR: bad key",
            ),
        ):
            rc = main(["python async"])
        assert rc == 1

    def test_passes_count_arg(self, tmp_path: Path) -> None:
        captured = {}

        def mock_search(query, count=_DEFAULT_COUNT, adj_dir=None):
            captured["count"] = count
            return "OK:results"

        with (
            patch.dict(os.environ, {"ADJ_DIR": str(tmp_path)}),
            patch(
                "adjutant.capabilities.search.search.web_search",
                side_effect=mock_search,
            ),
        ):
            main(["python async", "7"])

        assert captured["count"] == 7
