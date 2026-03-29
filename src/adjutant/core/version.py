"""Version management utilities.

Single source of truth: the VERSION file at the project root.
All other version references (pyproject.toml dynamic, CLI) derive from it.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

_SEMVER_RE = re.compile(
    r"^(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)"
    r"(?:-(?P<pre>[0-9A-Za-z\-.]+))?(?:\+(?P<build>[0-9A-Za-z\-.]+))?$"
)

# Conventional Commit prefixes and their default bump levels
COMMIT_TYPES: dict[str, str | None] = {
    "feat": "minor",
    "fix": "patch",
    "docs": None,
    "style": None,
    "refactor": None,
    "perf": "patch",
    "test": None,
    "build": None,
    "ci": None,
    "chore": None,
    "revert": "patch",
}

_CONVENTIONAL_RE = re.compile(
    r"^(?P<type>" + "|".join(COMMIT_TYPES) + r")"
    r"(?:\((?P<scope>[a-zA-Z0-9_/\-]+)\))?"
    r"(?P<breaking>!)?"
    r": (?P<desc>.+)$",
    re.MULTILINE,
)


def project_root() -> Path:
    """Find the project root by walking up from this file to find VERSION."""
    current = Path(__file__).resolve().parent
    for _ in range(10):
        if (current / "VERSION").is_file():
            return current
        current = current.parent
    msg = "Could not find VERSION file in any parent directory"
    raise FileNotFoundError(msg)


def read_version(root: Path | None = None) -> str:
    """Read the current version from the VERSION file."""
    root = root or project_root()
    version_file = root / "VERSION"
    if not version_file.is_file():
        msg = f"VERSION file not found at {version_file}"
        raise FileNotFoundError(msg)
    return version_file.read_text().strip()


def parse_semver(v: str) -> tuple[int, int, int, str]:
    """Parse a semver string into (major, minor, patch, prerelease).

    Raises ValueError if not valid semver.
    """
    v = v.lstrip("v")
    m = _SEMVER_RE.match(v)
    if not m:
        msg = f"Invalid semver: {v!r}"
        raise ValueError(msg)
    return (
        int(m.group("major")),
        int(m.group("minor")),
        int(m.group("patch")),
        m.group("pre") or "",
    )


def bump_version(current: str, bump: str) -> str:
    """Bump a semver version string.

    Args:
        current: Current version string (e.g. "0.2.0").
        bump: One of "major", "minor", "patch".

    Returns:
        New version string.
    """
    major, minor, patch, _ = parse_semver(current)
    if bump == "major":
        return f"{major + 1}.0.0"
    if bump == "minor":
        return f"{major}.{minor + 1}.0"
    if bump == "patch":
        return f"{major}.{minor}.{patch + 1}"
    msg = f"Invalid bump type: {bump!r} (expected major, minor, or patch)"
    raise ValueError(msg)


def validate_conventional_commit(message: str) -> tuple[str, str | None, bool, str]:
    """Validate a commit message follows Conventional Commits.

    Returns:
        Tuple of (type, scope_or_none, is_breaking, description).

    Raises:
        ValueError with a helpful message if invalid.
    """
    # Strip comments (lines starting with #)
    lines = [ln for ln in message.splitlines() if not ln.startswith("#")]
    clean = "\n".join(lines).strip()
    if not clean:
        msg = "Empty commit message"
        raise ValueError(msg)

    first_line = clean.splitlines()[0]
    m = _CONVENTIONAL_RE.match(first_line)
    if not m:
        allowed = ", ".join(sorted(COMMIT_TYPES))
        msg = (
            f"Commit message does not follow Conventional Commits format.\n"
            f"\n"
            f"  Got:      {first_line!r}\n"
            f"  Expected: <type>[optional scope]: <description>\n"
            f"\n"
            f"  Valid types: {allowed}\n"
            f"\n"
            f"  Examples:\n"
            f"    feat: add user login\n"
            f"    fix(auth): handle expired tokens\n"
            f"    chore!: drop Python 3.10 support\n"
        )
        raise ValueError(msg)

    is_breaking = bool(m.group("breaking")) or "BREAKING CHANGE:" in clean
    return m.group("type"), m.group("scope"), is_breaking, m.group("desc")


def infer_bump(commit_type: str, is_breaking: bool) -> str:
    """Infer semver bump level from a conventional commit type."""
    if is_breaking:
        return "major"
    return COMMIT_TYPES.get(commit_type) or "patch"


def write_version(new_version: str, root: Path | None = None) -> None:
    """Write a new version to the VERSION file."""
    root = root or project_root()
    (root / "VERSION").write_text(new_version + "\n")


def do_bump(
    bump: str,
    root: Path | None = None,
    *,
    commit: bool = True,
    tag: bool = True,
) -> str:
    """Bump the version, optionally commit and tag.

    Args:
        bump: One of "major", "minor", "patch".
        root: Project root directory.
        commit: Whether to create a git commit.
        tag: Whether to create a git tag.

    Returns:
        The new version string.
    """
    root = root or project_root()
    current = read_version(root)
    new = bump_version(current, bump)

    write_version(new, root)

    if commit:
        subprocess.run(
            ["git", "add", "VERSION"],
            cwd=root,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "commit", "-m", f"chore: bump version {current} → {new}"],
            cwd=root,
            check=True,
            capture_output=True,
        )
    if tag:
        subprocess.run(
            ["git", "tag", f"v{new}"],
            cwd=root,
            check=True,
            capture_output=True,
        )

    return new


def main_commit_msg(argv: list[str] | None = None) -> int:
    """Entry point for the commit-msg git hook."""
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        sys.stderr.write("Usage: commit-msg <message-file>\n")
        return 1

    msg_file = Path(args[0])
    message = msg_file.read_text()

    try:
        validate_conventional_commit(message)
    except ValueError as exc:
        sys.stderr.write(f"\n{exc}\n")
        return 1
    return 0
