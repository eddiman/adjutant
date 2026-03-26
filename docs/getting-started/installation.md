# Installation

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

## Install

Clone the repository to any location you like — Adjutant can live anywhere:

```bash
git clone https://github.com/eddiman/adjutant.git /path/to/adjutant
cd /path/to/adjutant
python3 -m venv .venv
.venv/bin/pip install -e .
```

This installs the `adjutant` CLI entry point into `.venv/bin/adjutant`. Add it to your shell profile (adjust the path to match where you cloned):

```bash
echo 'alias adjutant="/path/to/adjutant/.venv/bin/adjutant"' >> ~/.zshrc
source ~/.zshrc
```

The setup wizard will ask for the install path and write it to `adjutant.yaml`. Adjutant resolves its own location from that file — no hardcoded paths required.

## Auto-start on boot (macOS)

To keep Adjutant running across reboots, use `adjutant startup` which installs a LaunchAgent. See [Lifecycle](../guides/lifecycle.md) for details.

## Next step

[Create a Telegram bot](telegram-setup.md) to give Adjutant a messaging channel.
