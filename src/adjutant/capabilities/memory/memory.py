"""Persistent long-term memory for Adjutant.

Provides functions to initialise, add, recall, forget, digest, and
maintain the ``memory/`` directory tree.  All files are plain Markdown,
append-only where possible, with timestamps for auditability.
"""

from __future__ import annotations

import os
import re
import time
from datetime import datetime
from pathlib import Path

from adjutant.core.logging import adj_log

# ---------------------------------------------------------------------------
# Directory / file scaffolding
# ---------------------------------------------------------------------------

# Relative paths (under ``adj_dir / "memory"``) for every directory that
# must exist after ``memory_init``.
_DIRS: list[str] = [
    "facts",
    "patterns",
    "summaries/weekly",
    "summaries/monthly",
    "conversations",
    "working",
]

# Scaffold files created with a heading if they don't exist.
_SCAFFOLD_FILES: dict[str, str] = {
    "facts/people.md": "# People\n\nPeople the agent interacts with — preferences, context, roles.\n",
    "facts/projects.md": "# Projects\n\nLearned project knowledge beyond registry.md.\n",
    "facts/decisions.md": "# Decisions\n\nSignificant decisions and their rationale.\n",
    "facts/corrections.md": "# Corrections\n\nThings the agent got wrong and their corrections.\n",
    "patterns/preferences.md": "# Preferences\n\nUser communication and style preferences.\n",
    "patterns/workflows.md": "# Workflows\n\nRecurring workflows and processes observed.\n",
    "patterns/exceptions.md": "# Exceptions\n\nEdge cases, gotchas, and workarounds learned from experience.\n",
}


def _ensure_memory_dir(adj_dir: Path) -> Path:
    """Return ``adj_dir / "memory"``, creating it and sub-dirs if needed."""
    memory_dir = adj_dir / "memory"
    if not memory_dir.is_dir():
        memory_init(adj_dir)
    return memory_dir


def memory_init(adj_dir: Path) -> str:
    """Create the full memory directory structure with scaffold files.

    Safe to call repeatedly — only creates what's missing.

    Returns:
        A human-readable confirmation string.
    """
    memory_dir = adj_dir / "memory"

    for rel in _DIRS:
        (memory_dir / rel).mkdir(parents=True, exist_ok=True)

    for rel_path, header in _SCAFFOLD_FILES.items():
        fp = memory_dir / rel_path
        if not fp.is_file():
            fp.parent.mkdir(parents=True, exist_ok=True)
            fp.write_text(header)

    # Ensure the index file exists
    index_path = memory_dir / "memory.md"
    if not index_path.is_file():
        memory_index_update(adj_dir)

    adj_log("memory", "Memory directory initialised")
    return "Memory system initialised."


# ---------------------------------------------------------------------------
# Add (remember)
# ---------------------------------------------------------------------------


def memory_add(adj_dir: Path, text: str, *, category: str | None = None) -> str:
    """Append a timestamped entry to the appropriate memory file.

    Args:
        adj_dir: Adjutant root directory.
        text: The content to remember.
        category: Explicit relative path (e.g. ``"facts/corrections.md"``).
            If *None*, auto-classify via :func:`classify_memory`.

    Returns:
        Confirmation string including the chosen category.
    """
    from adjutant.capabilities.memory.classify import classify_memory

    memory_dir = _ensure_memory_dir(adj_dir)

    if not category:
        category = classify_memory(text)

    target = memory_dir / category
    target.parent.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    entry = f"\n## {ts}\n\n{text}\n"

    # Create with header if brand-new file
    if not target.is_file():
        heading = category.split("/")[-1].replace(".md", "").title()
        target.write_text(f"# {heading}\n{entry}")
    else:
        with open(target, "a") as f:
            f.write(entry)

    # Keep the index fresh
    memory_index_update(adj_dir)

    short_cat = category.replace(".md", "").replace("/", " > ")
    adj_log("memory", f"Added memory to {category}: {text[:80]}")
    return f"Remembered in {short_cat}."


