"""Step 4: Telegram Credential Setup.

Replaces: scripts/setup/steps/messaging.sh

Walks the user through creating a Telegram bot and obtaining credentials.
If .env already has valid credentials, skips with a success message.

Sets module-level state:
  WIZARD_TELEGRAM_TOKEN       — the bot token
  WIZARD_TELEGRAM_CHAT_ID     — the chat ID
  WIZARD_TELEGRAM_ENABLED     — True if Telegram is enabled
"""

from __future__ import annotations

import re
import sys
from typing import TYPE_CHECKING, Any

from adjutant.setup.wizard import (
    DIM,
    RESET,
    wiz_confirm,
    wiz_fail,
    wiz_info,
    wiz_input,
    wiz_ok,
    wiz_step,
    wiz_warn,
)

if TYPE_CHECKING:
    from pathlib import Path

# Module-level wizard state (populated by step_messaging)
WIZARD_TELEGRAM_TOKEN: str = ""
WIZARD_TELEGRAM_CHAT_ID: str = ""
WIZARD_TELEGRAM_ENABLED: bool = False

_TOKEN_RE = re.compile(r"^\d+:[A-Za-z0-9_-]+$")
_CHAT_ID_RE = re.compile(r"^-?\d+$")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _read_env_cred(env_file: Path, key: str) -> str:
    """Read a credential from .env — delegates to core/env.py."""
    from adjutant.core.env import get_credential

    return get_credential(key, env_file) or ""


def _get_http_client() -> Any:
    """Return an HTTP client. Lazy import to keep module light."""
    try:
        from adjutant.lib.http import get_client

        return get_client()
    except Exception:  # noqa: BLE001 — fallback to requests
        import requests  # type: ignore[import-untyped]

        return requests.Session()


def _validate_token(token: str) -> str | None:
    """Call Telegram getMe. Returns bot username on success or None."""
    try:
        client = _get_http_client()
        resp = client.get(
            f"https://api.telegram.org/bot{token}/getMe",
            timeout=10,
        )
        data: dict[str, Any] = resp.json()
        if data.get("ok"):
            username: str = data["result"].get("username", "unknown")
            return username
    except Exception:  # noqa: BLE001 — non-fatal token validation
        pass
    return None


def _auto_detect_chat_id(token: str) -> str | None:
    """Call getUpdates and return the last message's chat ID."""
    try:
        client = _get_http_client()
        resp = client.get(
            f"https://api.telegram.org/bot{token}/getUpdates?limit=5",
            timeout=10,
        )
        data: dict[str, Any] = resp.json()
        if data.get("ok") and data.get("result"):
            result: list[dict[str, Any]] = data["result"]
            if result:
                chat_id = result[-1].get("message", {}).get("chat", {}).get("id")
                if chat_id is not None:
                    return str(chat_id)
    except Exception:  # noqa: BLE001 — non-fatal chat ID detection
        pass
    return None


def _get_existing_token(dry_run: bool = False) -> bool:
    """Prompt user to paste an existing token. Returns True on success."""
    global WIZARD_TELEGRAM_TOKEN
    print("", file=sys.stderr)
    token = wiz_input("Paste your bot token")

    if not token:
        wiz_fail("No token provided")
        return False

    if not _TOKEN_RE.match(token):
        wiz_warn("Token format looks unusual (expected: 123456789:ABCdefGHI...)")
        if not wiz_confirm("Use this token anyway?", "N"):
            return False

    # Test the token
    sys.stderr.write("  Testing bot token... ")
    sys.stderr.flush()
    if dry_run:
        print("", file=sys.stderr)
        wiz_ok("[DRY RUN] Would verify bot token")
        WIZARD_TELEGRAM_TOKEN = token or "dry-run-token"
        return True

    username = _validate_token(token)
    print("", file=sys.stderr)
    if username:
        wiz_ok(f"Bot verified: @{username}")
    else:
        wiz_warn("Could not verify token (network issue or invalid token)")
        if not wiz_confirm("Continue anyway?", "N"):
            return False

    WIZARD_TELEGRAM_TOKEN = token
    return True


def _create_new_bot(dry_run: bool = False) -> bool:
    """Walk user through BotFather flow. Returns True on success."""
    global WIZARD_TELEGRAM_TOKEN
    print("", file=sys.stderr)
    print("  Let me walk you through creating a Telegram bot:", file=sys.stderr)
    print("", file=sys.stderr)
    print(f"  {RESET}1.{RESET} Open Telegram and search for @BotFather", file=sys.stderr)
    print("  2. Send /newbot and follow the prompts", file=sys.stderr)
    print("  3. BotFather will give you a bot token", file=sys.stderr)
    print("", file=sys.stderr)

    token = wiz_input("Paste the bot token here")
    if not token:
        wiz_fail("No token provided")
        return False

    sys.stderr.write("  Testing bot token... ")
    sys.stderr.flush()
    if dry_run:
        print("", file=sys.stderr)
        wiz_ok("[DRY RUN] Would verify bot token")
        WIZARD_TELEGRAM_TOKEN = token
        return True

    username = _validate_token(token)
    print("", file=sys.stderr)
    if username:
        wiz_ok(f"Bot verified: @{username}")
    else:
        wiz_warn("Could not verify token — continuing anyway")

    WIZARD_TELEGRAM_TOKEN = token
    return True


