# News Briefings

Adjutant can deliver daily curated news briefings from Hacker News, Reddit, and RSS feeds. The pipeline fetches articles, ranks them with an LLM, and delivers a digest via Telegram and/or journal entry.

## How It Works

The news pipeline has three stages:

1. **Fetch** -- pulls articles from configured sources (HN Algolia API, Reddit JSON API, RSS/HTML feeds) based on keywords
2. **Analyze** -- sends fetched articles to an LLM for relevance ranking and summarization
3. **Deliver** -- formats the top stories as a markdown briefing, sends via Telegram, and writes to the journal

## Running a Briefing

### Manual

```bash
adjutant news
```

### Scheduled

Add a schedule in `adjutant.yaml`:

```yaml
schedules:
  - name: "news_briefing"
    description: "Daily AI news briefing"
    schedule: "0 8 * * 1-5"  # Weekdays at 8am
    script: ".venv/bin/python -m adjutant news"
    enabled: true
```

Then sync the schedule to crontab:

```bash
adjutant schedule sync
```

## Configuration

News settings live in `news_config.json` at the Adjutant root. An example template is provided at `news_config.json.example`.

### Full Schema

```json
{
  "keywords": ["AI agents", "LLM", "transformer"],

  "sources": {
    "hackernews": {
      "enabled": true,
      "max_items": 20,
      "lookback_hours": 24
    },
    "reddit": {
      "enabled": false,
      "subreddits": ["MachineLearning", "LocalLLaMA"],
      "max_items": 20,
      "lookback_hours": 24
    },
    "blogs": {
      "enabled": false,
      "feeds": [
        {"name": "Example Blog", "url": "https://example.com/feed", "type": "rss"}
      ]
    }
  },

  "analysis": {
    "model": "anthropic/claude-haiku-4-5",
    "top_n": 3,
    "prefilter_limit": 20
  },

  "deduplication": {
    "window_days": 30
  },

  "delivery": {
    "telegram": true,
    "journal": true
  },

  "cleanup": {
    "raw_retention_days": 7,
    "analyzed_retention_days": 7
  }
}
```

### Key Settings

| Setting | Description |
|---------|-------------|
| `keywords` | Search terms used across all sources. Combined with OR logic. |
| `sources.hackernews.enabled` | Fetch from Hacker News Algolia API |
| `sources.reddit.subreddits` | Which subreddits to search |
| `sources.blogs.feeds` | RSS/Atom feed URLs to check |
| `analysis.model` | Which LLM to use for ranking (default: Haiku for cost) |
| `analysis.top_n` | Number of top stories to include in the briefing |
| `delivery.telegram` | Send the briefing via Telegram |
| `delivery.journal` | Write the briefing to the journal |
| `deduplication.window_days` | How long to remember seen articles to avoid repeats |

## Output

A typical briefing looks like:

```
Agentic AI News -- 16.03.2026

1. New Architecture for Long-Context Agents
   -> https://example.com/article1
   Novel approach to maintaining context over extended agent sessions...

2. OpenCode 2.0 Released
   -> https://opencode.ai/blog/v2
   Major update to the OpenCode runtime with improved tool calling...

3. Self-Improving Agents: A Survey
   -> https://arxiv.org/abs/2026.12345
   Comprehensive survey of autonomous agent self-improvement techniques...
```

## Intermediate Files

The pipeline stores intermediate results in `state/`:

| Path | Contents |
|------|----------|
| `state/news_raw/YYYY-MM-DD.json` | Raw fetched articles |
| `state/news_analyzed/YYYY-MM-DD.json` | LLM-ranked results |
| `state/news_dedup.json` | Deduplication cache (seen URLs) |

Old files are cleaned up automatically based on `cleanup.*_retention_days`.

## Dependencies

- The RSS/blog source requires the optional `feedparser` package: `pip install feedparser`
- All sources require network access
