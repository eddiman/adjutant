"""Re-runnable health check and repair for an existing Adjutant installation.

Replaces: scripts/setup/repair.sh

Detects issues with an existing Adjutant installation and offers to fix each
one with user confirmation (prompt-before-fix).

Checks:
  - adjutant.yaml present
  - .env present with valid credentials
  - CLI executable and on PATH
  - Script permissions (*.sh executable)
  - .env permissions (600)
  - Required directories exist
  - Dependencies available
  - Listener running
  - Scheduled jobs synced to crontab

Public API:
  run_repair(adj_dir: Path, *, dry_run: bool = False) -> None
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from typing import Optional

from adjutant.setup.wizard import (
    BOLD,
    GREEN,
    RED,
    RESET,
    YELLOW,
    wiz_confirm,
    wiz_fail,
    wiz_info,
    wiz_ok,
    wiz_warn,
)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_MINIMAL_CONFIG = """\
instance:
  name: "adjutant"
identity:
  soul: "identity/soul.md"
  heart: "identity/heart.md"
  registry: "identity/registry.md"
messaging:
  backend: "telegram"
features:
  news:
    enabled: false
  screenshot:
    enabled: true
  vision:
    enabled: true
  usage_tracking:
    enabled: true
"""


def _dry_run_would(desc: str) -> None:
    wiz_info(f"[DRY RUN] Would: {desc}")


def _read_env_cred(env_file: Path, key: str) -> str:
    """Read a credential from .env — delegates to core/env.py."""
    from adjutant.core.env import get_credential

    return get_credential(key, env_file) or ""


def _file_octal_perms(path: Path) -> str:
    """Return octal permission string like '600' for a file."""
    mode = path.stat().st_mode
    return oct(stat.S_IMODE(mode))[2:]


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------


def _check_config(
    adj_dir: Path, dry_run: bool, issues_found: int, issues_fixed: int
) -> tuple[int, int]:
    config_file = adj_dir / "adjutant.yaml"
    if config_file.is_file():
        wiz_ok("adjutant.yaml present")
    else:
        wiz_fail("adjutant.yaml missing")
        issues_found += 1
        if wiz_confirm("Create default adjutant.yaml?", "Y"):
            if dry_run:
                _dry_run_would(f"write {config_file} (minimal config)")
                wiz_ok("  -> would create adjutant.yaml")
            else:
                config_file.write_text(_MINIMAL_CONFIG)
                wiz_ok("  -> fixed (created adjutant.yaml)")
            issues_fixed += 1
    return issues_found, issues_fixed


def _check_credentials(
    adj_dir: Path, dry_run: bool, issues_found: int, issues_fixed: int
) -> tuple[int, int]:
    env_file = adj_dir / ".env"
    if env_file.is_file():
        token = _read_env_cred(env_file, "TELEGRAM_BOT_TOKEN")
        chatid = _read_env_cred(env_file, "TELEGRAM_CHAT_ID")
        placeholders = {"your-bot-token-here", "your-chat-id-here", ""}
        if token not in placeholders and chatid not in placeholders:
            wiz_ok(".env present with valid credentials")
        else:
            wiz_fail(".env present but credentials are placeholder values")
            issues_found += 1
            if wiz_confirm("Run Telegram credential setup?", "Y"):
                try:
                    from adjutant.setup.steps.messaging import step_messaging

                    if step_messaging(adj_dir, dry_run=dry_run):
                        issues_fixed += 1
                except Exception as exc:
                    wiz_warn(f"  -> Could not run messaging step: {exc}")
    else:
        wiz_fail(".env missing")
        issues_found += 1
        if wiz_confirm("Create .env with Telegram credentials?", "Y"):
            try:
                from adjutant.setup.steps.messaging import step_messaging

                if step_messaging(adj_dir, dry_run=dry_run):
                    issues_fixed += 1
            except Exception as exc:
                wiz_warn(f"  -> Could not run messaging step: {exc}")
    return issues_found, issues_fixed


def _check_cli_executable(
    adj_dir: Path, dry_run: bool, issues_found: int, issues_fixed: int
) -> tuple[int, int]:
    adjutant_cli = adj_dir / "adjutant"
    if adjutant_cli.is_file():
        if os.access(adjutant_cli, os.X_OK):
            wiz_ok("adjutant CLI executable")
        else:
            wiz_fail("adjutant CLI not executable")
            issues_found += 1
            if wiz_confirm("Fix permissions (chmod +x)?", "Y"):
                if dry_run:
                    _dry_run_would(f"chmod +x {adjutant_cli}")
                    wiz_ok("  -> would fix")
                else:
                    adjutant_cli.chmod(adjutant_cli.stat().st_mode | 0o111)
                    wiz_ok("  -> fixed")
                issues_fixed += 1
    else:
        wiz_warn(f"adjutant CLI not found at {adjutant_cli}")
    return issues_found, issues_fixed


def _check_path(
    adj_dir: Path, dry_run: bool, issues_found: int, issues_fixed: int
) -> tuple[int, int]:
    if shutil.which("adjutant"):
        wiz_ok("adjutant on PATH")
    else:
        wiz_warn("adjutant not on PATH")
        issues_found += 1
        adjutant_cli = adj_dir / "adjutant"

        shell_name = os.path.basename(os.environ.get("SHELL", "bash"))
        if shell_name == "zsh":
            shell_rc = Path.home() / ".zshrc"
        elif shell_name == "bash":
            shell_rc = Path.home() / ".bashrc"
        else:
            shell_rc = Path.home() / ".profile"

        if shell_rc.is_file():
            content = shell_rc.read_text()
            if "alias adjutant=" not in content:
                if wiz_confirm(f"Add alias to {shell_rc}?", "Y"):
                    if dry_run:
                        _dry_run_would(f"append alias adjutant='{adjutant_cli}' to {shell_rc}")
                        wiz_ok(f"  -> would add alias to {shell_rc}")
                    else:
                        with open(shell_rc, "a") as f:
                            f.write(f"\n# Adjutant CLI (added by setup wizard)\n")
                            f.write(f"alias adjutant='{adjutant_cli}'\n")
                        wiz_ok(f"  -> added alias to {shell_rc}")
                    issues_fixed += 1
            else:
                wiz_ok(f"  -> alias already in {shell_rc}")
    return issues_found, issues_fixed


def _check_script_permissions(
    adj_dir: Path, dry_run: bool, issues_found: int, issues_fixed: int
) -> tuple[int, int]:
    scripts_dir = adj_dir / "scripts"
    if not scripts_dir.is_dir():
        return issues_found, issues_fixed

    non_exec = [p for p in scripts_dir.rglob("*.sh") if p.is_file() and not os.access(p, os.X_OK)]
    if not non_exec:
        wiz_ok("scripts/ permissions OK")
    else:
        wiz_fail(f"{len(non_exec)} scripts not executable")
        issues_found += 1
        if wiz_confirm("Fix script permissions?", "Y"):
            if dry_run:
                _dry_run_would(f"chmod +x all *.sh files under {scripts_dir}/")
                wiz_ok("  -> would fix")
            else:
                for p in non_exec:
                    p.chmod(p.stat().st_mode | 0o111)
                wiz_ok("  -> fixed")
            issues_fixed += 1
    return issues_found, issues_fixed


def _check_env_permissions(
    adj_dir: Path, dry_run: bool, issues_found: int, issues_fixed: int
) -> tuple[int, int]:
    env_file = adj_dir / ".env"
    if not env_file.is_file():
        return issues_found, issues_fixed

    perms = _file_octal_perms(env_file)
    if perms == "600":
        wiz_ok(".env permissions (600)")
    else:
        wiz_warn(f".env permissions are {perms} (should be 600)")
        issues_found += 1
        if wiz_confirm("Restrict .env to owner-only (chmod 600)?", "Y"):
            if dry_run:
                _dry_run_would(f"chmod 600 {env_file}")
                wiz_ok("  -> would fix")
            else:
                env_file.chmod(0o600)
                wiz_ok("  -> fixed")
            issues_fixed += 1
    return issues_found, issues_fixed


def _check_required_dirs(
    adj_dir: Path, dry_run: bool, issues_found: int, issues_fixed: int
) -> tuple[int, int]:
    required = ["state", "journal", "identity", "prompts", "photos", "screenshots"]
    for dirname in required:
        d = adj_dir / dirname
        if d.is_dir():
            wiz_ok(f"{dirname}/ directory exists")
        else:
            wiz_fail(f"{dirname}/ directory missing")
            issues_found += 1
            if wiz_confirm(f"Create {dirname}/?", "Y"):
                if dry_run:
                    _dry_run_would(f"mkdir -p {d}")
                    wiz_ok("  -> would create")
                else:
                    d.mkdir(parents=True, exist_ok=True)
                    wiz_ok("  -> created")
                issues_fixed += 1
    return issues_found, issues_fixed


def _check_dependencies(issues_found: int) -> int:
    deps = ["bash", "curl", "jq", "python3", "opencode"]
    wiz_ok("Dependencies:")
    all_ok = True
    for cmd in deps:
        if shutil.which(cmd):
            print(f"    {cmd:<12} OK", file=sys.stderr)
        else:
            print(f"    {cmd:<12} {RED}MISSING{RESET}", file=sys.stderr)
            all_ok = False
    if not all_ok:
        issues_found += 1
    return issues_found


def _check_listener(
    adj_dir: Path, dry_run: bool, issues_found: int, issues_fixed: int
) -> tuple[int, int]:
    listener_status = "Stopped"
    try:
        from adjutant.messaging.telegram.service import get_status

        listener_status = get_status(adj_dir)
    except Exception:
        # Fallback: check if service.sh exists and call it
        service_sh = adj_dir / "scripts" / "messaging" / "telegram" / "service.sh"
        if service_sh.is_file():
            try:
                result = subprocess.run(
                    ["bash", str(service_sh), "status"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                listener_status = result.stdout.strip() or "Stopped"
            except Exception:
                listener_status = "Stopped"

    if listener_status.startswith("Running"):
        wiz_ok(f"Listener: {listener_status}")
    else:
        wiz_warn("Listener not running")
        issues_found += 1
        if wiz_confirm("Start the listener now?", "Y"):
            if dry_run:
                _dry_run_would("start listener service")
                wiz_ok("  -> would start listener")
                issues_fixed += 1
            else:
                started = False
                # Try Python service module first
                try:
                    from adjutant.messaging.telegram.service import start_service

                    start_service(adj_dir)
                    wiz_ok("  -> started")
                    issues_fixed += 1
                    started = True
                except Exception:
                    pass

                if not started:
                    service_sh = adj_dir / "scripts" / "messaging" / "telegram" / "service.sh"
                    if service_sh.is_file():
                        try:
                            result = subprocess.run(
                                ["bash", str(service_sh), "start"],
                                capture_output=True,
                                text=True,
                                timeout=30,
                            )
                            output = result.stdout.strip()
                            if "Started" in output or "Already running" in output:
                                wiz_ok(f"  -> {output}")
                                issues_fixed += 1
                            else:
                                wiz_warn(f"  -> {output or 'unknown error'}")
                        except Exception as exc:
                            wiz_warn(f"  -> Failed to start: {exc}")
                    else:
                        wiz_warn("  -> service.sh not found")
    return issues_found, issues_fixed


def _check_scheduled_jobs(
    adj_dir: Path, dry_run: bool, issues_found: int, issues_fixed: int
) -> tuple[int, int]:
    try:
        from adjutant.capabilities.schedule.manage import (
            schedule_count,
            schedule_list,
        )
        from adjutant.capabilities.schedule.install import install_all

        count = schedule_count(adj_dir)
        if count == 0:
            wiz_info("Scheduled jobs: none registered")
            return issues_found, issues_fixed

        # Check which enabled jobs are missing from crontab
        try:
            crontab_result = subprocess.run(
                ["crontab", "-l"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            crontab_text = crontab_result.stdout
        except Exception:
            crontab_text = ""

        schedules = schedule_list(adj_dir)
        missing = 0
        for sched in schedules:
            if not sched.get("enabled", False):
                continue
            marker = f"# adjutant:{sched['name']}"
            if marker not in crontab_text:
                missing += 1

        if missing == 0:
            wiz_ok(f"Scheduled jobs: all {count} job(s) synced to crontab")
        else:
            wiz_warn(f"Scheduled jobs: {missing} enabled job(s) missing from crontab")
            issues_found += 1
            if wiz_confirm("Sync schedule registry to crontab now?", "Y"):
                if dry_run:
                    _dry_run_would("adjutant schedule sync (install_all)")
                    wiz_ok("  -> would sync")
                else:
                    try:
                        install_all(adj_dir)
                        wiz_ok("  -> synced")
                    except Exception as exc:
                        wiz_warn(f"  -> sync failed: {exc}")
                issues_fixed += 1
    except ImportError:
        wiz_warn("Scheduled jobs: could not load schedule registry (skipping check)")
    return issues_found, issues_fixed


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run_repair(adj_dir: Path, *, dry_run: bool = False) -> None:
    """Run all health checks on *adj_dir* and prompt to fix each issue found.

    Args:
        adj_dir: Root directory of the Adjutant installation.
        dry_run: If True, print what would be done without making changes.
    """
    print("", file=sys.stderr)
    print(f"  {BOLD}Checking installation health...{RESET}", file=sys.stderr)
    print("", file=sys.stderr)

    issues_found = 0
    issues_fixed = 0

    issues_found, issues_fixed = _check_config(adj_dir, dry_run, issues_found, issues_fixed)
    issues_found, issues_fixed = _check_credentials(adj_dir, dry_run, issues_found, issues_fixed)
    issues_found, issues_fixed = _check_cli_executable(adj_dir, dry_run, issues_found, issues_fixed)
    issues_found, issues_fixed = _check_path(adj_dir, dry_run, issues_found, issues_fixed)
    issues_found, issues_fixed = _check_script_permissions(
        adj_dir, dry_run, issues_found, issues_fixed
    )
    issues_found, issues_fixed = _check_env_permissions(
        adj_dir, dry_run, issues_found, issues_fixed
    )
    issues_found, issues_fixed = _check_required_dirs(adj_dir, dry_run, issues_found, issues_fixed)
    issues_found = _check_dependencies(issues_found)
    issues_found, issues_fixed = _check_listener(adj_dir, dry_run, issues_found, issues_fixed)
    issues_found, issues_fixed = _check_scheduled_jobs(adj_dir, dry_run, issues_found, issues_fixed)

    # Summary
    print("", file=sys.stderr)
    if issues_found == 0:
        wiz_ok("All checks passed. Adjutant is healthy.")
    elif issues_fixed == issues_found:
        wiz_ok(f"Found {issues_found} issue(s), all fixed.")
    else:
        remaining = issues_found - issues_fixed
        wiz_warn(f"Found {issues_found} issue(s), fixed {issues_fixed}, {remaining} remaining.")
    print("", file=sys.stderr)
