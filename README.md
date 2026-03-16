# Adjutant

A persistent personal agent that runs on your machine and stays in contact with you through Telegram. You send it messages — questions, commands, requests — and it responds using an LLM with full awareness of your projects and priorities.

**Version**: 2.0.0

## What It Does

- Responds to natural language queries via Telegram
- Queries domain-specific knowledge bases via isolated sub-agents
- Runs on-demand pulse checks (`/pulse`) and deep reflections (`/reflect`)
- Takes screenshots, analyzes images, and searches the web
- Stays quiet by default — no background jobs run unless you configure them

Adjutant is **on-demand, not autonomous**. It responds when you message it. Proactive behaviour (project scanning, notifications) only happens when you trigger `/pulse` or `/reflect`, or if you set up a cron job yourself.

## Quick Start

Adjutant can be installed anywhere — there is no hardcoded path.

```bash
git clone https://github.com/eddiman/adjutant.git /path/to/adjutant
cd /path/to/adjutant
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/adjutant setup
```

The setup wizard checks prerequisites, asks where Adjutant lives, prompts for your Telegram credentials, and sets up identity files.

**Requirements**: Python 3.11+, [opencode](https://opencode.ai), Telegram bot token

---

## Starting & Stopping

```bash
adjutant start      # Start the Telegram listener
adjutant stop       # Stop the Telegram listener
adjutant restart    # Stop all services and start fresh
adjutant startup    # Full startup / recovery from KILLED state
adjutant pause      # Soft pause — listener stays up, stops processing
adjutant resume     # Resume from pause
adjutant kill       # Emergency shutdown — kills all processes, sets KILLED lockfile
```

After `adjutant kill`, run `adjutant startup` to recover.

## Directory Structure

```
$ADJ_DIR/                       # Install directory (set by adjutant.yaml)
├── .opencode/
│   └── agents/
│       └── adjutant.md        # Agent definition (tracked)
├── adjutant                    # CLI shim
├── adjutant.yaml               # Root marker + unified config (gitignored)
├── opencode.json               # Workspace permissions
├── .env                        # Secrets (gitignored)
├── identity/                   # Identity files (gitignored)
│   ├── soul.md                 # Identity, values, decision frameworks
│   ├── heart.md                # Current priorities
│   └── registry.md             # Registered projects to monitor
├── knowledge_bases/
│   └── registry.yaml           # Registered knowledge bases (gitignored)
├── templates/kb/               # KB scaffold templates (tracked)
├── prompts/                    # Pulse/review/escalation prompts (tracked)
├── src/adjutant/               # Python source
├── journal/                    # Daily entries (gitignored)
├── insights/                   # Generated insights (gitignored)
└── state/                      # Runtime state (gitignored)
```

## Telegram Commands

| Command | What it does |
|---------|-------------|
| `/status` | Current state, scheduled jobs, last autonomous cycle |
| `/pause` | Soft pause — stops processing without killing the listener |
| `/resume` | Resume from pause |
| `/pulse` | Quick project scan |
| `/restart` | Restart all services |
| `/screenshot <url>` | Take full-page screenshot |
| `/reflect` | Deep reflection (requires `/confirm`) |
| `/model` | Show or switch the active model |
| `/kb` | List knowledge bases |
| `/kb query <name> <question>` | Query a knowledge base |
| `/search <query>` | Web search via Brave API |
| `/help` | List all commands |

Any other message is treated as natural language.

## CLI Reference

| Command | What it does |
|---------|-------------|
| `adjutant startup` | Full startup / recovery from KILLED state |
| `adjutant start` / `stop` / `restart` | Manage the Telegram listener |
| `adjutant pause` / `resume` / `kill` | Lifecycle control |
| `adjutant status` | Show current status |
| `adjutant logs` | Tail the listener log |
| `adjutant doctor` | Check health and dependencies |
| `adjutant notify "msg"` | Send a Telegram notification (respects daily budget) |
| `adjutant reply "msg"` | Send a Telegram reply (Markdown, no budget cap) |
| `adjutant screenshot <url>` | Take and send a full-page screenshot |
| `adjutant search "query"` | Web search via Brave API |
| `adjutant news` | Run the news briefing manually |
| `adjutant rotate` | Archive old journal entries and rotate logs |
| `adjutant update` | Self-update to the latest release |
| `adjutant setup` | Interactive setup wizard |
| `adjutant kb list` | List registered knowledge bases |
| `adjutant kb create` | Create a new knowledge base (interactive wizard) |
| `adjutant kb query <name> "q"` | Query a knowledge base |
| `adjutant kb run <name> <op>` | Run a KB-local operation |
| `adjutant kb remove <name>` | Unregister a knowledge base |
| `adjutant kb info <name>` | Show details about a knowledge base |
| `adjutant schedule list` | List all scheduled jobs |
| `adjutant schedule add` | Register a new scheduled job |
| `adjutant schedule enable/disable <name>` | Toggle a job |
| `adjutant schedule run <name>` | Run a job immediately |

## Philosophy

- **Observe first, act rarely** — default is logging + selective notification
- **Human-in-the-loop** — Adjutant advises, you decide
- **Cap-conservative** — uses Haiku by default, Opus only on explicit request
- **No surprises** — surface things before they become emergencies
- **Install anywhere** — no hardcoded paths; everything resolves from `adjutant.yaml`

## Documentation

Full docs in `docs/` — start with [Getting Started](docs/guides/getting-started.md).

## License

MIT — see [LICENSE](LICENSE) for details.
