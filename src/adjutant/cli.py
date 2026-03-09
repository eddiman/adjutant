"""CLI entrypoint — Click-based CLI for Adjutant.

Subcommands implemented so far:
  status              — Show operational status
  pulse               — Run the autonomous pulse cron job
  review              — Run the autonomous review cron job
  rotate              — Rotate journal entries and operational log
  reply <message>     — Send a Telegram reply (Markdown)
  notify <message>    — Send a proactive Telegram notification (budget-guarded)
  update              — Self-update Adjutant from GitHub releases
  setup               — Run the interactive setup wizard
  uninstall           — Remove Adjutant from this machine
  kb run <kb> <op>    — Run a KB-local operation
  kb query <kb> <q>   — Query a KB sub-agent by name or path
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


if __name__ == "__main__":
    main()