# ---------------------------------------------------------------------------
# Forget (archive)
# ---------------------------------------------------------------------------

_SEARCHABLE_DIRS = ("facts", "patterns")


def memory_forget(adj_dir: Path, query: str) -> str:
    """Search memory files for entries matching *query* and archive them.

    Matching is case-insensitive substring search within ``## <date>``
    delimited sections.  Matched sections are moved to
    ``memory/.archive/<original-relative-path>``.

    Returns:
        Summary of what was archived, or ``"No matching memories found."``.
    """
    memory_dir = _ensure_memory_dir(adj_dir)
    archive_dir = memory_dir / ".archive"
    lower_query = query.lower()
    archived_count = 0

    for sub in _SEARCHABLE_DIRS:
        sub_dir = memory_dir / sub
        if not sub_dir.is_dir():
            continue
        for md_file in sorted(sub_dir.glob("*.md")):
            if not md_file.is_file():
                continue
            content = md_file.read_text()
            sections = _split_sections(content)
            if not sections:
                continue

            kept: list[str] = []
            removed: list[str] = []
            for section in sections:
                if lower_query in section.lower():
                    removed.append(section)
                else:
                    kept.append(section)

            if not removed:
                continue

            # Write removed sections to archive
            rel = md_file.relative_to(memory_dir)
            arch_path = archive_dir / rel
            arch_path.parent.mkdir(parents=True, exist_ok=True)
            with open(arch_path, "a") as f:
                for section in removed:
                    f.write(section)
            archived_count += len(removed)

            # Rewrite original without removed sections
            md_file.write_text("".join(kept) if kept else "")

    if archived_count == 0:
        return "No matching memories found."

    memory_index_update(adj_dir)
    adj_log("memory", f"Archived {archived_count} entries matching '{query}'")
    return f"Archived {archived_count} memory {'entry' if archived_count == 1 else 'entries'}."


def _split_sections(content: str) -> list[str]:
    """Split markdown content into ``## ``-delimited sections.

    The text *before* the first ``## `` heading (the file header) is
    preserved as the first element so it can be kept when rewriting.
    """
    parts = re.split(r"(?=^## )", content, flags=re.MULTILINE)
    return parts


# ---------------------------------------------------------------------------
# Recall (search)
# ---------------------------------------------------------------------------


def memory_recall(adj_dir: Path, query: str | None = None) -> str:
    """Search memory for entries relevant to *query*.

    If *query* is empty or None, return the memory index.

    Returns:
        Formatted matching entries, or the index.
    """
    memory_dir = adj_dir / "memory"
    if not memory_dir.is_dir():
        return "No memory system found. Run `adjutant memory init` to set it up."

    if not query:
        index_path = memory_dir / "memory.md"
        if index_path.is_file():
            return index_path.read_text()
        return "Memory index is empty."

    lower_query = query.lower()
    results: list[str] = []

    for sub in (*_SEARCHABLE_DIRS, "conversations"):
        sub_dir = memory_dir / sub
        if not sub_dir.is_dir():
            continue
        for md_file in sorted(sub_dir.glob("*.md")):
            if not md_file.is_file():
                continue
            content = md_file.read_text()
            sections = _split_sections(content)
            rel = md_file.relative_to(memory_dir)
            for section in sections:
                if lower_query in section.lower() and section.startswith("## "):
                    results.append(f"**{rel}**\n{section.strip()}")

    if not results:
        return f"No memories matching '{query}'."

    header = f"Found {len(results)} {'entry' if len(results) == 1 else 'entries'} matching '{query}':\n\n"
    return header + "\n---\n".join(results)


# ---------------------------------------------------------------------------
# Digest (journal → summary)
# ---------------------------------------------------------------------------


