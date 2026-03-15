"""Send a Telegram notification with a daily budget guard.

Replaces: scripts/messaging/telegram/notify.sh

Tracks a per-day counter in state/notify_count_YYYY-MM-DD.txt
Refuses to send if count >= max_per_day (from adjutant.yaml, default 3)
Max message length is 4096 (Telegram hard limit).
No parse_mode=Markdown.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

from adjutant.core.config import load_typed_config
from adjutant.core.env import require_telegram_credentials
from adjutant.lib.http import get_client
from adjutant.messaging.telegram.send import sanitize_message

_TELEGRAM_NOTIFY_MAX_LEN = 4096


class BudgetExceededError(Exception):
    """Raised when the daily notification budget is exhausted."""

    def __init__(self, count: int, max_count: int) -> None:
        self.count = count
        self.max_count = max_count
        super().__init__(f"budget_exceeded ({count}/{max_count} sent today)")


def _count_file(state_dir: Path, today: date | None = None) -> Path:
    """Return path to today's notification count file."""
    d = today or date.today()
    return state_dir / f"notify_count_{d.isoformat()}.txt"


def _read_count(state_dir: Path, today: date | None = None) -> int:
    f = _count_file(state_dir, today)
    if f.is_file():
        try:
            return int(f.read_text().strip())
        except ValueError:
            return 0
    return 0


def _write_count(state_dir: Path, count: int, today: date | None = None) -> None:
    f = _count_file(state_dir, today)
    state_dir.mkdir(parents=True, exist_ok=True)
    f.write_text(str(count))


def get_max_per_day(adj_dir: Path) -> int:
    """Read max_per_day from adjutant.yaml, default 3."""
    config = load_typed_config(adj_dir / "adjutant.yaml")
    return config.notifications.max_per_day


def send_notify(
    message: str,
    adj_dir: Path,
    *,
    env_path: Path | None = None,
    today: date | None = None,
) -> tuple[int, int]:
    """Send a Telegram notification, enforcing the daily budget.

    Args:
        message: Text to send.
        adj_dir: Adjutant root directory (for state/ and adjutant.yaml).
        env_path: Override .env path (for testing).
        today: Override today's date (for testing).

    Returns:
        Tuple of (new_count, max_per_day).

    Raises:
        BudgetExceededError: If the daily limit is reached.
        RuntimeError: If credentials are missing.
    """
    state_dir = adj_dir / "state"
    max_per_day = get_max_per_day(adj_dir)
    count = _read_count(state_dir, today)

    if count >= max_per_day:
        raise BudgetExceededError(count, max_per_day)

    bot_token, chat_id = require_telegram_credentials(env_path or (adj_dir / ".env"))

    sanitized = sanitize_message(message, _TELEGRAM_NOTIFY_MAX_LEN)
    if not sanitized:
        raise ValueError("Message is empty after sanitisation")

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": sanitized}

    client = get_client()
    resp = client.post(url, json_data=payload)

    # Verify Telegram accepted the message before counting it
    if not resp.get("ok"):
        error_desc = resp.get("description", "unknown error")
        raise RuntimeError(f"Telegram API rejected notification: {error_desc}")

    new_count = count + 1
    _write_count(state_dir, new_count, today)
    return new_count, max_per_day


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: notify.py <message>"""
    import os

    args = argv if argv is not None else sys.argv[1:]

    if not args:
        sys.stderr.write('Usage: notify.py "message"\n')
        return 1

    message = args[0]
    adj_dir_str = os.environ.get("ADJ_DIR", "").strip()
    if not adj_dir_str:
        sys.stderr.write("ERROR: ADJ_DIR not set\n")
        return 1

    adj_dir = Path(adj_dir_str)

    try:
        new_count, max_per_day = send_notify(message, adj_dir)
        print(f"Sent. ({new_count}/{max_per_day} today)")
        return 0
    except BudgetExceededError as exc:
        print(f"ERROR:{exc}")
        return 1
    except (RuntimeError, ValueError) as exc:
        sys.stderr.write(f"ERROR: {exc}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
