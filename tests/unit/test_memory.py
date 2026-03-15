"""Unit tests for adjutant.capabilities.memory."""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

import pytest

from adjutant.capabilities.memory.classify import (
    CATEGORIES,
    DEFAULT_CATEGORY,
    classify_memory,
)
from adjutant.capabilities.memory.memory import (
    _ensure_memory_dir,
    _file_summary,
    _fmt_size,
    _split_sections,
    memory_add,
    memory_clean_working,
    memory_digest,
    memory_forget,
    memory_index_update,
    memory_init,
    memory_recall,
    memory_status,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _memory_dir(adj_dir: Path) -> Path:
    return adj_dir / "memory"


def _scaffold(adj_dir: Path) -> Path:
    """Run memory_init and return the memory directory."""
    memory_init(adj_dir)
    return _memory_dir(adj_dir)


def _write_journal(adj_dir: Path, date_str: str, content: str) -> Path:
    """Write a journal file and return its path."""
    journal_dir = adj_dir / "journal"
    journal_dir.mkdir(parents=True, exist_ok=True)
    p = journal_dir / f"{date_str}.md"
    p.write_text(content)
    return p


# ---------------------------------------------------------------------------
# classify_memory
# ---------------------------------------------------------------------------


class TestClassifyMemory:
    def test_correction_keywords(self) -> None:
        assert classify_memory("That was wrong, the correct value is 42") == "facts/corrections.md"

    def test_decision_keywords(self) -> None:
        assert classify_memory("We decided to use PostgreSQL") == "facts/decisions.md"

    def test_people_keywords(self) -> None:
        assert classify_memory("Their name is Alice and she works at Acme") == "facts/people.md"

    def test_project_keywords(self) -> None:
        assert (
            classify_memory("The project uses a microservice architecture") == "facts/projects.md"
        )

    def test_preference_keywords(self) -> None:
        assert (
            classify_memory("I prefer terse output, never use emojis") == "patterns/preferences.md"
        )

    def test_workflow_keywords(self) -> None:
        assert (
            classify_memory("The weekly routine is to review PRs every Monday")
            == "patterns/workflows.md"
        )

    def test_exception_keywords(self) -> None:
        assert (
            classify_memory("Watch out for this edge case with the API") == "patterns/exceptions.md"
        )

    def test_defaults_to_projects_for_ambiguous(self) -> None:
        assert classify_memory("some random text with no keywords") == DEFAULT_CATEGORY

    def test_empty_text_defaults(self) -> None:
        assert classify_memory("") == DEFAULT_CATEGORY

    def test_highest_score_wins(self) -> None:
        # "decided" (decision) + "chose" (decision) + "settled on" (decision) = 3 hits
        # "wrong" (correction) = 1 hit → decision wins
        result = classify_memory(
            "We decided, chose, and settled on option B even though option A was wrong"
        )
        assert result == "facts/decisions.md"

    def test_case_insensitive(self) -> None:
        assert classify_memory("That was WRONG and INCORRECT") == "facts/corrections.md"

    def test_all_categories_have_keywords(self) -> None:
        for cat, keywords in CATEGORIES.items():
            assert len(keywords) > 0, f"{cat} has no keywords"


# ---------------------------------------------------------------------------
# memory_init
# ---------------------------------------------------------------------------


class TestMemoryInit:
    def test_creates_directory_structure(self, tmp_path: Path) -> None:
        result = memory_init(tmp_path)
        mem = _memory_dir(tmp_path)
        assert mem.is_dir()
        assert (mem / "facts").is_dir()
        assert (mem / "patterns").is_dir()
        assert (mem / "summaries" / "weekly").is_dir()
        assert (mem / "summaries" / "monthly").is_dir()
        assert (mem / "conversations").is_dir()
        assert (mem / "working").is_dir()
        assert "initialised" in result.lower()

    def test_creates_scaffold_files(self, tmp_path: Path) -> None:
        memory_init(tmp_path)
        mem = _memory_dir(tmp_path)
        assert (mem / "facts" / "people.md").is_file()
        assert (mem / "facts" / "projects.md").is_file()
        assert (mem / "facts" / "decisions.md").is_file()
        assert (mem / "facts" / "corrections.md").is_file()
        assert (mem / "patterns" / "preferences.md").is_file()
        assert (mem / "patterns" / "workflows.md").is_file()
        assert (mem / "patterns" / "exceptions.md").is_file()

    def test_creates_index_file(self, tmp_path: Path) -> None:
        memory_init(tmp_path)
        index = _memory_dir(tmp_path) / "memory.md"
        assert index.is_file()
        content = index.read_text()
        assert "Memory Index" in content

    def test_idempotent(self, tmp_path: Path) -> None:
        memory_init(tmp_path)
        # Add content to a file
        (tmp_path / "memory" / "facts" / "corrections.md").write_text(
            "# Corrections\n\n## 2026-01-01\n\nTest\n"
        )
        memory_init(tmp_path)
        # Existing content should survive
        content = (tmp_path / "memory" / "facts" / "corrections.md").read_text()
        assert "Test" in content

    def test_scaffold_files_have_headers(self, tmp_path: Path) -> None:
        memory_init(tmp_path)
        content = (tmp_path / "memory" / "facts" / "people.md").read_text()
        assert content.startswith("# People")


# ---------------------------------------------------------------------------
# _ensure_memory_dir
# ---------------------------------------------------------------------------


class TestEnsureMemoryDir:
    def test_creates_if_missing(self, tmp_path: Path) -> None:
        mem = _ensure_memory_dir(tmp_path)
        assert mem.is_dir()
        assert (mem / "facts").is_dir()

    def test_returns_existing(self, tmp_path: Path) -> None:
        _scaffold(tmp_path)
        mem = _ensure_memory_dir(tmp_path)
        assert mem == tmp_path / "memory"


# ---------------------------------------------------------------------------
# memory_add
# ---------------------------------------------------------------------------


class TestMemoryAdd:
    def test_auto_classify_and_append(self, tmp_path: Path) -> None:
        result = memory_add(tmp_path, "That was wrong, the answer is 42")
        assert "corrections" in result.lower()
        content = (tmp_path / "memory" / "facts" / "corrections.md").read_text()
        assert "the answer is 42" in content

    def test_explicit_category(self, tmp_path: Path) -> None:
        result = memory_add(tmp_path, "Custom entry", category="facts/people.md")
        assert "people" in result.lower()
        content = (tmp_path / "memory" / "facts" / "people.md").read_text()
        assert "Custom entry" in content

    def test_entry_has_timestamp(self, tmp_path: Path) -> None:
        memory_add(tmp_path, "Test entry", category="facts/decisions.md")
        content = (tmp_path / "memory" / "facts" / "decisions.md").read_text()
        today = datetime.now().strftime("%Y-%m-%d")
        assert today in content

    def test_appends_to_existing(self, tmp_path: Path) -> None:
        memory_add(tmp_path, "First entry", category="facts/projects.md")
        memory_add(tmp_path, "Second entry", category="facts/projects.md")
        content = (tmp_path / "memory" / "facts" / "projects.md").read_text()
        assert "First entry" in content
        assert "Second entry" in content

    def test_updates_index(self, tmp_path: Path) -> None:
        memory_add(tmp_path, "Something to remember", category="facts/decisions.md")
        index = (tmp_path / "memory" / "memory.md").read_text()
        assert "decisions" in index

    def test_creates_new_file_for_unknown_category(self, tmp_path: Path) -> None:
        result = memory_add(tmp_path, "Something custom", category="facts/custom.md")
        assert (tmp_path / "memory" / "facts" / "custom.md").is_file()


# ---------------------------------------------------------------------------
# memory_forget
# ---------------------------------------------------------------------------


class TestMemoryForget:
    def test_archives_matching_entries(self, tmp_path: Path) -> None:
        _scaffold(tmp_path)
        mem = _memory_dir(tmp_path)
        (mem / "facts" / "corrections.md").write_text(
            "# Corrections\n\n## 2026-01-01 10:00\n\nWrong about the API endpoint.\n\n"
            "## 2026-01-02 10:00\n\nDatabase schema was correct after all.\n"
        )
        result = memory_forget(tmp_path, "API endpoint")
        assert "1" in result  # 1 entry archived
        # Archived section should exist
        archive = mem / ".archive" / "facts" / "corrections.md"
        assert archive.is_file()
        assert "API endpoint" in archive.read_text()
        # Original should not have the removed section
        remaining = (mem / "facts" / "corrections.md").read_text()
        assert "API endpoint" not in remaining
        assert "Database schema" in remaining

    def test_no_match_returns_not_found(self, tmp_path: Path) -> None:
        _scaffold(tmp_path)
        result = memory_forget(tmp_path, "nonexistent topic xyz")
        assert "no matching" in result.lower()

    def test_archives_multiple_matches(self, tmp_path: Path) -> None:
        _scaffold(tmp_path)
        mem = _memory_dir(tmp_path)
        (mem / "facts" / "projects.md").write_text(
            "# Projects\n\n## 2026-01-01\n\nThe API uses REST.\n\n"
            "## 2026-01-02\n\nThe API has rate limiting.\n\n"
            "## 2026-01-03\n\nDatabase uses PostgreSQL.\n"
        )
        result = memory_forget(tmp_path, "API")
        assert "2" in result  # 2 entries archived


# ---------------------------------------------------------------------------
# _split_sections
# ---------------------------------------------------------------------------


class TestSplitSections:
    def test_splits_on_h2(self) -> None:
        content = "# Header\n\n## Section 1\n\nBody 1\n\n## Section 2\n\nBody 2\n"
        parts = _split_sections(content)
        assert len(parts) == 3  # header + 2 sections
        assert parts[0].startswith("# Header")
        assert parts[1].startswith("## Section 1")
        assert parts[2].startswith("## Section 2")

    def test_no_sections(self) -> None:
        content = "# Just a header\n\nSome text.\n"
        parts = _split_sections(content)
        assert len(parts) == 1

    def test_empty_content(self) -> None:
        parts = _split_sections("")
        assert len(parts) == 1
        assert parts[0] == ""


# ---------------------------------------------------------------------------
# memory_recall
# ---------------------------------------------------------------------------


class TestMemoryRecall:
    def test_no_memory_dir(self, tmp_path: Path) -> None:
        result = memory_recall(tmp_path, None)
        assert "no memory" in result.lower()

    def test_no_query_returns_index(self, tmp_path: Path) -> None:
        _scaffold(tmp_path)
        result = memory_recall(tmp_path, None)
        assert "Memory Index" in result

    def test_empty_query_returns_index(self, tmp_path: Path) -> None:
        _scaffold(tmp_path)
        result = memory_recall(tmp_path, "")
        # empty string is treated as None
        # Actually memory_recall treats "" as falsy → returns index
        assert "Memory Index" in result

    def test_finds_matching_entries(self, tmp_path: Path) -> None:
        mem = _scaffold(tmp_path)
        (mem / "facts" / "corrections.md").write_text(
            "# Corrections\n\n## 2026-01-01\n\nThe frobnicator was misconfigured.\n"
        )
        result = memory_recall(tmp_path, "frobnicator")
        assert "frobnicator" in result
        assert "1 entry" in result

    def test_no_matches(self, tmp_path: Path) -> None:
        _scaffold(tmp_path)
        result = memory_recall(tmp_path, "zzzznonexistentzzzz")
        assert "no memories" in result.lower()

    def test_searches_across_categories(self, tmp_path: Path) -> None:
        mem = _scaffold(tmp_path)
        (mem / "facts" / "corrections.md").write_text(
            "# Corrections\n\n## 2026-01-01\n\nAlpha was wrong.\n"
        )
        (mem / "patterns" / "exceptions.md").write_text(
            "# Exceptions\n\n## 2026-01-02\n\nAlpha has an edge case.\n"
        )
        result = memory_recall(tmp_path, "Alpha")
        assert "2 entries" in result


# ---------------------------------------------------------------------------
# memory_digest
# ---------------------------------------------------------------------------


class TestMemoryDigest:
    def test_no_journal_dir(self, tmp_path: Path) -> None:
        result = memory_digest(tmp_path)
        assert "no journal" in result.lower()

    def test_no_recent_entries(self, tmp_path: Path) -> None:
        journal_dir = tmp_path / "journal"
        journal_dir.mkdir(parents=True)
        # Create an old file
        old = journal_dir / "2020-01-01.md"
        old.write_text("Ancient history.")
        # Make it actually old
        import os

        old_time = time.time() - 60 * 86400  # 60 days ago
        os.utime(old, (old_time, old_time))
        result = memory_digest(tmp_path)
        assert "no journal entries" in result.lower()

    def test_creates_weekly_summary(self, tmp_path: Path) -> None:
        today = datetime.now().strftime("%Y-%m-%d")
        _write_journal(tmp_path, today, "## 10:00 — Pulse\n\n- All good.\n")
        result = memory_digest(tmp_path)
        assert "digest created" in result.lower()

        # Check the summary file exists
        mem = _memory_dir(tmp_path)
        weekly_dir = mem / "summaries" / "weekly"
        assert weekly_dir.is_dir()
        summaries = list(weekly_dir.glob("*.md"))
        assert len(summaries) == 1
        content = summaries[0].read_text()
        assert "Weekly Digest" in content
        assert "All good" in content

    def test_includes_multiple_days(self, tmp_path: Path) -> None:
        _write_journal(tmp_path, "2026-03-14", "Day 1 content.")
        _write_journal(tmp_path, "2026-03-15", "Day 2 content.")
        result = memory_digest(tmp_path, days=30)
        assert "2 journal entries" in result

    def test_updates_index_after_digest(self, tmp_path: Path) -> None:
        today = datetime.now().strftime("%Y-%m-%d")
        _write_journal(tmp_path, today, "Journal content.")
        memory_digest(tmp_path)
        index = (_memory_dir(tmp_path) / "memory.md").read_text()
        assert "weekly" in index.lower()


# ---------------------------------------------------------------------------
# memory_index_update
# ---------------------------------------------------------------------------


class TestMemoryIndexUpdate:
    def test_generates_index(self, tmp_path: Path) -> None:
        _scaffold(tmp_path)
        content = memory_index_update(tmp_path)
        assert "Memory Index" in content
        assert "Facts" in content
        assert "Patterns" in content

    def test_no_memory_dir(self, tmp_path: Path) -> None:
        result = memory_index_update(tmp_path)
        assert result == ""

    def test_shows_entry_counts(self, tmp_path: Path) -> None:
        mem = _scaffold(tmp_path)
        (mem / "facts" / "corrections.md").write_text(
            "# Corrections\n\n## 2026-01-01\n\nEntry 1.\n\n## 2026-01-02\n\nEntry 2.\n"
        )
        content = memory_index_update(tmp_path)
        assert "2 entries" in content

    def test_shows_weekly_summary_count(self, tmp_path: Path) -> None:
        mem = _scaffold(tmp_path)
        (mem / "summaries" / "weekly" / "2026-W10.md").write_text("# Week 10\n")
        content = memory_index_update(tmp_path)
        assert "1 digest" in content

    def test_shows_conversation_files(self, tmp_path: Path) -> None:
        mem = _scaffold(tmp_path)
        (mem / "conversations" / "2026-03-15-memory-design.md").write_text("# Memory Design\n")
        content = memory_index_update(tmp_path)
        assert "memory-design" in content


# ---------------------------------------------------------------------------
# memory_clean_working
# ---------------------------------------------------------------------------


class TestMemoryCleanWorking:
    def test_removes_old_files(self, tmp_path: Path) -> None:
        mem = _scaffold(tmp_path)
        working = mem / "working"
        old_file = working / "old-note.md"
        old_file.write_text("Old working note.")
        # Make it old
        old_time = time.time() - 10 * 86400  # 10 days ago
        import os

        os.utime(old_file, (old_time, old_time))

        removed = memory_clean_working(tmp_path, max_age_days=7)
        assert removed == 1
        assert not old_file.exists()

    def test_keeps_recent_files(self, tmp_path: Path) -> None:
        mem = _scaffold(tmp_path)
        working = mem / "working"
        recent = working / "recent-note.md"
        recent.write_text("Recent working note.")

        removed = memory_clean_working(tmp_path, max_age_days=7)
        assert removed == 0
        assert recent.is_file()

    def test_no_working_dir(self, tmp_path: Path) -> None:
        removed = memory_clean_working(tmp_path)
        assert removed == 0

    def test_mixed_old_and_new(self, tmp_path: Path) -> None:
        mem = _scaffold(tmp_path)
        working = mem / "working"
        import os

        old = working / "old.md"
        old.write_text("Old.")
        old_time = time.time() - 10 * 86400
        os.utime(old, (old_time, old_time))

        recent = working / "recent.md"
        recent.write_text("Recent.")

        removed = memory_clean_working(tmp_path, max_age_days=7)
        assert removed == 1
        assert not old.exists()
        assert recent.is_file()


# ---------------------------------------------------------------------------
# memory_status
# ---------------------------------------------------------------------------


class TestMemoryStatus:
    def test_not_initialised(self, tmp_path: Path) -> None:
        result = memory_status(tmp_path)
        assert "not initialised" in result.lower()

    def test_shows_categories(self, tmp_path: Path) -> None:
        _scaffold(tmp_path)
        result = memory_status(tmp_path)
        assert "Facts" in result
        assert "Patterns" in result
        assert "Summaries" in result

    def test_counts_entries(self, tmp_path: Path) -> None:
        mem = _scaffold(tmp_path)
        (mem / "facts" / "corrections.md").write_text("# Corrections\n\n## 2026-01-01\n\nEntry.\n")
        result = memory_status(tmp_path)
        assert "Entries: 1" in result


# ---------------------------------------------------------------------------
# _file_summary
# ---------------------------------------------------------------------------


class TestFileSummary:
    def test_file_with_header_only(self, tmp_path: Path) -> None:
        p = tmp_path / "test.md"
        p.write_text("# Header\n")
        result = _file_summary(p)
        assert "no entries" in result

    def test_nonexistent_returns_empty(self, tmp_path: Path) -> None:
        p = tmp_path / "nope.md"
        result = _file_summary(p)
        assert "empty" in result

    def test_file_with_entries(self, tmp_path: Path) -> None:
        p = tmp_path / "test.md"
        p.write_text("# Header\n\n" + "## 2026-01-01\n\nContent.\n" * 3)
        result = _file_summary(p)
        assert "3 entries" in result

    def test_nonexistent_file_via_missing_path(self, tmp_path: Path) -> None:
        p = tmp_path / "missing.md"
        result = _file_summary(p)
        assert "empty" in result


# ---------------------------------------------------------------------------
# _fmt_size
# ---------------------------------------------------------------------------


class TestFmtSize:
    def test_bytes(self) -> None:
        assert _fmt_size(500) == "500B"

    def test_kilobytes(self) -> None:
        assert _fmt_size(2048) == "2.0KB"

    def test_megabytes(self) -> None:
        assert _fmt_size(2 * 1024 * 1024) == "2.0MB"


# ---------------------------------------------------------------------------
# CLI integration (via Click CliRunner)
# ---------------------------------------------------------------------------


class TestMemoryCLI:
    @pytest.fixture()
    def cli_env(self, tmp_path: Path, monkeypatch):
        """Set up a minimal adj_dir + env for CLI tests."""
        from click.testing import CliRunner

        adj_dir = tmp_path / "adj"
        adj_dir.mkdir()
        (adj_dir / ".adjutant-root").touch()
        (adj_dir / "adjutant.yaml").write_text("instance:\n  name: test\n")
        (adj_dir / "state").mkdir()
        monkeypatch.setenv("ADJ_DIR", str(adj_dir))
        monkeypatch.setenv("ADJUTANT_HOME", str(adj_dir))
        return CliRunner(), adj_dir

    def test_memory_init_command(self, cli_env) -> None:
        from adjutant.cli import main

        runner, adj_dir = cli_env
        result = runner.invoke(main, ["memory", "init"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "initialised" in result.output.lower()
        assert (adj_dir / "memory").is_dir()

    def test_memory_status_command(self, cli_env) -> None:
        from adjutant.cli import main

        runner, adj_dir = cli_env
        runner.invoke(main, ["memory", "init"], catch_exceptions=False)
        result = runner.invoke(main, ["memory", "status"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Memory System Status" in result.output

    def test_memory_remember_command(self, cli_env) -> None:
        from adjutant.cli import main

        runner, _ = cli_env
        result = runner.invoke(
            main, ["memory", "remember", "The API uses REST"], catch_exceptions=False
        )
        assert result.exit_code == 0
        assert "remembered" in result.output.lower()

    def test_memory_recall_command(self, cli_env) -> None:
        from adjutant.cli import main

        runner, _ = cli_env
        runner.invoke(main, ["memory", "init"], catch_exceptions=False)
        result = runner.invoke(main, ["memory", "recall"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Memory Index" in result.output

    def test_memory_digest_no_journal(self, cli_env) -> None:
        from adjutant.cli import main

        runner, _ = cli_env
        result = runner.invoke(main, ["memory", "digest"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "no journal" in result.output.lower()

    def test_memory_forget_command(self, cli_env) -> None:
        from adjutant.cli import main

        runner, _ = cli_env
        runner.invoke(
            main, ["memory", "remember", "The wrong API endpoint"], catch_exceptions=False
        )
        result = runner.invoke(main, ["memory", "forget", "wrong API"], catch_exceptions=False)
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# Dispatch integration
# ---------------------------------------------------------------------------


class TestDispatchMemoryCommands:
    """Verify that memory commands are wired into dispatch.py."""

    def test_remember_import(self) -> None:
        """cmd_remember is importable from commands."""
        from adjutant.messaging.telegram.commands import cmd_remember

        assert callable(cmd_remember)

    def test_forget_import(self) -> None:
        from adjutant.messaging.telegram.commands import cmd_forget

        assert callable(cmd_forget)

    def test_recall_import(self) -> None:
        from adjutant.messaging.telegram.commands import cmd_recall

        assert callable(cmd_recall)

    def test_digest_import(self) -> None:
        from adjutant.messaging.telegram.commands import cmd_digest

        assert callable(cmd_digest)
