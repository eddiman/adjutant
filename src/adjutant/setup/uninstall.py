"""Adjutant uninstaller.

Replaces: scripts/setup/uninstall.sh

Interactive removal:
  1. Confirms intent (requires typing "yes")
  2. Stops all running processes (opencode, telegram listener, scheduled jobs)
  3. Removes platform service (launchd / systemd)
  4. Offers to remove PATH alias from shell rc
  5. Offers to delete all Adjutant files
"""

from __future__ import annotations

import os
import platform
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

from adjutant.setup.wizard import wiz_info, wiz_ok, wiz_warn


# ---------------------------------------------------------------------------
# Banner / confirm
# ---------------------------------------------------------------------------


def _banner(adj_dir: Path) -> None:
    print("", file=sys.stderr)
    print("\033[1m━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\033[0m", file=sys.stderr)
    print("\033[1m  Adjutant — Uninstall\033[0m", file=sys.stderr)
    print("\033[1m━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\033[0m", file=sys.stderr)
    print("", file=sys.stderr)
    print(f"  Installation directory: \033[1m{adj_dir}\033[0m", file=sys.stderr)
    print("", file=sys.stderr)


def _confirm_intent() -> bool:
    """Ask user to type 'yes' explicitly."""
    print("  \033[33mThis will stop all Adjutant processes and optionally\033[0m", file=sys.stderr)
    print(
        "  \033[33mremove Adjutant from your PATH and/or delete all files.\033[0m", file=sys.stderr
    )
    print("", file=sys.stderr)
    sys.stderr.write("  Type \033[1myes\033[0m to continue, or anything else to abort: ")
    sys.stderr.flush()
    try:
        answer = input().strip()
    except (EOFError, KeyboardInterrupt):
        print("", file=sys.stderr)
        return False
    print("", file=sys.stderr)
    return answer == "yes"


# ---------------------------------------------------------------------------
# Stop processes
# ---------------------------------------------------------------------------


def _pkill(pattern: str) -> None:
    """Best-effort pkill by pattern."""
    try:
        subprocess.run(["pkill", "-TERM", "-f", pattern], capture_output=True)
        time.sleep(0.5)
        subprocess.run(["pkill", "-KILL", "-f", pattern], capture_output=True)
    except FileNotFoundError:
        pass


def _kill_pid_file(pid_file: Path) -> None:
    """Kill the PID stored in pid_file (TERM then KILL)."""
    if not pid_file.is_file():
        return
    try:
        pid = int(pid_file.read_text().strip())
        os.kill(pid, signal.SIGTERM)
        time.sleep(1)
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    except (ValueError, ProcessLookupError, PermissionError, OSError):
        pass
    try:
        pid_file.unlink()
    except OSError:
        pass


def stop_processes(adj_dir: Path) -> None:
    """Stop opencode, telegram listener, and scheduled jobs."""
    print("\033[1mStopping processes...\033[0m", file=sys.stderr)
    print("", file=sys.stderr)

    # OpenCode web server
    print("  Stopping OpenCode...", file=sys.stderr)
    _pkill("opencode web")
    pid_file = adj_dir / "state" / "opencode_web.pid"
    if pid_file.is_file():
        pid_file.unlink(missing_ok=True)
    wiz_ok("OpenCode stopped")

    # Telegram listener — 3-tier
    print("  Stopping Telegram listener...", file=sys.stderr)
    _kill_pid_file(adj_dir / "state" / "telegram.pid")

    lock_dir = adj_dir / "state" / "listener.lock"
    _kill_pid_file(lock_dir / "pid")
    shutil.rmtree(lock_dir, ignore_errors=True)

    _pkill(r"messaging/telegram/listener\.sh")
    _pkill(r"telegram_listener\.sh")
    wiz_ok("Telegram listener stopped")

    # Scheduled jobs
    print("  Stopping scheduled jobs...", file=sys.stderr)
    _stop_scheduled_jobs(adj_dir)
    wiz_ok("Scheduled jobs stopped")

    # Clear KILLED lockfile
    (adj_dir / "KILLED").unlink(missing_ok=True)
    print("", file=sys.stderr)


