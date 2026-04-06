# Adjutant

A persistent personal AI agent framework that runs on your machine and communicates through Telegram. Send messages, commands, and photos — Adjutant responds using LLM-powered reasoning with full awareness of your projects and knowledge bases.

Supports two LLM backends: [OpenCode](https://opencode.ai) and [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code), switchable via configuration.

## What It Does

- **Conversational AI** — natural language via Telegram, routed through OpenCode or Claude Code CLI
- **Knowledge bases** — sandboxed sub-agent workspaces for domain-specific knowledge
- **Scheduled jobs** — cron-based tasks that run autonomously and notify you of results
- **Autonomous cycles** — periodic pulse and review operations with configurable notification budgets
- **Long-term memory** — structured memory system that persists across conversations
- **News briefings** — aggregated, LLM-ranked news from Hacker News, Reddit, and RSS
- **Screenshots & vision** — capture and analyze web pages or images (OpenCode backend)
- **Web search** — Brave Search API integration
- **Web dashboard** — canvas-based KB explorer and operational dashboard

## Quick Start

```bash
git clone https://github.com/eddiman/adjutant.git
cd adjutant
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/adjutant setup
```

The setup wizard checks prerequisites, configures your LLM backend, prompts for Telegram credentials, and sets up identity files.

**Requirements**: Python 3.11+, [OpenCode](https://opencode.ai) or [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code), Telegram bot token

## Backends

| | OpenCode | Claude Code CLI |
|---|---|---|
| Auth | Anthropic API key | Claude Pro/Team/Enterprise subscription |
| Vision | Yes | Yes (via Read tool) |
| Cost tracking | No | Yes |
| Model listing | Yes | Yes |
| Permission modes | N/A | skip / allowlist |

Switch backends by editing `adjutant.yaml`:

```yaml
llm:
  backend: "opencode"    # or "claude-cli"
```

## Lifecycle

```bash
adjutant start       # Start the Telegram listener
adjutant stop        # Stop the Telegram listener
adjutant restart     # Restart all services
adjutant pause       # Soft pause — listener stays up, stops processing
adjutant resume      # Resume from pause
adjutant kill        # Emergency shutdown
adjutant startup     # Recovery from KILLED state
adjutant status      # Show current state
adjutant doctor      # Health check
```

## Telegram Commands

| Command | What it does |
|---------|-------------|
| `/status` | Current state, scheduled jobs, last autonomous cycle |
| `/pulse` | Quick project scan across all KBs |
| `/reflect` | Deep reflection (requires `/confirm`) |
| `/model` | Show or switch the active model |
| `/models` | List available models |
| `/kb list` | List knowledge bases |
| `/kb <name> <question>` | Query a knowledge base |
| `/search <query>` | Web search via Brave API |
| `/screenshot <url>` | Take a full-page screenshot |
| `/remember <text>` | Store a memory entry |
| `/memory [query]` | Search or show memory index |
| `/news` | Run news briefing |
| `/schedule list` | List scheduled jobs |
| `/pause` / `/resume` | Pause/resume processing |
| `/help` | List all commands |

Any other message is treated as natural language and routed to the LLM backend.

## CLI Reference

| Command | What it does |
|---------|-------------|
| `adjutant setup` | Interactive setup wizard |
| `adjutant start` / `stop` / `restart` | Manage the Telegram listener |
| `adjutant pause` / `resume` / `kill` | Lifecycle control |
| `adjutant startup` | Full startup / recovery |
| `adjutant status` / `adjutant doctor` | Status and health checks |
| `adjutant logs` | Tail the listener log |
| `adjutant notify "msg"` | Send notification (respects daily budget) |
| `adjutant reply "msg"` | Send reply (Markdown, no budget cap) |
| `adjutant screenshot <url>` | Take and send a screenshot |
| `adjutant search "query"` | Web search |
| `adjutant news` | Run news briefing |
| `adjutant rotate` | Archive old journals and rotate logs |
| `adjutant update` | Self-update to latest release |
| `adjutant kb list/create/query/run/remove/info` | Knowledge base management |
| `adjutant schedule list/add/enable/disable/run` | Schedule management |
| `adjutant memory remember/forget/recall/digest/status` | Memory management |

## Monorepo Structure

```
adjutant/
├── src/adjutant/          # Core Python package
├── web/                   # Web dashboard (Express + React)
├── site/                  # Documentation site (Docusaurus)
├── docs/                  # Documentation source
└── .github/workflows/     # CI/CD (release, docs deploy)
```

## Documentation

Full docs at [eddiman.github.io/adjutant](https://eddiman.github.io/adjutant/) — or browse `docs/` locally:

- [Getting Started](docs/getting-started/installation.md)
- [Commands](docs/guides/commands.md)
- [Backends](docs/guides/backends.md)
- [Knowledge Bases](docs/guides/knowledge-bases.md)
- [Architecture](docs/architecture/overview.md)

## Philosophy

- **Observe first, act rarely** — default is logging + selective notification
- **Human-in-the-loop** — Adjutant advises, you decide
- **Cap-conservative** — uses Haiku by default, Opus only on explicit request
- **No surprises** — surface things before they become emergencies
- **Install anywhere** — no hardcoded paths; everything resolves from `adjutant.yaml`

## License

MIT — see [LICENSE](LICENSE) for details.
