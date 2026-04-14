# Troubleshooting

Common issues and how to resolve them.

## First Steps

For any issue, start with:

```bash
adjutant doctor
```

This checks dependencies, credentials, file permissions, and service state. It's read-only and won't modify anything.

If doctor reports problems:

```bash
adjutant setup --repair
```

Repair mode detects what's broken and fixes it.

## Listener Issues

### Listener won't start

**Symptoms**: `adjutant start` exits silently or reports an error.

**Check**:
```bash
adjutant status
```

**Common causes**:

| Cause | Fix |
|-------|-----|
| `KILLED` lockfile exists | Run `adjutant startup` (not `adjutant start`) |
| Another listener already running | Run `adjutant stop` first, then `adjutant start` |
| Missing credentials | Check `.env` has `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` |
| LLM backend not found | Install [OpenCode](https://opencode.ai) or [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) and ensure it's on PATH |

**Important**: `adjutant start` will refuse to start if a `KILLED` lockfile is present. Use `adjutant startup` for recovery -- it clears the lockfile, restores crontab, and starts fresh.

### Bot doesn't respond to messages

**Check in order**:

1. Is the listener running? `adjutant status`
2. Is it paused? Look for `PAUSED` in the status output. Run `adjutant resume`.
3. Is the chat ID correct? The bot only responds to the chat ID in `.env`.
4. Check the log: `adjutant logs` -- look for errors or "rejected unauthorized sender"
5. Rate limited? Adjutant limits to 10 messages per 60 seconds by default.

### Listener crashes repeatedly

Check `state/adjutant.log` and `state/listener.stderr.log` for error details. Common causes:

- Invalid bot token (Telegram returns 401)
- Network connectivity issues
- LLM backend process crashes

If using LaunchAgent (macOS), the service will auto-restart. Check crash frequency with:

```bash
adjutant logs
```

## KILLED State

### How to recover

```bash
adjutant startup
```

This clears the `KILLED` lockfile, restores crontab from backup, re-syncs schedules, starts the listener, and sends a recovery notification.

### What triggered the kill?

Check the log around the time of the kill:

```bash
adjutant logs
```

Look for `[control] Emergency kill` entries.

## Scheduling Issues

### Cron jobs not firing

1. Verify crontab is installed: `crontab -l`
2. Check if jobs are enabled: `adjutant schedule list`
3. Re-sync: `adjutant schedule sync`

### "opencode/claude not found on PATH" in cron

Cron runs with a minimal `PATH` (`/usr/bin:/bin`), which typically excludes
directories like `/opt/homebrew/bin` where your LLM backend binary is installed. Adjutant
snapshots your interactive shell's `PATH` when installing cron entries (via
`adjutant schedule sync`), so re-syncing usually fixes this:

```bash
adjutant schedule sync
```

As a fallback, you can set the binary path explicitly:

```bash
# For OpenCode:
export OPENCODE_BIN=/opt/homebrew/bin/opencode

# For Claude Code CLI:
export CLAUDE_CODE_BIN=/usr/local/bin/claude
```

### macOS Full Disk Access

On macOS, cron needs Full Disk Access to run scripts that access files outside standard directories.

**Fix**: System Settings > Privacy & Security > Full Disk Access > add `/usr/sbin/cron`

### Jobs fire but produce no output

Check the job's log file (shown in `adjutant schedule list`). The log path is defined in the schedule's YAML config.

## CloudCLI Web Server Issues

### CloudCLI not found on PATH

CloudCLI is the web UI for the `claude-cli` backend. Install it:

```bash
npm install -g @siteboon/claude-code-ui
```

Or set the binary path explicitly:

```bash
export CLOUDCLI_BIN=/path/to/cloudcli
```

### CloudCLI web server won't start

Check the log:

```bash
cat state/cloudcli_web.log
```

Common causes:

| Cause | Fix |
|-------|-----|
| Port already in use | Set a different port: `export CLOUDCLI_PORT=4000` |
| Binary not found | Install CloudCLI or set `CLOUDCLI_BIN` |
| Node.js version mismatch | CloudCLI requires Node.js 18+. Check `node --version` |

### CloudCLI starts but is unreachable

CloudCLI binds to `0.0.0.0` by default (all interfaces). If accessing over VPN, ensure the VPN routes traffic to the correct IP. Check:

```bash
curl http://localhost:3001/health
```

Should return `{"status":"ok",...}`.

---

## Model / AI Issues

### "Model not found" errors

The configured model may not be available in your backend setup. Check:

```bash
adjutant status
```

Look at the current tier mapping. Switch to a known working tier:

```
/model cheap
```

### Model switch doesn't persist

Model changes via `/model` are stored in `state/telegram_model.txt` as a tier name (`cheap`, `medium`, or `expensive`). They persist across restarts but not across `adjutant kill` + `adjutant startup` (which resets state). Set the default model in `adjutant.yaml` instead:

```yaml
llm:
  models:
    cheap: "anthropic/claude-haiku-4-5"
```

### Responses are very slow

- Check which tier is active with `/model` -- expensive tiers are slower
- Switch to a cheaper model: `/model cheap`
- Check if your backend is healthy: `opencode --version` or `claude --version`

## Knowledge Base Issues

### KB query returns empty or errors

1. Check the KB exists: `adjutant kb list`
2. Check KB info: `adjutant kb info <name>`
3. Verify the KB path exists on disk
4. Try a direct query: `adjutant kb query <name> "test question"`

### KB not auto-detected in chat

The agent uses KB names and descriptions to detect relevance. Improve auto-detection by giving your KB a descriptive `description` field in `knowledge_bases/registry.yaml`.

## Rate Limiting

### "Slow down" messages

Adjutant limits to 10 messages per 60 seconds by default. Wait a minute and try again. This protects against accidental message floods and excessive API usage.

## File Permission Issues

```bash
adjutant setup --repair
```

Repair mode checks and fixes:
- CLI executable permissions
- Directory permissions
- Missing directories

## Getting More Help

- Check the [commands reference](commands.md) for correct usage
- Read `state/adjutant.log` for detailed error information
- Run `adjutant doctor` for a comprehensive health check
- Check the [GitHub issues](https://github.com/eddiman/adjutant/issues)
