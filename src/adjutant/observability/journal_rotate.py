"""Archive old journal entries and rotate the operational log.

Replaces: scripts/observability/journal_rotate.sh

Three rotation targets:
  1. journal/*.md          → journal/.archive/  (gzip-compressed)
  2. journal/news/*.md     → journal/news/.archive/ (gzip-compressed)
  3. state/adjutant.log    → state/adjutant.log.1.gz (shift rotation chain)

Configuration (from adjutant.yaml under the ``journal`` key):
  journal.retention_days      — days to keep uncompressed (default: 30)
  journal.news_retention_days — days to keep news entries (default: 14)
  journal.log_max_size_kb     — rotate log when it exceeds this (default: 5120 KB)
  journal.log_rotations       — number of compressed log backups (default: 3)

Exit codes mirror the bash script:
  0 — success (or nothing to do)
  SystemExit(1) — fatal error
"""

from __future__ import annotations

import gzip
import os
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from adjutant.core.config import load_typed_config
from adjutant.core.logging import adj_log


@dataclass
class RotateConfig:
    """Resolved rotation parameters."""

    retention_days: int = 30
    news_retention_days: int = 14
    log_max_size_kb: int = 5120
    log_rotations: int = 3

    @classmethod
    def from_adj_dir(cls, adj_dir: Path) -> RotateConfig:
        """Load from adjutant.yaml in adj_dir."""
        cfg = load_typed_config(adj_dir / "adjutant.yaml")
        j = cfg.journal
        return cls(
            retention_days=j.retention_days,
            news_retention_days=j.news_retention_days,
            log_max_size_kb=j.log_max_size_kb,
            log_rotations=j.log_rotations,
        )


@dataclass
class RotateResult:
    """Summary of a rotation run."""

    archived_journal: int = 0
    archived_news: int = 0
    log_rotated: bool = False

    @property
    def total_archived(self) -> int:
        return self.archived_journal + self.archived_news

    @property
    def anything_done(self) -> bool:
        return self.total_archived > 0 or self.log_rotated


def _is_older_than(path: Path, days: int) -> bool:
    """Return True if the file's mtime is older than `days` days."""
    cutoff = time.time() - days * 86400
    try:
        return path.stat().st_mtime < cutoff
    except OSError:
        return False


def _gzip_file(src: Path, dest: Path) -> None:
    """Compress src into dest (a .gz file)."""
    with src.open("rb") as f_in, gzip.open(dest, "wb") as f_out:
        shutil.copyfileobj(f_in, f_out)


def rotate_journal(
    adj_dir: Path,
    config: RotateConfig,
    *,
    dry_run: bool = False,
    quiet: bool = False,
) -> int:
    """Archive old main journal entries.

    Returns:
        Number of entries archived.
    """
    journal_dir = adj_dir / "journal"
    archive_dir = journal_dir / ".archive"

    if not journal_dir.is_dir():
        if not quiet:
            print("No journal directory found, skipping.")
        return 0

    old_files = [
        f
        for f in journal_dir.glob("*.md")
        if f.is_file() and _is_older_than(f, config.retention_days)
    ]

    if not old_files:
        if not quiet:
            print(f"Journal: nothing to archive (retention: {config.retention_days} days)")
        return 0

    if not dry_run:
        archive_dir.mkdir(parents=True, exist_ok=True)

    count = 0
    for md_file in sorted(old_files):
        if dry_run:
            if not quiet:
                print(f"  [dry-run] Would archive: {md_file.name}")
        else:
            dest = archive_dir / f"{md_file.name}.gz"
            _gzip_file(md_file, dest)
            md_file.unlink()
            adj_log("journal", f"Archived: {md_file.name}")
        count += 1

    if not quiet:
        print(f"Journal: archived {count} entries → .archive/")
    return count


def rotate_news(
    adj_dir: Path,
    config: RotateConfig,
    *,
    dry_run: bool = False,
    quiet: bool = False,
) -> int:
    """Archive old news journal entries.

    Returns:
        Number of entries archived.
    """
    news_dir = adj_dir / "journal" / "news"
    archive_dir = news_dir / ".archive"

    if not news_dir.is_dir():
        if not quiet:
            print("No news journal directory found, skipping.")
        return 0

    old_files = [
        f
        for f in news_dir.glob("*.md")
        if f.is_file() and _is_older_than(f, config.news_retention_days)
    ]

    if not old_files:
        if not quiet:
            print(f"News:    nothing to archive (retention: {config.news_retention_days} days)")
        return 0

    if not dry_run:
        archive_dir.mkdir(parents=True, exist_ok=True)

    count = 0
    for md_file in sorted(old_files):
        if dry_run:
            if not quiet:
                print(f"  [dry-run] Would archive news: {md_file.name}")
        else:
            dest = archive_dir / f"{md_file.name}.gz"
            _gzip_file(md_file, dest)
            md_file.unlink()
            adj_log("journal", f"Archived news: {md_file.name}")
        count += 1

    if not quiet:
        print(f"News:    archived {count} entries → news/.archive/")
    return count


