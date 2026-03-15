"""CLI entrypoint — Click-based CLI for Adjutant.

Subcommands:
  start               — Start the Telegram listener
  stop                — Stop the Telegram listener
  restart             — Restart all services
  status              — Show operational status
  pause               — Pause Adjutant (soft stop)
  resume              — Resume from pause
  kill                — Emergency shutdown
  startup             — Full startup / recovery
  pulse               — Run the autonomous pulse cron job
  review              — Run the autonomous review cron job
  rotate              — Rotate journal entries and operational log
  reply <message>     — Send a Telegram reply (Markdown)
  notify <message>    — Send a proactive Telegram notification (budget-guarded)
  screenshot <url>    — Take and send a screenshot via Telegram
  news                — Run the news briefing
  update              — Self-update Adjutant from GitHub releases
  logs                — Tail the listener log
  doctor              — Health check
  setup               — Run the interactive setup wizard
  uninstall           — Remove Adjutant from this machine
  kb run <kb> <op>    — Run a KB-local operation
  kb query <kb> <q>   — Query a KB sub-agent by name or path
  kb create           — Interactive KB creation wizard
  kb list             — List registered knowledge bases
  kb remove <name>    — Unregister a KB
  kb info <name>      — Show details about a KB
  schedule add        — Interactive wizard to add a scheduled job
  schedule list       — List scheduled jobs
  schedule enable     — Enable a scheduled job
  schedule disable    — Disable a scheduled job
  schedule remove     — Remove a scheduled job
  schedule sync       — Reconcile crontab with config
  schedule run        — Run a scheduled job immediately
  memory init         — Initialise the memory directory
  memory remember     — Store a memory entry (auto-classified)
  memory forget       — Archive memory entries matching a topic
  memory recall       — Search long-term memory
  memory digest       — Compress journal entries into weekly summary
  memory status       — Show memory system stats
"""

from __future__ import annotations

import sys

import click

from adjutant.core.paths import AdjutantDirNotFoundError, init_adj_dir


@click.group()
@click.version_option(version="2.0.0", prog_name="adjutant")
@click.pass_context
def main(ctx: click.Context) -> None:
    """Adjutant — autonomous agent framework."""
    ctx.ensure_object(dict)
    try:
        adj_dir = init_adj_dir()
        ctx.obj["adj_dir"] = adj_dir
    except AdjutantDirNotFoundError:
        # Don't fail on --help or version; only fail on actual commands
        ctx.obj["adj_dir"] = None


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


