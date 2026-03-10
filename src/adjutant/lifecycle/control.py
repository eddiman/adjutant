"""Adjutant lifecycle control: pause, resume, restart, emergency_kill, startup.

Replaces five bash scripts:
  scripts/lifecycle/pause.sh
  scripts/lifecycle/resume.sh
  scripts/lifecycle/restart.sh
  scripts/lifecycle/emergency_kill.sh
  scripts/lifecycle/startup.sh
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _adj_dir() -> Path:
    raw = os.environ.get("ADJ_DIR", "").strip()
    if not raw:
        raise RuntimeError("ADJ_DIR not set")
    return Path(raw)


def _timestamp() -> str:
    return datetime.now().strftime("%H:%M:%S %d.%m.%Y")


def _log_journal(adj_dir: Path, message: str) -> None:
    """Append a timestamped line to today's journal file."""
    today = datetime.now().strftime("%Y-%m-%d")
    log_file = adj_dir / "journal" / f"{today}.md"
    try:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with open(log_file, "a") as f:
            f.write(f"\n[{_timestamp()}] {message}\n")
    except OSError:
        pass


def _adj_log(component: str, message: str) -> None:
    """Call adj_log equivalent (Python logging module)."""
    try:
        from adjutant.core.logging import adj_log

        adj_log(component, message)
    except Exception:
        pass  # non-fatal if logging unavailable


def _send_notify(adj_dir: Path, text: str) -> None:
    """Send a Telegram notification, silently ignoring failures."""
    try:
        from adjutant.messaging.telegram.notify import send_notify

        send_notify(text, adj_dir)
    except Exception:
        # Non-fatal — matches bash `|| true`
        pass


def _kill_by_pattern(pattern: str, sig: signal.Signals = signal.SIGTERM) -> None:
    """Send signal to all processes matching the pattern. Silently ignores errors."""
    try:
        result = subprocess.run(["pgrep", "-f", pattern], capture_output=True, text=True)
        for pid_str in result.stdout.splitlines():
            pid_str = pid_str.strip()
            if not pid_str.isdigit():
                continue
            try:
                os.kill(int(pid_str), sig)
            except (ProcessLookupError, PermissionError):
                pass
    except OSError:
        pass


def _kill_pidfile(pid_file: Path, sig: signal.Signals = signal.SIGTERM) -> None:
    """Send signal to PID in file. Silently ignores missing file / dead process."""
    try:
        pid = int(pid_file.read_text().strip())
        os.kill(pid, sig)
    except (FileNotFoundError, ValueError, ProcessLookupError, PermissionError):
        pass


def _pid_alive(pid: int) -> bool:
    """Return True if process with PID is running."""
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def _pgrep_first(pattern: str) -> Optional[int]:
    """Return first PID matching pattern, or None."""
    try:
        result = subprocess.run(["pgrep", "-f", pattern], capture_output=True, text=True)
        for line in result.stdout.splitlines():
            line = line.strip()
            if line.isdigit():
                return int(line)
    except OSError:
        pass
    return None


def _read_pid(path: Path) -> Optional[int]:
    """Read integer PID from file, or return None."""
    try:
        return int(path.read_text().strip())
    except (FileNotFoundError, ValueError):
        return None


# ---------------------------------------------------------------------------
# pause
# ---------------------------------------------------------------------------


def pause(adj_dir: Optional[Path] = None) -> str:
    """Create the PAUSED lockfile.

    Returns:
        Human-readable message string.
    """
    from adjutant.core.lockfiles import set_paused

    d = adj_dir or _adj_dir()
    set_paused(d)
    return "Adjutant paused. All heartbeats will skip until resumed.\nResume with: adjutant resume"


# ---------------------------------------------------------------------------
# resume
# ---------------------------------------------------------------------------


def resume(adj_dir: Optional[Path] = None) -> str:
    """Remove the PAUSED lockfile.

    Returns:
        Human-readable message string.
    """
    from adjutant.core.lockfiles import clear_paused

    d = adj_dir or _adj_dir()
    clear_paused(d)
    return "Adjutant resumed. Heartbeats will run on next schedule."


# ---------------------------------------------------------------------------
# restart
# ---------------------------------------------------------------------------