def memory_digest(adj_dir: Path, *, days: int = 7) -> str:
    """Compress recent journal entries into a weekly summary.

    Reads ``journal/YYYY-MM-DD.md`` files from the last *days* days,
    concatenates them, and writes a summary file at
    ``memory/summaries/weekly/YYYY-WNN.md``.

    Returns:
        Confirmation string describing what was digested.
    """
    memory_dir = _ensure_memory_dir(adj_dir)
    journal_dir = adj_dir / "journal"

    if not journal_dir.is_dir():
        return "No journal directory found — nothing to digest."

    cutoff = time.time() - days * 86400
    entries: list[tuple[str, str]] = []

    for f in sorted(journal_dir.glob("*.md")):
        if f.is_file() and f.stat().st_mtime >= cutoff:
            entries.append((f.stem, f.read_text()))

    if not entries:
        return f"No journal entries in the last {days} days."

    # Build raw digest content
    combined = ""
    for date_str, content in entries:
        combined += f"### {date_str}\n\n{content}\n\n"

    # Determine week identifier
    now = datetime.now()
    year, week, _ = now.isocalendar()
    week_id = f"{year}-W{week:02d}"

    summary_dir = memory_dir / "summaries" / "weekly"
    summary_dir.mkdir(parents=True, exist_ok=True)
    summary_path = summary_dir / f"{week_id}.md"

    summary_content = (
        f"# Weekly Digest — {week_id}\n\n"
        f"Generated: {now.strftime('%Y-%m-%d %H:%M')}\n"
        f"Period: {entries[0][0]} to {entries[-1][0]} ({len(entries)} days)\n\n"
        f"---\n\n"
        f"{combined}"
    )

    summary_path.write_text(summary_content)
    memory_index_update(adj_dir)

    adj_log("memory", f"Digest created: {week_id} ({len(entries)} journal entries)")
    return f"Digest created: {week_id} — {len(entries)} journal entries compressed."


# ---------------------------------------------------------------------------
# Index
# ---------------------------------------------------------------------------


def memory_index_update(adj_dir: Path) -> str:
    """Regenerate ``memory/memory.md`` from current file state.

    Returns:
        The generated index content.
    """
    memory_dir = adj_dir / "memory"
    if not memory_dir.is_dir():
        return ""

    lines: list[str] = [
        "# Memory Index\n",
        f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n",
        "",
    ]

    # Facts
    facts_dir = memory_dir / "facts"
    if facts_dir.is_dir():
        lines.append("## Facts\n")
        for md in sorted(facts_dir.glob("*.md")):
            lines.append(f"- **{md.stem}** — {_file_summary(md)}")
        lines.append("")

    # Patterns
    patterns_dir = memory_dir / "patterns"
    if patterns_dir.is_dir():
        lines.append("## Patterns\n")
        for md in sorted(patterns_dir.glob("*.md")):
            lines.append(f"- **{md.stem}** — {_file_summary(md)}")
        lines.append("")

    # Summaries
    weekly_dir = memory_dir / "summaries" / "weekly"
    monthly_dir = memory_dir / "summaries" / "monthly"
    weekly_count = len(list(weekly_dir.glob("*.md"))) if weekly_dir.is_dir() else 0
    monthly_count = len(list(monthly_dir.glob("*.md"))) if monthly_dir.is_dir() else 0
    if weekly_count or monthly_count:
        lines.append("## Summaries\n")
        if weekly_count:
            lines.append(f"- **weekly/** — {weekly_count} digest(s)")
        if monthly_count:
            lines.append(f"- **monthly/** — {monthly_count} summary(ies)")
        lines.append("")

    # Conversations
    conv_dir = memory_dir / "conversations"
    if conv_dir.is_dir():
        conv_files = sorted(conv_dir.glob("*.md"))
        if conv_files:
            lines.append("## Conversations\n")
            for md in conv_files[-5:]:  # Last 5 only
                lines.append(f"- {md.stem}")
            if len(conv_files) > 5:
                lines.append(f"- ... and {len(conv_files) - 5} more")
            lines.append("")

    # Working
    working_dir = memory_dir / "working"
    if working_dir.is_dir():
        working_files = list(working_dir.glob("*.md"))
        if working_files:
            lines.append("## Working Memory\n")
            lines.append(f"- {len(working_files)} active note(s)")
            lines.append("")

    content = "\n".join(lines)
    (memory_dir / "memory.md").write_text(content)
    return content


