# Setup Wizard

Run the interactive setup wizard to configure your Adjutant installation:

```bash
adjutant setup
```

## Wizard steps

The wizard walks through eight steps:

1. **Prerequisites** — verifies dependencies are in place (Python, backend CLI, curl)
2. **Install path** — confirms where Adjutant lives on disk
3. **Backend** — choose between OpenCode and Claude Code CLI (see [Backends](../guides/backends.md))
4. **Identity** — creates your `soul.md`, `heart.md`, and `registry.md` files (see [Configuration](../guides/configuration.md))
5. **Messaging** — prompts for your Telegram bot token and chat ID, writes them to `.env`
6. **Features** — optional news briefing, screenshot, vision, search, and usage tracking
7. **Service** — installs the shell alias and optionally sets up auto-start on boot
8. **Heartbeat** — enables autonomous pulse/review schedule and sets notification budget

## Backend selection

During step 3, the wizard asks which LLM backend to use:

| Backend | Best for |
|---------|----------|
| **OpenCode** | Vision support, model listing, session resume |
| **Claude Code CLI** | Cost tracking, permission allowlists |

You can switch backends later by editing `adjutant.yaml` — see [Backends](../guides/backends.md).

## Repair mode

If something needs fixing after initial setup, re-run in repair mode:

```bash
adjutant setup --repair
```

Repair mode runs health checks and offers to fix each issue found.

## Dry-run mode

Preview what the wizard would do without making changes:

```bash
adjutant setup --dry-run
```

Prompts run interactively as normal; filesystem writes, service installs, and crontab edits are suppressed and printed as `[DRY RUN] Would: ...` instead.

For implementation details, see [Setup Wizard Internals](../development/setup-wizard.md).

## Next step

[Send your first message](first-message.md) to verify everything is working.
