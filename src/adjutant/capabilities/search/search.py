"""Web search via Brave Search API.

Replaces: scripts/capabilities/search/search.sh

Uses the Brave Search API to return structured web results. Token-efficient:
only title, URL, and description are extracted from the top N results.

Requires: BRAVE_API_KEY in .env

Output format:
  OK:Search results for "<query>" (N results):

  [1] Title
      https://url
      Description

  [2] ...

Error output:
  ERROR:<reason>
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import quote


_BRAVE_API_URL = "https://api.search.brave.com/res/v1/web/search"
_DEFAULT_COUNT = 5
_MAX_COUNT = 10
_MIN_COUNT = 1
_BRAVE_TIMEOUT = 15.0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def web_search(
    query: str,
    count: int = _DEFAULT_COUNT,
    adj_dir: Path | None = None,
    *,
    env_path: Path | None = None,
) -> str:
    """Run a Brave Search query and return formatted results.

    Args:
        query: Search query string.
        count: Number of results to return (clamped to 1–10).
        adj_dir: Adjutant root directory (for .env lookup).
        env_path: Override .env path (for testing).

    Returns:
        "OK:<formatted results>" on success.
        "ERROR:<reason>" on failure.
    """
    from adjutant.core.env import get_credential
    from adjutant.core.logging import adj_log

    if not query:
        return "ERROR: No query provided."

    # Clamp count
    count = max(_MIN_COUNT, min(_MAX_COUNT, int(count)))

    # Resolve env_path
    if env_path is None and adj_dir is not None:
        env_path = adj_dir / ".env"

    # Load API key
    brave_api_key = get_credential("BRAVE_API_KEY", env_path)
    if not brave_api_key:
        return (
            "ERROR: BRAVE_API_KEY not set in .env — get a free key at https://api.search.brave.com"
        )

    adj_log("search", f"Search requested: {query} (count={count})")

    # URL-encode the query
    encoded_query = quote(query)

    # Call Brave Search API
    try:
        from adjutant.lib.http import get_client, HttpClientError

        client = get_client()
        response = client.get(
            _BRAVE_API_URL,
            params={
                "q": encoded_query,
                "count": str(count),
                "safesearch": "moderate",
            },
            headers={
                "Accept": "application/json",
                "X-Subscription-Token": brave_api_key,
            },
        )
    except Exception as e:
        error_str = str(e)
        adj_log("search", f"Brave API error: {error_str}")
        return f"ERROR: Brave Search API request failed — {error_str}"

    # Extract results
    web_results = []
    if isinstance(response, dict):
        web_data = response.get("web", {})
        if isinstance(web_data, dict):
            web_results = web_data.get("results", []) or []

    if not web_results:
        adj_log("search", f"No results for: {query}")
        return f"OK:No results found for: {query}"

    # Format results
    lines = [f'Search results for "{query}" ({len(web_results)} results):', ""]
    for i, item in enumerate(web_results, start=1):
        title = item.get("title", "")
        url = item.get("url", "")
        description = item.get("description") or "No description"
        lines.append(f"[{i}] {title}")
        lines.append(f"    {url}")
        lines.append(f"    {description}")
        lines.append("")

    adj_log("search", f"Search returned {len(web_results)} results for: {query}")
    return "OK:" + "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: search.py <query> [count]"""
    args = argv if argv is not None else sys.argv[1:]

    if not args:
        sys.stderr.write("Usage: search.py <query> [count]\n")
        return 1

    query = args[0]
    count = _DEFAULT_COUNT
    if len(args) > 1:
        try:
            count = int(args[1])
        except ValueError:
            sys.stderr.write(f"ERROR: count must be an integer, got '{args[1]}'\n")
            return 1

    adj_dir_str = os.environ.get("ADJ_DIR", "").strip()
    adj_dir = Path(adj_dir_str) if adj_dir_str else None

    result = web_search(query, count, adj_dir)
    print(result)
    return 0 if result.startswith("OK:") else 1


if __name__ == "__main__":
    sys.exit(main())