def _file_summary(path: Path) -> str:
    """Return a short summary line for a memory file."""
    if not path.is_file():
        return "empty"
    content = path.read_text()
    # Count ## headings (each is an entry)
    entry_count = content.count("\n## ")
    if entry_count == 0:
        return "no entries yet"
    mtime = datetime.fromtimestamp(path.stat().st_mtime)
    return f"{entry_count} {'entry' if entry_count == 1 else 'entries'}, updated {mtime.strftime('%Y-%m-%d')}"


# ---------------------------------------------------------------------------
# Working-memory cleanup
# ---------------------------------------------------------------------------


def memory_clean_working(adj_dir: Path, *, max_age_days: int = 7) -> int:
    """Remove files in ``memory/working/`` older than *max_age_days*.

    Returns:
        Number of files removed.
    """
    working_dir = adj_dir / "memory" / "working"
    if not working_dir.is_dir():
        return 0

    cutoff = time.time() - max_age_days * 86400
    removed = 0
    for f in working_dir.iterdir():
        if f.is_file() and f.stat().st_mtime < cutoff:
            f.unlink()
            removed += 1

    if removed:
        adj_log("memory", f"Cleaned {removed} expired working-memory files")
    return removed


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


def memory_status(adj_dir: Path) -> str:
    """Return a formatted status report of the memory system.

    Returns:
        Multi-line string suitable for display.
    """
    memory_dir = adj_dir / "memory"
    if not memory_dir.is_dir():
        return "Memory system not initialised. Run `adjutant memory init`."

    lines: list[str] = ["Memory System Status", "=" * 20, ""]

    for label, sub in [("Facts", "facts"), ("Patterns", "patterns")]:
        sub_dir = memory_dir / sub
        if sub_dir.is_dir():
            files = list(sub_dir.glob("*.md"))
            total_size = sum(f.stat().st_size for f in files if f.is_file())
            total_entries = 0
            for f in files:
                if f.is_file():
                    total_entries += f.read_text().count("\n## ")
            lines.append(f"{label}:")
            lines.append(
                f"  Files: {len(files)}, Entries: {total_entries}, Size: {_fmt_size(total_size)}"
            )

    # Summaries
    weekly_dir = memory_dir / "summaries" / "weekly"
    monthly_dir = memory_dir / "summaries" / "monthly"
    weekly_count = len(list(weekly_dir.glob("*.md"))) if weekly_dir.is_dir() else 0
    monthly_count = len(list(monthly_dir.glob("*.md"))) if monthly_dir.is_dir() else 0
    lines.append(f"Summaries:")
    lines.append(f"  Weekly: {weekly_count}, Monthly: {monthly_count}")

    # Conversations
    conv_dir = memory_dir / "conversations"
    conv_count = len(list(conv_dir.glob("*.md"))) if conv_dir.is_dir() else 0
    lines.append(f"Conversations: {conv_count}")

    # Working
    working_dir = memory_dir / "working"
    working_count = len(list(working_dir.glob("*.md"))) if working_dir.is_dir() else 0
    lines.append(f"Working: {working_count} active note(s)")

    # Archive
    archive_dir = memory_dir / ".archive"
    if archive_dir.is_dir():
        arch_count = sum(1 for _ in archive_dir.rglob("*.md"))
        lines.append(f"Archived: {arch_count} entry(ies)")

    return "\n".join(lines)


def _fmt_size(size_bytes: int) -> str:
    """Format byte count as human-readable."""
    if size_bytes < 1024:
        return f"{size_bytes}B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f}KB"
    return f"{size_bytes / (1024 * 1024):.1f}MB"
