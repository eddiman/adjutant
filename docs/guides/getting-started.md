# Getting Started

Adjutant is a personal agent that runs on your machine and stays in contact with you through Telegram. You send it messages — questions, commands, requests — and it responds. When you're not talking to it, it monitors the projects and knowledge bases you've registered and notifies you when something needs your attention.

This guide takes you from zero to your first conversation in about 10 minutes.

---

## Prerequisites

Before installing, make sure you have:

- **macOS or Linux**
- **Python 3.11+** — `python3 --version` to check
- **An LLM backend** — either [OpenCode](https://opencode.ai) or [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code)
- **curl** (installed on every macOS/Linux system by default)

Check your backend is working:

```bash
# OpenCode
opencode --version

# Or Claude Code CLI
claude --version
```

---

## Step 1 — Install

From a release tarball or a clone, run the installer from the repo root:

```bash
git clone https://github.com/eddiman/adjutant.git /path/to/adjutant
cd /path/to/adjutant
python3 install.py
```

For release assets, download and extract the tarball first, then run the same command:

```bash
curl -fsSL https://github.com/eddiman/adjutant/releases/latest/download/adjutant-vX.Y.Z.tar.gz -o adjutant.tar.gz
tar xzf adjutant.tar.gz
cd adjutant-vX.Y.Z
python3 install.py
```

The installer creates `.venv`, installs Adjutant into it, and launches the setup wizard. After setup, add the generated CLI shim to your shell profile if you want a short `adjutant` command everywhere:

```bash
echo 'alias adjutant="/path/to/adjutant/.venv/bin/adjutant"' >> ~/.zshrc
source ~/.zshrc
```

Adjutant resolves its own location from the install directory marker and config — no hardcoded paths required.

---

## Step 2 — Create a Telegram bot

Adjutant communicates through Telegram. You'll need a bot token and your chat ID.

**Create a bot:**

1. Open Telegram and search for `@BotFather`
2. Send `/newbot`
3. Follow the prompts — choose a name and username for your bot
4. BotFather will give you a token that looks like `123456789:ABCdefGHIjklMNOpqrsTUVwxyz` — save it

**Get your chat ID:**

1. Start a conversation with your new bot (click Start or send any message)
2. Open this URL in your browser, replacing `YOUR_TOKEN` with your token:
   ```
   https://api.telegram.org/botYOUR_TOKEN/getUpdates
   ```
3. Find `"chat":{"id":123456789}` in the response — that number is your chat ID

---

## Step 3 — Run the setup wizard

```bash
adjutant setup
```

The wizard walks through seven steps:

1. **Prerequisites** — verifies dependencies are in place
2. **Install path** — confirms where Adjutant lives
3. **Identity** — creates your `soul.md`, `heart.md`, and `registry.md` files (see [Configuration](configuration.md))
4. **Messaging** — prompts for your Telegram bot token and chat ID, writes them to `.env`
5. **Features** — optional news briefing and search configuration
6. **Service** — installs the shell alias and optionally sets up auto-start on boot
7. **Heartbeat** — optional autonomous pulse/review scheduling

At the end, the wizard shows a completion banner. If something needs fixing later, re-run the wizard in repair mode:

```bash
adjutant setup --repair
```

---

## Step 4 — Start the listener

```bash
adjutant start
```

The Telegram listener starts in the background. Verify it's running:

```bash
adjutant status
```

You should see `Adjutant is up and running.` and the listener's PID.

---

## Step 5 — Send your first message

Open Telegram and send a message to your bot. Try:

- `/status` — Adjutant replies with its current state
- `/help` — lists all available commands
- `What time is it?` — a natural language question; Adjutant responds via the AI agent

That's it. Adjutant is running.

---

## Auto-start on boot (macOS)

To keep Adjutant running across reboots, use `adjutant startup` which installs a LaunchAgent. Alternatively you can install it manually:

```bash
cat > ~/Library/LaunchAgents/com.adjutant.telegram.plist << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.adjutant.telegram</string>
    <key>ProgramArguments</key>
    <array>
        <string>/path/to/adjutant/.venv/bin/python</string>
        <string>-m</string>
        <string>adjutant.messaging.telegram.listener</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/path/to/adjutant</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>ThrottleInterval</key>
    <integer>30</integer>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
        <key>ADJ_DIR</key>
        <string>/path/to/adjutant</string>
    </dict>
    <key>StandardOutPath</key>
    <string>/path/to/adjutant/state/launchd_stdout.log</string>
    <key>StandardErrorPath</key>
    <string>/path/to/adjutant/state/launchd_stderr.log</string>
</dict>
</plist>
EOF

launchctl load ~/Library/LaunchAgents/com.adjutant.telegram.plist
```

Replace `/path/to/adjutant` with your actual install path.

Key plist properties:
- **`KeepAlive: true`** — unconditional restart on any exit (including clean exit 0)
- **`ThrottleInterval: 30`** — prevents restart loops faster than every 30 seconds
- **`ADJ_DIR`** — the listener reads this to find config, state, and identity files
- The listener does NOT send a startup notification — only `adjutant start` does, so launchd auto-restarts don't spam Telegram

---

## Next steps

- **Configure what Adjutant knows about you** → [Configuration](configuration.md)
- **See all commands** → [Commands](commands.md)
- **Add a knowledge base** → [Knowledge Bases](knowledge-bases.md)
- **Understand start/stop/pause** → [Lifecycle](lifecycle.md)
