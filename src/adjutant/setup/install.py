"""Adjutant curl-style installer.

Replaces: scripts/setup/install.sh

What this script does:
  1. Checks system prerequisites (bash 4+, curl/python3, jq, opencode)
  2. Asks where to install Adjutant (default: ~/.adjutant)
  3. Downloads the latest release tarball from GitHub Releases
  4. Runs the interactive setup wizard

Environment variables (all optional):
  ADJUTANT_INSTALL_DIR   Override install path (skips the prompt)
  ADJUTANT_REPO          Override GitHub owner/repo (default: eddiman/adjutant)
  ADJUTANT_VERSION       Pin a specific release tag (default: latest)
  ADJUTANT_NO_WIZARD     Set to "true" to skip the wizard after install
"""

from __future__ import annotations

import os
import shutil
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import Optional
from urllib.request import urlopen, Request
from urllib.error import URLError
import json

# ---------------------------------------------------------------------------
# Colour helpers — delegates to wizard.py for NO_COLOR compliance
# ---------------------------------------------------------------------------

from adjutant.setup.wizard import BOLD, CYAN, GREEN, RED, RESET, YELLOW  # noqa: E402


def info(msg: str) -> None:
    print(f"  {CYAN}→{RESET} {msg}", file=sys.stderr)


def ok(msg: str) -> None:
    print(f"  {GREEN}✓{RESET} {msg}", file=sys.stderr)


def warn(msg: str) -> None:
    print(f"  {YELLOW}!{RESET} {msg}", file=sys.stderr)


def die(msg: str) -> None:
    print(f"\n  {RED}✗ Error:{RESET} {msg}\n", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# Banner
# ---------------------------------------------------------------------------


def print_banner() -> None:
    print("", file=sys.stderr)
    print(f"  {BOLD}Adjutant{RESET} — persistent autonomous agent", file=sys.stderr)
    print("  ─────────────────────────────────────────", file=sys.stderr)
    print("", file=sys.stderr)


# ---------------------------------------------------------------------------
# Prerequisite checks
# ---------------------------------------------------------------------------


def check_prerequisites() -> None:
    info("Checking prerequisites...")
    failed = False

    # python3 (we're already running in Python, but check it's ≥ 3.9)
    py_ver = sys.version_info
    if py_ver >= (3, 9):
        ok(f"python3 {py_ver.major}.{py_ver.minor}.{py_ver.micro} (>= 3.9)")
    else:
        warn(f"python3 3.9+ required (found {py_ver.major}.{py_ver.minor})")
        failed = True

    # curl (optional: used for display; urllib handles downloads)
    if shutil.which("curl"):
        ok("curl found")
    else:
        warn("curl not found — downloads will use Python urllib instead")

    # jq
    if shutil.which("jq"):
        ok("jq found")
    else:
        warn("jq not found — JSON parsing will use Python's built-in json module")
        if sys.platform == "darwin":
            warn("  Install with: brew install jq")
        else:
            warn("  Install with: sudo apt-get install jq")

    # opencode
    if shutil.which("opencode"):
        ok("opencode found")
    else:
        warn("opencode not found — required for LLM calls")
        warn("  Install from: https://opencode.ai")
        failed = True

    if failed:
        print("", file=sys.stderr)
        die("Prerequisites not met. Install the missing tools and run this installer again.")

    print("", file=sys.stderr)


# ---------------------------------------------------------------------------
# Install directory
# ---------------------------------------------------------------------------


def prompt_install_dir() -> Path:
    """Prompt for install directory, return chosen Path."""
    default_dir = Path.home() / ".adjutant"
    env_dir = os.environ.get("ADJUTANT_INSTALL_DIR", "")

    if env_dir:
        install_dir = Path(env_dir).expanduser()
    else:
        sys.stderr.write(f"  {BOLD}Install directory{RESET} [{default_dir}]: ")
        sys.stderr.flush()
        try:
            answer = input().strip()
        except (EOFError, KeyboardInterrupt):
            print("", file=sys.stderr)
            die("Installation aborted.")
        install_dir = Path(answer).expanduser() if answer else default_dir

    if install_dir.exists() and not install_dir.is_dir():
        die(f"'{install_dir}' exists and is not a directory.")

    if install_dir.is_dir() and (install_dir / ".adjutant-root").is_file():
        print("", file=sys.stderr)
        warn(f"Adjutant is already installed at '{install_dir}'.")
        print(
            f"  Run {BOLD}adjutant setup --repair{RESET} to check the existing installation.\n",
            file=sys.stderr,
        )
        sys.exit(0)

    return install_dir


# ---------------------------------------------------------------------------
# Version resolution
# ---------------------------------------------------------------------------


def resolve_version() -> str:
    """Return the version tag to download (pinned or latest)."""
    version = os.environ.get("ADJUTANT_VERSION", "")

    if not version:
        repo = os.environ.get("ADJUTANT_REPO", "eddiman/adjutant")
        api_url = f"https://api.github.com/repos/{repo}/releases/latest"
        info("Fetching latest release...")

        try:
            req = Request(api_url, headers={"Accept": "application/vnd.github+json"})
            with urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode())
                version = data.get("tag_name", "")
        except (URLError, json.JSONDecodeError, Exception) as exc:
            die(f"Could not fetch latest release from {api_url}: {exc}")

    if not version or version == "null":
        die(
            f"No releases found at https://api.github.com/repos/{os.environ.get('ADJUTANT_REPO', 'eddiman/adjutant')}."
        )

    return version