def _stop_scheduled_jobs(adj_dir: Path) -> None:
    """Kill any running scripts listed in adjutant.yaml schedules."""
    config = adj_dir / "adjutant.yaml"
    if not config.is_file():
        return
    in_schedules = False
    for line in config.read_text().splitlines():
        if line.startswith("schedules:"):
            in_schedules = True
            continue
        if in_schedules and line and line[0] not in (" ", "\t", "-"):
            break
        if in_schedules:
            stripped = line.strip().lstrip("- ")
            if stripped.startswith("script:"):
                script = stripped[len("script:") :].strip().strip("\"'")
                if script:
                    resolved = Path(script) if Path(script).is_absolute() else adj_dir / script
                    _pkill(str(resolved))


# ---------------------------------------------------------------------------
# Remove platform service
# ---------------------------------------------------------------------------


def _detect_os() -> str:
    s = platform.system()
    return "macos" if s == "Darwin" else ("linux" if s == "Linux" else "unknown")


def remove_service(adj_dir: Path) -> None:
    """Remove launchd (macOS) or systemd (Linux) service."""
    os_name = _detect_os()
    if os_name == "macos":
        _remove_launchd()
    elif os_name == "linux":
        _remove_systemd()


def _remove_launchd() -> None:
    home = Path.home()
    candidates = [
        home / "Library" / "LaunchAgents" / "com.adjutant.telegram.plist",
        home / "Library" / "LaunchAgents" / "adjutant.telegram.plist",
    ]
    found = next((p for p in candidates if p.is_file()), None)
    if found is None:
        wiz_info("No LaunchAgent plist found — skipping")
        return

    print("\033[1mRemoving LaunchAgent...\033[0m", file=sys.stderr)
    print("", file=sys.stderr)
    try:
        subprocess.run(["launchctl", "unload", str(found)], capture_output=True)
    except FileNotFoundError:
        pass
    found.unlink(missing_ok=True)
    wiz_ok(f"LaunchAgent removed: {found}")
    print("", file=sys.stderr)


def _remove_systemd() -> None:
    svc_file = Path.home() / ".config" / "systemd" / "user" / "adjutant-telegram.service"
    if not svc_file.is_file():
        wiz_info("No systemd service file found — skipping")
        return

    print("\033[1mRemoving systemd service...\033[0m", file=sys.stderr)
    print("", file=sys.stderr)
    for cmd in [
        ["systemctl", "--user", "stop", "adjutant-telegram.service"],
        ["systemctl", "--user", "disable", "adjutant-telegram.service"],
    ]:
        try:
            subprocess.run(cmd, capture_output=True)
        except FileNotFoundError:
            break
    svc_file.unlink(missing_ok=True)
    try:
        subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True)
    except FileNotFoundError:
        pass
    wiz_ok(f"systemd service removed: {svc_file}")
    print("", file=sys.stderr)


# ---------------------------------------------------------------------------
# Remove PATH alias
# ---------------------------------------------------------------------------


def remove_path_alias(adj_dir: Path) -> None:
    """Offer to remove the adjutant alias from the shell rc file."""
    print("\033[1mShell alias / PATH\033[0m", file=sys.stderr)
    print("", file=sys.stderr)

    shell_name = Path(os.environ.get("SHELL", "")).name
    shell_rc_map = {
        "zsh": Path.home() / ".zshrc",
        "bash": Path.home() / ".bashrc",
        "fish": Path.home() / ".config" / "fish" / "config.fish",
    }
    shell_rc = shell_rc_map.get(shell_name, Path.home() / ".profile")

    if not shell_rc.is_file() or "alias adjutant" not in shell_rc.read_text():
        wiz_info(f"No adjutant alias found in {shell_rc}")
        if str(adj_dir) in os.environ.get("PATH", ""):
            wiz_info(f"Note: {adj_dir} appears to be on PATH — remove it manually if desired")
        print("", file=sys.stderr)
        return

    wiz_info(f"Found alias in: {shell_rc}")
    print("", file=sys.stderr)

    sys.stderr.write(f"  Remove adjutant alias from {shell_rc}? [y/N]: ")
    sys.stderr.flush()
    try:
        answer = input().strip().lower()
    except (EOFError, KeyboardInterrupt):
        answer = ""

    if answer not in ("y", "yes"):
        wiz_info("Alias left in place")
        print("", file=sys.stderr)
        return

    text = shell_rc.read_text()
    if shell_name == "fish":
        text = re.sub(r"alias adjutant [^\n]*\n?", "", text)
    else:
        text = re.sub(r"# Adjutant CLI \(added by setup wizard\)\n?", "", text)
        text = re.sub(r"alias adjutant=[^\n]*\n?", "", text)

    shell_rc.write_text(text)
    wiz_ok(f"Alias removed from {shell_rc}")
    wiz_info(f"Restart your terminal or run: source {shell_rc}")
    print("", file=sys.stderr)


