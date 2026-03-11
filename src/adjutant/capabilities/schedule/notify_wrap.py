"""Cron job notification wrapper.

Replaces: scripts/capabilities/schedule/notify_wrap.sh

Runs a scheduled script, captures its output and exit code, then sends a
Telegram notification with the result. Used by install.py when a job has
notify: true set in adjutant.yaml.

Notification format (success):
  [job_name] <first line of output>

Notification format (failure):
  [job_name] ERROR (rc=N): <first line of output>

Always exits 0 so cron does not generate its own mail on failure.
The real exit code is preserved in the notification message.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def notify_wrap(
    job_name: str,
    script_path: str,
    adj_dir: Path,
) -> int:
    """Run script_path, capture output, send Telegram notification.

    Args:
        job_name: Job name (used as notification prefix).
        script_path: Path to the script to run (or a command string).
        adj_dir: Adjutant root directory.

    Returns:
        Always 0 (cron must not see failure exit codes).
    """
    from adjutant.core.logging import adj_log

    # Run the script, capturing combined stdout+stderr.
    # Use shell=True so that script_path can be a full command string
    # (e.g. ".venv/bin/python -m adjutant news"), not just a bare file path.
    try:
        result = subprocess.run(
            script_path,
            capture_output=True,
            text=True,
            shell=True,
            cwd=str(adj_dir),
        )
        script_rc = result.returncode
        output = result.stdout + result.stderr
    except OSError as e:
        script_rc = 1
        output = str(e)

    # Extract first non-empty line for the summary
    summary = next((line for line in output.splitlines() if line.strip()), "(no output)")

    if script_rc == 0:
        message = f"[{job_name}] {summary}"
    else:
        message = f"[{job_name}] ERROR (rc={script_rc}): {summary}"

    adj_log("schedule", message)

    # Send Telegram notification — fire and forget, don't fail the wrapper
    try:
        from adjutant.messaging.telegram.notify import send_notify

        send_notify(message, adj_dir)
    except Exception as e:
        adj_log("schedule", f"[{job_name}] notify failed: {e}")

    # Always exit 0
    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: notify_wrap.py <job_name> <script_path>"""
    args = argv if argv is not None else sys.argv[1:]

    if len(args) < 2:
        sys.stderr.write("Usage: notify_wrap.py <job_name> <script_path...>\n")
        return 1

    job_name = args[0]
    script_path = " ".join(
        args[1:]
    )  # join in case command has spaces (e.g. "python -m adjutant news")

    adj_dir_str = os.environ.get("ADJ_DIR", "").strip()
    if not adj_dir_str:
        sys.stderr.write("ERROR: ADJ_DIR not set\n")
        return 1

    adj_dir = Path(adj_dir_str)

    return notify_wrap(job_name, script_path, adj_dir)


if __name__ == "__main__":
    sys.exit(main())
