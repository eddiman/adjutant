"""Adjutant lifecycle control: pause, resume, restart, emergency_kill, startup.

Replaces five bash scripts:
  scripts/lifecycle/pause.sh
  scripts/lifecycle/resume.sh
  scripts/lifecycle/restart.sh
  scripts/lifecycle/emergency_kill.sh
  scripts/lifecycle/startup.sh
"""

from __future__ import annotations

import contextlib
import os
import shutil
import signal
import subprocess
import time
from datetime import datetime
from pathlib import Path

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
    except Exception:  # noqa: BLE001 — last-resort: logging itself failed
        import sys

        print(f"[{component}] {message}", file=sys.stderr)


def _send_notify(adj_dir: Path, text: str) -> None:
    """Send a Telegram notification, silently ignoring failures."""
    try:
        from adjutant.messaging.telegram.notify import send_notify

        send_notify(text, adj_dir)
    except Exception:  # noqa: BLE001 — non-fatal, matches bash `|| true`
        pass


def _kill_by_pattern(pattern: str, sig: signal.Signals = signal.SIGTERM) -> None:
    """Send signal to all processes matching the pattern. Silently ignores errors."""
    from adjutant.core.process import find_by_cmdline

    for proc in find_by_cmdline(pattern):
        with contextlib.suppress(ProcessLookupError, PermissionError, OSError):
            os.kill(proc.pid, sig)


def _kill_pidfile(pid_file: Path, sig: signal.Signals = signal.SIGTERM) -> None:
    """Send signal to PID in file. Silently ignores missing file / dead process."""
    try:
        pid = int(pid_file.read_text().strip())
        os.kill(pid, sig)
    except (FileNotFoundError, ValueError, ProcessLookupError, PermissionError):
        pass


def _pid_alive(pid: int) -> bool:
    """Check if PID is running. Delegates to core.process.pid_is_alive."""
    from adjutant.core.process import pid_is_alive

    return pid_is_alive(pid)


def _pgrep_first(pattern: str) -> int | None:
    """Return first PID matching pattern, or None."""
    from adjutant.core.process import find_by_cmdline

    procs = find_by_cmdline(pattern)
    return procs[0].pid if procs else None


def _read_pid(path: Path) -> int | None:
    """Read integer PID from file, or return None."""
    try:
        return int(path.read_text().strip())
    except (FileNotFoundError, ValueError):
        return None


# ---------------------------------------------------------------------------
# pause
# ---------------------------------------------------------------------------


def pause(adj_dir: Path | None = None) -> str:
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


def resume(adj_dir: Path | None = None) -> str:
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


def restart(adj_dir: Path | None = None) -> str:
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


def emergency_kill(adj_dir: Path | None = None) -> str:
    """Nuclear shutdown of all systems.

    Creates KILLED lockfile, terminates all processes, backs up and removes
    crontab, logs the event, and sends Telegram notifications.

    Returns:
        Human-readable output string.
    """
    from adjutant.core.config import load_typed_config
    from adjutant.core.lockfiles import set_killed

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

    # Terminate OpenCode processes (scoped to this Adjutant's ADJ_DIR)
    adj_dir_str = str(d)
    lines.append("Terminating OpenCode processes...")
    _kill_by_pattern(f"opencode.*{adj_dir_str}", signal.SIGTERM)
    time.sleep(2)
    _kill_by_pattern(f"opencode.*{adj_dir_str}", signal.SIGKILL)
    # Also kill any opencode processes launched by this Adjutant's listener
    _kill_by_pattern("opencode.*adjutant", signal.SIGTERM)
    time.sleep(1)
    _kill_by_pattern("opencode.*adjutant", signal.SIGKILL)
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
    except Exception:  # noqa: BLE001 — graceful degradation on schedule term
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

    with contextlib.suppress(OSError):
        subprocess.run(["crontab", "-r"], capture_output=True)
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


def _sync_schedule_crontab(adj_dir: Path) -> str:
    """Sync schedule registry to crontab. Returns status line."""
    try:
        from adjutant.capabilities.schedule.install import install_all

        install_all(adj_dir)
    except Exception:  # noqa: BLE001 — graceful degradation on crontab sync
        return "Could not load schedule registry — crontab not synced"

    try:
        result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        count = result.stdout.count("# adjutant:")
        if count > 0:
            return f"Crontab synced ({count} registered job(s))"
        return "Crontab synced (no enabled jobs)"
    except OSError:
        return "Crontab synced"


