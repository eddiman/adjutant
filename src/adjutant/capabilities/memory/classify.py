"""Auto-classify memory text into the appropriate category file.

Uses keyword scoring to route ``/remember`` content to the right
markdown file under ``memory/``.  No LLM call — pure pattern matching.
"""

from __future__ import annotations

# Category → list of trigger phrases (lowercase).
# Order within each list doesn't matter; scoring counts unique hits.
CATEGORIES: dict[str, list[str]] = {
    "facts/corrections.md": [
        "wrong",
        "incorrect",
        "mistake",
        "actually",
        "correction",
        "not right",
        "fix that",
        "corrected",
        "was wrong",
        "that's not",
    ],
    "facts/decisions.md": [
        "decided",
        "decision",
        "chose",
        "chosen",
        "went with",
        "agreed",
        "settled on",
        "picked",
        "opted for",
        "ruling",
    ],
    "facts/people.md": [
        "person",
        "people",
        "name is",
        "works at",
        "contact",
        "team",
        "colleague",
        "their role",
        "who is",
        "manager",
    ],
    "facts/projects.md": [
        "project",
        "repo",
        "codebase",
        "architecture",
        "stack",
        "deployment",
        "build",
        "service",
        "database",
        "endpoint",
    ],
    "patterns/preferences.md": [
        "prefer",
        "preference",
        "always",
        "never",
        "style",
        "format",
        "tone",
        "don't like",
        "i like",
        "i want",
    ],
    "patterns/workflows.md": [
        "workflow",
        "process",
        "routine",
        "every day",
        "weekly",
        "usually",
        "typically",
        "step by step",
        "procedure",
        "habit",
    ],
    "patterns/exceptions.md": [
        "exception",
        "edge case",
        "gotcha",
        "watch out",
        "careful",
        "workaround",
        "quirk",
        "caveat",
        "beware",
        "trap",
    ],
}

# Fall back to this when no category scores above zero.
DEFAULT_CATEGORY = "facts/projects.md"


def classify_memory(text: str) -> str:
    """Return the relative memory file path best matching *text*.

    Scores each category by counting how many of its keywords appear
    (as substrings) in the lowercased text.  Ties are broken by
    declaration order in :data:`CATEGORIES`.

    Returns:
        A relative path like ``"facts/corrections.md"``.
    """
    lower = text.lower()
    best_category = DEFAULT_CATEGORY
    best_score = 0

    for category, keywords in CATEGORIES.items():
        score = sum(1 for kw in keywords if kw in lower)
        if score > best_score:
            best_score = score
            best_category = category

    return best_category
