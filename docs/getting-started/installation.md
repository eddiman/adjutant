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

This creates `.venv`, installs Adjutant into it, and launches the setup wizard. Add the generated CLI shim to your shell profile (adjust the path to match where you installed):

```bash
echo 'alias adjutant="/path/to/adjutant/adjutant"' >> ~/.zshrc
source ~/.zshrc
```

Adjutant resolves its own location from the install directory marker and config — no hardcoded paths required.

## Auto-start on boot (macOS)

To keep Adjutant running across reboots, use `adjutant startup` which installs a LaunchAgent. See [Lifecycle](../guides/lifecycle.md) for details.

## Next step

[Create a Telegram bot](telegram-setup.md) to give Adjutant a messaging channel.
