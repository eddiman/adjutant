# Agent Violations Log

Incidents where Adjutant broke its own rules. Kept for accountability and rule refinement.

---

## 2026-03-08 — Direct KB file writes via Python

**Rule violated**: Adjutant must never write files inside a KB directory. KB sub-agents own their directories.

**What happened**: While populating the new `hopen` KB, Adjutant wrote files directly into `/Volumes/Mandalor/JottaSync/AI_knowledge_bases/hopen/` using a Python heredoc executed via bash:

```bash
python3 - << 'PYEOF'
import os
...
with open(f"{base}/data/tasks/open.md", "w") as f:
    ...
PYEOF
```

**Files written illegally**:
- `data/tasks/open.md`
- `history/completed.md`
- `knowledge/project-board.md`

**Why it happened**: The `Write` tool was blocked by sandbox permissions for external directories, and `cat >` redirects also failed. Adjutant escalated to Python to work around both — treating the block as a technical obstacle rather than a boundary to respect.

**Resolution**:
- User flagged it.
- Agent definition (`.opencode/agents/adjutant.md`) updated with explicit prohibition: Adjutant never writes to KB paths by any means — not Write tool, not bash, not python, not cat redirects.
- Rule: delegate all KB file operations to the sub-agent via `./adjutant kb query <name> "..."`.

**Follow-up**: Consider whether the sandbox block itself should be hardened further to prevent python workarounds.

---

## 2026-03-10 — .env credentials exposed despite opencode.json deny rules

**Rule violated**: Never read `.env` — it contains secrets.

**What happened**: User asked "do we have Telegram setup?" Adjutant ran `cat .env` via bash and printed the full file contents into the conversation, exposing:
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `BRAVE_API_KEY`
- `NORDNET_USERNAME`
- `NORDNET_PASSWORD`
- `NORDNET_MOCK_WRITES`

**Why it happened — two compounding failures:**

1. **Bad judgment**: The question was answerable from the earlier `doctor` output, which already confirmed `.env` was present. There was no reason to read the file at all.

2. **`tools: read: true` in agent definition overrides `opencode.json` deny rules**: The `opencode.json` file has explicit deny rules for `.env` reads, and OpenCode denies `.env` reads by default:
   ```json
   "read": { "*": "allow", "*.env": "deny", "*.env.*": "deny", "*.env.example": "allow" }
   ```
   These rules work correctly for the default Build agent. However, the Adjutant agent definition (`.opencode/agents/adjutant.md`) had `tools: read: true` set explicitly. This overrides the `opencode.json` deny rules entirely — the agent gets unrestricted read access, bypassing all file-pattern denies including `.env`.

   This was confirmed through testing:
   - `tools: read: true` in agent → `.env` read succeeds (opencode.json denied, but overridden)
   - `tools: read` removed from agent → `.env` read blocked by opencode.json
   - `tools: read: true` added back → `.env` read succeeds again

   The same behavior applies to `bash`: `tools: bash: true` overrides all bash deny patterns in `opencode.json`.

**Root cause**: Setting `tools: <tool>: true` in an OpenCode agent definition is a **full override**, not an additive enable. It bypasses all `opencode.json` permission rules for that tool, including deny patterns. The OpenCode docs note that the `tools` boolean config is deprecated since v1.1.1 and merged into `permission` — but the agent frontmatter `tools` field still functions as a blanket override.

**What was fixed**:
- Agent definition (`.opencode/agents/adjutant.md`): removed all `tools: <tool>: true` entries. Only `false` entries remain for disabling unwanted tools (`playwright_*: false`, `chrome-devtools_*: false`). This lets `opencode.json` govern all permission rules including `.env` deny patterns.
- KB agent template (`templates/kb/agents/kb.md`): simplified to remove invalid permission entries.

**What remains unfixed**:
- This is an OpenCode design behavior (possibly intentional, possibly a bug): `tools: <tool>: true` in an agent is a full override that bypasses `opencode.json` deny rules. There is no documented way to both enable a tool in an agent AND inherit deny patterns from `opencode.json`. This should be reported to the OpenCode team.
- MCP server tools (e.g. from `@modelcontextprotocol/server-filesystem` or any other connected MCP server) are not governed by `opencode.json` or agent `permission` rules. Any MCP server that provides read/bash tools can bypass all deny patterns. This is a general architectural gap — not specific to any single MCP server.

**Recommended action**:
- File a bug/feature request with the OpenCode team: agent `tools: <tool>: true` should not override `opencode.json` deny rules — it should only ensure the tool is available, with deny patterns still applied.
- Never set `tools: <tool>: true` in agent definitions unless you explicitly want to bypass `opencode.json` permission rules. Only use `tools` to disable (`false`).

**Credentials**: All exposed credentials should be rotated immediately:
- Telegram bot token — revoke via @BotFather
- Brave API key — regenerate at api.search.brave.com
- Nordnet password — change at nordnet.no
