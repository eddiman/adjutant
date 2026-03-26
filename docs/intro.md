---
slug: /
---

# Introduction

Adjutant is a persistent autonomous agent framework that runs on your local machine. It listens for messages through Telegram, routes them through a backend-agnostic dispatcher, and responds via LLM-powered reasoning or built-in commands.

## What Adjutant does

- **Conversational AI** — send natural-language messages via Telegram; Adjutant responds using OpenCode or Claude Code CLI as its reasoning backend.
- **Knowledge bases** — register directories as queryable knowledge bases. Adjutant reads, writes, and searches them on your behalf.
- **Scheduled jobs** — define cron-based tasks that run autonomously and notify you of results.
- **Autonomous cycles** — periodic pulse and review operations let Adjutant act proactively, within configurable notification budgets.
- **Long-term memory** — a structured memory system that persists facts, preferences, and decisions across conversations.
- **News briefings** — aggregated, LLM-ranked news from Hacker News, Reddit, and RSS feeds.
- **Screenshots and vision** — capture and analyze web pages or images.
- **Web search** — Brave Search API integration for real-time web queries.

## Dual-backend architecture

Adjutant supports two LLM backends, switchable via configuration:

| | OpenCode | Claude Code CLI |
|---|---|---|
| Vision/images | Yes | No |
| Model listing | Yes | No |
| Cost tracking | No | Yes |
| Process reaping | Yes | No |
| Permission modes | N/A | skip / allowlist |

Both backends share the same protocol — all capabilities work identically regardless of which backend is active. See [Backends](guides/backends.md) for setup and switching.

## Quick start

1. [Install Adjutant](getting-started/installation.md)
2. [Create a Telegram bot](getting-started/telegram-setup.md)
3. [Run the setup wizard](getting-started/setup-wizard.md)
4. [Send your first message](getting-started/first-message.md)
