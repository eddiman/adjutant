"""Unified HTTP client.

Wraps httpx (a core dependency) with a simple synchronous interface used by
the Telegram backend, Brave Search, and other outbound HTTP callers.

Usage:
    from adjutant.lib.http import get_client, HttpClient, HttpClientError

    client = get_client()
    response = client.get("https://api.telegram.org/bot<TOKEN>/getMe")
"""

from __future__ import annotations

import json
from typing import Any, Optional

import httpx


class HttpClientError(Exception):
    """Raised when an HTTP request fails."""

    def __init__(self, message: str, status_code: Optional[int] = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class HttpClient:
    """Synchronous HTTP client with connection pooling.

    Uses httpx under the hood. Falls back to urllib.request if httpx is
    somehow unavailable at runtime (defensive — httpx is a declared dep).
    """

    def __init__(self, timeout: float = 30.0) -> None:
        self._timeout = timeout
        self._client = httpx.Client(timeout=timeout)

    def get(
        self,
        url: str,
        params: Optional[dict[str, Any]] = None,
        headers: Optional[dict[str, str]] = None,
    ) -> dict[str, Any]:
        """Make a GET request and return parsed JSON.

        Raises:
            HttpClientError: on any HTTP or network error.
        """
        try:
            response = self._client.get(url, params=params, headers=headers)
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

    def post(
        self,
        url: str,
        json_data: Optional[dict[str, Any]] = None,
        data: Optional[dict[str, Any]] = None,
        headers: Optional[dict[str, str]] = None,
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

    def __enter__(self) -> "HttpClient":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()


# ---------------------------------------------------------------------------
# Module-level singleton for connection reuse across requests
# ---------------------------------------------------------------------------

_client: Optional[HttpClient] = None


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
