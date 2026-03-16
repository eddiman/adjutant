"""Analyze and rank raw news items using keyword pre-filter + LLM.

Replaces: scripts/news/analyze.sh

Reads state/news_raw/<date>.json, deduplicates against state/news_seen_urls.json,
pre-filters by keyword match, sends top N items to a configurable model for ranking,
and writes results to state/news_analyzed/<date>.json.

Output format:
  OK:<path> on success
  ERROR:<reason> on failure
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def analyze_news(adj_dir: Path | None = None) -> str:
    """Analyze today's raw news and write ranked results.

    Returns ``OK:<path>`` on success, ``ERROR:<reason>`` on failure.
    """
    import os

    if adj_dir is None:
        adj_dir = Path(os.environ.get("ADJ_DIR", ""))

    from adjutant.core.lockfiles import check_killed
    from adjutant.core.logging import adj_log
    from adjutant.core.opencode import opencode_run
    from adjutant.lib.ndjson import parse_ndjson

    if not check_killed(adj_dir):
        return "ERROR:adjutant is stopped (killed flag set)"

    config_path = adj_dir / "news_config.json"
    if not config_path.exists():
        return f"ERROR:Configuration file not found: {config_path}"

    try:
        with config_path.open() as f:
            config = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        return f"ERROR:Failed to read config: {exc}"

    today = datetime.now().strftime("%Y-%m-%d")
    state_dir = adj_dir / "state"
    raw_file = state_dir / "news_raw" / f"{today}.json"
    analyzed_dir = state_dir / "news_analyzed"
    analyzed_dir.mkdir(parents=True, exist_ok=True)
    output_file = analyzed_dir / f"{today}.json"
    dedup_file = state_dir / "news_seen_urls.json"

    if not raw_file.exists():
        return f"ERROR:Raw news file not found: {raw_file}"

    # Initialise dedup file if missing
    if not dedup_file.exists():
        dedup_file.write_text('{"urls":[]}')

    adj_log("news-analyze", f"Starting news analysis for {today}")

    try:
        raw_items: list[dict[str, Any]] = json.loads(raw_file.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        return f"ERROR:Failed to read raw file: {exc}"

    adj_log("news-analyze", f"Loaded {len(raw_items)} raw items")

    # ── Step 1: Deduplication ──────────────────────────────────────────────
    adj_log("news-analyze", "Deduplicating...")
    try:
        dedup_data = json.loads(dedup_file.read_text())
        seen_urls = {entry["url"] for entry in dedup_data.get("urls", [])}
    except (json.JSONDecodeError, OSError):
        seen_urls = set()

    unseen_items = [item for item in raw_items if item.get("url") not in seen_urls]
    adj_log("news-analyze", f"After dedup: {len(unseen_items)} unseen items")

    if not unseen_items:
        adj_log("news-analyze", "No new items to analyze")
        output_file.write_text("[]")
        return f"OK:{output_file}"

    # ── Step 2: Keyword pre-filter ─────────────────────────────────────────
    adj_log("news-analyze", "Pre-filtering with keywords...")
    keywords = [k.lower() for k in config.get("keywords", [])]
    kw_pattern = re.compile("|".join(re.escape(k) for k in keywords), re.IGNORECASE)

    filtered = [item for item in unseen_items if kw_pattern.search(item.get("title", ""))]

    adj_log("news-analyze", f"After keyword filter: {len(filtered)} items")

    if not filtered:
        adj_log(
            "news-analyze",
            "No items match keywords — falling back to top scored items",
        )
        filtered = sorted(unseen_items, key=lambda x: -(x.get("score") or 0))

    prefilter_limit = int(config.get("analysis", {}).get("prefilter_limit", 10))
    top_items = sorted(filtered, key=lambda x: -(x.get("score") or 0))[:prefilter_limit]
    adj_log("news-analyze", f"Sending top {len(top_items)} items to LLM...")

    # ── Step 3: LLM analysis ───────────────────────────────────────────────
    items_text = "\n".join(
        f"{i + 1}. {item.get('title', '')} — {item.get('url', '')} "
        f"— [score: {item.get('score', 0)}, source: {item.get('source', '')}]"
        for i, item in enumerate(top_items)
    )

    top_n = int(config.get("analysis", {}).get("top_n", 5))
    model = config.get("analysis", {}).get("model", "anthropic/claude-haiku-4-5")

    prompt = (
        f"You are analyzing agentic AI news. Here are {len(top_items)} candidate items:\n\n"
        f"{items_text}\n\n"
        f"Pick the top {top_n} most interesting/novel items. Prioritize: new models, "
        "frameworks, research papers, implementations, significant benchmarks.\n\n"
        "Return ONLY a JSON array (no other text):\n"
        '[\n  {"rank": 1, "title": "...", "url": "...", '
        '"summary": "One sentence why it matters"}\n]'
    )

    adj_log("news-analyze", f"Calling {model}...")

    try:
        result = asyncio.run(opencode_run(["run", prompt, "--model", model, "--format", "json"]))
    except Exception as exc:
        return f"ERROR:LLM call failed: {exc}"

    ndjson_result = parse_ndjson(result.stdout or "")

    # Extract JSON array from the response text
    raw_text = ndjson_result.text or ""
    match = re.search(r"\[.*\]", raw_text, re.DOTALL)
    if not match:
        return f"ERROR:LLM did not return valid JSON array. Response: {raw_text[:200]}"

    try:
        analyzed: list[dict[str, Any]] = json.loads(match.group())
    except json.JSONDecodeError as exc:
        return f"ERROR:Failed to parse LLM JSON: {exc}"

    output_file.write_text(json.dumps(analyzed, indent=2))
    adj_log(
        "news-analyze",
        f"Analysis complete: {len(analyzed)} items selected → {output_file}",
    )
    return f"OK:{output_file}"


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    import os

    adj_dir_str = os.environ.get("ADJ_DIR", "")
    if not adj_dir_str:
        print("ERROR: ADJ_DIR not set", file=sys.stderr)
        return 1

    result = analyze_news(Path(adj_dir_str))
    print(result)
    return 0 if result.startswith("OK:") else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
