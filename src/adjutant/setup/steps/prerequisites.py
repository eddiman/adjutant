"""Step 1: Dependency check.

Replaces: scripts/setup/steps/prerequisites.sh

Checks for required and optional dependencies and reports their status.
Returns True if all required deps are present (optional may be missing).
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from adjutant.setup.wizard import (
    wiz_fail,
    wiz_info,
    wiz_ok,
    wiz_step,
    wiz_warn,
    DIM,
    RESET,
)

import sys


@dataclass
class PrerequisiteResult:
    deps_ok: list[str] = field(default_factory=list)
    deps_missing: list[str] = field(default_factory=list)
    optdeps_ok: list[str] = field(default_factory=list)
    optdeps_missing: list[str] = field(default_factory=list)


def _get_version(cmd: str) -> str:
    """Try to get a version string for a command."""
    version_flags = {
        "bash": ["--version"],
        "curl": ["--version"],
        "jq": ["--version"],
        "python3": ["--version"],
        "opencode": ["--version"],
        "bats": ["--version"],
    }
    flags = version_flags.get(cmd, ["--version"])
    try:
        result = subprocess.run(
            [cmd] + flags,
            capture_output=True,
            text=True,
            timeout=5,
        )
        output = (result.stdout or result.stderr or "").strip().splitlines()
        if output:
            # Return just the first meaningful line, trimmed
            return output[0].strip()[:60]
        return "found"
    except Exception:
        return "found"


def _check_playwright() -> bool:
    """Return True if npx playwright is available."""
    if shutil.which("npx") is None:
        return False
    try:
        result = subprocess.run(
            ["npx", "playwright", "--version"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        return result.returncode == 0
    except Exception:
        return False


def _playwright_version() -> str:
    """Return playwright version string or 'found'."""
    try:
        result = subprocess.run(
            ["npx", "playwright", "--version"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        v = (result.stdout or result.stderr or "").strip().splitlines()
        return v[0].strip()[:60] if v else "found"
    except Exception:
        return "found"


def step_prerequisites() -> bool:
    """Run Step 1: Prerequisites check.

    Returns:
        True if all required deps are present; False otherwise.
    """
    wiz_step(1, 7, "Prerequisites Check")
    print("", file=sys.stderr)

    required_deps = ["bash", "curl", "jq", "python3", "opencode"]
    result = PrerequisiteResult()
    all_required_ok = True

    for cmd in required_deps:
        if shutil.which(cmd) is not None:
            version = _get_version(cmd)
            wiz_ok(f"{cmd} ({version})")
            result.deps_ok.append(cmd)
        else:
            wiz_fail(f"{cmd} not found")
            result.deps_missing.append(cmd)
            all_required_ok = False

    # Optional dependencies
    print("", file=sys.stderr)
    print(f"  {DIM}Optional:{RESET}", file=sys.stderr)

    # Playwright — may take a moment
    sys.stderr.write("  Checking playwright... ")
    sys.stderr.flush()
    if _check_playwright():
        pw_ver = _playwright_version()
        sys.stderr.write("\r")
        sys.stderr.flush()
        wiz_ok(f"playwright ({pw_ver})")
        result.optdeps_ok.append("playwright")
    else:
        sys.stderr.write("\r")
        sys.stderr.flush()
        wiz_warn("playwright not found")
        wiz_info("Needed for /screenshot. Install with: npx playwright install chromium")
        result.optdeps_missing.append("playwright")

    # bc (used for cost estimation in bash; Python equiv doesn't need it)
    if shutil.which("bc") is not None:
        wiz_ok("bc (math for cost estimates)")
        result.optdeps_ok.append("bc")
    else:
        wiz_warn("bc not found — cost estimates will be approximate")
        result.optdeps_missing.append("bc")

    # bats (for development/testing)
    if shutil.which("bats") is not None:
        wiz_ok("bats (testing framework)")
        result.optdeps_ok.append("bats")
    else:
        wiz_info("bats not found — install with: brew install bats-core")
        result.optdeps_missing.append("bats")

    # Summary
    print("", file=sys.stderr)
    if all_required_ok:
        wiz_ok("All required dependencies found")
        return True
    else:
        wiz_fail(f"Missing required dependencies: {', '.join(result.deps_missing)}")
        print("", file=sys.stderr)
        wiz_info("Install missing dependencies and re-run 'adjutant setup'")
        return False
