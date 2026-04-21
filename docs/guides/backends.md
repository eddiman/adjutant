# LLM Backends

Adjutant supports two LLM backends. You choose one in `adjutant.yaml` and all AI interactions route through it.

| Backend | Binary | Auth | Billing |
|---------|--------|------|---------|
| **OpenCode** (`opencode`) | `opencode` CLI | Anthropic API key | Pay-per-token |
| **Claude Code CLI** (`claude-cli`) | `claude` CLI | Claude subscription (Pro/Team/Enterprise) | Included in subscription |

---

## Choosing a backend

Set `llm.backend` in `adjutant.yaml`:

```yaml
llm:
  backend: "opencode"      # or "claude-cli"
```

Or use the setup wizard, which will ask during initial configuration:

```bash
adjutant setup
```

### When to use OpenCode

- You have an Anthropic API key
- You want streaming output
- You want process reaping for orphan cleanup

### When to use Claude Code CLI

- You have a Claude Pro, Team, or Enterprise subscription
- You prefer subscription-based billing over pay-per-token
- You want per-request cost tracking (Claude CLI reports `cost_usd` in JSON output)

---

## Switching backends

1. Edit `adjutant.yaml`:
   ```yaml
   llm:
     backend: "claude-cli"   # was "opencode"
   ```
2. Restart Adjutant: `adjutant restart`

On restart, Adjutant detects the backend change and automatically:
- Translates the active model ID to the new backend's format
- Clears the Telegram session (new backend, new conversation)
- Records the switch in `state/backend.txt`

No data is lost. You can switch back at any time.

---

## Capability differences

| Capability | OpenCode | Claude CLI |
|-----------|----------|------------|
| Vision (image analysis) | Yes (native) | Yes (via Read tool image injection) |
| Dynamic model listing | Yes | Yes |
| Process reaping | Yes | No (not needed) |
| Backend-native web server | No | No |
| Streaming output | Yes | No (single-shot JSON) |
| Cost tracking per request | No | Yes |
| Session resume | Yes (`--session`) | Yes (`--resume`) |

If you use a feature that the current backend doesn't support, Adjutant tells you clearly rather than failing silently.

---

## Claude CLI setup

### 1. Install the Claude Code CLI

```bash
npm install -g @anthropic-ai/claude-code
```

### 2. Authenticate

```bash
claude login
```

### 3. Configure Adjutant

```yaml
# adjutant.yaml
llm:
  backend: "claude-cli"
```

### 4. Verify

```bash
adjutant doctor
```

The doctor command checks that the `claude` binary is on PATH, hooks are executable, and the backend is healthy.

### 5. Access the web UI

Use `adjutant web` to start Adjutant's own web dashboard from the monorepo checkout. Backend-native web servers are retired on both backends.

---

## Permission modes (Claude CLI only)

Claude Code requires explicit permission handling for non-interactive (subprocess) use. Adjutant supports two modes:

### `skip` mode (default)

```yaml
llm:
  backend: "claude-cli"
  permission_mode: "skip"
```

Uses `--dangerously-skip-permissions`. This bypasses Claude Code's deny rules in `.claude/settings.json`, but **hooks still fire**. The hooks in `.claude/hooks/` are the primary technical defense for `.env` protection.

### `allowlist` mode

```yaml
llm:
  backend: "claude-cli"
  permission_mode: "allowlist"
  allowed_tools: "Read,Glob,Grep,Edit,Write,Bash(*)"
```

Uses `--allowedTools` with an explicit whitelist. More restrictive but requires listing every tool the agent needs.

---

## Security: `.env` protection

Both backends protect `.env` files through layered defenses:

| Layer | OpenCode | Claude CLI |
|-------|----------|------------|
| **Workspace permissions** | `opencode.json` deny rules | `.claude/settings.json` (bypassed by `--dangerously-skip-permissions`) |
| **Hooks** | N/A | `.claude/hooks/block-env-access.sh` + `block-env-read.sh` (always active) |
| **Agent instructions** | "Never read .env" in agent prompt | Same |

On Claude CLI, the hooks are the primary defense. They fire even when `--dangerously-skip-permissions` is active, blocking:
- `cat .env`, `head .env`, `tail .env`, and similar read commands
- `source .env` and `. .env`
- `printenv`, `env`, `export -p`
- `grep`, `awk`, `sed` on `.env` files
- Read tool calls targeting `.env` paths

---

## KB compatibility

Switching backends is transparent for all KB interactions:

- **Adjutant querying KBs** (`kb query`, `kb write`): Handled automatically by the backend abstraction in `query.py`.
- **KB-internal LLM calls**: KBs with their own LLM pipelines (e.g. portfolio-kb's analyze pipeline) read the active backend from `adjutant.yaml` via the `ADJ_DIR` env var and dispatch to the appropriate binary. Switching `llm.backend` switches both Adjutant and KB-internal calls.
- **Workspace configs**: Both `opencode.json` and `.claude/settings.json` are scaffolded during KB creation. When switching backends, `_handle_backend_switch()` auto-generates any missing scaffold files.

See `docs/development/backend-guide.md` for the implementation pattern for KB-internal LLM calls.

---

## Known behavioral differences

- **Response style**: Claude CLI responses may feel different from OpenCode responses because OpenCode uses streaming output while Claude CLI uses single-shot JSON mode. This affects Telegram delivery — OpenCode responses can arrive incrementally, Claude CLI delivers the full response at once.
- **Vision**: OpenCode passes images natively. Claude CLI uses Read tool image injection (the image is read into the prompt context). Both work, but the mechanisms differ.
- **Model names**: OpenCode uses full IDs (`anthropic/claude-sonnet-4-6`), Claude CLI uses short names (`sonnet`). Adjutant translates automatically.
- **Cost tracking**: Only Claude CLI reports `cost_usd`. OpenCode responses have no cost field.
- **Process cleanup**: OpenCode spawns `bash-language-server` child processes that need reaping. Claude CLI does not have this issue.

---

## Troubleshooting

### `claude not found on PATH`

Install Claude Code CLI: `npm install -g @anthropic-ai/claude-code`

Or set the `CLAUDE_CODE_BIN` environment variable to the full path:

```bash
export CLAUDE_CODE_BIN=/usr/local/bin/claude
```

### `Not authenticated` / `login required`

Run `claude login` and follow the prompts.

### Hooks not working

Check that hook scripts are executable:

```bash
chmod +x .claude/hooks/block-env-access.sh
chmod +x .claude/hooks/block-env-read.sh
```

`adjutant doctor` flags non-executable hooks as errors.

### Backend switch didn't take effect

Restart Adjutant after changing `llm.backend`:

```bash
adjutant restart
```

Check `state/backend.txt` to confirm the active backend.
