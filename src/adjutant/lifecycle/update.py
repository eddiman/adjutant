"""Adjutant self-update mechanism.

Replaces: scripts/lifecycle/update.sh

Checks GitHub releases for a newer version, downloads the tarball,
backs up framework dirs, extracts with rsync-exclusion semantics, and
runs adjutant doctor.

Environment variables (match bash original):
  ADJUTANT_REPO     GitHub owner/repo (default: eddiman/adjutant)
  ADJUTANT_VERSION  Force a specific version tag to install
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime
from pathlib import Path

import httpx

from adjutant.core.logging import adj_log
from adjutant.core.paths import get_adj_dir, init_adj_dir, AdjutantDirNotFoundError

_DEFAULT_REPO = "eddiman/adjutant"

# Directories/files backed up before update
_BACKUP_DIRS = ["scripts", "templates", "tests", "src"]
_BACKUP_FILES = ["adjutant", "VERSION", ".adjutant-root"]

# rsync-style exclusions applied when applying the update
_UPDATE_EXCLUDES = {
    "adjutant.yaml",
    "identity/soul.md",
    "identity/heart.md",
    "identity/registry.md",
    "news_config.json",
    ".env",
    "journal",
    "knowledge_bases",
    "state",
    "insights",
    "photos",
    "screenshots",
}


# ---------------------------------------------------------------------------
# Semver comparison
# ---------------------------------------------------------------------------


def _parse_version(v: str) -> tuple[int, int, int]:
    """Parse a version string like 'v1.2.3' or '1.2.3' into a tuple."""
    v = v.lstrip("v")
    parts = re.split(r"[.\-]", v)[:3]
    result = []
    for p in parts:
        try:
            result.append(int(p))
        except ValueError:
            result.append(0)
    while len(result) < 3:
        result.append(0)
    return tuple(result)  # type: ignore[return-value]


def semver_lt(a: str, b: str) -> bool:
    """Return True if version a < version b."""
    return _parse_version(a) < _parse_version(b)


# ---------------------------------------------------------------------------
# Version queries
# ---------------------------------------------------------------------------


def get_current_version(adj_dir: Path) -> str:
    """Read VERSION file, returns 'unknown' if absent."""
    ver_file = adj_dir / "VERSION"
    if ver_file.is_file():
        return ver_file.read_text().strip()
    return "unknown"


def get_latest_version(repo: str = _DEFAULT_REPO) -> str:
    """Fetch latest release tag from GitHub API.

    Raises:
        RuntimeError: If the API call fails or no release found.
    """
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    try:
        from adjutant.lib.http import get_client

        client = get_client()
        data = client.get(url)
    except Exception as exc:
        raise RuntimeError(
            f"Could not reach GitHub API at {url}. Check your internet connection. ({exc})"
        ) from exc

    tag = data.get("tag_name")
    if not tag or tag == "null":
        raise RuntimeError(f"No releases found at {url}. Has a release been published?")
    return str(tag)


# ---------------------------------------------------------------------------
# Backup
# ---------------------------------------------------------------------------


def backup_current(adj_dir: Path, *, quiet: bool = False) -> Path:
    """Copy framework dirs/files to .backup/pre-update_<timestamp>/."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = adj_dir / ".backup" / f"pre-update_{ts}"
    backup_path.mkdir(parents=True, exist_ok=True)

    if not quiet:
        print(f"  → Backing up current install to {backup_path}...")

    for d in _BACKUP_DIRS:
        src = adj_dir / d
        if src.is_dir():
            shutil.copytree(src, backup_path / d, dirs_exist_ok=True)

    for f in _BACKUP_FILES:
        src = adj_dir / f
        if src.is_file():
            shutil.copy2(src, backup_path / f)

    if not quiet:
        print(f"  ✓ Backup saved to {backup_path}")

    return backup_path


# ---------------------------------------------------------------------------
# Download and apply
# ---------------------------------------------------------------------------


def _should_exclude(rel_path: str) -> bool:
    """Return True if rel_path matches an update exclusion."""
    for excl in _UPDATE_EXCLUDES:
        if rel_path == excl or rel_path.startswith(excl + "/"):
            return True
    return False


