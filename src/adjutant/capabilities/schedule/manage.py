"""Scheduled job CRUD operations.

Replaces: scripts/capabilities/schedule/manage.sh

Provides functions for registering, listing, inspecting, enabling/disabling,
and removing scheduled jobs declared in adjutant.yaml schedules:.

Uses load_typed_config() from core/config.py (Python) instead of awk
(bash). All mutations rewrite the YAML schedules: block in-place.

The ScheduleConfig pydantic model in config.py does not include notify or
kb_name/kb_operation fields — these are accessed via the raw dict API
(load_config) for full fidelity.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import yaml


# ---------------------------------------------------------------------------
# Raw YAML helpers — read/write the schedules: block without losing other keys
# ---------------------------------------------------------------------------


def _load_yaml_raw(config_path: Path) -> dict:
    """Load adjutant.yaml as a raw dict. Returns {} if missing/invalid."""
    if not config_path.is_file():
        return {}
    try:
        with open(config_path) as f:
            data = yaml.safe_load(f)
        return data if isinstance(data, dict) else {}
    except (yaml.YAMLError, OSError):
        return {}


def _save_yaml_raw(config_path: Path, data: dict) -> None:
    """Write dict back to YAML, preserving key order."""
    with open(config_path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def _get_schedules(data: dict) -> list[dict]:
    """Extract the schedules list from the raw config dict."""
    raw = data.get("schedules")
    if not isinstance(raw, list):
        return []
    return [s for s in raw if isinstance(s, dict)]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _resolve_path(p: str, adj_dir: Path) -> str:
    """Absolute path stays as-is; relative is prepended with adj_dir."""
    if p.startswith("/"):
        return p
    return str(adj_dir / p)


def _resolve_command(entry: dict, adj_dir: Path) -> str:
    """Resolve an entry to a runnable command string.

    Supports:
      - script: <path>
      - kb_name: <name> + kb_operation: <operation>
    """
    kb_name = entry.get("kb_name", "") or ""
    kb_operation = entry.get("kb_operation", "") or ""

    if kb_name and kb_operation:
        return f"bash {adj_dir}/scripts/capabilities/kb/run.sh {kb_name} {kb_operation}"

    script = entry.get("script", "") or ""
    if script:
        return _resolve_path(script, adj_dir)

    return ""


# ---------------------------------------------------------------------------
# Query API
# ---------------------------------------------------------------------------


def schedule_count(config_path: Path) -> int:
    """Return the number of registered schedule entries."""
    data = _load_yaml_raw(config_path)
    return len(_get_schedules(data))


def schedule_exists(config_path: Path, name: str) -> bool:
    """Return True if a job with the given name is registered."""
    data = _load_yaml_raw(config_path)
    return any(s.get("name") == name for s in _get_schedules(data))


def schedule_list(config_path: Path) -> list[dict]:
    """Return all registered schedule entries as raw dicts."""
    data = _load_yaml_raw(config_path)
    return _get_schedules(data)


def schedule_get(config_path: Path, name: str) -> Optional[dict]:
    """Return the raw dict for a schedule entry, or None if not found."""
    data = _load_yaml_raw(config_path)
    for s in _get_schedules(data):
        if s.get("name") == name:
            return dict(s)
    return None


def schedule_get_field(config_path: Path, name: str, field: str) -> str:
    """Return a single field from a schedule entry, or empty string."""
    entry = schedule_get(config_path, name)
    if entry is None:
        return ""
    val = entry.get(field)
    if val is None:
        return ""
    return str(val)


# ---------------------------------------------------------------------------
# Mutation helpers
# ---------------------------------------------------------------------------

_VALID_JOB_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


def _schedule_append(
    config_path: Path,
    name: str,
    description: str,
    schedule: str,
    script: str,
    logpath: Optional[str] = None,
    enabled: bool = True,
    notify: bool = False,
) -> None:
    """Append a new job entry to the schedules: block in adjutant.yaml."""
    if logpath is None:
        logpath = f"state/{name}.log"

    data = _load_yaml_raw(config_path)
    if "schedules" not in data or not isinstance(data.get("schedules"), list):
        data["schedules"] = []

    entry: dict = {
        "name": name,
        "description": description,
        "schedule": schedule,
        "script": script,
        "log": logpath,
        "enabled": enabled,
        "notify": notify,
    }
    data["schedules"].append(entry)
    _save_yaml_raw(config_path, data)


# ---------------------------------------------------------------------------
# Public mutation API
# ---------------------------------------------------------------------------


def schedule_add(
    config_path: Path,
    name: str,
    description: str,
    schedule: str,
    script: str,
    logpath: Optional[str] = None,
    adj_dir: Optional[Path] = None,
) -> None:
    """Register a job and install its crontab entry.

    Args:
        config_path: Path to adjutant.yaml.
        name: Unique job name (lowercase alphanumeric + hyphens/underscores).
        description: Human-readable description.
        schedule: Cron expression (e.g. '0 9 * * 1-5').
        script: Path to the script (absolute or relative to adj_dir).
        logpath: Log file path (default: state/<name>.log).
        adj_dir: Adjutant root directory (for crontab install).

    Raises:
        ValueError: If name is invalid or already registered.
    """
    if not _VALID_JOB_NAME.match(name):
        raise ValueError(
            f"Job name must be lowercase alphanumeric with hyphens/underscores "
            f"(e.g. 'portfolio-fetch'), got '{name}'."
        )

    if schedule_exists(config_path, name):
        raise ValueError(
            f"Job '{name}' already registered. Use schedule_set_enabled or schedule_remove first."
        )

    _schedule_append(config_path, name, description, schedule, script, logpath, enabled=True)

    if adj_dir is not None:
        from adjutant.capabilities.schedule.install import install_one

        install_one(adj_dir, name)


def schedule_remove(
    config_path: Path,
    name: str,
    adj_dir: Optional[Path] = None,
) -> None:
    """Remove a job from the registry and uninstall its crontab entry.

    Raises:
        ValueError: If the job is not registered.
    """
    if not schedule_exists(config_path, name):
        raise ValueError(f"Job '{name}' not found in registry.")

    # Uninstall crontab first
    if adj_dir is not None:
        from adjutant.capabilities.schedule.install import uninstall_one

        uninstall_one(adj_dir, name)

    data = _load_yaml_raw(config_path)
    schedules = _get_schedules(data)
    data["schedules"] = [s for s in schedules if s.get("name") != name]
    _save_yaml_raw(config_path, data)


def schedule_set_enabled(
    config_path: Path,
    name: str,
    enabled: bool,
    adj_dir: Optional[Path] = None,
) -> None:
    """Enable or disable a job.

    Args:
        config_path: Path to adjutant.yaml.
        name: Job name.
        enabled: True to enable, False to disable.
        adj_dir: Adjutant root directory (for crontab sync).

    Raises:
        ValueError: If the job is not registered.
    """
    if not schedule_exists(config_path, name):
        raise ValueError(f"Job '{name}' not found in registry.")

    data = _load_yaml_raw(config_path)
    for s in data.get("schedules", []):
        if isinstance(s, dict) and s.get("name") == name:
            s["enabled"] = enabled
            break
    _save_yaml_raw(config_path, data)

    if adj_dir is not None:
        from adjutant.capabilities.schedule.install import install_one, uninstall_one

        if enabled:
            install_one(adj_dir, name)
        else:
            uninstall_one(adj_dir, name)
