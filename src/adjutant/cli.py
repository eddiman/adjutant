"""CLI entrypoint — basic Click CLI for Phase 1.

Provides ``adjutant --help`` and version info. Later phases add subcommands.
"""

from __future__ import annotations

import click

from adjutant.core.paths import init_adj_dir, AdjutantDirNotFoundError


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


if __name__ == "__main__":
    main()
