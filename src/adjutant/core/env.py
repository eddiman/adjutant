"""Credential loading — secure .env file extraction.

Security: Never ``exec``/``source`` the .env file. Uses line-by-line parsing
with quote stripping, matching the bash ``grep | head -1 | cut -d'=' -f2- | tr -d "'\\"``
pattern from env.sh.
"""

from __future__ import annotations

import os
from pathlib import Path


def _env_file_path() -> Path:
    """Return the path to the .env file."""
    adj_dir = os.environ.get("ADJ_DIR", "").strip()
    if not adj_dir:
        raise RuntimeError("ADJ_DIR not set. Call init_adj_dir() (from paths.py) first.")
    return Path(adj_dir) / ".env"


def load_env(env_path: Path | None = None) -> bool:
    """Verify the .env file exists.

    Args:
        env_path: Explicit path to .env file. Defaults to $ADJ_DIR/.env.

    Returns:
        True if the file exists, False otherwise.
    """
    path = env_path or _env_file_path()
    return path.is_file()


def get_credential(key: str, env_path: Path | None = None) -> str | None:
    """Extract a single credential value by key name.

    Matches bash: ``grep -E '^KEY=' .env | head -1 | cut -d'=' -f2- | tr -d "'\\"``

    Args:
        key: The environment variable name to extract.
        env_path: Explicit path to .env file. Defaults to $ADJ_DIR/.env.

    Returns:
        The credential value with surrounding quotes stripped, or None if not found
        or the .env file doesn't exist.
    """
    path = env_path or _env_file_path()
    if not path.is_file():
        return None

    prefix = f"{key}="
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if stripped.startswith(prefix):
            value = stripped[len(prefix) :]
            # Strip surrounding single or double quotes (matches tr -d "'\"")
            value = value.strip("'\"")
            return value

    return None


def has_credential(key: str, env_path: Path | None = None) -> bool:
    """Check if a credential is set (non-empty).

    Args:
        key: The environment variable name to check.
        env_path: Explicit path to .env file.

    Returns:
        True if the credential exists and is non-empty.
    """
    value = get_credential(key, env_path)
    return bool(value)


def require_telegram_credentials(env_path: Path | None = None) -> tuple[str, str]:
    """Load and validate Telegram credentials.

    Returns:
        Tuple of (bot_token, chat_id).

    Raises:
        RuntimeError: If .env is missing or credentials are incomplete.
    """
    path = env_path or _env_file_path()
    if not load_env(path):
        raise RuntimeError(f"{path} not found. Create it from .env.example with your credentials.")

    bot_token = get_credential("TELEGRAM_BOT_TOKEN", path)
    chat_id = get_credential("TELEGRAM_CHAT_ID", path)

    if not bot_token or not chat_id:
        raise RuntimeError(f"TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set in {path}")

    return bot_token, chat_id
