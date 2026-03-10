"""Crontab reconciler for scheduled jobs.

Replaces: scripts/capabilities/schedule/install.sh

Single source of truth for how managed cron entries are formatted.
All functions read job metadata from adjutant.yaml via manage.py.

Crontab entry format:
  <schedule> <resolved_command> >> <resolved_log> 2>&1  # adjutant:<name>

The "# adjutant:<name>" marker is the identity key used to find/replace
existing entries.

Backwards compatibility: lines containing ".adjutant" but without
"# adjutant:<name>" (old pre-phase-8 format) are left untouched.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _marker(name: str) -> str:
    """Return the crontab marker string for a job name."""
    return f"# adjutant:{name}"


def _resolve_path(p: str, adj_dir: Path) -> str:
    """Absolute path stays as-is; relative is prepended with adj_dir."""
    if p.startswith("/"):
        return p
    return str(adj_dir / p)


def _resolve_command(entry: dict, adj_dir: Path) -> str:
    """Resolve a schedule entry dict to a runnable command string."""
    kb_name = entry.get("kb_name", "") or ""
    kb_operation = entry.get("kb_operation", "") or ""

    if kb_name and kb_operation:
        venv_py = adj_dir / ".venv" / "bin" / "python"
        python = str(venv_py) if venv_py.exists() else "python3"
        return f"{python} -m adjutant kb run {kb_name} {kb_operation}"

    script = entry.get("script", "") or ""
    if script:
        return _resolve_path(script, adj_dir)

    return ""


def _read_crontab() -> str:
    """Read the current crontab. Returns empty string if none exists."""
    result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    if result.returncode == 0:
        return result.stdout
    return ""


def _write_crontab(content: str) -> None:
    """Write content to crontab. Empty content clears the crontab."""
    if not content.strip():
        subprocess.run(["crontab", "-r"], capture_output=True)
        return
    proc = subprocess.run(["crontab", "-"], input=content, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"crontab write failed: {proc.stderr.strip()}")


def _config_path(adj_dir: Path) -> Path:
    return adj_dir / "adjutant.yaml"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def install_all(adj_dir: Path) -> None:
    """Reconcile the full crontab with the current registry.

    For each enabled job: ensure its crontab line exists and is current.
    For each disabled job: ensure no crontab line exists.
    Lines without a "# adjutant:<name>" suffix are left untouched.
    Idempotent — safe to call repeatedly.
    """
    from adjutant.capabilities.schedule.manage import schedule_list

    config = _config_path(adj_dir)
    for entry in schedule_list(config):
        name = entry.get("name", "")
        if not name:
            continue
        if entry.get("enabled") is True or entry.get("enabled") == "true":
            install_one(adj_dir, name)
        else:
            uninstall_one(adj_dir, name)


def install_one(adj_dir: Path, name: str) -> None:
    """Install or update the crontab entry for a single job.

    Reads job metadata from adjutant.yaml via manage.py.

    Args:
        adj_dir: Adjutant root directory.
        name: Job name.

    Raises:
        ValueError: If the job is not registered or has no runnable command.
    """
    from adjutant.capabilities.schedule.manage import schedule_exists, schedule_get

    config = _config_path(adj_dir)

    if not schedule_exists(config, name):
        raise ValueError(f"Job '{name}' not found in registry.")

    entry = schedule_get(config, name)
    if entry is None:
        raise ValueError(f"Job '{name}' not found in registry.")

    sched = entry.get("schedule", "") or ""
    log_raw = entry.get("log", "") or f"state/{name}.log"
    notify = entry.get("notify", False)

    log_path = _resolve_path(str(log_raw), adj_dir)
    script_path = _resolve_command(entry, adj_dir)

    if not script_path:
        raise ValueError(f"Job '{name}' has no runnable script or KB operation configured.")

    # Ensure log directory exists
    try:
        Path(log_path).parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass

    marker = _marker(name)

    if notify:
        wrap_py = adj_dir / "src" / "adjutant" / "capabilities" / "schedule" / "notify_wrap.py"
        venv_py = adj_dir / ".venv" / "bin" / "python"
        python = str(venv_py) if venv_py.exists() else "python3"
        cron_line = f"{sched} ADJ_DIR={adj_dir} {python} {wrap_py} {name} {script_path} >> {log_path} 2>&1  {marker}"
    else:
        cron_line = f"{sched} ADJ_DIR={adj_dir} {script_path} >> {log_path} 2>&1  {marker}"

    # Remove any existing entry for this job, then append new one
    existing = _read_crontab()
    lines = [l for l in existing.splitlines() if marker not in l]
    lines.append(cron_line)
    _write_crontab("\n".join(lines) + "\n")


def uninstall_one(adj_dir: Path, name: str) -> None:
    """Remove the crontab entry for a single job.

    Always succeeds — no error if entry was not present.
    """
    marker = _marker(name)
    existing = _read_crontab()

    if marker not in existing:
        return

    lines = [l for l in existing.splitlines() if marker not in l]
    _write_crontab("\n".join(lines) + "\n" if lines else "")


def run_now(adj_dir: Path, name: str) -> int:
    """Run a job immediately in the foreground.

    Used by "adjutant schedule run <name>" and "/schedule run <name>".

    Args:
        adj_dir: Adjutant root directory.
        name: Job name.

    Returns:
        Exit code of the job script.

    Raises:
        ValueError: If the job is not registered, has no command, or script is missing/not executable.
    """
    from adjutant.capabilities.schedule.manage import schedule_exists, schedule_get

    import os

    config = _config_path(adj_dir)

    if not schedule_exists(config, name):
        raise ValueError(f"Job '{name}' not found in registry.")

    entry = schedule_get(config, name)
    command = _resolve_command(entry or {}, adj_dir)

    if not command:
        raise ValueError(f"Job '{name}' has no runnable script or KB operation configured.")

    # If the command is a shell string (not a bare file path), run via shell
    kb_name = (entry or {}).get("kb_name", "") or ""
    kb_operation = (entry or {}).get("kb_operation", "") or ""
    if kb_name and kb_operation:
        env = {**os.environ, "ADJ_DIR": str(adj_dir)}
        result = subprocess.run(command, shell=True, env=env)
        return result.returncode

    script_path = Path(command)
    if not script_path.is_file():
        raise ValueError(f"Script not found: {command}")
    if not os.access(script_path, os.X_OK):
        raise ValueError(f"Script is not executable: {command}")

    result = subprocess.run(["bash", str(script_path)])
    return result.returncode