# ---------------------------------------------------------------------------
# Download and extract
# ---------------------------------------------------------------------------


def download_and_extract(version: str, install_dir: Path) -> None:
    """Download tarball for *version* and extract into *install_dir*."""
    repo = os.environ.get("ADJUTANT_REPO", "eddiman/adjutant")
    tarball_url = f"https://github.com/{repo}/releases/download/{version}/adjutant-{version}.tar.gz"

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_tarball = Path(tmp_dir) / "adjutant.tar.gz"

        info(f"Downloading adjutant {version}...")
        try:
            with urlopen(tarball_url, timeout=120) as resp, open(tmp_tarball, "wb") as f:
                while chunk := resp.read(65536):
                    f.write(chunk)
        except (URLError, Exception) as exc:
            die(f"Download failed from {tarball_url}: {exc}")
        ok(f"Downloaded adjutant {version}")

        info(f"Extracting to {install_dir}...")
        install_dir.mkdir(parents=True, exist_ok=True)
        try:
            with tarfile.open(tmp_tarball, "r:gz") as tf:
                # --strip-components=1 equivalent: strip leading path component
                members = tf.getmembers()
                for member in members:
                    parts = Path(member.name).parts
                    if len(parts) > 1:
                        member.name = str(Path(*parts[1:]))
                    else:
                        continue  # Skip the top-level directory entry
                    tf.extract(member, path=install_dir)
        except (tarfile.TarError, Exception) as exc:
            die(f"Extraction failed: {exc}. The tarball may be corrupt — try again.")
        ok(f"Extracted to {install_dir}")


# ---------------------------------------------------------------------------
# Wizard launcher
# ---------------------------------------------------------------------------


def run_wizard(install_dir: Path) -> None:
    """Import and invoke the setup wizard for *install_dir*."""
    wizard_py = install_dir / "src" / "adjutant" / "setup" / "wizard.py"
    if not wizard_py.is_file():
        die(f"Wizard not found at '{wizard_py}'. The extraction may have failed.")

    print("", file=sys.stderr)
    print(f"  {BOLD}Starting setup wizard...{RESET}", file=sys.stderr)
    print("", file=sys.stderr)

    # Set environment so the wizard knows its home dir
    os.environ["ADJ_DIR"] = str(install_dir)
    os.environ["ADJUTANT_HOME"] = str(install_dir)

    # Dynamically import and run the wizard from the extracted directory
    # (it may not be on sys.path yet)
    src_dir = str(install_dir / "src")
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)

    try:
        from adjutant.setup.wizard import run_wizard as _run_wizard

        _run_wizard(install_dir)
    except ImportError as exc:
        die(f"Could not import wizard from {src_dir}: {exc}")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def main() -> None:
    print_banner()
    check_prerequisites()

    install_dir = prompt_install_dir()
    print("", file=sys.stderr)

    version = resolve_version()
    ok(f"Version: {version}")
    print("", file=sys.stderr)

    download_and_extract(version, install_dir)
    print("", file=sys.stderr)

    if os.environ.get("ADJUTANT_NO_WIZARD") == "true":
        ok(f"Adjutant {version} installed to {install_dir}")
        info(f"Run {BOLD}adjutant setup{RESET} to complete setup.")
    else:
        run_wizard(install_dir)


if __name__ == "__main__":
    main()
