# First Message

With setup complete, start the Telegram listener and verify Adjutant is working.

## Start the listener

```bash
adjutant start
```

The Telegram listener starts in the background. Verify it's running:

```bash
adjutant status
```

You should see `Adjutant is up and running.` and the listener's PID.

## Send a message

Open Telegram and send a message to your bot. Try these:

| Message | What happens |
|---------|-------------|
| `/status` | Adjutant replies with its current operational state |
| `/help` | Lists all available slash commands |
| `/model` | Shows the current tier and available tier mappings |
| `What time is it?` | A natural language question routed to the LLM backend |

That's it. Adjutant is running.

## Next steps

- **Configure what Adjutant knows about you** — [Configuration](../guides/configuration.md)
- **See all commands** — [Commands](../guides/commands.md)
- **Add a knowledge base** — [Knowledge Bases](../guides/knowledge-bases.md)
- **Understand start/stop/pause** — [Lifecycle](../guides/lifecycle.md)
- **Set up autonomous cycles** — [Autonomy](../guides/autonomy.md)
