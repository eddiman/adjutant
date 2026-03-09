"""Tests for adjutant.core.logging — Structured logging."""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from adjutant.core.logging import (
    _sanitize_message,
    adj_log,
    fmt_ts,
    log_debug,
    log_error,
    log_warn,
)


class TestAdjLog:
    """Test adj_log() — primary log function."""

    def test_basic_log_format(self, adj_dir: Path):
        log_file = adj_dir / "state" / "adjutant.log"
        adj_log("telegram", "Received message", log_file=log_file)
        content = log_file.read_text()
        # Format: [HH:MM DD.MM.YYYY] [telegram] Received message
        assert re.match(
            r"\[\d{2}:\d{2} \d{2}\.\d{2}\.\d{4}\] \[telegram\] Received message\n",
            content,
        )

    def test_append_only(self, adj_dir: Path):
        log_file = adj_dir / "state" / "adjutant.log"
        adj_log("test", "first", log_file=log_file)
        adj_log("test", "second", log_file=log_file)
        lines = log_file.read_text().splitlines()
        assert len(lines) == 2
        assert "first" in lines[0]
        assert "second" in lines[1]

    def test_default_context(self, adj_dir: Path):
        """adj_log uses the provided context."""
        log_file = adj_dir / "state" / "adjutant.log"
        adj_log("opencode", "test msg", log_file=log_file)
        assert "[opencode]" in log_file.read_text()

    def test_creates_state_dir(self, adj_dir: Path):
        """adj_log creates state dir if it doesn't exist."""
        # Remove state dir
        import shutil

        state = adj_dir / "state"
        if state.exists():
            shutil.rmtree(state)
        log_file = adj_dir / "state" / "adjutant.log"
        adj_log("test", "msg", log_file=log_file)
        # It should succeed (we pass log_file directly, so state dir creation
        # is handled by _log_path, but we write to explicit path)
        # Actually let's test the default path behavior
        adj_log("test", "auto path")  # Uses _log_path() which creates state dir
        assert (adj_dir / "state").is_dir()

    def test_control_char_stripping(self, adj_dir: Path):
        log_file = adj_dir / "state" / "adjutant.log"
        adj_log("test", "hello\x00world\x01end", log_file=log_file)
        content = log_file.read_text()
        assert "helloworld" in content
        assert "\x00" not in content
        assert "\x01" not in content

    def test_newline_replaced_with_space(self, adj_dir: Path):
        log_file = adj_dir / "state" / "adjutant.log"
        adj_log("test", "line1\nline2", log_file=log_file)
        content = log_file.read_text()
        assert "line1 line2" in content

    def test_tab_replaced_with_space(self, adj_dir: Path):
        log_file = adj_dir / "state" / "adjutant.log"
        adj_log("test", "col1\tcol2", log_file=log_file)
        content = log_file.read_text()
        assert "col1 col2" in content

    def test_carriage_return_stripped(self, adj_dir: Path):
        log_file = adj_dir / "state" / "adjutant.log"
        adj_log("test", "hello\rworld", log_file=log_file)
        content = log_file.read_text()
        assert "hello world" in content


class TestSanitizeMessage:
    """Test _sanitize_message() directly."""

    def test_normal_text_unchanged(self):
        assert _sanitize_message("hello world") == "hello world"

    def test_null_bytes_stripped(self):
        assert _sanitize_message("a\x00b") == "ab"

    def test_newlines_to_spaces(self):
        assert _sanitize_message("a\nb\nc") == "a b c"

    def test_tabs_to_spaces(self):
        assert _sanitize_message("a\tb") == "a b"

    def test_empty_string(self):
        assert _sanitize_message("") == ""

    def test_unicode_preserved(self):
        assert _sanitize_message("hello 🌍 world") == "hello 🌍 world"


class TestFmtTs:
    """Test fmt_ts() — ISO-8601 to European format conversion."""

    def test_iso8601_with_z(self):
        result = fmt_ts("2026-02-26T14:30:00Z")
        assert result == "14:30 26.02.2026"

    def test_iso8601_without_z(self):
        result = fmt_ts("2026-02-26T14:30:00")
        assert result == "14:30 26.02.2026"

    def test_date_with_space(self):
        result = fmt_ts("2026-02-26 14:30:00")
        assert result == "14:30 26.02.2026"

    def test_date_only(self):
        result = fmt_ts("2026-02-26")
        assert result == "00:00 26.02.2026"

    def test_empty_input(self):
        assert fmt_ts("") == ""

    def test_whitespace_only(self):
        assert fmt_ts("   ") == ""

    def test_unparseable_passthrough(self):
        """Unparseable strings are returned as-is."""
        assert fmt_ts("not-a-date") == "not-a-date"

    def test_iso8601_with_timezone(self):
        result = fmt_ts("2026-02-26T14:30:00+01:00")
        assert result == "14:30 26.02.2026"


class TestLogError:
    """Test log_error() — writes to both log and stderr."""

    def test_log_error_writes_to_file(self, adj_dir: Path):
        log_file = adj_dir / "state" / "adjutant.log"
        log_error("test", "something failed", log_file=log_file)
        content = log_file.read_text()
        assert "ERROR: something failed" in content
        assert "[test]" in content

    def test_log_error_writes_to_stderr(self, adj_dir: Path, capsys):
        log_file = adj_dir / "state" / "adjutant.log"
        log_error("test", "bad thing", log_file=log_file)
        captured = capsys.readouterr()
        assert "ERROR [test]: bad thing" in captured.err


class TestLogWarn:
    """Test log_warn() — writes to log file only."""

    def test_log_warn_writes_to_file(self, adj_dir: Path):
        log_file = adj_dir / "state" / "adjutant.log"
        log_warn("test", "slow response", log_file=log_file)
        content = log_file.read_text()
        assert "WARNING: slow response" in content

    def test_log_warn_not_to_stderr(self, adj_dir: Path, capsys):
        log_file = adj_dir / "state" / "adjutant.log"
        log_warn("test", "slow response", log_file=log_file)
        captured = capsys.readouterr()
        assert captured.err == ""


class TestLogDebug:
    """Test log_debug() — conditional on env var."""

    def test_debug_writes_when_enabled(self, adj_dir: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setenv("ADJUTANT_DEBUG", "1")
        log_file = adj_dir / "state" / "adjutant.log"
        log_debug("test", "verbose info", log_file=log_file)
        content = log_file.read_text()
        assert "DEBUG: verbose info" in content

    def test_debug_silent_when_disabled(self, adj_dir: Path, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.delenv("ADJUTANT_DEBUG", raising=False)
        monkeypatch.delenv("DEBUG", raising=False)
        log_file = adj_dir / "state" / "adjutant.log"
        log_debug("test", "verbose info", log_file=log_file)
        assert not log_file.exists()

    def test_debug_writes_when_debug_env(self, adj_dir: Path, monkeypatch: pytest.MonkeyPatch):
        """DEBUG env var also enables debug logging."""
        monkeypatch.delenv("ADJUTANT_DEBUG", raising=False)
        monkeypatch.setenv("DEBUG", "1")
        log_file = adj_dir / "state" / "adjutant.log"
        log_debug("test", "verbose info", log_file=log_file)
        content = log_file.read_text()
        assert "DEBUG: verbose info" in content
