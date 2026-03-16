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

The agent definition loaded by `opencode run --agent adjutant`. This file lives at `.opencode/agents/adjutant.md`. It specifies:
- Which identity files to load
- System prompt instructions for the AI
- Behavioural constraints

This file is tracked in the repo (it contains no personal data). The identity files it references are gitignored and personal.

---

## OpenCode Integration

Natural language processing and long-running agent tasks use OpenCode. All AI calls go through `opencode_run()` (defined in `core/opencode.py`) rather than calling `opencode` directly.

### Why wrap `opencode`?

Every `opencode run` invocation spawns a `bash-language-server` child process (~400MB RSS). When `opencode` exits, this child survives as an orphan (reparented to PID 1). Without intervention, these accumulate over time.

`core/opencode.py` provides process management to prevent this — it takes a snapshot of `bash-language-server` PIDs before calling `opencode run`, then kills any new ones that appeared after it exits.

---

## LLM Model Configuration

Three model tiers are configured in `adjutant.yaml`:

| Tier | Use case |
|------|---------|
| `cheap` | Routine chat, triage, classification (default for standard chat) |
| `medium` | Escalations, deeper analysis |
| `expensive` | Complex reasoning (`/confirm` only) |

The active model for Telegram chat is stored in `state/telegram_model.txt` and can be switched at runtime via `/model <model-name>`.

---

## Security Model

Adjutant is sandboxed to its install directory (`$ADJ_DIR`). External directory access is denied at the OpenCode permission level — configured in `opencode.json`, not in the agent prompt. This prevents:
- Accidental writes to user projects outside the adjutant directory
- Prompt injection risk from external files being read directly by the agent

All external knowledge enters through KB sub-agents, which are sandboxed to their own directories and run as separate `opencode run --agent kb` invocations.

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
