"""Send a plain Telegram message with Markdown enabled.

Replaces: scripts/messaging/telegram/reply.sh

The bash script:
  1. Sources paths.sh + env.sh to get TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID
  2. Sanitises the message (strip control chars, clamp to 4000 chars)
  3. POSTs to sendMessage with parse_mode=Markdown

This module does the same thing via httpx and the credentials from
adjutant.core.env.require_telegram_credentials().
"""

from __future__ import annotations

import re
import sys

from adjutant.core.env import require_telegram_credentials
from adjutant.lib.http import get_client

# Telegram maximum message length
_TELEGRAM_MAX_LEN = 4000


def _sanitize(message: str) -> str:
    """Strip control characters, preserve printable ASCII and Unicode.

    Matches bash: ``tr -d '\\000-\\010\\013-\\037\\177' | cut -c1-4000``
    Strips 0x00-0x08, 0x0B-0x1F, 0x7F (same as tr).  Newlines (0x0A) and
    tabs (0x09) are kept because Telegram renders them.  Message is then
    clamped to 4000 characters.
    """
    # Strip control chars: 0x00-0x08, 0x0B-0x1F, 0x7F
    message = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", message)
    return message[:_TELEGRAM_MAX_LEN]


def send_reply(
    message: str,
    *,
    reply_to_message_id: int | None = None,
    parse_mode: str = "Markdown",
    env_path: str | None = None,
) -> None:
    """Send a Telegram message.

    Args:
        message: The text to send.  Will be sanitised and clamped to 4000 chars.
        reply_to_message_id: If set, reply to this message ID.
        parse_mode: Telegram parse mode (default: ``Markdown``).
        env_path: Override path to .env file (for testing).

    Raises:
        RuntimeError: If credentials are missing or the API call fails.
    """
    from pathlib import Path

    bot_token, chat_id = require_telegram_credentials(Path(env_path) if env_path else None)

    sanitized = _sanitize(message)
    if not sanitized:
        raise ValueError("Message is empty after sanitisation")

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload: dict[str, object] = {
        "chat_id": chat_id,
        "text": sanitized,
        "parse_mode": parse_mode,
    }
    if reply_to_message_id is not None:
        payload["reply_to_message_id"] = reply_to_message_id

    client = get_client()
    client.post(url, json_data=payload)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: reply.py <message>

    Mirrors the bash script's CLI contract.
    """
    import sys as _sys

    args = argv if argv is not None else _sys.argv[1:]
    if not args:
        _sys.stderr.write('Usage: reply.py "message"\n')
        return 1

    message = args[0]
    try:
        send_reply(message)
        print("Replied.")
        return 0
    except (RuntimeError, ValueError) as exc:
        _sys.stderr.write(f"ERROR: {exc}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
