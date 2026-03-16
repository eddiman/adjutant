"""Fetch agentic AI news from configured sources.

Replaces: scripts/news/fetch.sh

Reads news_config.json to determine which sources are enabled, then fetches
from Hacker News Algolia API, Reddit JSON API, and RSS/HTML blog feeds.
Writes raw results as a JSON array to state/news_raw/<YYYY-MM-DD>.json.

Output format (stdout/return):
  OK:<path> on success
  ERROR:<reason> on failure
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

NewsItem = dict[str, Any]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _load_config(config_path: Path) -> dict[str, Any]:
    with config_path.open() as f:
        result: dict[str, Any] = json.load(f)
        return result


def _epoch_lookback(hours: int) -> int:
    """Return a Unix timestamp `hours` ago from now."""
    return int((datetime.now(UTC) - timedelta(hours=hours)).timestamp())


def _fetch_hackernews(config: dict[str, Any], http_get: Any) -> list[NewsItem]:
    hn_cfg = config.get("sources", {}).get("hackernews", {})
    if not hn_cfg.get("enabled", False):
        return []

    max_items = int(hn_cfg.get("max_items", 20))
    lookback_hours = int(hn_cfg.get("lookback_hours", 24))
    keywords = config.get("keywords", [])
    query = " OR ".join(keywords)

    timestamp = _epoch_lookback(lookback_hours)
    url = (
        f"https://hn.algolia.com/api/v1/search"
        f"?query={query}&tags=story"
        f"&numericFilters=created_at_i>{timestamp}"
        f"&hitsPerPage={max_items}"
    )

    data = http_get(url)
    hits = data.get("hits", []) if isinstance(data, dict) else []

    items: list[NewsItem] = []
    for hit in hits:
        obj_id = str(hit.get("objectID", ""))
        fallback_url = f"https://news.ycombinator.com/item?id={obj_id}"
        items.append(
            {
                "title": hit.get("title", ""),
                "url": hit.get("url") or fallback_url,
                "score": hit.get("points") or 0,
                "source": "hackernews",
                "timestamp": hit.get("created_at", ""),
            }
        )
    return items


def _fetch_reddit(config: dict[str, Any], http_get: Any) -> list[NewsItem]:
    reddit_cfg = config.get("sources", {}).get("reddit", {})
    if not reddit_cfg.get("enabled", False):
        return []

    subreddits = reddit_cfg.get("subreddits", [])
    max_items = int(reddit_cfg.get("max_items", 20))
    keywords = config.get("keywords", [])
    query = "+OR+".join(k.replace(" ", "+") for k in keywords)

    items: list[NewsItem] = []
    for subreddit in subreddits:
        url = (
            f"https://www.reddit.com/r/{subreddit}/search.json"
            f"?q={query}&restrict_sr=1&sort=new&t=day&limit={max_items}"
        )
        try:
            data = http_get(url, headers={"User-Agent": "Adjutant/1.0"})
        except Exception:  # noqa: BLE001 — skip single source on fetch error
            continue

        children = data.get("data", {}).get("children", []) if isinstance(data, dict) else []
        for child in children:
            post = child.get("data", {})
            items.append(
                {
                    "title": post.get("title", ""),
                    "url": post.get("url", ""),
                    "score": post.get("ups") or 0,
                    "source": "reddit",
                    "timestamp": datetime.fromtimestamp(
                        post.get("created_utc", 0), tz=UTC
                    ).isoformat(),
                }
            )
    return items


def _parse_rss(xml_text: str, name: str) -> list[NewsItem]:
    """Parse RSS 2.0 or Atom feed, return list of NewsItems."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    items: list[NewsItem] = []

    # RSS 2.0
    for item in root.findall("./channel/item")[:10]:
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub = (item.findtext("pubDate") or "").strip()
        if title and link:
            items.append(
                {
                    "title": title,
                    "url": link,
                    "score": 0,
                    "source": f"rss:{name}",
                    "timestamp": pub,
                }
            )

    # Atom
    for entry in root.findall("atom:entry", ns)[:10]:
        title = (entry.findtext("atom:title", "", ns) or "").strip()
        link_el = entry.find("atom:link", ns)
        link = ((link_el.get("href", "") if link_el is not None else "") or "").strip()
        pub = (
            entry.findtext("atom:published", "", ns) or entry.findtext("atom:updated", "", ns) or ""
        ).strip()
        if title and link:
            items.append(
                {
                    "title": title,
                    "url": link,
                    "score": 0,
                    "source": f"rss:{name}",
                    "timestamp": pub,
                }
            )
    return items


