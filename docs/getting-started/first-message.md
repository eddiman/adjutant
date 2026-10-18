# First Message

With setup complete, start Adjutant's runtime services and verify they are working.

## Start Adjutant

```bash
adjutant start
```

The durable-operation worker starts first, followed by the Telegram listener. This order ensures that natural-language messages can run as soon as the listener accepts them. Verify Adjutant is running:

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