@main.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Show Adjutant status."""
    adj_dir = ctx.obj.get("adj_dir")
    if adj_dir is None:
        click.echo("Adjutant directory not found. Run setup first.")
        raise SystemExit(1)

    from adjutant.core.lockfiles import is_killed, is_paused

    if is_killed(adj_dir):
        click.echo("Status: KILLED")
    elif is_paused(adj_dir):
        click.echo("Status: PAUSED")
    else:
        click.echo("Status: OPERATIONAL")
    click.echo(f"Directory: {adj_dir}")


# ---------------------------------------------------------------------------
# pulse / review (cron wrappers)
# ---------------------------------------------------------------------------


@main.command()
@click.pass_context
def pulse(ctx: click.Context) -> None:
    """Run the autonomous pulse job (exec opencode with prompts/pulse.md)."""
    adj_dir = ctx.obj.get("adj_dir")
    if adj_dir is None:
        click.echo("Adjutant directory not found.", err=True)
        raise SystemExit(1)

    from adjutant.lifecycle.cron import pulse_cron

    pulse_cron(adj_dir=adj_dir)


@main.command()
@click.pass_context
def review(ctx: click.Context) -> None:
    """Run the autonomous review job (exec opencode with prompts/review.md)."""
    adj_dir = ctx.obj.get("adj_dir")
    if adj_dir is None:
        click.echo("Adjutant directory not found.", err=True)
        raise SystemExit(1)

    from adjutant.lifecycle.cron import review_cron

    review_cron(adj_dir=adj_dir)


# ---------------------------------------------------------------------------
# rotate
# ---------------------------------------------------------------------------


@main.command()
@click.option("--dry-run", is_flag=True, default=False, help="Show what would happen.")
@click.option("--quiet", is_flag=True, default=False, help="Suppress output (for cron).")
@click.pass_context
def rotate(ctx: click.Context, dry_run: bool, quiet: bool) -> None:
    """Rotate journal entries and the operational log."""
    adj_dir = ctx.obj.get("adj_dir")
    if adj_dir is None:
        click.echo("Adjutant directory not found.", err=True)
        raise SystemExit(1)

    from adjutant.observability.journal_rotate import rotate_all

    rotate_all(adj_dir, dry_run=dry_run, quiet=quiet)


# ---------------------------------------------------------------------------
# reply
# ---------------------------------------------------------------------------


@main.command()
@click.argument("message")
@click.option("--reply-to", type=int, default=None, help="Reply to this Telegram message ID.")
def reply(message: str, reply_to: int | None) -> None:
    """Send a Telegram reply (Markdown enabled)."""
    from adjutant.messaging.telegram.reply import send_reply

    try:
        send_reply(message, reply_to_message_id=reply_to)
        click.echo("Replied.")
    except (RuntimeError, ValueError) as exc:
        click.echo(f"ERROR: {exc}", err=True)
        raise SystemExit(1) from exc


# ---------------------------------------------------------------------------
# kb group
# ---------------------------------------------------------------------------


@main.group()
def kb() -> None:
    """Knowledge base commands."""


@kb.command(name="run")
@click.argument("kb_name")
@click.argument("operation")
@click.argument("args", nargs=-1)
@click.pass_context
def kb_run_cmd(ctx: click.Context, kb_name: str, operation: str, args: tuple[str, ...]) -> None:
    """Run a KB-local operation.

    KB_NAME   Name of the knowledge base.\n
    OPERATION Operation name (e.g. fetch, analyze, reconcile).\n
    ARGS      Additional arguments passed to the operation script.
    """
    adj_dir = ctx.obj.get("adj_dir")
    if adj_dir is None:
        click.echo("Adjutant directory not found.", err=True)
        raise SystemExit(1)

    from adjutant.capabilities.kb.run import (
        KBNotFoundError,
        KBOperationNotFoundError,
        KBRunError,
        kb_run,
    )

    try:
        output = kb_run(adj_dir, kb_name, operation, list(args))
        click.echo(output, nl=False)
    except (KBNotFoundError, KBOperationNotFoundError, KBRunError, ValueError) as exc:
        click.echo(f"ERROR: {exc}", err=True)
        raise SystemExit(1) from exc


# ---------------------------------------------------------------------------
# notify
# ---------------------------------------------------------------------------


@main.command()
@click.argument("message")
@click.pass_context
def notify(ctx: click.Context, message: str) -> None:
    """Send a proactive Telegram notification (respects daily budget)."""
    adj_dir = ctx.obj.get("adj_dir")
    if adj_dir is None:
        click.echo("Adjutant directory not found.", err=True)
        raise SystemExit(1)

    from adjutant.messaging.telegram.notify import BudgetExceededError, send_notify

    try:
        count, max_pd = send_notify(message, adj_dir)
        click.echo(f"Sent. ({count}/{max_pd} today)")
    except BudgetExceededError as exc:
        click.echo(f"ERROR: {exc}", err=True)
        raise SystemExit(1) from exc
    except (RuntimeError, ValueError) as exc:
        click.echo(f"ERROR: {exc}", err=True)
        raise SystemExit(1) from exc


# ---------------------------------------------------------------------------
# update
# ---------------------------------------------------------------------------


@main.command()
@click.option("--check", "check_only", is_flag=True, default=False, help="Only check for updates.")
@click.option("--yes", "auto_yes", is_flag=True, default=False, help="Skip confirmation prompt.")
@click.option("--version", "version_tag", default=None, help="Force a specific version tag.")
@click.option("--quiet", is_flag=True, default=False)
@click.pass_context
def update(
    ctx: click.Context,
    check_only: bool,
    auto_yes: bool,
    version_tag: str | None,
    quiet: bool,
) -> None:
    """Self-update Adjutant from GitHub releases."""
    adj_dir = ctx.obj.get("adj_dir")
    if adj_dir is None:
        click.echo("Adjutant directory not found.", err=True)
        raise SystemExit(1)

    from adjutant.lifecycle.update import update as do_update

    try:
        do_update(adj_dir, check_only=check_only, auto_yes=auto_yes, quiet=quiet)
    except (RuntimeError, SystemExit) as exc:
        if isinstance(exc, SystemExit):
            raise
        click.echo(f"ERROR: {exc}", err=True)
        raise SystemExit(1) from exc


# ---------------------------------------------------------------------------
# setup
# ---------------------------------------------------------------------------


@main.command(name="setup")
@click.option("--repair", is_flag=True, default=False, help="Force repair mode.")
@click.option("--dry-run", is_flag=True, default=False, help="Simulate without writing files.")
@click.pass_context
def setup_cmd(ctx: click.Context, repair: bool, dry_run: bool) -> None:
    """Run the interactive setup wizard."""
    adj_dir = ctx.obj.get("adj_dir")

    from adjutant.setup.wizard import run_wizard

    try:
        run_wizard(adj_dir, dry_run=dry_run, repair=repair)
    except (KeyboardInterrupt, SystemExit) as exc:
        if isinstance(exc, SystemExit):
            raise
        click.echo("\nCancelled.", err=True)
        raise SystemExit(1) from exc


# ---------------------------------------------------------------------------
# uninstall
# ---------------------------------------------------------------------------


@main.command()
@click.pass_context
def uninstall(ctx: click.Context) -> None:
    """Remove Adjutant from this machine."""
    adj_dir = ctx.obj.get("adj_dir")
    if adj_dir is None:
        click.echo("Adjutant directory not found.", err=True)
        raise SystemExit(1)

    from adjutant.setup.uninstall import uninstall as do_uninstall

    try:
        do_uninstall(adj_dir)
    except (KeyboardInterrupt, SystemExit) as exc:
        if isinstance(exc, SystemExit):
            raise
        click.echo("\nCancelled.", err=True)
        raise SystemExit(1) from exc


# ---------------------------------------------------------------------------
# kb query
# ---------------------------------------------------------------------------


@kb.command(name="query")
@click.argument("kb_name", required=False)
@click.argument("query_text", required=False)
@click.option("--path", "kb_path", default=None, help="Query by directory path instead of name.")
@click.pass_context
def kb_query_cmd(
    ctx: click.Context,
    kb_name: str | None,
    query_text: str | None,
    kb_path: str | None,
) -> None:
    """Query a knowledge base sub-agent.

    Usage:\n
      adjutant kb query my-kb "What is the current value?"\n
      adjutant kb query --path /path/to/kb "What is the current value?"
    """
    import asyncio

    adj_dir = ctx.obj.get("adj_dir")
    if adj_dir is None:
        click.echo("Adjutant directory not found.", err=True)
        raise SystemExit(1)

    from adjutant.capabilities.kb.query import KBQueryError, kb_query, kb_query_by_path
    from adjutant.core.opencode import OpenCodeNotFoundError
    from pathlib import Path as _Path

    try:
        if kb_path:
            if not query_text:
                click.echo("ERROR: A query argument is required with --path.", err=True)
                raise SystemExit(1)
            answer = asyncio.run(kb_query_by_path(_Path(kb_path), query_text, adj_dir))
        else:
            if not kb_name or not query_text:
                click.echo("ERROR: KB_NAME and QUERY_TEXT are required.", err=True)
                raise SystemExit(1)
            answer = asyncio.run(kb_query(kb_name, query_text, adj_dir))

        click.echo(answer, nl=False)
    except (KBQueryError, OpenCodeNotFoundError) as exc:
        click.echo(f"ERROR: {exc}", err=True)
        raise SystemExit(1) from exc


@kb.command(name="write")
@click.argument("kb_name", required=False)
@click.argument("instruction", required=False)
@click.option("--path", "kb_path", default=None, help="Write by directory path instead of name.")
@click.pass_context
def kb_write_cmd(
    ctx: click.Context,
    kb_name: str | None,
    instruction: str | None,
    kb_path: str | None,
) -> None:
    """Dispatch a write operation to a KB sub-agent (fire-and-forget).

    Spawns the sub-agent in the background and returns immediately.
    The sub-agent logs completion/failure to adjutant.log.

    Usage:\n
      adjutant kb write my-kb "Update issue #12: mark complete"\n
      adjutant kb write --path /path/to/kb "Add new entry"
    """
    adj_dir = ctx.obj.get("adj_dir")
    if adj_dir is None:
        click.echo("Adjutant directory not found.", err=True)
        raise SystemExit(1)

    from adjutant.capabilities.kb.query import KBQueryError, kb_write, kb_write_by_path
    from adjutant.core.opencode import OpenCodeNotFoundError
    from pathlib import Path as _Path

    try:
        if kb_path:
            if not instruction:
                click.echo("ERROR: An instruction argument is required with --path.", err=True)
                raise SystemExit(1)
            msg = kb_write_by_path(_Path(kb_path), instruction, adj_dir)
        else:
            if not kb_name or not instruction:
                click.echo("ERROR: KB_NAME and INSTRUCTION are required.", err=True)
                raise SystemExit(1)
            msg = kb_write(kb_name, instruction, adj_dir)

        click.echo(msg)
    except (KBQueryError, OpenCodeNotFoundError) as exc:
        click.echo(f"ERROR: {exc}", err=True)
        raise SystemExit(1) from exc


# ---------------------------------------------------------------------------
# start / stop / restart
# ---------------------------------------------------------------------------


@main.command()
@click.pass_context
def start(ctx: click.Context) -> None:
    """Start the Telegram listener."""
    adj_dir = ctx.obj.get("adj_dir")
    if adj_dir is None:
        click.echo("Adjutant directory not found. Run setup first.", err=True)
        raise SystemExit(1)

    from adjutant.messaging.telegram.service import listener_start

    click.echo(listener_start(adj_dir))


@main.command()
@click.pass_context
def stop(ctx: click.Context) -> None:
    """Stop the Telegram listener."""
    adj_dir = ctx.obj.get("adj_dir")
    if adj_dir is None:
        click.echo("Adjutant directory not found.", err=True)
        raise SystemExit(1)

    from adjutant.messaging.telegram.service import listener_stop

    click.echo(listener_stop(adj_dir))


@main.command()
@click.pass_context
def restart(ctx: click.Context) -> None:
    """Restart all services."""
    adj_dir = ctx.obj.get("adj_dir")
    if adj_dir is None:
        click.echo("Adjutant directory not found.", err=True)
        raise SystemExit(1)

    from adjutant.lifecycle.control import restart as do_restart

    click.echo(do_restart(adj_dir))


# ---------------------------------------------------------------------------
# pause / resume / kill / startup
# ---------------------------------------------------------------------------


@main.command()
@click.pass_context
def pause(ctx: click.Context) -> None:
    """Pause Adjutant (heartbeats skip until resumed)."""
    adj_dir = ctx.obj.get("adj_dir")
    if adj_dir is None:
        click.echo("Adjutant directory not found.", err=True)
        raise SystemExit(1)

    from adjutant.lifecycle.control import pause as do_pause

    click.echo(do_pause(adj_dir))


@main.command()
@click.pass_context
def resume(ctx: click.Context) -> None:
    """Resume Adjutant from pause."""
    adj_dir = ctx.obj.get("adj_dir")
    if adj_dir is None:
        click.echo("Adjutant directory not found.", err=True)
        raise SystemExit(1)

    from adjutant.lifecycle.control import resume as do_resume

    click.echo(do_resume(adj_dir))


@main.command(name="kill")
@click.pass_context
def kill_cmd(ctx: click.Context) -> None:
    """Emergency shutdown (sets KILLED flag, disables crontab)."""
    adj_dir = ctx.obj.get("adj_dir")
    if adj_dir is None:
        click.echo("Adjutant directory not found.", err=True)
        raise SystemExit(1)

    from adjutant.lifecycle.control import emergency_kill

    click.echo(emergency_kill(adj_dir))


@main.command()
@click.pass_context
def startup(ctx: click.Context) -> None:
    """Full startup / recovery from KILLED state."""
    adj_dir = ctx.obj.get("adj_dir")
    if adj_dir is None:
        click.echo("Adjutant directory not found.", err=True)
        raise SystemExit(1)

    from adjutant.lifecycle.control import startup as do_startup

    click.echo(do_startup(adj_dir))


# ---------------------------------------------------------------------------
# screenshot
# ---------------------------------------------------------------------------


@main.command()
@click.argument("url")
@click.argument("caption", required=False, default=None)
@click.pass_context
def screenshot(ctx: click.Context, url: str, caption: str | None) -> None:
    """Take a screenshot of URL and send it via Telegram."""
    adj_dir = ctx.obj.get("adj_dir")
    if adj_dir is None:
        click.echo("Adjutant directory not found.", err=True)
        raise SystemExit(1)

    from adjutant.capabilities.screenshot.screenshot import take_and_send

    result = take_and_send(url, adj_dir=adj_dir, caption=caption or "")
    if result.startswith("OK:"):
        click.echo(result[3:])
    else:
        click.echo(result[7:] if result.startswith("ERROR:") else result, err=True)
        raise SystemExit(1)


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------


@main.command()
@click.argument("query")
@click.option("--count", "-n", default=5, help="Number of results (1-10).")
@click.pass_context
def search(ctx: click.Context, query: str, count: int) -> None:
    """Search the web via Brave Search API."""
    adj_dir = ctx.obj.get("adj_dir")

    from adjutant.capabilities.search.search import web_search

    result = web_search(query, count=count, adj_dir=adj_dir)
    if result.startswith("OK:"):
        click.echo(result[3:])
    else:
        click.echo(result[6:] if result.startswith("ERROR:") else result, err=True)
        raise SystemExit(1)


# ---------------------------------------------------------------------------
# news
# ---------------------------------------------------------------------------


@main.command()
@click.pass_context
def news(ctx: click.Context) -> None:
    """Run the news briefing pipeline."""
    adj_dir = ctx.obj.get("adj_dir")
    if adj_dir is None:
        click.echo("Adjutant directory not found.", err=True)
        raise SystemExit(1)

    from adjutant.news.briefing import run_briefing

    try:
        result = run_briefing(adj_dir)
        click.echo(result)
    except Exception as exc:  # noqa: BLE001
        click.echo(f"ERROR: {exc}", err=True)
        raise SystemExit(1) from exc


# ---------------------------------------------------------------------------
# logs
# ---------------------------------------------------------------------------


@main.command()
@click.pass_context
def logs(ctx: click.Context) -> None:
    """Tail the Adjutant listener log."""
    import subprocess

    adj_dir = ctx.obj.get("adj_dir")
    if adj_dir is None:
        click.echo("Adjutant directory not found.", err=True)
        raise SystemExit(1)

    from pathlib import Path

    log_file = Path(adj_dir) / "state" / "adjutant.log"
    if not log_file.exists():
        log_file = Path(adj_dir) / "state" / "telegram_listener.log"
    if not log_file.exists():
        click.echo(f"No log file found in {adj_dir}/state/", err=True)
        raise SystemExit(1)

    try:
        subprocess.run(["tail", "-f", str(log_file)], check=False)
    except KeyboardInterrupt:
        pass


# ---------------------------------------------------------------------------
# doctor
# ---------------------------------------------------------------------------


@main.command()
@click.pass_context
def doctor(ctx: click.Context) -> None:
    """Check health and dependencies."""
    import shutil
    import subprocess
    from pathlib import Path

    adj_dir = ctx.obj.get("adj_dir")

    click.echo("Adjutant Health Check")
    click.echo("=====================")
    click.echo()

    if adj_dir:
        click.echo(f"Installation: {adj_dir}")
    else:
        click.echo("Installation: NOT FOUND (run setup)")

    import platform as _platform

    click.echo(f"OS:           {_platform.system()}")
    click.echo()

    click.echo("Dependencies:")
    for cmd in ("bash", "curl", "jq", "python3", "opencode"):
        path = shutil.which(cmd)
        if path:
            try:
                ver = subprocess.check_output(
                    [cmd, "--version"], stderr=subprocess.STDOUT, text=True
                ).splitlines()[0]
            except Exception:  # noqa: BLE001
                ver = "unknown version"
            click.echo(f"  {cmd:<12} OK ({ver})")
        else:
            click.echo(f"  {cmd:<12} MISSING")

    click.echo()
    click.echo("Optional:")
    try:
        subprocess.check_output(["npx", "playwright", "--version"], stderr=subprocess.STDOUT)
        click.echo(f"  {'playwright':<12} OK")
    except Exception:  # noqa: BLE001
        click.echo(f"  {'playwright':<12} not installed (needed for screenshot)")

    if adj_dir:
        click.echo()
        click.echo("Configuration:")
        for fname in (
            "adjutant.yaml",
            ".env",
            "identity/soul.md",
            "identity/heart.md",
            "identity/registry.md",
            "news_config.json",
            "opencode.json",
        ):
            present = (Path(adj_dir) / fname).exists()
            click.echo(f"  {fname:<20} {'present' if present else 'MISSING'}")

        click.echo()
        click.echo("State:")
        from adjutant.core.lockfiles import is_killed, is_paused

        if is_killed(adj_dir):
            click.echo("  Status: KILLED (run 'adjutant startup' to recover)")
        elif is_paused(adj_dir):
            click.echo("  Status: PAUSED (run 'adjutant resume')")
        else:
            click.echo("  Status: operational")

        from adjutant.messaging.telegram.service import listener_status

        click.echo(f"  Listener: {listener_status(adj_dir)}")


# ---------------------------------------------------------------------------
# schedule group
# ---------------------------------------------------------------------------


@main.group()
def schedule() -> None:
    """Scheduled job management."""


@schedule.command(name="add")
@click.pass_context
def schedule_add_cmd(ctx: click.Context) -> None:
    """Interactive wizard to register a new scheduled job."""
    adj_dir = ctx.obj.get("adj_dir")
    if adj_dir is None:
        click.echo("Adjutant directory not found.", err=True)
        raise SystemExit(1)

    from adjutant.setup.steps.schedule_wizard import schedule_wizard

    schedule_wizard(adj_dir)


@schedule.command(name="list")
@click.pass_context
def schedule_list_cmd(ctx: click.Context) -> None:
    """List all registered scheduled jobs."""
    from pathlib import Path

    adj_dir = ctx.obj.get("adj_dir")
    if adj_dir is None:
        click.echo("Adjutant directory not found.", err=True)
        raise SystemExit(1)

    from adjutant.capabilities.schedule.manage import schedule_count, schedule_list

    config_path = Path(adj_dir) / "adjutant.yaml"
    count = schedule_count(config_path)
    if count == 0:
        click.echo("No scheduled jobs registered.")
        click.echo("Add one with: adjutant schedule add")
        return

    click.echo(f"Scheduled jobs ({count}):")
    click.echo()
    click.echo(f"  {'NAME':<22} {'ENABLED':<8} {'SCHEDULE':<20} DESCRIPTION")
    click.echo(f"  {'----':<22} {'-------':<8} {'--------':<20} -----------")
    for entry in schedule_list(config_path):
        name = entry.get("name", "")
        desc = entry.get("description", "")
        sched = entry.get("schedule", "")
        enabled = str(entry.get("enabled", True)).lower()
        click.echo(f"  {name:<22} {enabled:<8} {sched:<20} {desc}")


@schedule.command(name="enable")
@click.argument("name")
@click.pass_context
def schedule_enable_cmd(ctx: click.Context, name: str) -> None:
    """Enable a scheduled job (installs crontab entry)."""
    from pathlib import Path

    adj_dir = ctx.obj.get("adj_dir")
    if adj_dir is None:
        click.echo("Adjutant directory not found.", err=True)
        raise SystemExit(1)

    from adjutant.capabilities.schedule.manage import schedule_set_enabled

    schedule_set_enabled(Path(adj_dir) / "adjutant.yaml", name, True)
    click.echo(f"Enabled job '{name}' — crontab entry installed.")


@schedule.command(name="disable")
@click.argument("name")
@click.pass_context
def schedule_disable_cmd(ctx: click.Context, name: str) -> None:
    """Disable a scheduled job (removes crontab entry, keeps registry)."""
    from pathlib import Path

    adj_dir = ctx.obj.get("adj_dir")
    if adj_dir is None:
        click.echo("Adjutant directory not found.", err=True)
        raise SystemExit(1)

    from adjutant.capabilities.schedule.manage import schedule_set_enabled

    schedule_set_enabled(Path(adj_dir) / "adjutant.yaml", name, False)
    click.echo(f"Disabled job '{name}' — crontab entry removed.")


@schedule.command(name="remove")
@click.argument("name")
@click.pass_context
def schedule_remove_cmd(ctx: click.Context, name: str) -> None:
    """Remove a job from registry and crontab."""
    from pathlib import Path

    adj_dir = ctx.obj.get("adj_dir")
    if adj_dir is None:
        click.echo("Adjutant directory not found.", err=True)
        raise SystemExit(1)

    from adjutant.capabilities.schedule.manage import schedule_remove

    schedule_remove(Path(adj_dir) / "adjutant.yaml", name)
    click.echo(f"Removed scheduled job '{name}' from registry and crontab.")


@schedule.command(name="sync")
@click.pass_context
def schedule_sync_cmd(ctx: click.Context) -> None:
    """Reconcile crontab with adjutant.yaml schedules (idempotent)."""
    adj_dir = ctx.obj.get("adj_dir")
    if adj_dir is None:
        click.echo("Adjutant directory not found.", err=True)
        raise SystemExit(1)

    from adjutant.capabilities.schedule.install import install_all

    install_all(adj_dir)
    click.echo("Crontab reconciled with adjutant.yaml schedules.")


@schedule.command(name="run")
@click.argument("name")
@click.pass_context
def schedule_run_cmd(ctx: click.Context, name: str) -> None:
    """Run a scheduled job immediately in the foreground (for testing)."""
    from pathlib import Path

    adj_dir = ctx.obj.get("adj_dir")
    if adj_dir is None:
        click.echo("Adjutant directory not found.", err=True)
        raise SystemExit(1)

    from adjutant.capabilities.schedule.manage import _resolve_command, schedule_get

    config_path = Path(adj_dir) / "adjutant.yaml"
    entry = schedule_get(config_path, name)
    if entry is None:
        click.echo(f"ERROR: Scheduled job '{name}' not found.", err=True)
        raise SystemExit(1)

    import subprocess

    cmd = _resolve_command(entry, adj_dir)
    click.echo(f"Running: {cmd}")
    subprocess.run(cmd, shell=True, check=False)


# ---------------------------------------------------------------------------
# kb create / list / remove / info
# ---------------------------------------------------------------------------


@kb.command(name="create")
@click.option("--quick", is_flag=True, default=False, help="Non-interactive quick create.")
@click.option("--name", default=None, help="KB name (required with --quick).")
@click.option("--path", "kb_path", default=None, help="KB directory path.")
@click.option("--desc", default=None, help="Short description.")
@click.option("--model", default=None, help="Model slug.")
@click.option("--access", default="read-only", help="Access level (read-only or read-write).")
@click.pass_context
def kb_create_cmd(
    ctx: click.Context,
    quick: bool,
    name: str | None,
    kb_path: str | None,
    desc: str | None,
    model: str | None,
    access: str,
) -> None:
    """Create a new knowledge base."""
    adj_dir = ctx.obj.get("adj_dir")
    if adj_dir is None:
        click.echo("Adjutant directory not found.", err=True)
        raise SystemExit(1)

    from adjutant.setup.steps.kb_wizard import kb_wizard_interactive, kb_quick_create

    try:
        if quick:
            if not name or not kb_path:
                click.echo("ERROR: --name and --path are required with --quick.", err=True)
                raise SystemExit(1)
            kb_quick_create(
                adj_dir,
                name=name,
                kb_path=kb_path,
                description=desc or "",
                model=model or "inherit",
                access=access,
            )
        else:
            kb_wizard_interactive(adj_dir)
    except (ValueError, RuntimeError) as exc:
        click.echo(f"ERROR: {exc}", err=True)
        raise SystemExit(1) from exc


@kb.command(name="list")
@click.pass_context
def kb_list_cmd(ctx: click.Context) -> None:
    """List registered knowledge bases."""
    adj_dir = ctx.obj.get("adj_dir")
    if adj_dir is None:
        click.echo("Adjutant directory not found.", err=True)
        raise SystemExit(1)

    from adjutant.capabilities.kb.manage import kb_count, kb_list

    count = kb_count(adj_dir)
    if count == 0:
        click.echo("No knowledge bases registered.")
        click.echo("Create one with: adjutant kb create")
        return

    click.echo(f"Registered knowledge bases ({count}):")
    click.echo()
    click.echo(f"  {'NAME':<20} {'ACCESS':<12} DESCRIPTION")
    click.echo(f"  {'----':<20} {'------':<12} -----------")
    for entry in kb_list(adj_dir):
        click.echo(f"  {entry.name:<20} {entry.access:<12} {entry.description}")


@kb.command(name="remove")
@click.argument("name")
@click.pass_context
def kb_remove_cmd(ctx: click.Context, name: str) -> None:
    """Unregister a knowledge base (files are NOT deleted)."""
    adj_dir = ctx.obj.get("adj_dir")
    if adj_dir is None:
        click.echo("Adjutant directory not found.", err=True)
        raise SystemExit(1)

    from adjutant.capabilities.kb.manage import kb_remove

    try:
        kb_remove(adj_dir, name)
        click.echo(f"Unregistered knowledge base '{name}'. Files were NOT deleted.")
    except ValueError as exc:
        click.echo(f"ERROR: {exc}", err=True)
        raise SystemExit(1) from exc


@kb.command(name="info")
@click.argument("name")
@click.pass_context
def kb_info_cmd(ctx: click.Context, name: str) -> None:
    """Show details about a knowledge base."""
    adj_dir = ctx.obj.get("adj_dir")
    if adj_dir is None:
        click.echo("Adjutant directory not found.", err=True)
        raise SystemExit(1)

    from adjutant.capabilities.kb.manage import kb_info

    try:
        entry = kb_info(adj_dir, name)
        click.echo(f"Name:        {entry.name}")
        click.echo(f"Path:        {entry.path}")
        click.echo(f"Description: {entry.description}")
        click.echo(f"Model:       {entry.model}")
        click.echo(f"Access:      {entry.access}")
        click.echo(f"Created:     {entry.created}")
    except ValueError as exc:
        click.echo(f"ERROR: {exc}", err=True)
        raise SystemExit(1) from exc


# ---------------------------------------------------------------------------
# memory group
# ---------------------------------------------------------------------------


@main.group()
def memory() -> None:
    """Long-term memory management."""


@memory.command(name="init")
@click.pass_context
def memory_init_cmd(ctx: click.Context) -> None:
    """Initialise the memory directory structure."""
    adj_dir = ctx.obj.get("adj_dir")
    if adj_dir is None:
        click.echo("Adjutant directory not found.", err=True)
        raise SystemExit(1)

    from adjutant.capabilities.memory.memory import memory_init

    result = memory_init(adj_dir)
    click.echo(result)


@memory.command(name="remember")
@click.argument("text")
@click.pass_context
def memory_remember_cmd(ctx: click.Context, text: str) -> None:
    """Store a memory entry (auto-classified)."""
    adj_dir = ctx.obj.get("adj_dir")
    if adj_dir is None:
        click.echo("Adjutant directory not found.", err=True)
        raise SystemExit(1)

    from adjutant.capabilities.memory.memory import memory_add

    result = memory_add(adj_dir, text)
    click.echo(result)


@memory.command(name="forget")
@click.argument("query")
@click.pass_context
def memory_forget_cmd(ctx: click.Context, query: str) -> None:
    """Archive memory entries matching a topic."""
    adj_dir = ctx.obj.get("adj_dir")
    if adj_dir is None:
        click.echo("Adjutant directory not found.", err=True)
        raise SystemExit(1)

    from adjutant.capabilities.memory.memory import memory_forget

    result = memory_forget(adj_dir, query)
    click.echo(result)


@memory.command(name="recall")
@click.argument("query", required=False, default="")
@click.pass_context
def memory_recall_cmd(ctx: click.Context, query: str) -> None:
    """Search long-term memory (or show the index)."""
    adj_dir = ctx.obj.get("adj_dir")
    if adj_dir is None:
        click.echo("Adjutant directory not found.", err=True)
        raise SystemExit(1)

    from adjutant.capabilities.memory.memory import memory_recall

    result = memory_recall(adj_dir, query.strip() or None)
    click.echo(result)


@memory.command(name="digest")
@click.option("--days", "-d", default=7, help="Number of days to digest (default: 7).")
@click.pass_context
def memory_digest_cmd(ctx: click.Context, days: int) -> None:
    """Compress recent journal entries into a weekly memory summary."""
    adj_dir = ctx.obj.get("adj_dir")
    if adj_dir is None:
        click.echo("Adjutant directory not found.", err=True)
        raise SystemExit(1)

    from adjutant.capabilities.memory.memory import memory_digest

    result = memory_digest(adj_dir, days=days)
    click.echo(result)


@memory.command(name="status")
@click.pass_context
def memory_status_cmd(ctx: click.Context) -> None:
    """Show memory system stats."""
    adj_dir = ctx.obj.get("adj_dir")
    if adj_dir is None:
        click.echo("Adjutant directory not found.", err=True)
        raise SystemExit(1)

    from adjutant.capabilities.memory.memory import memory_status

    result = memory_status(adj_dir)
    click.echo(result)


if __name__ == "__main__":
    main()