def _fetch_blogs(config: dict[str, Any], http_get: Any) -> list[NewsItem]:
    blog_cfg = config.get("sources", {}).get("blogs", {})
    if not blog_cfg.get("enabled", False):
        return []

    feeds = blog_cfg.get("feeds", [])
    items: list[NewsItem] = []
    now_iso = datetime.now(UTC).isoformat()

    for feed in feeds:
        name = feed.get("name", "unknown")
        url = feed.get("url", "")
        feed_type = feed.get("type", "rss")

        try:
            content = http_get(url, raw=True)
        except Exception:  # noqa: BLE001 — skip single feed on fetch error
            continue

        if feed_type == "rss":
            items.extend(
                _parse_rss(
                    content
                    if isinstance(content, str)
                    else content.decode("utf-8", errors="replace"),
                    name,
                )
            )
        elif feed_type == "html":
            # Basic HTML scraping: look for <a> with news/blog/article in href
            import re

            pattern = re.compile(r'<a[^>]+href="([^"]+)"[^>]*>([^<]+)</a>', re.IGNORECASE)
            found = False
            for m in pattern.finditer(
                content if isinstance(content, str) else content.decode("utf-8", errors="replace")
            ):
                href, title = m.group(1), m.group(2).strip()
                if any(kw in href.lower() for kw in ("news", "blog", "post", "article")):
                    if not href.startswith("http"):
                        # Make absolute
                        from urllib.parse import urljoin

                        href = urljoin(url, href)
                    items.append(
                        {
                            "title": title,
                            "url": href,
                            "score": 0,
                            "source": f"blog:{name}",
                            "timestamp": now_iso,
                        }
                    )
                    found = True
            if not found:
                items.append(
                    {
                        "title": f"{name} News",
                        "url": url,
                        "score": 0,
                        "source": f"blog:{name}",
                        "timestamp": now_iso,
                    }
                )

    return items


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def fetch_news(adj_dir: Path | None = None) -> str:
    """Fetch news from all enabled sources and write to state/news_raw/<date>.json.

    Returns ``OK:<path>`` on success, ``ERROR:<reason>`` on failure.
    """
    if adj_dir is None:
        import os

        adj_dir = Path(os.environ.get("ADJ_DIR", ""))

    from adjutant.core.lockfiles import check_killed
    from adjutant.core.logging import adj_log

    if not check_killed(adj_dir):
        return "ERROR:adjutant is stopped (killed flag set)"

    config_path = adj_dir / "news_config.json"
    if not config_path.exists():
        return f"ERROR:Configuration file not found: {config_path}"

    try:
        config = _load_config(config_path)
    except (json.JSONDecodeError, OSError) as exc:
        return f"ERROR:Failed to read config: {exc}"

    today = datetime.now().strftime("%Y-%m-%d")
    raw_dir = adj_dir / "state" / "news_raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    output_path = raw_dir / f"{today}.json"

    adj_log("news-fetch", f"Starting news fetch for {today}")

    from adjutant.lib.http import get_client

    client = get_client()

    def _http_get(url: str, headers: dict[str, str] | None = None, raw: bool = False) -> Any:
        if raw:
            return client.get_text(url, headers=headers or {})
        return client.get(url, headers=headers or {})

    try:
        hn_items = _fetch_hackernews(config, _http_get)
    except Exception as exc:
        adj_log("news-fetch", f"Hacker News fetch failed: {exc}")
        hn_items = []

    try:
        reddit_items = _fetch_reddit(config, _http_get)
    except Exception as exc:
        adj_log("news-fetch", f"Reddit fetch failed: {exc}")
        reddit_items = []

    try:
        blog_items = _fetch_blogs(config, _http_get)
    except Exception as exc:
        adj_log("news-fetch", f"Blog fetch failed: {exc}")
        blog_items = []

    all_items = hn_items + reddit_items + blog_items

    output_path.write_text(json.dumps(all_items, indent=2))
    adj_log("news-fetch", f"Fetched {len(all_items)} total items → {output_path}")

    return f"OK:{output_path}"


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    import os

    adj_dir_str = os.environ.get("ADJ_DIR", "")
    if not adj_dir_str:
        print("ERROR: ADJ_DIR not set", file=sys.stderr)
        return 1

    result = fetch_news(Path(adj_dir_str))
    print(result)
    return 0 if result.startswith("OK:") else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
