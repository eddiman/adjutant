# Commands

Adjutant has two command interfaces: **Telegram slash commands** (sent from your phone) and the **`adjutant` CLI** (run from your terminal). Both reach the same underlying system.

---

## Telegram Commands

Send these to your Adjutant bot in Telegram. Commands are only accepted from the chat ID configured in `.env`.

### Status and monitoring

| Command | What it does |
|---------|-------------|
| `/status` | Shows whether Adjutant is up and running, paused, or killed — plus scheduled jobs, last autonomous cycle, and notification count today |
| `/pulse` | Queries each registered KB for a quick status update — current state, blockers, and upcoming deadlines. No direct file access; all project knowledge flows through KB sub-agents. |
| `/reflect` | Requests a deep reflection using the medium model (Sonnet). Queries each KB in depth and encourages read-write KBs to update stale data. Adjutant will ask for `/confirm` before proceeding |
| `/confirm` | Confirms a pending `/reflect`. If you don't send this, the reflection is cancelled |

### Control

| Command | What it does |
|---------|-------------|
| `/pause` | Soft pause — Adjutant stops processing new messages. The listener stays running so it can be resumed without a restart |
| `/resume` | Resumes from a pause |
| `/restart` | Restarts all services |
| `/kill` | Emergency shutdown — kills all processes, removes cron jobs, and sets a KILLED lockfile. Requires `adjutant startup` to recover (see [Lifecycle](lifecycle.md)) |

### Capabilities

| Command | What it does |
|---------|-------------|
| `/screenshot <url>` | Takes a full-page screenshot of the URL and sends it back as an image. Automatically generates a visual description caption using the vision model. Requires Playwright to be installed. |
| `/search <query>` | Searches the web via the Brave Search API and returns the top 5 results (title, URL, description). No browser automation — fast, token-efficient, and not subject to bot detection. Requires `BRAVE_API_KEY` in `.env`. |
| `/kb` | Lists all registered knowledge bases |
| `/kb query <name> <question>` | Queries a specific knowledge base with your question. Example: `/kb query my-project what's the current status?` |
| `/kb write <name> <instruction>` | Writes to a read-write knowledge base. The sub-agent performs the requested update within the KB's sandbox. Only works for KBs with `access: read-write`. |
| `/schedule` | Lists all registered scheduled jobs with enabled/disabled status and schedule |
| `/schedule run <name>` | Runs a scheduled job immediately. Output is sent to chat. |
| `/schedule enable <name>` | Enables a job and installs its crontab entry |
| `/schedule disable <name>` | Disables a job and removes its crontab entry (keeps the registry entry) |

### Memory

| Command | What it does |
|---------|-------------|
| `/remember <text>` | Saves something to long-term memory. Auto-classified into the right category (corrections, decisions, preferences, etc.) |
| `/forget <topic>` | Archives memory entries matching a topic. Entries are moved to `.archive/`, not deleted. |
| `/recall [query]` | Searches long-term memory for entries matching a query. With no query, shows the memory index. |
| `/digest` | Compresses recent journal entries (past 7 days) into a weekly memory summary. |

### Configuration

| Command | What it does |
|---------|-------------|
| `/model` | Shows the currently active model |
| `/model <name>` | Switches to a different model for the current session. Example: `/model anthropic/claude-opus-4-5`. The model reverts to default on session expiry. |

### Help

| Command | What it does |
|---------|-------------|
| `/help` | Lists all available commands |
| `/start` | Alias for `/help` — sent automatically by Telegram when you first open the bot |

### Natural language

Any message that doesn't start with `/` is treated as a natural language query. Adjutant passes it to the AI agent with your full identity context loaded (`soul.md`, `heart.md`, `registry.md`). You can ask anything — questions about your projects, requests to draft something, queries about knowledge bases.

If a long-running response is in progress when you send a new message, the previous job is cancelled and the new one starts immediately.

---

## CLI Commands

Run from your terminal after adding the `adjutant` alias to your shell profile.

### Service management