def _get_chat_id(dry_run: bool = False) -> bool:
    """Auto-detect or prompt for chat ID. Returns True on success."""
    global WIZARD_TELEGRAM_CHAT_ID
    print("  Now I need your chat ID.", file=sys.stderr)
    print("", file=sys.stderr)
    print("  1. Send any message to your new bot in Telegram", file=sys.stderr)
    print("  2. I'll check for it automatically", file=sys.stderr)
    print("", file=sys.stderr)

    if wiz_confirm("Ready? (press Enter after sending a message to the bot)", "Y"):
        if dry_run:
            WIZARD_TELEGRAM_CHAT_ID = "0"
            wiz_ok("[DRY RUN] Would auto-detect chat ID (using placeholder 0)")
            return True

        sys.stderr.write("  Checking for messages... ")
        sys.stderr.flush()
        chat_id = _auto_detect_chat_id(WIZARD_TELEGRAM_TOKEN)
        print("", file=sys.stderr)
        if chat_id:
            wiz_ok(f"Found chat ID: {chat_id}")
            WIZARD_TELEGRAM_CHAT_ID = chat_id
            return True

        wiz_warn("Couldn't auto-detect chat ID")

    # Manual fallback
    print("", file=sys.stderr)
    print("  To find your chat ID manually:", file=sys.stderr)
    print(
        f"  {DIM}Visit: https://api.telegram.org/bot<TOKEN>/getUpdates{RESET}",
        file=sys.stderr,
    )
    print(
        f'  {DIM}Look for "chat":{{"id":NNNNN}} in the response{RESET}',
        file=sys.stderr,
    )
    print("", file=sys.stderr)

    chat_id = wiz_input("Enter your chat ID")
    if not chat_id:
        wiz_fail("No chat ID provided")
        return False

    if not _CHAT_ID_RE.match(chat_id):
        wiz_warn("Chat ID should be numeric")
        if not wiz_confirm("Use this value anyway?", "N"):
            return False

    wiz_ok(f"Chat ID set: {chat_id}")
    WIZARD_TELEGRAM_CHAT_ID = chat_id
    return True


def _write_env(adj_dir: Path, dry_run: bool = False) -> None:
    """Write/update credentials in .env."""
    env_file = adj_dir / ".env"
    if dry_run:
        wiz_ok(f"[DRY RUN] Would write/update {env_file} (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)")
        return

    if env_file.is_file():
        content = env_file.read_text()
        lines = content.splitlines()
        new_lines: list[str] = []
        token_written = False
        chatid_written = False
        for line in lines:
            if line.startswith("TELEGRAM_BOT_TOKEN="):
                new_lines.append(f"TELEGRAM_BOT_TOKEN={WIZARD_TELEGRAM_TOKEN}")
                token_written = True
            elif line.startswith("TELEGRAM_CHAT_ID="):
                new_lines.append(f"TELEGRAM_CHAT_ID={WIZARD_TELEGRAM_CHAT_ID}")
                chatid_written = True
            else:
                new_lines.append(line)
        if not token_written:
            new_lines.append(f"TELEGRAM_BOT_TOKEN={WIZARD_TELEGRAM_TOKEN}")
        if not chatid_written:
            new_lines.append(f"TELEGRAM_CHAT_ID={WIZARD_TELEGRAM_CHAT_ID}")
        env_file.write_text("\n".join(new_lines) + "\n")
    else:
        from datetime import datetime

        today = datetime.now().strftime("%Y-%m-%d")
        env_file.write_text(
            f"# Adjutant — Credentials\n"
            f"# Generated by setup wizard on {today}\n"
            f"TELEGRAM_BOT_TOKEN={WIZARD_TELEGRAM_TOKEN}\n"
            f"TELEGRAM_CHAT_ID={WIZARD_TELEGRAM_CHAT_ID}\n"
        )

    # Restrict permissions — secrets file
    env_file.chmod(0o600)


# ---------------------------------------------------------------------------
# Public step entry point
# ---------------------------------------------------------------------------


def step_messaging(adj_dir: Path, *, dry_run: bool = False) -> bool:
    """Run Step 4: Telegram Messaging Setup.

    Returns:
        True on success or skip; False if setup failed.
    """
    global WIZARD_TELEGRAM_TOKEN, WIZARD_TELEGRAM_CHAT_ID, WIZARD_TELEGRAM_ENABLED
    wiz_step(4, 7, "Messaging — Telegram Setup")
    print("", file=sys.stderr)

    # Top-level skip
    if not wiz_confirm(
        "Set up Telegram messaging? (you can do this later with 'adjutant setup')", "Y"
    ):
        wiz_info("Skipping Telegram setup")
        wiz_info("Run 'adjutant setup' at any time to configure messaging")
        WIZARD_TELEGRAM_ENABLED = False
        return True
    WIZARD_TELEGRAM_ENABLED = True

    env_file = adj_dir / ".env"

    # Check for existing valid credentials
    if env_file.is_file():
        existing_token = _read_env_cred(env_file, "TELEGRAM_BOT_TOKEN")
        existing_chatid = _read_env_cred(env_file, "TELEGRAM_CHAT_ID")

        if (
            existing_token
            and existing_token != "your-bot-token-here"
            and existing_chatid
            and existing_chatid != "your-chat-id-here"
        ):
            wiz_ok("Telegram bot token configured")
            wiz_ok(f"Telegram chat ID configured ({existing_chatid})")
            print("", file=sys.stderr)
            if not wiz_confirm("Re-configure Telegram credentials?", "N"):
                WIZARD_TELEGRAM_TOKEN = existing_token
                WIZARD_TELEGRAM_CHAT_ID = existing_chatid
                return True

    # Ask if user already has a token
    print("", file=sys.stderr)
    if wiz_confirm("Do you have a Telegram bot token?", "N"):
        if not _get_existing_token(dry_run=dry_run):
            return False
    else:
        if not _create_new_bot(dry_run=dry_run):
            return False

    # Get the chat ID
    print("", file=sys.stderr)
    if not _get_chat_id(dry_run=dry_run):
        return False

    # Write to .env
    _write_env(adj_dir, dry_run=dry_run)
    wiz_ok("Saved credentials to .env")

    return True
