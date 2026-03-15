"""Step 6: Service Installation.

Replaces: scripts/setup/steps/service.sh

Installs platform-appropriate service management:
  - macOS: LaunchAgent plist for auto-start
  - Linux: systemd user service
  - Both: cron jobs for enabled scheduled jobs
Also handles:
  - PATH/alias setup for the 'adjutant' CLI
  - File permissions
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from adjutant.setup.wizard import (
    BOLD,
    RESET,
    detect_os,
    wiz_confirm,
    wiz_info,
    wiz_ok,
    wiz_step,
    wiz_warn,
)

# ---------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------


def _fix_permissions(adj_dir: Path, *, dry_run: bool = False) -> None:
    adjutant_cli = adj_dir / "adjutant"

    # Make CLI executable
    if adjutant_cli.is_file():
        if not os.access(str(adjutant_cli), os.X_OK):
            if dry_run:
                wiz_ok("[DRY RUN] Would make adjutant CLI executable")
            else:
                adjutant_cli.chmod(adjutant_cli.stat().st_mode | 0o111)
                wiz_ok("Made adjutant CLI executable")
        else:
            wiz_ok("adjutant CLI is executable")

    # Make all scripts executable
    scripts_dir = adj_dir / "scripts"
    if scripts_dir.is_dir():
        if not dry_run:
            for sh in scripts_dir.rglob("*.sh"):
                if not os.access(str(sh), os.X_OK):
                    sh.chmod(sh.stat().st_mode | 0o111)
    wiz_ok("Script permissions OK")

    # Restrict .env
    env_file = adj_dir / ".env"
    if env_file.is_file():
        if dry_run:
            wiz_ok("[DRY RUN] Would chmod 600 .env")
        else:
            env_file.chmod(0o600)
            wiz_ok(".env permissions restricted (600)")


# ---------------------------------------------------------------------------
# CLI alias
# ---------------------------------------------------------------------------


def _setup_cli(adj_dir: Path, *, dry_run: bool = False) -> None:
    adjutant_cli = adj_dir / "adjutant"

    # Already on PATH?
    if shutil.which("adjutant") is not None:
        wiz_ok("adjutant is on PATH")
        return

    # adj_dir on PATH?
    path_dirs = os.environ.get("PATH", "").split(":")
    if str(adj_dir) in path_dirs:
        wiz_ok("adjutant directory is on PATH")
        return

    print("", file=sys.stderr)
    if not wiz_confirm("adjutant is not on PATH. Add a shell alias?", "Y"):
        wiz_info(f"You can add it later: alias adjutant='{adjutant_cli}'")
        return

    # Detect shell config file
    shell_name = os.path.basename(os.environ.get("SHELL", ""))
    shell_rc_map = {
        "zsh": Path.home() / ".zshrc",
        "bash": Path.home() / ".bashrc",
        "fish": Path.home() / ".config" / "fish" / "config.fish",
    }
    shell_rc = shell_rc_map.get(shell_name, Path.home() / ".profile")

    if not shell_rc.is_file():
        wiz_warn(f"Shell config not found: {shell_rc}")
        wiz_info(f"Add manually: alias adjutant='{adjutant_cli}'")
        return

    # Already there?
    if "alias adjutant=" in shell_rc.read_text():
        wiz_ok(f"Alias already exists in {shell_rc}")
        return

    if dry_run:
        wiz_ok(f"[DRY RUN] Would append alias adjutant='{adjutant_cli}' to {shell_rc}")
        wiz_info(f"Run 'source {shell_rc}' or restart your terminal")
        return

    if shell_name == "fish":
        with open(shell_rc, "a") as f:
            f.write(f"\nalias adjutant '{adjutant_cli}'\n")
    else:
        with open(shell_rc, "a") as f:
            f.write(f"\n# Adjutant CLI (added by setup wizard)\n")
            f.write(f"alias adjutant='{adjutant_cli}'\n")

    wiz_ok(f"Added alias to {shell_rc}")
    wiz_info(f"Run 'source {shell_rc}' or restart your terminal")


# ---------------------------------------------------------------------------
# macOS LaunchAgent
# ---------------------------------------------------------------------------

_LAUNCHD_PLIST = """\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.adjutant.telegram</string>
  <key>ProgramArguments</key>
  <array>
    <string>{python}</string>
    <string>-m</string>
    <string>adjutant.messaging.telegram.listener</string>
  </array>
  <key>WorkingDirectory</key>
  <string>{adj_dir}</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>ThrottleInterval</key>
  <integer>30</integer>
  <key>StandardOutPath</key>
  <string>{adj_dir}/state/launchd_stdout.log</string>
  <key>StandardErrorPath</key>
  <string>{adj_dir}/state/launchd_stderr.log</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    <key>ADJ_DIR</key>
    <string>{adj_dir}</string>
  </dict>
