"""Interactive scheduled-job creation wizard.

Replaces: scripts/setup/steps/schedule_wizard.sh

Walks the user through registering a new scheduled job in adjutant.yaml
schedules: and installing the crontab entry immediately.

Called by: adjutant schedule add
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from adjutant.setup.wizard import (
    expand_path,
    wiz_confirm,
    wiz_header,
    wiz_info,
    wiz_input,
    wiz_ok,
    wiz_warn,
)

_VALID_JOB_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
_CRON_EXAMPLES = """\
  Examples:
    0 8 * * 1-5      weekdays at 8:00am
    0 9,17 * * 1-5   weekdays at 9am and 5pm
    0 * * * *         every hour
    */30 * * * *      every 30 minutes
    0 20 * * 1-5      weekdays at 8pm
    0 6 * * *         every day at 6am"""


def _schedule_exists(adj_dir: Path, name: str) -> bool:
    """Check if a job name is already in adjutant.yaml schedules."""
    config = adj_dir / "adjutant.yaml"
    if not config.is_file():
        return False
    in_schedules = False
    for line in config.read_text().splitlines():
        if line.startswith("schedules:"):
            in_schedules = True
            continue
        if in_schedules and line and line[0] not in (" ", "\t", "-"):
            break
        if in_schedules:
            stripped = line.strip().lstrip("- ")
            if stripped.startswith("name:"):
                val = stripped[len("name:") :].strip().strip("\"'")
                if val == name:
                    return True
    return False


def _validate_cron(schedule: str) -> bool:
    """Return True if schedule has exactly 5 whitespace-separated fields."""
    return len(schedule.split()) == 5


def _add_schedule_to_yaml(
    adj_dir: Path,
    name: str,
    description: str,
    schedule: str,
    script: str,
    log: str,
) -> None:
    """Append a new schedule entry to adjutant.yaml."""
    config = adj_dir / "adjutant.yaml"
    text = config.read_text() if config.is_file() else ""

    entry = (
        f'\n  - name: "{name}"\n'
        f'    description: "{description}"\n'
        f'    schedule: "{schedule}"\n'
        f'    script: "{script}"\n'
        f'    log: "{log}"\n'
        f"    enabled: true\n"
    )

    if "schedules:" in text:
        # Append after the schedules: key
        text = text + entry
    else:
        text = text + f"\nschedules:{entry}"

    config.write_text(text)


def _install_crontab(adj_dir: Path, name: str, schedule: str, script: str, log: str) -> None:
    """Install a crontab entry for the job."""
    import subprocess

    # Resolve script path
    script_path = Path(script)
    if not script_path.is_absolute():
        script_path = adj_dir / script

    log_path = Path(log)
    if not log_path.is_absolute():
        log_path = adj_dir / log

    cron_line = f"{schedule} {script_path} >> {log_path} 2>&1 # adjutant:{name}"

    try:
        result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        existing = result.stdout if result.returncode == 0 else ""
        new_crontab = existing.rstrip("\n") + "\n" + cron_line + "\n"
        subprocess.run(["crontab", "-"], input=new_crontab, text=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        raise RuntimeError(f"crontab install failed: {exc}") from exc


def schedule_wizard(adj_dir: Path) -> None:
    """Run the interactive schedule creation wizard.

    Args:
        adj_dir: Adjutant root directory.
    """
    wiz_header("Add a Scheduled Job")
    print("", file=sys.stderr)
    wiz_info("Register any script as a scheduled job in adjutant.yaml schedules:.")
    wiz_info("The job will be installed in your crontab immediately.")
    print("", file=sys.stderr)

    # Step 1: Name
    print("  \033[1mName\033[0m", file=sys.stderr)
    wiz_info("Lowercase alphanumeric with hyphens or underscores (e.g. portfolio-fetch)")
    print("", file=sys.stderr)

    job_name = ""
    while True:
        job_name = wiz_input("Job name", "")
        if not job_name:
            wiz_warn("Name cannot be empty.")
            continue
        if not _VALID_JOB_NAME.match(job_name):
            wiz_warn("Must be lowercase alphanumeric with hyphens/underscores.")
            continue
        if _schedule_exists(adj_dir, job_name):
            wiz_warn(f"A job named '{job_name}' is already registered.")
            wiz_info(f"Use 'adjutant schedule remove {job_name}' first if you want to replace it.")
            continue
        break
    print("", file=sys.stderr)

    # Step 2: Description
    print("  \033[1mDescription\033[0m", file=sys.stderr)
    wiz_info("Shown in 'adjutant schedule list'. Free text.")
    print("", file=sys.stderr)

    description = wiz_input("Description", "") or f"Scheduled job: {job_name}"
    print("", file=sys.stderr)

    # Step 3: Script path
    print("  \033[1mScript path\033[0m", file=sys.stderr)
    wiz_info(f"Absolute path, or relative to your Adjutant directory ({adj_dir}).")
    wiz_info("The script must exit 0 on success.")
    print("", file=sys.stderr)

    script = ""
    while True:
        script = wiz_input("Script path", "")
        if not script:
            wiz_warn("Script path cannot be empty.")
            continue
        script = expand_path(script)

        resolved = Path(script) if Path(script).is_absolute() else adj_dir / script

        if not resolved.is_file():
            wiz_warn(f"File not found: {resolved}")
            if wiz_confirm("Use this path anyway? (you can create the script later)", "N"):
                break
            continue

        if not os.access(resolved, os.X_OK):
            wiz_warn(f"Script is not executable: {resolved}")
            if wiz_confirm("Make it executable now?", "Y"):
                resolved.chmod(resolved.stat().st_mode | 0o111)
                wiz_ok("Made executable.")
        break
    print("", file=sys.stderr)

    # Step 4: Schedule
    print("  \033[1mSchedule (cron syntax)\033[0m", file=sys.stderr)
    print(_CRON_EXAMPLES, file=sys.stderr)
    print("", file=sys.stderr)

    cron_schedule = ""
    while True:
        cron_schedule = wiz_input("Schedule", "")
        if not cron_schedule:
            wiz_warn("Schedule cannot be empty.")
            continue
        if not _validate_cron(cron_schedule):
            field_count = len(cron_schedule.split())
            wiz_warn(f"A cron schedule must have exactly 5 fields (got {field_count}).")
            wiz_info("Example: 0 8 * * 1-5")
            continue
        break
    print("", file=sys.stderr)

    # Step 5: Log file
    print("  \033[1mLog file\033[0m", file=sys.stderr)
    wiz_info("Where stdout/stderr from the job is written.")
    wiz_info(f"Relative paths are relative to {adj_dir}.")
    print("", file=sys.stderr)

    log = wiz_input("Log file", f"state/{job_name}.log") or f"state/{job_name}.log"
    print("", file=sys.stderr)

    # Summary + confirm
    wiz_header("Summary")
    wiz_info(f"Name:        {job_name}")
    wiz_info(f"Description: {description}")
    wiz_info(f"Script:      {script}")
    wiz_info(f"Schedule:    {cron_schedule}")
    wiz_info(f"Log:         {log}")
    print("", file=sys.stderr)

    if not wiz_confirm("Register and install this job?", "Y"):
        print("Cancelled.", file=sys.stderr)
        return

    print("", file=sys.stderr)

    # Write to adjutant.yaml
    print("  Adding to adjutant.yaml...", end="", file=sys.stderr)
    sys.stderr.flush()
    _add_schedule_to_yaml(adj_dir, job_name, description, cron_schedule, script, log)
    print(" done", file=sys.stderr)

    # Install crontab
    try:
        _install_crontab(adj_dir, job_name, cron_schedule, script, log)
        wiz_ok(f"Job '{job_name}' registered and crontab entry installed.")
    except RuntimeError as exc:
        wiz_warn(f"crontab install failed: {exc}. Add the entry manually.")

    print("", file=sys.stderr)
    wiz_info("Verify with:  adjutant schedule list")
    wiz_info(f"Test now:     adjutant schedule run {job_name}")
    wiz_info(f"Disable:      adjutant schedule disable {job_name}")
    wiz_info(f"Remove:       adjutant schedule remove {job_name}")
    print("", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    import os as _os

    adj_dir_str = _os.environ.get("ADJ_DIR", "").strip()
    if not adj_dir_str:
        sys.stderr.write("ERROR: ADJ_DIR not set\n")
        return 1

    adj_dir = Path(adj_dir_str)
    try:
        schedule_wizard(adj_dir)
        return 0
    except (KeyboardInterrupt, SystemExit):
        print("\nCancelled.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
