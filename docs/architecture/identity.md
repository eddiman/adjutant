# Identity & Agent

How Adjutant's persona is defined, loaded, and used during conversations.

---

## Three-Layer Identity Model

The agent's personality and knowledge are split across three files in `identity/`. All three are loaded into the agent's context at chat time, every request.

| File | Role | Mutability |
|------|------|-----------|
| `identity/soul.md` | Core values, principles, personality, communication style. Who the agent fundamentally is. | Rarely changes |
| `identity/heart.md` | Current priorities, active concerns, focus areas. What matters right now. | Occasionally updated |
| `identity/registry.md` | Operational facts: current projects, people, preferences, schedule. | Frequently updated |

All three files are user-specific and gitignored. Example templates (`*.example`) are tracked in the repo. The setup wizard creates your personal copies from these templates.

### Why three files?

Loading context has a cost — both in tokens and latency. Splitting identity into layers lets you update the parts that change frequently (`registry.md`) without touching the stable core (`soul.md`). It also makes each file's purpose clear: soul defines *who*, heart defines *how*, registry defines *what's currently happening*.

---

## Agent Definition — `.opencode/agents/adjutant.md`

The agent definition file lives at `.opencode/agents/adjutant.md`. Both backends read from this same location:
- **OpenCode:** loaded via `opencode run --agent adjutant`
- **Claude CLI:** YAML frontmatter is stripped, markdown body passed via `--system-prompt-file`

This file specifies which identity files to load, system prompt instructions, and behavioural constraints. It is tracked in the repo (it contains no personal data). The identity files it references are gitignored and personal.

---

## LLM Backend Integration

Natural language processing and long-running agent tasks use the LLM backend. All AI calls go through `get_backend().run()` (defined in `core/backend.py`) rather than calling `opencode` or `claude` directly.

Two backends are supported:
- **OpenCode** (`opencode`): Uses the OpenCode CLI with an Anthropic API key. Supports vision, streaming, model listing, and process reaping.
- **Claude Code CLI** (`claude-cli`): Uses the Claude Code CLI with a Claude subscription. Supports cost tracking and a web server (CloudCLI).

The backend is configured in `adjutant.yaml` under `llm.backend`. See [Backend Architecture](backends.md) for the full protocol and capability system.

### Why wrap `opencode`?

Every `opencode run` invocation spawns a `bash-language-server` child process (~400MB RSS). When `opencode` exits, this child survives as an orphan (reparented to PID 1). Without intervention, these accumulate over time.

`core/opencode.py` provides process management to prevent this — it takes a snapshot of `bash-language-server` PIDs before calling `opencode run`, then kills any new ones that appeared after it exits. This is handled internally by `backend_opencode.py`; call sites never interact with `opencode.py` directly.

---

## LLM Model Configuration

Three model tiers are configured in `adjutant.yaml`:

| Tier | Use case |
|------|---------|
| `cheap` | Routine chat, triage, classification (default for standard chat) |
| `medium` | Escalations, deeper analysis |
| `expensive` | Complex reasoning (`/confirm` only) |

The active Telegram chat tier is stored in `state/telegram_model.txt` and can be switched at runtime via `/model cheap`, `/model medium`, or `/model expensive`.

---

## Security Model

Adjutant is sandboxed to its install directory (`$ADJ_DIR`). External directory access is denied at the workspace permission level — configured in `opencode.json` (OpenCode) or `.claude/settings.json` + hooks (Claude CLI), not in the agent prompt. This prevents:
- Accidental writes to user projects outside the adjutant directory
- Prompt injection risk from external files being read directly by the agent

All external knowledge enters through KB sub-agents, which are sandboxed to their own directories and run as separate backend invocations scoped to the KB's workspace.

---

## Heartbeat and Notification Behaviour

The agent operates on-demand — there are no scheduled background jobs by default. Proactive behaviour is triggered by Telegram commands:

- `/pulse` — queries every registered KB via `kb_query()` for a brief status update (current state, blockers, upcoming deadlines). No direct access to external directories; all project knowledge flows through KB sub-agents.
- `/reflect` — queries every registered KB in depth and, for read-write KBs, encourages the sub-agent to update stale data files. Uses the medium tier (Sonnet); gated behind `/confirm` as a safety check.

When to expect notifications:
- A KB reports an active blocker, approaching deadline, or material status change → escalated to `insights/pending/` during pulse → processed and sent during reflect
- Action needed within 48h on a tracked priority

When the agent stays silent:
- No significant issues reported across KBs
- Routine status with no open deadlines
- Max 2–3 notifications per day; minor items are batched
