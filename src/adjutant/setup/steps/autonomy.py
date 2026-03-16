"""Step 7: Heartbeat Configuration.

Replaces: scripts/setup/steps/autonomy.sh

Guides the user through enabling the heartbeat pipeline (pulse + review):
  - Enable/disable the heartbeat cycle
  - Set notification budget (max_per_day)
  - Configure quiet hours
  - Enable pulse/review scheduled jobs via the schedule registry

Module-level state:
  WIZARD_HEARTBEAT_ENABLED     — bool
  WIZARD_HEARTBEAT_MAX_PER_DAY — int
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from adjutant.setup.wizard import (
    BOLD,
    DIM,
    RESET,
    wiz_confirm,
    wiz_info,
    wiz_input,
    wiz_ok,
    wiz_step,
    wiz_warn,
)

if TYPE_CHECKING:
    from pathlib import Path

WIZARD_HEARTBEAT_ENABLED: bool = False
WIZARD_HEARTBEAT_MAX_PER_DAY: int = 3


def _update_config(adj_dir: Path, *, dry_run: bool = False) -> None:
    """Write heartbeat.enabled and notifications.max_per_day to adjutant.yaml."""
    config_path = adj_dir / "adjutant.yaml"
    if not config_path.is_file():
        return
    if dry_run:
        wiz_ok("[DRY RUN] Would write heartbeat config to adjutant.yaml")
        return
    try:
        import yaml

        with open(config_path) as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            return

        # heartbeat.enabled
        heartbeat = data.setdefault("heartbeat", {})
        if not isinstance(heartbeat, dict):
            data["heartbeat"] = {"enabled": WIZARD_HEARTBEAT_ENABLED}
        else:
            heartbeat["enabled"] = WIZARD_HEARTBEAT_ENABLED

        # notifications.max_per_day
        notifications = data.setdefault("notifications", {})
        if not isinstance(notifications, dict):
            data["notifications"] = {"max_per_day": WIZARD_HEARTBEAT_MAX_PER_DAY}
        else:
            notifications["max_per_day"] = WIZARD_HEARTBEAT_MAX_PER_DAY

        with open(config_path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    except Exception:  # noqa: BLE001 — best-effort config write
        pass


def _update_quiet_hours(
    adj_dir: Path,
    enabled: bool,
    start: str,
    end: str,
    *,
    dry_run: bool = False,
) -> None:
    """Write quiet_hours settings to adjutant.yaml."""
    config_path = adj_dir / "adjutant.yaml"
    if not config_path.is_file():
        return
    if dry_run:
        wiz_ok("[DRY RUN] Would update quiet_hours in adjutant.yaml")
        return
    try:
        import yaml

        with open(config_path) as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            return

        notifications = data.setdefault("notifications", {})
        if not isinstance(notifications, dict):
            notifications = {}
            data["notifications"] = notifications

        quiet_hours = notifications.setdefault("quiet_hours", {})
        if not isinstance(quiet_hours, dict):
            quiet_hours = {}
            notifications["quiet_hours"] = quiet_hours

        quiet_hours["enabled"] = enabled
        quiet_hours["start"] = start
        quiet_hours["end"] = end

        with open(config_path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    except Exception:  # noqa: BLE001 — best-effort config write
        pass


def _enable_schedules(adj_dir: Path, *, dry_run: bool = False) -> None:
    """Enable autonomous_pulse and autonomous_review in the schedule registry."""
    if dry_run:
        wiz_ok("[DRY RUN] Would enable autonomous_pulse and autonomous_review in schedules:")
        return

    config_path = adj_dir / "adjutant.yaml"
    installed = 0

    try:
        from adjutant.capabilities.schedule.manage import schedule_exists, schedule_set_enabled
    except ImportError:
        wiz_warn(
            "Could not load schedule manager — enable manually with: "
            "adjutant schedule enable autonomous_pulse"
        )
        return

    for job_name, label in [
        ("autonomous_pulse", "autonomous_pulse enabled (weekdays 9am and 5pm)"),
        ("autonomous_review", "autonomous_review enabled (weekdays 8pm)"),
    ]:
        if schedule_exists(config_path, job_name):
            try:
                schedule_set_enabled(config_path, job_name, True)
                wiz_ok(label)
                installed += 1
            except Exception:
                wiz_warn(f"Failed to enable {job_name} — run: adjutant schedule enable {job_name}")
        else:
            wiz_warn(f"{job_name} not found in schedules: — add it with: adjutant schedule add")

    if installed > 0:
        wiz_info("Cron entries installed. Adjust schedules in adjutant.yaml schedules: if needed.")


def step_autonomy(adj_dir: Path, *, dry_run: bool = False) -> bool:
    """Run Step 7: Heartbeat Configuration.

    Returns:
        True always.
    """
    global WIZARD_HEARTBEAT_ENABLED, WIZARD_HEARTBEAT_MAX_PER_DAY

    wiz_step(7, 7, "Heartbeat Configuration")
    print("", file=sys.stderr)

    print(
        "  The heartbeat pipeline lets Adjutant query your knowledge bases on a schedule,",
        file=sys.stderr,
    )
    print(
        "  surface significant signals, and send you Telegram notifications.",
        file=sys.stderr,
    )
    print(
        "  You remain in full control via the PAUSED kill switch and a notification budget.",
        file=sys.stderr,
    )
    print("", file=sys.stderr)
    print(
        f"  {DIM}Pulse schedule:  0 9,17 * * 1-5  (weekdays 9am and 5pm){RESET}",
        file=sys.stderr,
    )
    print(
        f"  {DIM}Review schedule: 0 20 * * 1-5    (weekdays 8pm){RESET}",
        file=sys.stderr,
    )
    print(
        f"  {DIM}Edit in adjutant.yaml schedules: or with: "
        f"adjutant schedule disable autonomous_pulse{RESET}",
        file=sys.stderr,
    )
    print("", file=sys.stderr)

    if not wiz_confirm("Enable the heartbeat pipeline (pulse + review)?", "N"):
        WIZARD_HEARTBEAT_ENABLED = False
        wiz_info(
            "Heartbeat disabled — enable later by setting heartbeat.enabled: true in adjutant.yaml"
        )
        wiz_info("Then run: adjutant schedule enable autonomous_pulse")
        _update_config(adj_dir, dry_run=dry_run)
        print("", file=sys.stderr)
        return True

    WIZARD_HEARTBEAT_ENABLED = True
    wiz_ok("Heartbeat pipeline enabled")
    print("", file=sys.stderr)

    # Notification budget
    print(
        f"  {BOLD}Notification budget{RESET} (hard limit: sends are blocked once this is reached)",
        file=sys.stderr,
    )
    budget_input = wiz_input("Maximum notifications per day", "3")
    try:
        WIZARD_HEARTBEAT_MAX_PER_DAY = int(budget_input or "3")
    except ValueError:
        WIZARD_HEARTBEAT_MAX_PER_DAY = 3
    wiz_ok(f"Max notifications per day: {WIZARD_HEARTBEAT_MAX_PER_DAY}")
    print("", file=sys.stderr)

    # Quiet hours
    if wiz_confirm("Enable quiet hours? (suppress notifications during these hours)", "N"):
        quiet_start = wiz_input("Quiet hours start (HH:MM, 24h)", "22:00") or "22:00"
        quiet_end = wiz_input("Quiet hours end (HH:MM, 24h)", "07:00") or "07:00"
        wiz_ok(f"Quiet hours: {quiet_start} – {quiet_end}")
        _update_config(adj_dir, dry_run=dry_run)
        _update_quiet_hours(adj_dir, True, quiet_start, quiet_end, dry_run=dry_run)
    else:
        wiz_info("Quiet hours disabled")
        _update_config(adj_dir, dry_run=dry_run)

    # Enable scheduled jobs via registry
    print("", file=sys.stderr)
    _enable_schedules(adj_dir, dry_run=dry_run)
    print("", file=sys.stderr)

    return True
