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

import contextlib
import os
import shlex
import subprocess
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _marker(name: str) -> str:
    """Return the crontab marker string for a job name."""
    return f"# adjutant:{name}"


def _snapshot_path() -> str:
    """Build a minimal PATH for cron entries.

    Cron runs with a minimal PATH (/usr/bin:/bin) which typically excludes
    directories like /opt/homebrew/bin where tools such as opencode live.
    Instead of dumping the full shell PATH (which can exceed cron's line-
    length limits), we include only essential directories: system paths,
    Homebrew, and ~/.local/bin.

    Uses :data:`adjutant.core.platform.ESSENTIAL_PATH_DIRS` — the same
    directory list that :func:`adjutant.core.platform.ensure_path` uses
    at runtime.
    """
    from adjutant.core.platform import ESSENTIAL_PATH_DIRS

    essential = list(ESSENTIAL_PATH_DIRS)
    # Add ~/.local/bin if it exists (user-installed tools)
    local_bin = Path.home() / ".local" / "bin"
    if local_bin.is_dir():
        essential.insert(0, str(local_bin))
    return ":".join(essential)


def _resolve_path(p: str, adj_dir: Path) -> str:
    """Absolute path stays as-is; relative is prepended with adj_dir."""
    from adjutant.capabilities.schedule.manage import resolve_path

    return resolve_path(p, adj_dir)


def _resolve_command(entry: dict[str, Any], adj_dir: Path) -> str:
    """Resolve a schedule entry dict to a runnable command string."""
    from adjutant.capabilities.schedule.manage import resolve_command

    return resolve_command(entry, adj_dir)


def _resolve_command_argv(entry: dict[str, Any], adj_dir: Path) -> list[str]:
    """Resolve a schedule entry dict to a runnable argv list."""
    from adjutant.capabilities.schedule.manage import resolve_command_argv

    return resolve_command_argv(entry, adj_dir)


def _shell_quote_env_value(value: str) -> str:
    """Return a shell-safe value for inline VAR=... assignments."""
    return shlex.quote(value)


def _load_env_assignments(adj_dir: Path) -> list[str]:
    """Load .env as shell-safe KEY=value assignments for cron."""
    from adjutant.core.env import get_credential

    env_file = adj_dir / ".env"
    if not env_file.is_file():
        return []

    assignments: list[str] = []
    for line in env_file.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, _ = stripped.partition("=")
        key = key.strip()
        if not key:
            continue
        value = get_credential(key, env_file)
        if value is None:
            continue
        assignments.append(f"{key}={_shell_quote_env_value(value)}")
    return assignments


def _cron_shell_command(argv: list[str], log_path: str) -> str:
    """Build the shell command that cron executes for one job."""
    command = shlex.join(argv)
    return f"exec {command} >> {shlex.quote(log_path)} 2>&1"


def _job_environment(adj_dir: Path) -> dict[str, str]:
    """Return the environment for immediate schedule execution."""
    env = dict(os.environ)
    env["ADJ_DIR"] = str(adj_dir)
    env.setdefault("ADJUTANT_HOME", str(adj_dir))

    env_file = adj_dir / ".env"
    if env_file.is_file():
        from adjutant.core.env import get_credential

        for line in env_file.read_text().splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, _, _ = stripped.partition("=")
            key = key.strip()
            if not key:
                continue
            value = get_credential(key, env_file)
            if value is not None:
                env[key] = value
    return env


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
    command_argv = _resolve_command_argv(entry, adj_dir)

    if not command_argv:
        raise ValueError(f"Job '{name}' has no runnable script or KB operation configured.")

    # Ensure log directory exists
    with contextlib.suppress(OSError):
        Path(log_path).parent.mkdir(parents=True, exist_ok=True)

    marker = _marker(name)
    path_env = _snapshot_path()
    env_assignments = _load_env_assignments(adj_dir)

    if notify:
        wrap_py = adj_dir / "src" / "adjutant" / "capabilities" / "schedule" / "notify_wrap.py"
        venv_py = adj_dir / ".venv" / "bin" / "python"
        python = str(venv_py) if venv_py.exists() else "python3"
        inner_argv = [python, str(wrap_py), name, *command_argv]
    else:
        inner_argv = command_argv

    env_prefix = [
        f"PATH={_shell_quote_env_value(path_env)}",
        f"ADJ_DIR={_shell_quote_env_value(str(adj_dir))}",
        f"ADJUTANT_HOME={_shell_quote_env_value(str(adj_dir))}",
        *env_assignments,
    ]
    shell_cmd = _cron_shell_command(inner_argv, log_path)

    cron_line = f"{sched} {' '.join(env_prefix)} /bin/bash -lc {shlex.quote(shell_cmd)}  {marker}"

    # Remove any existing entry for this job, then append new one
    existing = _read_crontab()
    lines = [line for line in existing.splitlines() if marker not in line]
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

    lines = [line for line in existing.splitlines() if marker not in line]
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
        ValueError: If the job is not registered, has no command,
            or script is missing/not executable.
    """
    from adjutant.capabilities.schedule.manage import schedule_exists, schedule_get

    config = _config_path(adj_dir)

    if not schedule_exists(config, name):
        raise ValueError(f"Job '{name}' not found in registry.")

    entry = schedule_get(config, name)
    command_argv = _resolve_command_argv(entry or {}, adj_dir)

    if not command_argv:
        raise ValueError(f"Job '{name}' has no runnable script or KB operation configured.")

    command_path = Path(command_argv[0])
    if command_path.suffix == ".sh":
        if not command_path.is_file():
            raise ValueError(f"Script not found: {command_path}")
        if not os.access(command_path, os.X_OK):
            raise ValueError(f"Script is not executable: {command_path}")

    result = subprocess.run(command_argv, env=_job_environment(adj_dir), cwd=str(adj_dir))
    return result.returncode