# ---------------------------------------------------------------------------
# Remove files
# ---------------------------------------------------------------------------


def remove_files(adj_dir: Path) -> bool:
    """Offer to permanently delete adj_dir. Returns True if deleted."""
    print("\033[1mRemove all Adjutant files\033[0m", file=sys.stderr)
    print("", file=sys.stderr)
    wiz_info(f"This will permanently delete: {adj_dir}")
    print("", file=sys.stderr)

    cwd = Path.cwd().resolve()
    if str(cwd).startswith(str(adj_dir)):
        wiz_warn(f"Your current directory is inside {adj_dir}")
        wiz_warn("Your shell's working directory will be gone after removal.")
        print("", file=sys.stderr)

    if adj_dir.is_symlink():
        wiz_warn(f"{adj_dir} is a symlink — only the symlink will be removed, not the target")
        print("", file=sys.stderr)

    sys.stderr.write(f"  Permanently delete all files at {adj_dir}? [y/N]: ")
    sys.stderr.flush()
    try:
        answer = input().strip().lower()
    except (EOFError, KeyboardInterrupt):
        answer = ""

    if answer not in ("y", "yes"):
        return False

    # Clean crontab entries
    _remove_adjutant_crontab_entries()

    if adj_dir.is_symlink():
        adj_dir.unlink()
    else:
        shutil.rmtree(adj_dir)
    wiz_ok(f"Deleted: {adj_dir}")
    print("", file=sys.stderr)
    return True


def _remove_adjutant_crontab_entries() -> None:
    """Strip all # adjutant: entries from the crontab."""
    try:
        result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        if result.returncode != 0 or "# adjutant:" not in result.stdout:
            return
        print("  Removing crontab entries...", file=sys.stderr)
        lines = [l for l in result.stdout.splitlines() if "# adjutant:" not in l]
        subprocess.run(["crontab", "-"], input="\n".join(lines) + "\n", text=True, check=True)
        wiz_ok("Crontab entries removed")
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def uninstall(adj_dir: Path) -> None:
    """Run the full uninstall flow."""
    _banner(adj_dir)

    if not _confirm_intent():
        print("  Aborted. Nothing was changed.", file=sys.stderr)
        return

    stop_processes(adj_dir)
    remove_service(adj_dir)
    remove_path_alias(adj_dir)

    files_removed = remove_files(adj_dir)

    print("\033[1m━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\033[0m", file=sys.stderr)
    if files_removed:
        print("\033[1m\033[32m  Adjutant has been uninstalled.\033[0m", file=sys.stderr)
    else:
        print("\033[1m  Adjutant processes stopped.\033[0m", file=sys.stderr)
        print("", file=sys.stderr)
        print(f"\033[1m\033[33m  Your Adjutant files are intact.\033[0m", file=sys.stderr)
        print(f"  Location: \033[1m{adj_dir}\033[0m", file=sys.stderr)
        print("", file=sys.stderr)
        print("  To fully remove Adjutant, run:", file=sys.stderr)
        print(f"    \033[1madjutant uninstall\033[0m", file=sys.stderr)
    print("\033[1m━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\033[0m", file=sys.stderr)
    print("", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    from adjutant.core.paths import init_adj_dir, AdjutantDirNotFoundError

    try:
        adj_dir = init_adj_dir()
    except AdjutantDirNotFoundError as exc:
        sys.stderr.write(f"ERROR: {exc}\n")
        return 1

    try:
        uninstall(adj_dir)
        return 0
    except (KeyboardInterrupt, SystemExit):
        print("\nCancelled.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
