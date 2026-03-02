# Getting Started

Adjutant is a personal agent that runs on your machine and stays in contact with you through Telegram. You send it messages — questions, commands, requests — and it responds. When you're not talking to it, it monitors the projects and knowledge bases you've registered and notifies you when something needs your attention.

This guide takes you from zero to your first conversation in about 10 minutes.

---

## Prerequisites

Before installing, make sure you have:

- **macOS or Linux**
- **bash 4+** (macOS ships bash 3; install via `brew install bash`)
- **curl** (installed on every macOS/Linux system by default)
- **jq** — `brew install jq` on macOS, `apt install jq` on Linux
- **[opencode](https://opencode.ai)** — the AI runtime Adjutant uses for reasoning

Check opencode is working:

```bash
opencode --version
```

---

## Step 1 — Install

Run the installer:

```bash
curl -fsSL https://raw.githubusercontent.com/eddiman/adjutant/main/scripts/setup/install.sh | bash
```

The installer will:

1. Check that `curl`, `jq`, and `opencode` are available
2. Ask where to install (default: `~/.adjutant`)
3. Download the latest release tarball
4. Extract it to your chosen directory
5. Launch the interactive setup wizard

If you'd rather install from source (for development):

```bash
git clone https://github.com/eddiman/adjutant.git ~/.adjutant
bash ~/.adjutant/scripts/setup/wizard.sh
```

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

If the installer didn't launch it automatically:

```bash
adjutant setup
```

The wizard walks through six steps:

1. **Prerequisites** — verifies dependencies are in place
2. **Install path** — confirms where Adjutant lives
3. **Identity** — creates your `soul.md`, `heart.md`, and `registry.md` files (see [Configuration](configuration.md))
4. **Messaging** — prompts for your Telegram bot token and chat ID, writes them to `.env`
5. **Features** — optional news briefing configuration
6. **Service** — installs the shell alias and optionally sets up auto-start on boot

At the end, the wizard shows a verification summary. All six items should show as present.

If something is wrong later, you can re-run the wizard in repair mode:

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

You should see `RUNNING` and the listener's PID.

---

## Step 5 — Send your first message

Open Telegram and send a message to your bot. Try:

- `/status` — Adjutant replies with its current state
- `/help` — lists all available commands
- `What time is it?` — a natural language question; Adjutant responds via the AI agent

That's it. Adjutant is running.

---

## Adding the shell alias

The setup wizard offers to add an alias to your shell profile. If you skipped that step:

```bash
echo 'alias adjutant="~/.adjutant/adjutant"' >> ~/.zshrc
source ~/.zshrc
```

Adjust the path if you installed somewhere other than `~/.adjutant`.

---

## Auto-start on boot (macOS)

To keep Adjutant running across reboots, create a Launch Agent:

```bash
cat > ~/Library/LaunchAgents/adjutant.telegram.plist << 'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>adjutant.telegram</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Users/YOUR_USERNAME/.adjutant/scripts/messaging/telegram/listener.sh</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/Users/YOUR_USERNAME/.adjutant/state/listener.stdout.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/YOUR_USERNAME/.adjutant/state/listener.stderr.log</string>
</dict>
</plist>
EOF

launchctl load ~/Library/LaunchAgents/adjutant.telegram.plist
```

Replace `YOUR_USERNAME` with your macOS username.

---

## Next steps

- **Configure what Adjutant knows about you** → [Configuration](configuration.md)
- **See all commands** → [Commands](commands.md)
- **Add a knowledge base** → [Knowledge Bases](knowledge-bases.md)
- **Understand start/stop/pause** → [Lifecycle](lifecycle.md)
