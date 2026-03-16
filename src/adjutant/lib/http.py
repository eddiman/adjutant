"""Unified HTTP client.

Wraps httpx (a core dependency) with a simple synchronous interface used by
the Telegram backend, Brave Search, and other outbound HTTP callers.

Usage:
    from adjutant.lib.http import get_client, HttpClient, HttpClientError

    client = get_client()
    response = client.get("https://api.telegram.org/bot<TOKEN>/getMe")
"""

from __future__ import annotations

from typing import Any

import httpx


class HttpClientError(Exception):
    """Raised when an HTTP request fails."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class HttpClient:
    """Synchronous HTTP client with connection pooling.

    Uses httpx under the hood.
    """

    def __init__(self, timeout: float = 30.0) -> None:
        self._timeout = timeout
        self._client = httpx.Client(timeout=timeout)

    def get(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Make a GET request and return parsed JSON.

        Raises:
            HttpClientError: on any HTTP or network error.
        """
        try:
            response = self._client.get(url, params=params, headers=headers)
            response.raise_for_status()
            try:
                result: dict[str, Any] = response.json()
            except ValueError as e:
                raise HttpClientError(
                    f"Invalid JSON in response from {url}: {response.text[:200]}"
                ) from e
            return result
        except httpx.HTTPStatusError as e:
            raise HttpClientError(
                f"HTTP {e.response.status_code}: {e.response.text[:200]}",
                status_code=e.response.status_code,
            ) from e
        except httpx.RequestError as e:
            raise HttpClientError(f"Request error: {e}") from e

    def get_text(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> str:
        """Make a GET request and return raw response text (for RSS/HTML feeds).

        Raises:
            HttpClientError: on any HTTP or network error.
        """
        try:
            response = self._client.get(url, params=params, headers=headers)
            response.raise_for_status()
            return response.text
        except httpx.HTTPStatusError as e:
            raise HttpClientError(
                f"HTTP {e.response.status_code}: {e.response.text[:200]}",
                status_code=e.response.status_code,
            ) from e
        except httpx.RequestError as e:
            raise HttpClientError(f"Request error: {e}") from e

    def post(
        self,
        url: str,
        json_data: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Make a POST request and return parsed JSON.

        Args:
            json_data: Body encoded as JSON (Content-Type: application/json).
            data: Body encoded as form data (Content-Type: application/x-www-form-urlencoded).

        Raises:
            HttpClientError: on any HTTP or network error.
        """
        try:
            response = self._client.post(url, json=json_data, data=data, headers=headers)
            response.raise_for_status()
            result: dict[str, Any] = response.json()
            return result
        except httpx.HTTPStatusError as e:
            raise HttpClientError(
                f"HTTP {e.response.status_code}: {e.response.text[:200]}",
                status_code=e.response.status_code,
            ) from e
        except httpx.RequestError as e:
            raise HttpClientError(f"Request error: {e}") from e

    def close(self) -> None:
        """Close the underlying connection pool."""
        self._client.close()

    def __enter__(self) -> HttpClient:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()


# ---------------------------------------------------------------------------
# Module-level singleton for connection reuse across requests
# ---------------------------------------------------------------------------

_client: HttpClient | None = None


def get_client() -> HttpClient:
    """Return the shared HttpClient instance (creates it on first call)."""
    global _client
    if _client is None:
        _client = HttpClient()
    return _client


def reset_client() -> None:
    """Close and discard the shared client. Mainly useful in tests."""
    global _client
    if _client is not None:
        _client.close()
        _client = None
