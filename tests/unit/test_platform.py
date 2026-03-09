"""Tests for adjutant.core.platform — OS detection and portable utilities."""

from __future__ import annotations

import os
import re
import time
from pathlib import Path

import pytest

from adjutant.core.platform import (
    ADJUTANT_OS,
    date_subtract,
    date_subtract_epoch,
    detect_os,
    ensure_path,
    file_mtime,
    file_size,
)


class TestDetectOs:
    """Test OS detection."""

    def test_returns_known_value(self):
        assert ADJUTANT_OS in ("macos", "linux", "unknown")

    def test_detect_os_returns_string(self):
        result = detect_os()
        assert isinstance(result, str)
        assert result in ("macos", "linux", "unknown")


class TestDateSubtract:
    """Test date_subtract() — portable date arithmetic."""

    def test_hours_returns_iso8601(self):
        result = date_subtract(5, "hours")
        assert re.match(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", result)

    def test_days(self):
        result = date_subtract(7, "days")
        assert re.match(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", result)

    def test_minutes(self):
        result = date_subtract(30, "minutes")
        assert re.match(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", result)

    def test_seconds(self):
        result = date_subtract(60, "seconds")
        assert re.match(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", result)

    def test_singular_unit(self):
        """Singular forms (hour, day) work."""
        result = date_subtract(1, "hour")
        assert re.match(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", result)

    def test_unknown_unit_raises(self):
        with pytest.raises(ValueError, match="Unknown unit"):
            date_subtract(5, "fortnights")


class TestDateSubtractEpoch:
    """Test date_subtract_epoch() — returns epoch seconds."""

    def test_returns_integer(self):
        result = date_subtract_epoch(1, "hours")
        assert isinstance(result, int)

    def test_value_is_in_past(self):
        result = date_subtract_epoch(1, "hours")
        assert result < time.time()

    def test_unknown_unit_raises(self):
        with pytest.raises(ValueError):
            date_subtract_epoch(5, "lightyears")


class TestFileMtime:
    """Test file_mtime() — file modification time."""

    def test_existing_file(self, tmp_path: Path):
        f = tmp_path / "test.txt"
        f.write_text("hello")
        mtime, success = file_mtime(f)
        assert success is True
        assert mtime > 0

    def test_missing_file(self, tmp_path: Path):
        mtime, success = file_mtime(tmp_path / "nonexistent.txt")
        assert success is False
        assert mtime == 0


class TestFileSize:
    """Test file_size() — file size in bytes."""

    def test_existing_file(self, tmp_path: Path):
        f = tmp_path / "test.txt"
        f.write_text("hello")
        size, success = file_size(f)
        assert success is True
        assert size == 5

    def test_empty_file(self, tmp_path: Path):
        f = tmp_path / "empty.txt"
        f.write_text("")
        size, success = file_size(f)
        assert success is True
        assert size == 0

    def test_missing_file(self, tmp_path: Path):
        size, success = file_size(tmp_path / "nonexistent.txt")
        assert success is False
        assert size == 0


class TestEnsurePath:
    """Test ensure_path() — PATH management."""

    def test_idempotent(self, monkeypatch: pytest.MonkeyPatch):
        """Calling ensure_path twice doesn't duplicate entries."""
        original = os.environ.get("PATH", "")
        ensure_path()
        path_after_first = os.environ["PATH"]
        ensure_path()
        path_after_second = os.environ["PATH"]
        assert path_after_first == path_after_second

    def test_preserves_existing_entries(self, monkeypatch: pytest.MonkeyPatch):
        """Existing PATH entries are preserved."""
        monkeypatch.setenv("PATH", "/custom/bin:/usr/bin")
        ensure_path()
        assert "/custom/bin" in os.environ["PATH"]