def restart(adj_dir: Optional[Path] = None) -> str:
    """Stop all services and start fresh via startup().

    Returns:
        Human-readable multi-line output.
    """
    d = adj_dir or _adj_dir()
    ts = _timestamp()
    lines: list[str] = [f"Adjutant Restart - {ts}", "", "Stopping services...", ""]

    # Stop Telegram listener
    telegram_pid_file = d / "state" / "telegram.pid"
    telegram_pid = _read_pid(telegram_pid_file)
    if telegram_pid and _pid_alive(telegram_pid):
        _stop_telegram_service(d)
        lines.append("Telegram listener stopped")
    else:
        lines.append("Telegram listener not running")

    # Stop OpenCode web server
    web_pid_file = d / "state" / "opencode_web.pid"
    web_pid = _read_pid(web_pid_file)
    if web_pid and _pid_alive(web_pid):
        try:
            os.kill(web_pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass
        web_pid_file.unlink(missing_ok=True)
        lines.append("OpenCode web server stopped")
    else:
        # Look for orphan
        orphan = _pgrep_first("opencode web")
        if orphan:
            _kill_by_pattern("opencode web", signal.SIGTERM)
            time.sleep(1)
            lines.append("OpenCode web server stopped")
        else:
            lines.append("OpenCode web server not running")

    lines += ["", "Waiting for clean shutdown..."]
    time.sleep(2)

    lines += ["", "Starting services...", ""]

    # Delegate to startup
    startup_output = startup(d, interactive=False)
    lines.append(startup_output)
    lines += ["", "Restart complete"]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# emergency_kill
# ---------------------------------------------------------------------------


def emergency_kill(adj_dir: Optional[Path] = None) -> str:
    """Nuclear shutdown of all systems.

    Creates KILLED lockfile, terminates all processes, backs up and removes
    crontab, logs the event, and sends Telegram notifications.

    Returns:
        Human-readable output string.
    """
    from adjutant.core.lockfiles import set_killed
    from adjutant.core.config import load_typed_config

    d = adj_dir or _adj_dir()
    ts = _timestamp()
    lines: list[str] = [
        f"EMERGENCY KILL SWITCH ACTIVATED - {ts}",
        "",
    ]

    # Pre-kill notification
    lines.append("Sending pre-kill notification to Telegram...")
    _send_notify(
        d,
        "EMERGENCY KILL SWITCH ACTIVATED\n\n"
        "Terminating:\n"
        "- All opencode processes\n"
        "- Telegram listener\n"
        "- All scheduled jobs\n"
        "- Cron scheduler\n\n"
        "System will be locked until recovery.",
    )
    lines.append("")

    # Create KILLED lockfile
    set_killed(d)
    lines.append("KILLED lockfile created")

    # Terminate OpenCode processes
    lines.append("Terminating OpenCode processes...")
    _kill_by_pattern("opencode", signal.SIGTERM)
    time.sleep(2)
    _kill_by_pattern("opencode", signal.SIGKILL)
    web_pid_file = d / "state" / "opencode_web.pid"
    web_pid_file.unlink(missing_ok=True)
    lines.append("OpenCode processes terminated")

    # Terminate Telegram listener
    lines.append("Terminating Telegram listener...")
    _kill_pidfile(d / "state" / "telegram.pid", signal.SIGTERM)
    time.sleep(1)
    _kill_pidfile(d / "state" / "telegram.pid", signal.SIGKILL)
    (d / "state" / "telegram.pid").unlink(missing_ok=True)

    lock_pid = d / "state" / "listener.lock" / "pid"
    _kill_pidfile(lock_pid, signal.SIGTERM)
    time.sleep(1)
    _kill_pidfile(lock_pid, signal.SIGKILL)

    lock_dir = d / "state" / "listener.lock"
    if lock_dir.exists():
        shutil.rmtree(lock_dir, ignore_errors=True)

    _kill_by_pattern("telegram_listener.sh", signal.SIGTERM)
    _kill_by_pattern("messaging/telegram/listener.sh", signal.SIGTERM)
    lines.append("Telegram listener terminated")

    # Terminate registered scheduled jobs
    lines.append("Terminating registered scheduled jobs...")
    try:
        cfg = load_typed_config(d / "adjutant.yaml")
        for schedule in cfg.schedules:
            if not schedule.script:
                continue
            script_path = schedule.script
            if not script_path.startswith("/"):
                script_path = str(d / script_path)
            _kill_by_pattern(script_path, signal.SIGTERM)
        lines.append("Scheduled job processes terminated (registry-driven)")
    except Exception:
        lines.append(
            "Could not load schedule registry — scheduled job processes may still be running"
        )

    # Backup and disable crontab
    lines.append("Disabling crontab...")
    backup_path = d / "state" / "crontab.backup"
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        if result.returncode == 0:
            backup_path.write_text(result.stdout)
    except OSError:
        pass

    try:
        subprocess.run(["crontab", "-r"], capture_output=True)
    except OSError:
        pass
    lines.append("Crontab disabled (backed up to state/crontab.backup)")

    # Log the event
    _log_journal(d, "EMERGENCY KILL SWITCH ACTIVATED")
    _adj_log(
        "emergency", "EMERGENCY KILL SWITCH ACTIVATED — all processes terminated, cron disabled"
    )
    lines.append("Event logged to journal")

    # Final notification
    lines.append("Sending final notification...")
    _send_notify(
        d,
        f"System locked down.\n\nTo recover:\n  adjutant start\n\n"
        f"KILLED lockfile created at:\n  {d}/KILLED",
    )

    lines += [
        "",
        "=========================================",
        "Emergency shutdown complete",
        "=========================================",
        "",
        "System is LOCKED.",
        "Run startup to recover:",
        "  adjutant start",
        "",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# startup
# ---------------------------------------------------------------------------


def _stop_telegram_service(adj_dir: Path) -> None:
    """Stop the Telegram listener, cleaning up all stale pid/lock files."""
    from adjutant.messaging.telegram.service import listener_stop

    listener_stop(adj_dir)


def _start_telegram_service(adj_dir: Path) -> str:
    """Start the Telegram listener. Returns status line."""
    from adjutant.messaging.telegram.service import listener_start

    return listener_start(adj_dir)


def _start_opencode_web(adj_dir: Path) -> str:
    """Start the OpenCode web server. Returns status line."""
    web_pid_file = adj_dir / "state" / "opencode_web.pid"
    owned_pid = _read_pid(web_pid_file)

    running_pid = _pgrep_first("opencode web")

    if running_pid:
        if owned_pid and running_pid == owned_pid and _pid_alive(owned_pid):
            return f"OpenCode web server already running (PID {owned_pid})"
        # Orphan — kill all and restart
        _kill_by_pattern("opencode web", signal.SIGTERM)
        time.sleep(2)
        _kill_by_pattern("opencode web", signal.SIGKILL)
        web_pid_file.unlink(missing_ok=True)

    # Launch
    log_file = adj_dir / "state" / "opencode_web.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    opencode_bin = shutil.which("opencode")
    if not opencode_bin:
        return "OpenCode not found in PATH — web server not started"

    try:
        with open(log_file, "a") as lf:
            proc = subprocess.Popen(
                [opencode_bin, "web", "--mdns"],
                stdout=lf,
                stderr=lf,
                start_new_session=True,
            )
        web_pid_file.parent.mkdir(parents=True, exist_ok=True)
        web_pid_file.write_text(str(proc.pid))
        time.sleep(2)
        if _pgrep_first("opencode web"):
            return f"OpenCode web server started (PID {proc.pid})"
        return f"OpenCode web server failed to start (check {log_file})"
    except OSError as e:
        return f"OpenCode web server error: {e}"


def _sync_schedule_crontab(adj_dir: Path) -> str:
    """Sync schedule registry to crontab. Returns status line."""
    try:
        from adjutant.capabilities.schedule.install import install_all

        install_all(adj_dir)
    except Exception:
        return "Could not load schedule registry — crontab not synced"

    try:
        result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        count = result.stdout.count("# adjutant:")
        if count > 0:
            return f"Crontab synced ({count} registered job(s))"
        return "Crontab synced (no enabled jobs)"
    except OSError:
        return "Crontab synced"


def startup(
    adj_dir: Optional[Path] = None,
    interactive: bool = True,
) -> str:
    """Unified startup: handles both normal start and emergency recovery.

    Args:
        adj_dir:     Path to Adjutant directory. Defaults to $ADJ_DIR.
        interactive: If True, prompt for confirmation when in recovery mode.
                     Set to False when called non-interactively (e.g. from restart).

    Returns:
        Human-readable output string.
    """
    from adjutant.core.lockfiles import is_killed, is_paused, clear_killed

    d = adj_dir or _adj_dir()
    ts = _timestamp()
    lines: list[str] = [f"Adjutant Startup - {ts}", ""]

    # Mode detection
    recovery_mode = is_killed(d)
    if recovery_mode:
        lines.append("KILLED lockfile detected - entering RECOVERY MODE")
        lines.append("")

    # Recovery mode confirmation
    if recovery_mode:
        lines += [
            "This will:",
            "  - Remove KILLED lockfile",
            "  - Restore crontab from backup",
            "  - Start telegram listener",
            "  - Start OpenCode web server",
            "  - Send status to Telegram",
            "",
        ]

        if interactive:
            try:
                answer = input("Proceed with recovery? (y/N): ").strip().lower()
                if answer not in ("y", "yes"):
                    lines.append("Cancelled.")
                    return "\n".join(lines)
            except (EOFError, KeyboardInterrupt):
                lines.append("Cancelled.")
                return "\n".join(lines)

        # Remove KILLED
        clear_killed(d)
        lines.append("KILLED lockfile removed")

        # Restore crontab
        backup = d / "state" / "crontab.backup"
        if backup.exists():
            try:
                subprocess.run(["crontab", str(backup)], check=True)
                lines.append("Crontab restored")
            except (subprocess.CalledProcessError, OSError):
                lines.append("Failed to restore crontab")
        else:
            lines.append("No crontab backup found")

        # Re-sync schedule registry
        lines.append(_sync_schedule_crontab(d))

        _adj_log("startup", "System recovered from emergency kill switch")
        _log_journal(d, "System recovered from emergency kill switch")

    # Start services
    lines += ["", "Starting services...", ""]

    # Telegram listener
    lines.append(_start_telegram_service(d))

    # OpenCode web server
    lines.append(_start_opencode_web(d))

    # Post-startup PID sync
    sync_pid = _pgrep_first("messaging/telegram/listener")
    if sync_pid:
        lock_dir = d / "state" / "listener.lock"
        if not lock_dir.exists():
            lock_dir.mkdir(parents=True, exist_ok=True)
            (lock_dir / "pid").write_text(str(sync_pid))
        tg_pid_file = d / "state" / "telegram.pid"
        if not tg_pid_file.exists():
            tg_pid_file.write_text(str(sync_pid))

    sync_web = _pgrep_first("opencode web")
    web_pid_file = d / "state" / "opencode_web.pid"
    if sync_web and not web_pid_file.exists():
        web_pid_file.write_text(str(sync_web))

    # Sync schedules to crontab
    lines.append(_sync_schedule_crontab(d))

    # Gather status
    lines += ["", "Gathering status..."]
    try:
        from adjutant.observability.status import get_status

        status_output = get_status(d)
    except Exception:
        status_output = "Status unavailable"

    # Send notification
    lines += ["", "Sending Telegram notification..."]
    if recovery_mode:
        notification = (
            f"Adjutant Recovered & Online\n\nRecovery complete at {ts}\n\n"
            f"{status_output}\n\nSystem is operational.\n"
            "Send /pause to pause, or /status for updates."
        )
    else:
        notification = (
            f"Adjutant Online\n\nStarted at {ts}\n\n"
            f"{status_output}\n\nSystem is operational.\n"
            "Send /pause to pause, or /status for updates."
        )
    try:
        _send_notify(d, notification)
        lines.append("Telegram notification sent")
    except Exception:
        lines.append("Failed to send Telegram notification")

    lines += [
        "",
        "=========================================",
        "Startup complete",
        "=========================================",
        "",
        "Current status:",
        status_output,
        "",
    ]

    if is_paused(d):
        lines += [
            "System is PAUSED",
            "  Remove with: adjutant resume",
            "  Or send /resume via Telegram",
        ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI entrypoints
# ---------------------------------------------------------------------------


def main_pause(argv: list[str] | None = None) -> int:
    try:
        print(pause())
        return 0
    except RuntimeError as e:
        print(f"ERROR:{e}")
        return 1


def main_resume(argv: list[str] | None = None) -> int:
    try:
        print(resume())
        return 0
    except RuntimeError as e:
        print(f"ERROR:{e}")
        return 1


def main_restart(argv: list[str] | None = None) -> int:
    try:
        print(restart())
        return 0
    except RuntimeError as e:
        print(f"ERROR:{e}")
        return 1


def main_emergency_kill(argv: list[str] | None = None) -> int:
    try:
        print(emergency_kill())
        return 0
    except RuntimeError as e:
        print(f"ERROR:{e}")
        return 1


def main_startup(argv: list[str] | None = None) -> int:
    interactive = "--non-interactive" not in (argv or sys.argv)
    try:
        print(startup(interactive=interactive))
        return 0
    except RuntimeError as e:
        print(f"ERROR:{e}")
        return 1