</dict>
</plist>
"""


def _install_launchd(adj_dir: Path, *, dry_run: bool = False) -> None:
    if not wiz_confirm("Install Launch Agent for auto-start?", "Y"):
        wiz_info("Start manually with: adjutant start")
        return

    plist_dir = Path.home() / "Library" / "LaunchAgents"
    plist_file = plist_dir / "com.adjutant.telegram.plist"

    # Resolve Python interpreter — prefer the project venv, fall back to sys.executable
    venv_python = adj_dir / ".venv" / "bin" / "python"
    python = str(venv_python) if venv_python.is_file() else sys.executable

    if dry_run:
        wiz_ok(f"[DRY RUN] Would create {plist_file}")
        wiz_ok("[DRY RUN] Would load Launch Agent")
        return

    plist_dir.mkdir(parents=True, exist_ok=True)
    plist_content = _LAUNCHD_PLIST.format(python=python, adj_dir=adj_dir)
    plist_file.write_text(plist_content)
    wiz_ok(f"Created {plist_file}")

    if wiz_confirm("Load launch agent now? (starts the listener)", "Y"):
        subprocess.run(["launchctl", "unload", str(plist_file)], capture_output=True)
        result = subprocess.run(["launchctl", "load", str(plist_file)], capture_output=True)
        if result.returncode == 0:
            wiz_ok("Launch agent loaded")
        else:
            wiz_warn("Failed to load launch agent")
            wiz_info(f"Load manually: launchctl load {plist_file}")


# ---------------------------------------------------------------------------
# Linux systemd
# ---------------------------------------------------------------------------

_SYSTEMD_UNIT = """\
[Unit]
Description=Adjutant Telegram Listener
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart={listener}
Restart=on-failure
RestartSec=10
Environment=ADJUTANT_HOME={adj_dir}
Environment=PATH=/usr/local/bin:/usr/bin:/bin

[Install]
WantedBy=default.target
"""


def _install_systemd(adj_dir: Path, *, dry_run: bool = False) -> None:
    if not wiz_confirm("Install systemd user service for auto-start?", "Y"):
        wiz_info("Start manually with: adjutant start")
        return

    service_dir = Path.home() / ".config" / "systemd" / "user"
    service_file = service_dir / "adjutant-telegram.service"
    listener = adj_dir / "scripts" / "messaging" / "telegram" / "listener.sh"

    if dry_run:
        wiz_ok(f"[DRY RUN] Would create {service_file}")
        wiz_ok("[DRY RUN] Would enable and start systemd service")
        return

    service_dir.mkdir(parents=True, exist_ok=True)
    service_file.write_text(_SYSTEMD_UNIT.format(listener=listener, adj_dir=adj_dir))
    wiz_ok(f"Created {service_file}")

    if wiz_confirm("Enable and start the service now?", "Y"):
        subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True)
        r1 = subprocess.run(
            ["systemctl", "--user", "enable", "adjutant-telegram.service"],
            capture_output=True,
        )
        if r1.returncode == 0:
            wiz_ok("Service enabled")
        else:
            wiz_warn("Failed to enable service")

        r2 = subprocess.run(
            ["systemctl", "--user", "start", "adjutant-telegram.service"],
            capture_output=True,
        )
        if r2.returncode == 0:
            wiz_ok("Service started")
        else:
            wiz_warn("Failed to start service — check: systemctl --user status adjutant-telegram")


# ---------------------------------------------------------------------------
# Scheduled jobs
# ---------------------------------------------------------------------------


def _install_schedules(adj_dir: Path, *, dry_run: bool = False) -> None:
    config_path = adj_dir / "adjutant.yaml"
    try:
        from adjutant.capabilities.schedule.manage import schedule_count, schedule_list
        from adjutant.capabilities.schedule.install import install_all

        count = schedule_count(config_path)
    except Exception:
        count = 0

    if count == 0:
        wiz_info("No scheduled jobs configured in adjutant.yaml schedules:")
        wiz_info("Add one later with: adjutant schedule add")
        return

    if not wiz_confirm("Install cron entries for enabled scheduled jobs?", "Y"):
        wiz_info("Run manually with: adjutant schedule sync")
        return

    if dry_run:
        wiz_ok("[DRY RUN] Would install scheduled job cron entries")
        return

    try:
        install_all(adj_dir)
        jobs = schedule_list(config_path)
        enabled_count = sum(1 for j in jobs if j.get("enabled") is True)
        if enabled_count > 0:
            wiz_ok(f"Installed {enabled_count} cron job(s) from schedules:")
        else:
            wiz_info("No enabled jobs in schedules: — nothing installed.")
            wiz_info("Enable a job with: adjutant schedule enable <name>")
    except Exception as exc:
        wiz_warn(f"Failed to install cron entries: {exc}")


# ---------------------------------------------------------------------------
# Public step entry point
# ---------------------------------------------------------------------------


def step_service(adj_dir: Path, *, dry_run: bool = False) -> bool:
    """Run Step 6: Service Installation.

    Returns:
        True always.
    """
    wiz_step(6, 7, "Service Installation")
    print("", file=sys.stderr)

    os_name = detect_os()
    print(f"  Platform detected: {BOLD}{os_name}{RESET}", file=sys.stderr)
    print("", file=sys.stderr)

    _fix_permissions(adj_dir, dry_run=dry_run)
    _setup_cli(adj_dir, dry_run=dry_run)

    if os_name == "macos":
        _install_launchd(adj_dir, dry_run=dry_run)
    elif os_name == "linux":
        _install_systemd(adj_dir, dry_run=dry_run)
    else:
        wiz_warn("Unknown platform — skipping service installation")
        wiz_info("Start manually with: adjutant start")

    print("", file=sys.stderr)
    _install_schedules(adj_dir, dry_run=dry_run)
    print("", file=sys.stderr)

    return True
