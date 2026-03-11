"""Tests for adjutant.lib.http — unified HTTP client."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from adjutant.lib.http import HttpClient, HttpClientError, get_client, reset_client


class TestHttpClient:
    """Tests for HttpClient.get() and .post()."""

    def test_get_returns_parsed_json(self) -> None:
        with patch.object(httpx.Client, "get") as mock_get:
            mock_response = MagicMock()
            mock_response.json.return_value = {"ok": True}
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response

            client = HttpClient()
            result = client.get("https://example.com/api")
            assert result == {"ok": True}

    def test_get_with_params(self) -> None:
        with patch.object(httpx.Client, "get") as mock_get:
            mock_response = MagicMock()
            mock_response.json.return_value = {"result": []}
            mock_response.raise_for_status.return_value = None
            mock_get.return_value = mock_response

            client = HttpClient()
            result = client.get(
                "https://example.com/api",
                params={"key": "value"},
                headers={"Authorization": "Bearer token"},
            )
            assert result == {"result": []}
            mock_get.assert_called_once_with(
                "https://example.com/api",
                params={"key": "value"},
                headers={"Authorization": "Bearer token"},
            )

    def test_post_with_json(self) -> None:
        with patch.object(httpx.Client, "post") as mock_post:
            mock_response = MagicMock()
            mock_response.json.return_value = {"id": 123}
            mock_response.raise_for_status.return_value = None
            mock_post.return_value = mock_response

            client = HttpClient()
            result = client.post("https://example.com/api", json_data={"name": "test"})
            assert result == {"id": 123}

    def test_post_with_form_data(self) -> None:
        with patch.object(httpx.Client, "post") as mock_post:
            mock_response = MagicMock()
            mock_response.json.return_value = {"ok": True}
            mock_response.raise_for_status.return_value = None
            mock_post.return_value = mock_response

            client = HttpClient()
            result = client.post("https://example.com/api", data={"field": "value"})
            assert result == {"ok": True}

    def test_http_error_raises_client_error(self) -> None:
        with patch.object(httpx.Client, "get") as mock_get:
            mock_response = MagicMock()
            mock_response.status_code = 404
            mock_response.text = "Not Found"
            mock_get.return_value = mock_response
            mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                "404", request=MagicMock(), response=mock_response
            )

            client = HttpClient()
            with pytest.raises(HttpClientError) as exc_info:
                client.get("https://example.com/api")
            assert exc_info.value.status_code == 404

    def test_request_error_raises_client_error(self) -> None:
        with patch.object(httpx.Client, "get") as mock_get:
            mock_get.side_effect = httpx.ConnectError("Connection refused")

            client = HttpClient()
            with pytest.raises(HttpClientError) as exc_info:
                client.get("https://example.com/api")
            assert exc_info.value.status_code is None

    def test_context_manager(self) -> None:
        with HttpClient() as client:
            assert isinstance(client, HttpClient)


class TestSingleton:
    """Tests for get_client() / reset_client() singleton pattern."""

    def test_returns_same_instance(self) -> None:
        reset_client()
        c1 = get_client()
        c2 = get_client()
        assert c1 is c2

    def test_reset_creates_new_instance(self) -> None:
        reset_client()
        c1 = get_client()
        reset_client()
        c2 = get_client()
        assert c1 is not c2

    def teardown_method(self, _method) -> None:
        reset_client()


class TestHttpClientError:
    """Tests for HttpClientError."""

    def test_message_only(self) -> None:
        err = HttpClientError("Something went wrong")
        assert str(err) == "Something went wrong"
        assert err.status_code is None

    def test_with_status_code(self) -> None:
        err = HttpClientError("Not found", status_code=404)
        assert str(err) == "Not found"
        assert err.status_code == 404
