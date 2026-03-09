"""Daily agentic AI news briefing orchestrator.

Replaces: scripts/news/briefing.sh

Orchestrates the full news pipeline:
  1. Check operational state (killed flag)
  2. Fetch news  (fetch.py)
  3. Analyze news (analyze.py)
  4. Format markdown briefing
  5. Write to journal (optional)
  6. Send Telegram notification (optional)
  7. Update dedup cache
  8. Clean up old files

Output format:
  OK:<message> on success
  ERROR:<reason> on failure
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_briefing(adj_dir: Path | None = None) -> str:
    """Run the full news briefing pipeline.

    Returns ``OK:<message>`` on success, ``ERROR:<reason>`` on failure.
    """
    import os

    if adj_dir is None:
        adj_dir = Path(os.environ.get("ADJ_DIR", ""))

    from adjutant.core.lockfiles import check_operational
    from adjutant.core.logging import adj_log
    from adjutant.news.fetch import fetch_news
    from adjutant.news.analyze import analyze_news

    today_display = datetime.now().strftime("%d.%m.%Y")
    today_file = datetime.now().strftime("%Y-%m-%d")

    adj_log("news", f"===== Agentic AI News Briefing: {today_display} =====")

    # ── Step 1: operational check ──────────────────────────────────────────
    if not check_operational(adj_dir):
        return "ERROR:adjutant is not operational (paused or killed)"

    # ── Step 2: fetch ──────────────────────────────────────────────────────
    adj_log("news", "Fetching news...")
    fetch_result = fetch_news(adj_dir)
    if not fetch_result.startswith("OK:"):
        return f"ERROR:fetch failed: {fetch_result}"

    # ── Step 3: analyze ────────────────────────────────────────────────────
    adj_log("news", "Analyzing news...")
    analyze_result = analyze_news(adj_dir)
    if not analyze_result.startswith("OK:"):
        return f"ERROR:analyze failed: {analyze_result}"

    state_dir = adj_dir / "state"
    analyzed_file = state_dir / "news_analyzed" / f"{today_file}.json"

    if not analyzed_file.exists():
        adj_log("news", "No analysis results found")
        return "OK:no analysis results"

    try:
        items: list[dict] = json.loads(analyzed_file.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        return f"ERROR:Failed to read analyzed file: {exc}"

    if not items:
        adj_log("news", "No interesting news today")
        return "OK:no interesting news today"

    adj_log("news", f"Found {len(items)} items to deliver")

    # ── Step 4: format markdown briefing ──────────────────────────────────
    adj_log("news", "Formatting briefing...")
    lines = [f"🤖 Agentic AI News — {today_display}", ""]
    for item in items:
        rank = item.get("rank", "?")
        title = item.get("title", "")
        url = item.get("url", "")
        summary = item.get("summary", "")
        lines.append(f"{rank}. {title}")
        lines.append(f"   → {url}")
        lines.append(f"   {summary}")
        lines.append("")
    briefing = "\n".join(lines)

    # ── Step 5: write to journal (optional) ───────────────────────────────
    config_path = adj_dir / "news_config.json"
    config: dict = {}
    if config_path.exists():
        try:
            config = json.loads(config_path.read_text())
        except (json.JSONDecodeError, OSError):
            pass

    if config.get("delivery", {}).get("journal", False):
        adj_log("news", "Writing to journal...")
        journal_dir = adj_dir / "journal" / "news"
        journal_dir.mkdir(parents=True, exist_ok=True)
        (journal_dir / f"{today_file}.md").write_text(briefing)

    # ── Step 6: send Telegram (optional) ──────────────────────────────────
    if config.get("delivery", {}).get("telegram", False):
        adj_log("news", "Sending Telegram notification...")
        from adjutant.messaging.telegram.notify import send_notify

        send_notify(briefing, adj_dir=adj_dir)

    # ── Step 7: update dedup cache ─────────────────────────────────────────
    adj_log("news", "Updating dedup cache...")
    dedup_file = state_dir / "news_seen_urls.json"
    if not dedup_file.exists():
        dedup_file.write_text('{"urls":[]}')

    try:
        cache_data: dict = json.loads(dedup_file.read_text())
    except (json.JSONDecodeError, OSError):
        cache_data = {"urls": []}

    # Find raw items whose titles match the analyzed items
    raw_file = state_dir / "news_raw" / f"{today_file}.json"
    analyzed_titles = {item.get("title", "") for item in items}
    now_iso = datetime.now(timezone.utc).isoformat()

    new_entries: list[dict] = []
    if raw_file.exists():
        try:
            raw_items: list[dict] = json.loads(raw_file.read_text())
            for raw_item in raw_items:
                if raw_item.get("title", "") in analyzed_titles:
                    new_entries.append({"url": raw_item.get("url", ""), "first_seen": now_iso})
        except (json.JSONDecodeError, OSError):
            pass

    cache_data["urls"] = cache_data.get("urls", []) + new_entries

    # Prune entries outside window
    window_days = int(config.get("deduplication", {}).get("window_days", 30))
    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)

    def _parse_iso(ts: str) -> datetime | None:
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            return None

    cache_data["urls"] = [
        entry
        for entry in cache_data["urls"]
        if (_dt := _parse_iso(entry.get("first_seen", ""))) and _dt > cutoff
    ]

    dedup_file.write_text(json.dumps(cache_data, indent=2))
    adj_log("news", f"Dedup cache updated: {len(cache_data['urls'])} URLs tracked")

    # ── Step 8: clean up old files ─────────────────────────────────────────
    adj_log("news", "Cleaning up old files...")
    cleanup = config.get("cleanup", {})
    raw_retention = int(cleanup.get("raw_retention_days", 7))
    analyzed_retention = int(cleanup.get("analyzed_retention_days", 7))

    _prune_old_files(state_dir / "news_raw", raw_retention)
    _prune_old_files(state_dir / "news_analyzed", analyzed_retention)

    adj_log("news", "Briefing complete!")
    return "OK:briefing complete"


def _prune_old_files(directory: Path, retention_days: int) -> None:
    """Delete .json files in *directory* older than *retention_days* days."""
    if not directory.exists():
        return
    cutoff = datetime.now().timestamp() - retention_days * 86400
    for f in directory.glob("*.json"):
        try:
            if f.stat().st_mtime < cutoff:
                f.unlink()
        except OSError:
            pass


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    import os

    adj_dir_str = os.environ.get("ADJ_DIR", "")
    if not adj_dir_str:
        print("ERROR: ADJ_DIR not set", file=sys.stderr)
        return 1

    result = run_briefing(Path(adj_dir_str))
    print(result)
    return 0 if result.startswith("OK:") else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