def _detect_backend_change(adj_dir: Path) -> str | None:
    """Compare config backend against state/backend.txt.

    Returns the previous backend name if a switch is detected, else None.
    Writes current backend to state file.
    """
    try:
        from adjutant.core.config import load_typed_config

        config = load_typed_config(adj_dir / "adjutant.yaml")
        current = config.llm.backend
    except Exception:  # noqa: BLE001
        current = "opencode"

    state_file = adj_dir / "state" / "backend.txt"
    if state_file.exists():
        previous = state_file.read_text().strip()
        if previous != current:
            return previous
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(current)
    return None


def _handle_backend_switch(adj_dir: Path, old_backend: str, new_backend: str) -> list[str]:
    """Perform side effects when the backend changes. Returns status lines."""
    lines: list[str] = []

    # 1. Clear active session (format incompatible between backends)
    session_file = adj_dir / "state" / "telegram_session.json"
    if session_file.exists():
        session_file.unlink()
        lines.append("Cleared stale session (format incompatible)")

    # 2. Translate model ID
    model_file = adj_dir / "state" / "telegram_model.txt"
    if model_file.exists():
        from adjutant.core.backend import get_backend

        current_model = model_file.read_text().strip()
        if current_model not in {"cheap", "medium", "expensive"}:
            backend = get_backend(new_backend)
            new_model = backend.translate_model_id(current_model)
            if new_model != current_model:
                model_file.write_text(new_model)
                lines.append(f"Translated model: {current_model} → {new_model}")

    # 3. Record new backend
    (adj_dir / "state" / "backend.txt").write_text(new_backend)

    # 5. Log
    _adj_log("backend", f"Switched from {old_backend} to {new_backend}")
    lines.append(f"Backend switched: {old_backend} → {new_backend}")

    # 6. Warn about nested opencode dependencies
    if new_backend == "claude-cli":
        warnings = _warn_nested_opencode_dependencies(adj_dir)
        lines.extend(warnings)

    return lines


def _warn_nested_opencode_dependencies(adj_dir: Path) -> list[str]:
    """Warn about KBs that internally call opencode, which still need an API key.

    Some KBs (e.g. portfolio-kb) have their own analyze pipelines that internally
    call ``opencode run`` for LLM signal generation. Switching to claude-cli does
    NOT affect these nested dependencies — they still require a working OpenCode
    installation and API key.
    """
    warnings: list[str] = []
    try:
        from adjutant.capabilities.kb.manage import kb_list

        known_nested_patterns = {"portfolio"}
        nested_kbs = [
            kb.name
            for kb in kb_list(adj_dir)
            if any(p in kb.name.lower() or p in kb.path.lower() for p in known_nested_patterns)
        ]
        if nested_kbs:
            msg = (
                f"Warning: KB(s) {nested_kbs} internally use OpenCode for LLM calls. "
                f"These still require a working `opencode` binary and API key even though "
                f"the main backend is now claude-cli."
            )
            _adj_log("backend", msg)
            warnings.append(msg)
    except Exception:  # noqa: BLE001
        pass  # Registry unavailable — skip warning
    return warnings


def startup(
    adj_dir: Path | None = None,
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
    from adjutant.core.lockfiles import clear_killed, is_killed, is_paused

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

    # Backend switch detection
    old_backend = _detect_backend_change(d)
    if old_backend:
        lines += ["", "Backend change detected!", ""]
        try:
            from adjutant.core.config import load_typed_config

            new_backend = load_typed_config(d / "adjutant.yaml").llm.backend
        except Exception:  # noqa: BLE001
            new_backend = "opencode"
        switch_lines = _handle_backend_switch(d, old_backend, new_backend)
        lines.extend(f"  {l}" for l in switch_lines)

    # Start services
    lines += ["", "Starting services...", ""]

    # Telegram listener
    lines.append(_start_telegram_service(d))

    # Post-startup PID sync for the telegram listener
    sync_pid = _pgrep_first("messaging/telegram/listener")
    if sync_pid:
        lock_dir = d / "state" / "listener.lock"
        if not lock_dir.exists():
            lock_dir.mkdir(parents=True, exist_ok=True)
            (lock_dir / "pid").write_text(str(sync_pid))
        tg_pid_file = d / "state" / "telegram.pid"
        if not tg_pid_file.exists():
            tg_pid_file.write_text(str(sync_pid))

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
