"""Tests for adjutant.core.env — Credential loading."""

from __future__ import annotations

from pathlib import Path

import pytest

from adjutant.core.env import (
    get_credential,
    has_credential,
    load_env,
    require_telegram_credentials,
)


class TestLoadEnv:
    """Test load_env() — .env file existence check."""

    def test_load_env_success(self, adj_env: Path, adj_dir: Path):
        assert load_env(adj_env) is True

    def test_load_env_missing_file(self, adj_dir: Path):
        assert load_env(adj_dir / ".env") is False

    def test_load_env_default_path(self, adj_env: Path, adj_dir: Path):
        """load_env() with no args uses $ADJ_DIR/.env."""
        assert load_env() is True

    def test_load_env_no_adj_dir(self, monkeypatch: pytest.MonkeyPatch):
        """load_env() with no ADJ_DIR and no explicit path raises."""
        monkeypatch.delenv("ADJ_DIR", raising=False)
        with pytest.raises(RuntimeError, match="ADJ_DIR not set"):
            load_env()


class TestGetCredential:
    """Test get_credential() — key extraction from .env."""

    def test_get_existing_key(self, adj_env: Path):
        assert get_credential("TELEGRAM_BOT_TOKEN", adj_env) == "test-token-123"

    def test_get_chat_id(self, adj_env: Path):
        assert get_credential("TELEGRAM_CHAT_ID", adj_env) == "12345678"

    def test_get_missing_key(self, adj_env: Path):
        assert get_credential("NONEXISTENT_KEY", adj_env) is None

    def test_get_from_missing_file(self, adj_dir: Path):
        assert get_credential("ANYTHING", adj_dir / "nonexistent.env") is None

    def test_single_quote_stripping(self, adj_dir: Path):
        env_file = adj_dir / ".env"
        env_file.write_text("MY_KEY='quoted-value'\n")
        assert get_credential("MY_KEY", env_file) == "quoted-value"

    def test_double_quote_stripping(self, adj_dir: Path):
        env_file = adj_dir / ".env"
        env_file.write_text('MY_KEY="double-quoted"\n')
        assert get_credential("MY_KEY", env_file) == "double-quoted"

    def test_no_quotes(self, adj_dir: Path):
        env_file = adj_dir / ".env"
        env_file.write_text("MY_KEY=bare-value\n")
        assert get_credential("MY_KEY", env_file) == "bare-value"

    def test_empty_value(self, adj_dir: Path):
        env_file = adj_dir / ".env"
        env_file.write_text("MY_KEY=\n")
        assert get_credential("MY_KEY", env_file) == ""

    def test_value_with_equals_sign(self, adj_dir: Path):
        """Values can contain = signs (cut -d'=' -f2- behavior)."""
        env_file = adj_dir / ".env"
        env_file.write_text("MY_KEY=abc=def=ghi\n")
        assert get_credential("MY_KEY", env_file) == "abc=def=ghi"

    def test_first_match_wins(self, adj_dir: Path):
        """Matches bash head -1 behavior — first matching line wins."""
        env_file = adj_dir / ".env"
        env_file.write_text("MY_KEY=first\nMY_KEY=second\n")
        assert get_credential("MY_KEY", env_file) == "first"

    def test_comments_and_blank_lines_skipped(self, adj_dir: Path):
        env_file = adj_dir / ".env"
        env_file.write_text("# Comment\n\nMY_KEY=value\n")
        assert get_credential("MY_KEY", env_file) == "value"

    def test_default_path_from_adj_dir(self, adj_env: Path):
        """get_credential with no path uses $ADJ_DIR/.env."""
        assert get_credential("TELEGRAM_BOT_TOKEN") == "test-token-123"


class TestHasCredential:
    """Test has_credential() — boolean check."""

    def test_has_existing_credential(self, adj_env: Path):
        assert has_credential("TELEGRAM_BOT_TOKEN", adj_env) is True

    def test_has_missing_credential(self, adj_env: Path):
        assert has_credential("NONEXISTENT", adj_env) is False

    def test_has_empty_credential(self, adj_dir: Path):
        env_file = adj_dir / ".env"
        env_file.write_text("EMPTY_KEY=\n")
        assert has_credential("EMPTY_KEY", env_file) is False


class TestRequireTelegramCredentials:
    """Test require_telegram_credentials() — validates both present."""

    def test_success(self, adj_env: Path):
        token, chat_id = require_telegram_credentials(adj_env)
        assert token == "test-token-123"
        assert chat_id == "12345678"

    def test_missing_env_file(self, adj_dir: Path):
        with pytest.raises(RuntimeError, match="not found"):
            require_telegram_credentials(adj_dir / "missing.env")

    def test_missing_token(self, adj_dir: Path):
        env_file = adj_dir / ".env"
        env_file.write_text("TELEGRAM_CHAT_ID=12345678\n")
        with pytest.raises(RuntimeError, match="must be set"):
            require_telegram_credentials(env_file)

    def test_missing_chat_id(self, adj_dir: Path):
        env_file = adj_dir / ".env"
        env_file.write_text("TELEGRAM_BOT_TOKEN=test-token\n")
        with pytest.raises(RuntimeError, match="must be set"):
            require_telegram_credentials(env_file)