```bash
adjutant start        # Start the Telegram listener
adjutant stop         # Stop the Telegram listener
adjutant restart      # Restart all services
adjutant status       # Show system status (OPERATIONAL/PAUSED/KILLED)
```

### Lifecycle control

```bash
adjutant pause        # Pause Adjutant (soft stop — listener stays running)
adjutant resume       # Resume from pause
adjutant kill         # Emergency shutdown (hard stop — requires startup to recover)
adjutant startup      # Full startup, or recovery from KILLED state
adjutant update       # Self-update to the latest release
```

See [Lifecycle](lifecycle.md) for when to use each of these.

### Sending messages

```bash
adjutant notify "Your message here"   # Send a Telegram notification (respects daily budget)
adjutant reply "Your message here"    # Send a Telegram reply (Markdown, no budget cap)
adjutant screenshot https://example.com   # Take and send a screenshot
adjutant search "query"               # Search the web via Brave API (prints results)
adjutant news         # Run the news briefing pipeline manually
```

### Knowledge bases

```bash
adjutant kb list                      # List registered knowledge bases
adjutant kb create                    # Interactive KB creation wizard
adjutant kb create --quick \
  --name my-kb \
  --path /path/to/kb \
  --desc "What this KB is about"      # Quick non-interactive create (--desc, not --description)
adjutant kb info <name>               # Show details about a KB
adjutant kb query <name> "question"   # Query a KB
adjutant kb run <name> <operation>    # Run a KB-local operation by convention
adjutant kb remove <name>             # Unregister a KB (files are NOT deleted)
```

### Scheduled jobs

```bash
adjutant schedule list              # List all jobs: name, enabled, schedule, description
adjutant schedule add               # Interactive wizard to register a new scheduled job
adjutant schedule enable <name>     # Enable job → install crontab entry
adjutant schedule disable <name>    # Disable job → remove crontab entry, keep registry
adjutant schedule remove <name>     # Remove from registry and crontab
adjutant schedule sync              # Reconcile crontab with registry (idempotent)
adjutant schedule run <name>        # Run a job immediately in foreground (for testing)
```

See [Schedules](schedules.md) for the full guide including generic KB-backed scheduled jobs.

### Memory

```bash
adjutant memory init              # Initialise the memory directory structure
adjutant memory remember "text"   # Store a memory entry (auto-classified)
adjutant memory forget "topic"    # Archive memory entries matching a topic
adjutant memory recall            # Show the memory index
adjutant memory recall "query"    # Search long-term memory
adjutant memory digest            # Compress journal entries into weekly summary
adjutant memory digest --days 14  # Digest the last 14 days instead of 7
adjutant memory status            # Show memory system stats
```

### Maintenance

```bash
adjutant rotate       # Archive old journal entries and rotate logs
adjutant logs         # Tail the live log (state/adjutant.log)
adjutant doctor       # Health check: dependencies, credentials, config files, state
adjutant setup        # Interactive setup wizard (first run or repair)
adjutant setup --repair   # Repair mode — checks and fixes an existing install
```

### Help

```bash
adjutant --help              # Show all commands
adjutant kb --help           # Show KB subcommand help
adjutant schedule --help     # Show schedule subcommand help
```

---

## `adjutant doctor` output

Run `adjutant doctor` to see the health of your installation:

```
Adjutant Health Check
=====================

Installation: /Users/you/.adjutant
OS:           Darwin

Dependencies:
  bash         OK (GNU bash, version 5.2.15)
  curl         OK (curl 8.4.0)
  jq           OK (jq-1.7)
  python3      OK (Python 3.12.0)
  opencode     OK (opencode 0.3.1)

Optional:
  playwright   not installed (needed for screenshot)

Configuration:
  adjutant.yaml        present
  .env                 present
  identity/soul.md     present
  identity/heart.md    present
  identity/registry.md present
  news_config.json     present
  opencode.json        present

State:
  Status: operational
  Listener: Running (PID 12345)
```

If `adjutant doctor` reports missing dependencies or configuration, run `adjutant setup --repair` to fix them interactively.
