"""Adjutant status reporter.

Checks running/paused/killed state, lists scheduled jobs, shows the last
heartbeat, notification count, and recent actions.

Replaces bash scripts/observability/status.sh.
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


def _adj_dir() -> Path:
    raw = os.environ.get("ADJ_DIR", "").strip()
    if not raw:
        raise RuntimeError("ADJ_DIR not set")
    return Path(raw)


def _cron_human(expr: str) -> str:
    """Convert a 5-field cron expression to a short English description.

    Handles the patterns actually used in adjutant.yaml. Falls back to
    the raw expression for unrecognised patterns.
    """
    parts = expr.split()
    if len(parts) != 5:
        return expr
    minute, hour, _dom, _month, dow = parts

    # Day-of-week → phrase
    dow_map = {
        "1-5": "weekdays",
        "0,6": "weekends",
        "6,0": "weekends",
        "0": "Sundays",
        "1": "Mondays",
        "2": "Tuesdays",
        "3": "Wednesdays",
        "4": "Thursdays",
        "5": "Fridays",
        "6": "Saturdays",
        "*": "every day",
    }
    day_phrase = dow_map.get(dow, f"on dow={dow}")

    # */N minute interval
    if minute.startswith("*/") and hour == "*":
        interval = minute[2:]
        return f"every {interval} minutes"

    # Hourly (fixed minute, hour=*)
    if minute.isdigit() and hour == "*":
        return f"every hour at :{minute}"

    # Specific time(s)
    if minute.isdigit() and hour != "*":
        min_fmt = minute.zfill(2)
        if "," in hour:
            times = " and ".join(h.zfill(2) + ":" + min_fmt for h in hour.split(","))
        else:
            times = hour.zfill(2) + ":" + min_fmt
        return f"at {times}, {day_phrase}"

    return expr


def _format_timestamp(raw: str) -> str:
    """Parse an ISO-8601 UTC timestamp and format as 'Mon 09 Mar at 14:00'."""
    try:
        dt = datetime.strptime(raw, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        return dt.strftime("%a %d %b at %H:%M")
    except (ValueError, TypeError):
        return raw or ""


def _live_crontab() -> str:
    """Return the current user crontab, or empty string if none."""
    try:
        result = subprocess.run(
            ["crontab", "-l"],
            capture_output=True,
            text=True,
        )
        return result.stdout if result.returncode == 0 else ""
    except OSError:
        return ""


def _load_schedules(adj_dir: Path) -> list[dict]:
    """Load schedule list from adjutant.yaml via the typed config."""
    try:
        from adjutant.core.config import load_typed_config

        config = load_typed_config(adj_dir / "adjutant.yaml")
        return [
            {
                "name": s.name,
                "description": s.description,
                "schedule": s.schedule,
                "script": s.script,
                "log": s.log,
                "enabled": s.enabled,
                "notify": False,  # not in ScheduleConfig model — default False
            }
            for s in config.schedules
            if s.name
        ]
    except Exception:
        return []


def _status_line(adj_dir: Path) -> str:
    from adjutant.core.lockfiles import is_killed, is_paused

    if is_killed(adj_dir):
        return "Adjutant has been killed and is not running."
    elif is_paused(adj_dir):
        return "Adjutant is paused. Send /resume to bring it back."
    else:
        return "Adjutant is up and running."


def _schedules_section(adj_dir: Path) -> str:
    schedules = _load_schedules(adj_dir)
    if not schedules:
        return "No scheduled jobs configured."

    live = _live_crontab()
    active: list[str] = []
    inactive: list[str] = []

    for s in schedules:
        name = s["name"]
        desc = s.get("description", "")
        sched = s.get("schedule", "")
        enabled = s.get("enabled", False)
        notify = s.get("notify", False)

        human = _cron_human(sched)
        notify_note = " (notifies)" if notify else ""

        line = f"  {name} — {desc}, {human}{notify_note}"

        if enabled:
            if f"# adjutant:{name}" not in live:
                inactive.append(line + " [not in crontab]")
            else:
                active.append(line)
        else:
            inactive.append(line + " [disabled]")

    parts: list[str] = []
    if active:
        parts.append("Active jobs:\n" + "\n".join(active))
    if inactive:
        parts.append("Inactive jobs:\n" + "\n".join(inactive))
    return "\n".join(parts) if parts else "No scheduled jobs configured."


def _heartbeat_section(adj_dir: Path) -> str:
    hb_file = adj_dir / "state" / "last_heartbeat.json"
    if not hb_file.exists():
        return "No autonomous cycles have run yet."

    try:
        data = json.loads(hb_file.read_text())
    except (json.JSONDecodeError, OSError):
        return "No autonomous cycles have run yet."

    ts_raw = data.get("timestamp", "")
    hb_type = data.get("type", "")
    trigger = data.get("trigger", "")
    action = data.get("action", "")
    project = data.get("project", "")

    ts = _format_timestamp(ts_raw)
    line = f"Last cycle ran {ts}"
    if hb_type:
        line += f" ({hb_type})"
    if project:
        line += f" on {project}"
    if trigger:
        line += f", triggered by {trigger}"
    if action:
        line += f". {action}"
    return line + "."


def _notifications_section(adj_dir: Path) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    count_file = adj_dir / "state" / f"notify_count_{today}.txt"

    count = 0
    if count_file.exists():
        try:
            count = int(count_file.read_text().strip())
        except (ValueError, OSError):
            count = 0

    # Read max_per_day from config
    try:
        from adjutant.core.config import load_typed_config

        cfg = load_typed_config(adj_dir / "adjutant.yaml")
        max_per_day = cfg.notifications.max_per_day
    except Exception:
        max_per_day = 3

    if count == 0:
        return f"No notifications sent today (limit is {max_per_day})."
    return f"{count} of {max_per_day} notifications sent today."


def _actions_section(adj_dir: Path) -> str:
    actions_file = adj_dir / "state" / "actions.jsonl"
    if not actions_file.exists():
        return ""

    lines = actions_file.read_text().splitlines()
    # last 5 non-empty lines
    recent = [l for l in lines if l.strip()][-5:]
    if not recent:
        return ""

    parts = ["Recent actions:"]
    for line in recent:
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        ts = _format_timestamp(entry.get("ts", ""))
        action_type = entry.get("type", "")
        agent = entry.get("agent", "")
        if agent:
            parts.append(f"  {ts} — {action_type} ({agent})")
        else:
            parts.append(f"  {ts} — {action_type}")
    return "\n".join(parts)


def get_status(adj_dir: Optional[Path] = None) -> str:
    """Return a human-readable status report string.

    Args:
        adj_dir: Path to the Adjutant directory. Defaults to $ADJ_DIR.

    Returns:
        Multi-line status string.
    """
    d = adj_dir or _adj_dir()

    sections = [
        _status_line(d),
        "",
        _schedules_section(d),
        "",
        _heartbeat_section(d),
        "",
        _notifications_section(d),
    ]

    actions = _actions_section(d)
    if actions:
        sections += ["", actions]

    return "\n".join(sections)


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint: print status to stdout, exit 0."""
    try:
        print(get_status())
        return 0
    except RuntimeError as e:
        print(f"ERROR:{e}", flush=True)
        return 1


if __name__ == "__main__":
    import sys

    sys.exit(main())