def download_and_apply(
    version: str, adj_dir: Path, repo: str = _DEFAULT_REPO, *, quiet: bool = False
) -> None:
    """Download the release tarball and apply it to adj_dir.

    Excludes user-data files (adjutant.yaml, identity/, journal/, etc.)
    matching the rsync --exclude list in the bash original.
    """
    tarball_url = f"https://github.com/{repo}/releases/download/{version}/adjutant-{version}.tar.gz"

    if not quiet:
        print(f"  → Downloading adjutant {version}...")

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        tarball_path = tmp_path / "adjutant.tar.gz"

        try:
            with httpx.Client(timeout=120.0, follow_redirects=True) as http:
                with http.stream("GET", tarball_url) as resp:
                    resp.raise_for_status()
                    with open(tarball_path, "wb") as f:
                        for chunk in resp.iter_bytes():
                            f.write(chunk)
        except Exception as exc:
            raise RuntimeError(f"Download failed from {tarball_url}: {exc}") from exc

        if not quiet:
            print(f"  ✓ Downloaded adjutant {version}")
            print("  → Extracting update...")

        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()

        try:
            with tarfile.open(tarball_path, "r:gz") as tar:
                # Strip the top-level directory (--strip-components=1)
                members = tar.getmembers()
                for member in members:
                    parts = Path(member.name).parts
                    if len(parts) < 2:
                        continue
                    rel = str(Path(*parts[1:]))
                    if _should_exclude(rel):
                        continue
                    member.name = rel
                    tar.extract(member, extract_dir, filter="data")
        except Exception as exc:
            raise RuntimeError(
                f"Extraction failed. The tarball may be corrupt — try again. ({exc})"
            ) from exc

        if not quiet:
            print(f"  → Applying update to {adj_dir}...")

        # Copy non-excluded files from extract_dir to adj_dir
        for src_file in extract_dir.rglob("*"):
            if not src_file.is_file():
                continue
            rel = src_file.relative_to(extract_dir)
            if _should_exclude(str(rel)):
                continue
            dest = adj_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dest)

        if not quiet:
            print(f"  ✓ Applied adjutant {version}")


# ---------------------------------------------------------------------------
# Main update flow
# ---------------------------------------------------------------------------


def update(
    adj_dir: Path,
    *,
    check_only: bool = False,
    auto_yes: bool = False,
    force_version: str | None = None,
    repo: str | None = None,
    quiet: bool = False,
) -> None:
    """Run the full update flow.

    Args:
        adj_dir: Adjutant root directory.
        check_only: Only check, don't install.
        auto_yes: Skip confirmation prompt.
        force_version: Force a specific version to install.
        repo: Override GitHub repo (default: eddiman/adjutant).
        quiet: Suppress output.
    """
    _repo = repo or os.environ.get("ADJUTANT_REPO", _DEFAULT_REPO)
    _force = force_version or os.environ.get("ADJUTANT_VERSION", "")

    if not quiet:
        print("\n  Adjutant Update\n")

    current = get_current_version(adj_dir)
    if not quiet:
        print(f"  → Current version: {current}")

    if _force:
        target = _force
        if not quiet:
            print(f"  → Target version: {target} (forced)")
    else:
        if not quiet:
            print("  → Checking for updates...")
        target = get_latest_version(_repo)
        if not quiet:
            print(f"  → Latest version:  {target}")

    print()

    current_clean = current.lstrip("v")
    target_clean = target.lstrip("v")

    if current_clean == "unknown":
        if not quiet:
            print("  ! Cannot determine current version — VERSION file missing.")
            print("  ! Proceeding with update anyway.")
    elif not semver_lt(current_clean, target_clean):
        if not quiet:
            print(f"  ✓ Already up to date ({current}).\n")
        return

    if check_only:
        print(f"  Update available: {current} → {target}")
        print("  Run adjutant update to install.\n")
        return

    if not quiet:
        print(f"  Update available: {current} → {target}\n")

    if not auto_yes:
        answer = input("  Continue? [y/N] ").strip().lower()
        print()
        if answer not in ("y", "yes"):
            print("  Cancelled.\n")
            return

    # Warn if listener appears to be running
    _warn_if_listener_running(adj_dir, quiet=quiet)

    backup_current(adj_dir, quiet=quiet)
    print()

    download_and_apply(target, adj_dir, _repo, quiet=quiet)

    print()
    if not quiet:
        print(f"  ✓ Update complete: {current} → {target}\n")
        print("  → Running health check...\n")

    _run_doctor(adj_dir)

    print()
    adj_log("lifecycle", f"Updated from {current} to {target}")

    if not quiet:
        print("  → If the listener was running, restart it with: adjutant restart\n")


def _warn_if_listener_running(adj_dir: Path, *, quiet: bool = False) -> None:
    """Warn if telegram listener appears to be running."""
    try:
        from adjutant.messaging.telegram.service import listener_status

        status = listener_status(adj_dir)
        if "running" in status.lower():
            if not quiet:
                print("  ! Listener is currently running.")
                print("  ! It will continue using the old code until restarted.")
                print("  ! Run adjutant restart after the update completes.\n")
    except Exception:
        pass


def _run_doctor(adj_dir: Path) -> None:
    """Run adjutant doctor in the adj_dir."""
    subprocess.run([sys.executable, "-m", "adjutant", "doctor"])


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: update [--check] [--yes]"""
    args = argv if argv is not None else sys.argv[1:]

    check_only = False
    auto_yes = False

    for arg in args:
        if arg == "--check":
            check_only = True
        elif arg in ("--yes", "-y"):
            auto_yes = True
        elif arg in ("--help", "-h"):
            print("Usage: adjutant update [--check] [--yes]\n")
            print("  --check   Check for updates without installing")
            print("  --yes     Non-interactive (auto-confirm install)")
            return 0

    try:
        adj_dir = init_adj_dir()
    except AdjutantDirNotFoundError as exc:
        sys.stderr.write(f"ERROR: {exc}\n")
        return 1

    try:
        update(adj_dir, check_only=check_only, auto_yes=auto_yes)
        return 0
    except RuntimeError as exc:
        sys.stderr.write(f"ERROR: {exc}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
