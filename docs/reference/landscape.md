# AI Assistant Landscape

How Adjutant compares to other personal AI agent frameworks.

---

## Projects compared

**OpenClaw** (formerly Clawdbot/Moltbot) — open-source autonomous AI agent by Peter Steinberger. Went viral Jan 2026 via Moltbook. ~500k lines of code, 70+ dependencies. Creator joined OpenAI Feb 2026; project moving to open-source foundation. [github.com/openclaw/openclaw](https://github.com/openclaw/openclaw)

**NanoClaw** — lightweight reaction to OpenClaw by qwibitai. ~35k tokens of code. Same messaging-based interface but runs agents in Linux containers for true OS-level isolation. Built on Claude Agent SDK. [github.com/qwibitai/nanoclaw](https://github.com/qwibitai/nanoclaw)

**Adjutant** — this system. Personal orchestrator with scheduled heartbeats, knowledge bases, and Telegram messaging. Not an autonomous agent — a scoped assistant that monitors projects, answers questions from curated KBs, and sends briefings.

---

## Comparison

| Dimension | OpenClaw | NanoClaw | Adjutant |
|---|---|---|---|
| **Philosophy** | Maximize autonomy — AI that *does things* | Minimize attack surface — same idea, tiny codebase | Maximize clarity — AI that *knows things*, reduces mental load |
| **Codebase** | ~500k lines, 70+ deps | ~35k tokens, handful of files | Shell scripts + markdown + sub-agents |
| **Security model** | Application-level (allowlists, pairing codes) | Container isolation (Docker/Apple Container) | Filesystem sandboxing — `.adjutant/` only, KB sub-agents scoped to their dirs |
| **Interface** | Multi-platform messaging | WhatsApp primary, skills add others | Telegram |
| **Agent model** | General autonomous agent — acts across services | Contained agents per group/context | Scoped KB sub-agents for queries; no autonomous action |
| **Customization** | Plugin/skill ecosystem | Fork and have Claude Code rewrite the codebase | Edit markdown configs, shell scripts, knowledge bases |
| **Memory** | Persistent across sessions | Per-group CLAUDE.md | Journal, heartbeat state, KB files |
| **Autonomy level** | High — known to create dating profiles without user direction | Medium — contained but still autonomous | Low — advisory only, doesn't act without being asked |

---

## What Adjutant does differently

OpenClaw and NanoClaw are **autonomous agents** — they take actions on your behalf across services. Adjutant is a **knowledge orchestrator** — it curates and queries structured information to give you clarity.

**Adjutant advantages:**
- No prompt injection risk from external services (KB sub-agents only see their own directory)
- No runaway agent problem (can't take actions on your behalf)
- Knowledge structure is human-readable markdown — fully auditable
- KB structure is designed for how LLM sub-agents navigate: `data/current.md` as landing pad, `knowledge/` for reference, `history/` for archive

**What Adjutant lacks by comparison:**
- No cross-service integration (email, calendar, social networks)
- No autonomous workflows without the heartbeat cron
- Not designed for multi-user/group contexts

---

## Notes

NanoClaw's "small enough to understand" philosophy is the closest in spirit to Adjutant's design. Its container isolation model is the right approach if Adjutant ever grows autonomous capabilities — true OS-level sandboxing rather than application-level permission checks.

OpenClaw's MoltMatch incident (agent creating a dating profile without user direction) is a useful reference case for why Adjutant deliberately keeps autonomy low and human-in-the-loop.

*Last updated: 2026-03-01*
