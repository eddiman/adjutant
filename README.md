# Adjutant

A persistent personal agent that lives in `~/.adjutant/` and stays in contact with you through Telegram. You send it messages — questions, commands, requests — and it responds using an LLM with full awareness of your projects and priorities.

**Version**: 1.0.0

## What It Does

- Responds to natural language queries via Telegram
- Queries domain-specific knowledge bases via isolated sub-agents
- Runs on-demand pulse checks (`/pulse`) and deep reflections (`/reflect`)
- Takes screenshots, analyzes images, and runs capability scripts
- Stays quiet by default — no background jobs run unless you configure them

Adjutant is **on-demand, not autonomous**. It responds when you message it. Proactive behaviour (project scanning, notifications) only happens when you trigger `/pulse` or `/reflect`, or if you set up a cron job yourself. There is no scheduler running in the background.

## Quick Start

```bash
curl -fsSL https://raw.githubusercontent.com/eddiman/adjutant/main/scripts/setup/install.sh | bash
```

The installer checks prerequisites, asks where to install (default: `~/.adjutant`), downloads the latest release, and launches the interactive setup wizard. The wizard handles credentials, identity, and service installation.

**Requirements**: bash 4+, curl, jq, [opencode](https://opencode.ai)

---

### Developer Install (git clone)

If you want to work on the framework itself:

```bash
git clone https://github.com/eddiman/adjutant.git ~/.adjutant
cd ~/.adjutant
bash scripts/setup/wizard.sh
```

### Create Telegram Bot (optional)

Adjutant works without Telegram in CLI-only mode. To enable Telegram:

1. Open Telegram and search for `@BotFather`
2. Send `/newbot` and follow the prompts
3. Save the **bot token** you receive (e.g., `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`)

### Get Your Chat ID

1. Start a conversation with your new bot
2. Send any message
3. Visit: `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`
4. Find `"chat":{"id":123456789}` — that number is your chat ID

The setup wizard will prompt for both values and write them to `.env`.

## Starting & Stopping

```bash
adjutant startup    # Full startup / recovery from KILLED state
adjutant stop       # Stop the Telegram listener
adjutant restart    # Stop all services and start fresh
adjutant pause      # Soft pause — listener stays up, stops processing
adjutant resume     # Resume from pause
adjutant kill       # Emergency shutdown — kills all processes, sets KILLED lockfile
```

After `adjutant kill`, run `adjutant startup` to recover.

## Directory Structure

```
~/.adjutant/
├── .opencode/              # Local OpenCode workspace
│   └── agents/
│       └── adjutant.md    # Adjutant agent definition
├── adjutant                # CLI entrypoint
├── adjutant.yaml           # Root marker + unified config
├── README.md               # This file
├── identity/               # Identity files
│   ├── soul.md            # Identity, values, decision frameworks
│   ├── heart.md           # Current priorities
│   └── registry.md        # Registered projects to monitor
├── knowledge_bases/        # KB registry
│   └── registry.yaml      # Registered knowledge bases
├── templates/              # Templates for scaffolding
│   └── kb/                # KB scaffold templates
├── opencode.json           # Workspace config (inherits global MCPs)
├── .env                    # Secrets (gitignored)
├── .gitignore
├── journal/                # Daily entries (gitignored)
├── insights/               # Generated insights (gitignored)
├── state/                  # Session state (gitignored)
├── prompts/                # Heartbeat prompts
└── scripts/                # Helper scripts
    ├── common/            # Shared utilities (opencode.sh, paths.sh, env.sh, ...)
    ├── messaging/         # Telegram integration
    │   └── telegram/
    ├── lifecycle/         # Start, stop, restart, pause
    ├── news/              # News briefing pipeline
    ├── capabilities/      # Screenshot, vision, knowledge bases
    │   └── kb/            # KB CRUD + query pipeline
    ├── setup/             # Setup wizard + KB wizard
    └── observability/     # Status, usage tracking
```

## Telegram Commands

| Command | What it does |
|---------|-------------|
| `/status` | RUNNING/PAUSED + last heartbeat |
| `/pause` | Pause monitoring |
| `/resume` | Resume monitoring |
| `/pulse` | Quick project scan |
| `/restart` | Restart all services |
| `/screenshot <url>` | Take full-page screenshot |
| `/reflect` | Deep Opus reflection (costs ~$0.10–0.30) |
| `/model` | Show/switch model |
| `/kb` | List knowledge bases or query one (`/kb <name> <question>`) |
| `/help` | List commands |

Any other message is treated as natural language — ask about projects, priorities, deadlines, or anything in your watched files.

## Registering Projects

Edit `registry.md`:

```markdown
## Project Name

- **Path**: /absolute/path/to/project
- **Priority**: High | Medium | Low
- **Type**: Client work | Personal | Chapter management | etc.
- **Watch files**:
  - relative/path/to/file1.md
  - relative/path/to/file2.md
- **Agents**: agent-name (if OpenCode agents exist)
- **Concerns**: deadlines, stale data, gaps to watch for
```

## Updating Priorities

Edit `heart.md` to shift Adjutant's focus:

```markdown
# Adjutant — Heart

## Current Priorities
1. Project A — deadline Feb 28
2. Project B — speaker confirmation pending

## Active Concerns
- Project A: Sponsor renewal overdue
- Project B: Venue not confirmed

## Quiet Zones
- Project C — on hold until March
```

## CLI Reference

All operations go through the `adjutant` command. Add `~/.adjutant` to your `PATH` or call it directly.

| Command | What it does |
|---------|-------------|
| `adjutant startup` | Full startup / recovery from KILLED state |
| `adjutant stop` | Stop the Telegram listener |
| `adjutant restart` | Restart all services |
| `adjutant pause` | Soft pause — stops processing without killing the listener |
| `adjutant resume` | Resume from pause |
| `adjutant kill` | Emergency shutdown — kills everything, sets KILLED lockfile |
| `adjutant status` | Show current status |
| `adjutant logs` | Tail the listener log |
| `adjutant doctor` | Check health and dependencies |
| `adjutant news` | Run the news briefing manually |
| `adjutant notify "msg"` | Send a Telegram notification |
| `adjutant screenshot <url>` | Take and send a full-page screenshot |
| `adjutant rotate` | Archive old journal entries and rotate logs |
| `adjutant update` | Self-update to the latest release |
| `adjutant setup` | Interactive setup wizard |
| `adjutant kb list` | List registered knowledge bases |
| `adjutant kb create` | Create a new knowledge base (interactive wizard) |
| `adjutant kb query <name> "q"` | Query a knowledge base |
| `adjutant kb run <name> <op>` | Run a KB-local operation by convention |
| `adjutant kb remove <name>` | Unregister a knowledge base |
| `adjutant kb info <name>` | Show details about a knowledge base |
| `adjutant help` | Show all commands |

## Requirements

- macOS or Linux
- OpenCode CLI (`opencode`) on `$PATH`
- `jq` (`brew install jq` on macOS)
- Telegram account + bot token
- Claude API access (via OpenCode)

## Philosophy

- **Observe first, act rarely** — default is logging + selective notification
- **Human-in-the-loop** — Adjutant advises, you decide
- **Cap-conservative** — uses Haiku by default, Opus only on explicit request
- **No surprises** — surface things before they become emergencies

## License

License TBD — see repository for current status.
