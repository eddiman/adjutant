"""Tests for src/adjutant/observability/journal_rotate.py"""

from __future__ import annotations

import gzip
import os
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from adjutant.observability.journal_rotate import (
    RotateConfig,
    RotateResult,
    _is_older_than,
    rotate_journal,
    rotate_news,
    rotate_log,
    rotate_all,
    main,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_adj_dir(tmp_path: Path) -> Path:
    """Create a minimal adjutant directory layout."""
    (tmp_path / "state").mkdir()
    (tmp_path / "journal").mkdir()
    (tmp_path / "journal" / "news").mkdir()
    return tmp_path


def _old_file(parent: Path, name: str, days_old: int = 60) -> Path:
    """Create a file and backdate its mtime."""
    f = parent / name
    f.write_text(f"# {name}\n")
    old_time = time.time() - days_old * 86400
    os.utime(f, (old_time, old_time))
    return f


def _new_file(parent: Path, name: str) -> Path:
    """Create a file with current mtime."""
    f = parent / name
    f.write_text(f"# {name}\n")
    return f


# ---------------------------------------------------------------------------
# _is_older_than
# ---------------------------------------------------------------------------


class TestIsOlderThan:
    def test_old_file_returns_true(self, tmp_path: Path) -> None:
        f = _old_file(tmp_path, "old.md", days_old=60)
        assert _is_older_than(f, 30) is True

    def test_new_file_returns_false(self, tmp_path: Path) -> None:
        f = _new_file(tmp_path, "new.md")
        assert _is_older_than(f, 30) is False

    def test_missing_file_returns_false(self, tmp_path: Path) -> None:
        assert _is_older_than(tmp_path / "ghost.md", 30) is False


# ---------------------------------------------------------------------------
# rotate_journal
# ---------------------------------------------------------------------------


class TestRotateJournal:
    def test_archives_old_entries(self, tmp_path: Path) -> None:
        adj_dir = _make_adj_dir(tmp_path)
        journal_dir = adj_dir / "journal"
        _old_file(journal_dir, "2025-01-01.md")
        _old_file(journal_dir, "2025-01-02.md")
        _new_file(journal_dir, "2026-03-08.md")  # recent, should NOT be archived

        config = RotateConfig(retention_days=30)
        count = rotate_journal(adj_dir, config, quiet=True)

        assert count == 2
        archive_dir = journal_dir / ".archive"
        assert (archive_dir / "2025-01-01.md.gz").is_file()
        assert (archive_dir / "2025-01-02.md.gz").is_file()
        assert not (journal_dir / "2025-01-01.md").exists()
        assert (journal_dir / "2026-03-08.md").exists()  # recent untouched

    def test_archived_file_is_valid_gzip(self, tmp_path: Path) -> None:
        adj_dir = _make_adj_dir(tmp_path)
        journal_dir = adj_dir / "journal"
        _old_file(journal_dir, "entry.md")

        config = RotateConfig(retention_days=30)
        rotate_journal(adj_dir, config, quiet=True)

        gz_path = journal_dir / ".archive" / "entry.md.gz"
        with gzip.open(gz_path, "rt") as f:
            content = f.read()
        assert "entry.md" in content

    def test_dry_run_does_not_archive(self, tmp_path: Path) -> None:
        adj_dir = _make_adj_dir(tmp_path)
        journal_dir = adj_dir / "journal"
        _old_file(journal_dir, "old.md")

        config = RotateConfig(retention_days=30)
        count = rotate_journal(adj_dir, config, dry_run=True, quiet=True)

        assert count == 1
        assert not (journal_dir / ".archive").exists()
        assert (journal_dir / "old.md").exists()

    def test_skips_when_no_journal_dir(self, tmp_path: Path) -> None:
        # No journal dir created
        config = RotateConfig(retention_days=30)
        count = rotate_journal(tmp_path, config, quiet=True)
        assert count == 0

    def test_skips_when_nothing_old(self, tmp_path: Path) -> None:
        adj_dir = _make_adj_dir(tmp_path)
        _new_file(adj_dir / "journal", "today.md")

        config = RotateConfig(retention_days=30)
        count = rotate_journal(adj_dir, config, quiet=True)
        assert count == 0


# ---------------------------------------------------------------------------
# rotate_news
# ---------------------------------------------------------------------------


class TestRotateNews:
    def test_archives_old_news(self, tmp_path: Path) -> None:
        adj_dir = _make_adj_dir(tmp_path)
        news_dir = adj_dir / "journal" / "news"
        _old_file(news_dir, "briefing-old.md", days_old=30)
        _new_file(news_dir, "briefing-today.md")

        config = RotateConfig(news_retention_days=14)
        count = rotate_news(adj_dir, config, quiet=True)

        assert count == 1
        assert (news_dir / ".archive" / "briefing-old.md.gz").is_file()
        assert not (news_dir / "briefing-old.md").exists()
        assert (news_dir / "briefing-today.md").exists()

    def test_dry_run_no_archive(self, tmp_path: Path) -> None:
        adj_dir = _make_adj_dir(tmp_path)
        news_dir = adj_dir / "journal" / "news"
        _old_file(news_dir, "old-news.md", days_old=30)

        config = RotateConfig(news_retention_days=14)
        count = rotate_news(adj_dir, config, dry_run=True, quiet=True)

        assert count == 1
        assert not (news_dir / ".archive").exists()

    def test_skips_when_no_news_dir(self, tmp_path: Path) -> None:
        adj_dir = _make_adj_dir(tmp_path)
        (adj_dir / "journal" / "news").rmdir()

        config = RotateConfig(news_retention_days=14)
        count = rotate_news(adj_dir, config, quiet=True)
        assert count == 0


# ---------------------------------------------------------------------------
# rotate_log
# ---------------------------------------------------------------------------


class TestRotateLog:
    def _make_log(self, adj_dir: Path, size_kb: int) -> Path:
        log = adj_dir / "state" / "adjutant.log"
        log.write_bytes(b"x" * size_kb * 1024)
        return log

    def test_rotates_when_oversized(self, tmp_path: Path) -> None:
        adj_dir = _make_adj_dir(tmp_path)
        log = self._make_log(adj_dir, 6000)

        config = RotateConfig(log_max_size_kb=5120, log_rotations=3)
        rotated = rotate_log(adj_dir, config, quiet=True)

        assert rotated is True
        assert (adj_dir / "state" / "adjutant.log.1.gz").is_file()
        assert log.stat().st_size == 0  # truncated, not deleted

    def test_compressed_backup_is_valid_gzip(self, tmp_path: Path) -> None:
        adj_dir = _make_adj_dir(tmp_path)
        self._make_log(adj_dir, 6000)

        config = RotateConfig(log_max_size_kb=5120, log_rotations=3)
        rotate_log(adj_dir, config, quiet=True)

        gz = adj_dir / "state" / "adjutant.log.1.gz"
        with gzip.open(gz, "rb") as f:
            data = f.read()
        assert len(data) == 6000 * 1024

    def test_skips_when_undersized(self, tmp_path: Path) -> None:
        adj_dir = _make_adj_dir(tmp_path)
        self._make_log(adj_dir, 100)

        config = RotateConfig(log_max_size_kb=5120, log_rotations=3)
        rotated = rotate_log(adj_dir, config, quiet=True)

        assert rotated is False
        assert not (adj_dir / "state" / "adjutant.log.1.gz").exists()

    def test_shifts_rotation_chain(self, tmp_path: Path) -> None:
        adj_dir = _make_adj_dir(tmp_path)
        state = adj_dir / "state"
        # Pre-create existing backups
        (state / "adjutant.log.1.gz").write_bytes(b"old1")
        (state / "adjutant.log.2.gz").write_bytes(b"old2")
        self._make_log(adj_dir, 6000)

        config = RotateConfig(log_max_size_kb=5120, log_rotations=3)
        rotate_log(adj_dir, config, quiet=True)

        assert (state / "adjutant.log.3.gz").is_file()
        assert (state / "adjutant.log.2.gz").is_file()
        assert (state / "adjutant.log.1.gz").is_file()

    def test_removes_excess_rotations(self, tmp_path: Path) -> None:
        adj_dir = _make_adj_dir(tmp_path)
        state = adj_dir / "state"
        # 3 existing rotations + current = would make 4, but limit is 3
        (state / "adjutant.log.1.gz").write_bytes(b"r1")
        (state / "adjutant.log.2.gz").write_bytes(b"r2")
        (state / "adjutant.log.3.gz").write_bytes(b"r3")
        self._make_log(adj_dir, 6000)

        config = RotateConfig(log_max_size_kb=5120, log_rotations=3)
        rotate_log(adj_dir, config, quiet=True)

        # .4.gz should NOT exist
        assert not (state / "adjutant.log.4.gz").exists()

    def test_dry_run_does_not_rotate(self, tmp_path: Path) -> None:
        adj_dir = _make_adj_dir(tmp_path)
        log = self._make_log(adj_dir, 6000)
        original_size = log.stat().st_size

        config = RotateConfig(log_max_size_kb=5120, log_rotations=3)
        rotated = rotate_log(adj_dir, config, dry_run=True, quiet=True)

        assert rotated is False
        assert log.stat().st_size == original_size

    def test_skips_when_no_log(self, tmp_path: Path) -> None:
        adj_dir = _make_adj_dir(tmp_path)
        config = RotateConfig(log_max_size_kb=5120, log_rotations=3)
        rotated = rotate_log(adj_dir, config, quiet=True)
        assert rotated is False


# ---------------------------------------------------------------------------
# rotate_all
# ---------------------------------------------------------------------------


class TestRotateAll:
    def test_returns_rotate_result(self, tmp_path: Path) -> None:
        adj_dir = _make_adj_dir(tmp_path)
        config = RotateConfig()
        result = rotate_all(adj_dir, quiet=True, config=config)
        assert isinstance(result, RotateResult)

    def test_runs_all_three_steps(self, tmp_path: Path) -> None:
        adj_dir = _make_adj_dir(tmp_path)
        journal_dir = adj_dir / "journal"
        news_dir = journal_dir / "news"
        state_dir = adj_dir / "state"

        _old_file(journal_dir, "j.md")
        _old_file(news_dir, "n.md", days_old=30)
        log = state_dir / "adjutant.log"
        log.write_bytes(b"x" * 6000 * 1024)

        config = RotateConfig(
            retention_days=30,
            news_retention_days=14,
            log_max_size_kb=5120,
            log_rotations=3,
        )
        result = rotate_all(adj_dir, quiet=True, config=config)

        assert result.archived_journal == 1
        assert result.archived_news == 1
        assert result.log_rotated is True
        assert result.anything_done is True
        assert result.total_archived == 2

    def test_nothing_done_when_all_current(self, tmp_path: Path) -> None:
        adj_dir = _make_adj_dir(tmp_path)
        _new_file(adj_dir / "journal", "today.md")
        _new_file(adj_dir / "journal" / "news", "news-today.md")
        # Log is small
        (adj_dir / "state" / "adjutant.log").write_bytes(b"tiny log")

        config = RotateConfig()
        result = rotate_all(adj_dir, quiet=True, config=config)

        assert result.anything_done is False


# ---------------------------------------------------------------------------
# main (CLI)
# ---------------------------------------------------------------------------


class TestMain:
    def test_returns_0_on_success(self, tmp_path: Path) -> None:
        _make_adj_dir(tmp_path)
        with patch.dict(os.environ, {"ADJ_DIR": str(tmp_path)}):
            rc = main(["--quiet"])
        assert rc == 0

    def test_returns_1_when_adj_dir_missing(self) -> None:
        env = {k: v for k, v in os.environ.items() if k != "ADJ_DIR"}
        with patch.dict(os.environ, env, clear=True):
            rc = main(["--quiet"])
        assert rc == 1

    def test_returns_1_on_nonexistent_adj_dir(self, tmp_path: Path) -> None:
        with patch.dict(os.environ, {"ADJ_DIR": str(tmp_path / "nope")}):
            rc = main(["--quiet"])
        assert rc == 1

    def test_returns_0_for_help(self, tmp_path: Path) -> None:
        rc = main(["--help"])
        assert rc == 0

    def test_returns_1_on_unknown_flag(self) -> None:
        rc = main(["--unknown-flag"])
        assert rc == 1

    def test_dry_run_flag_passed_through(self, tmp_path: Path) -> None:
        _make_adj_dir(tmp_path)
        with (
            patch.dict(os.environ, {"ADJ_DIR": str(tmp_path)}),
            patch("adjutant.observability.journal_rotate.rotate_all") as mock_rotate,
        ):
            mock_rotate.return_value = RotateResult()
            main(["--dry-run", "--quiet"])

        call_kwargs = mock_rotate.call_args[1]
        assert call_kwargs["dry_run"] is True
        assert call_kwargs["quiet"] is True