def rotate_log(
    adj_dir: Path,
    config: RotateConfig,
    *,
    dry_run: bool = False,
    quiet: bool = False,
) -> bool:
    """Rotate state/adjutant.log if it exceeds the size threshold.

    Rotation scheme (matching bash):
      .N.gz → delete if N > log_rotations
      .2.gz → .3.gz, .1.gz → .2.gz (shift chain)
      current → .1.gz (compress)
      truncate current (don't delete — avoids race with concurrent writers)

    Returns:
        True if the log was rotated, False if skipped.
    """
    log_file = adj_dir / "state" / "adjutant.log"

    if not log_file.is_file():
        if not quiet:
            print("Log:     no adjutant.log found, skipping.")
        return False

    size_kb = log_file.stat().st_size // 1024

    if size_kb < config.log_max_size_kb:
        if not quiet:
            print(
                f"Log:     adjutant.log is {size_kb}KB "
                f"(threshold: {config.log_max_size_kb}KB), skipping."
            )
        return False

    if dry_run:
        if not quiet:
            print(
                f"  [dry-run] Would rotate adjutant.log "
                f"({size_kb}KB > {config.log_max_size_kb}KB threshold)"
            )
        return False

    # Shift existing rotations: .N → .N+1, delete if > log_rotations
    for i in range(config.log_rotations, 1, -1):
        src = Path(f"{log_file}.{i - 1}.gz")
        dst = Path(f"{log_file}.{i}.gz")
        if src.is_file():
            src.rename(dst)

    # Compress current log → .1.gz
    _gzip_file(log_file, Path(f"{log_file}.1.gz"))

    # Truncate (don't delete — matches bash `: > "$LOG_FILE"`)
    log_file.write_bytes(b"")

    # Clean up any rotations beyond the limit
    i = config.log_rotations + 1
    while True:
        extra = Path(f"{log_file}.{i}.gz")
        if not extra.is_file():
            break
        extra.unlink()
        i += 1

    adj_log("journal", f"Rotated adjutant.log (was {size_kb}KB)")
    if not quiet:
        print(
            f"Log:     rotated adjutant.log "
            f"({size_kb}KB → .1.gz, kept {config.log_rotations} backups)"
        )
    return True


def rotate_all(
    adj_dir: Path,
    *,
    dry_run: bool = False,
    quiet: bool = False,
    config: RotateConfig | None = None,
) -> RotateResult:
    """Run all three rotation steps.

    Args:
        adj_dir: Adjutant root directory.
        dry_run: Show what would happen without doing it.
        quiet: Suppress all output (for cron invocation).
        config: Override rotation config (for testing).

    Returns:
        RotateResult summary.
    """
    if config is None:
        config = RotateConfig.from_adj_dir(adj_dir)

    if not quiet:
        label = "=== Journal Rotation (dry run) ===" if dry_run else "=== Journal Rotation ==="
        print(label)

    result = RotateResult()
    result.archived_journal = rotate_journal(adj_dir, config, dry_run=dry_run, quiet=quiet)
    result.archived_news = rotate_news(adj_dir, config, dry_run=dry_run, quiet=quiet)
    result.log_rotated = rotate_log(adj_dir, config, dry_run=dry_run, quiet=quiet)

    if not dry_run and not quiet:
        if result.anything_done:
            print(f"Done. Archived {result.total_archived} journal entries.")
        else:
            print("Nothing to rotate.")

    return result


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: journal_rotate [--dry-run] [--quiet] [--help]"""
    args = argv if argv is not None else sys.argv[1:]

    dry_run = False
    quiet = False

    for arg in args:
        if arg in ("--dry-run",):
            dry_run = True
        elif arg in ("--quiet",):
            quiet = True
        elif arg in ("--help", "-h"):
            print(
                "Usage: journal_rotate [--dry-run] [--quiet]\n"
                "\n"
                "Options:\n"
                "  --dry-run   Show what would be archived without doing it\n"
                "  --quiet     Suppress output (for cron jobs)\n"
                "  --help      Show this help\n"
                "\n"
                "Rotates old journal entries, news briefings, and the operational log."
            )
            return 0
        else:
            sys.stderr.write(f"Unknown option: {arg}\n")
            sys.stderr.write("Run with --help for usage.\n")
            return 1

    adj_dir_str = os.environ.get("ADJ_DIR", "").strip()
    if not adj_dir_str:
        sys.stderr.write("ERROR: ADJ_DIR not set\n")
        return 1

    adj_dir = Path(adj_dir_str)
    if not adj_dir.is_dir():
        sys.stderr.write(f"ERROR: ADJ_DIR does not exist: {adj_dir}\n")
        return 1

    try:
        rotate_all(adj_dir, dry_run=dry_run, quiet=quiet)
        return 0
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"ERROR: {exc}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
