# KB Write Speedup Plan

**Date:** 2026-03-15
**Status:** In progress

## Problem

A message like "update 6 issues in hopen" triggers the adjutant agent (inside a 240s opencode session) to call `./adjutant kb query hopen "..."` **multiple times sequentially**. Each call spawns a full opencode subprocess (opencode-inside-opencode), takes 60-80s, and two of four timed out at the 80s `KB_QUERY_TIMEOUT`. Total wall time: ~240s, resulting in the chat session timing out.

### Evidence (adjutant.log, 2026-03-15)

```
[18:54] [kb] Query start:    kb='hopen' timeout=80.0s
[18:55] [kb] Query complete:  kb='hopen' reply_len=2044        # ~60s, OK
[18:55] [kb] Query start:    kb='hopen' timeout=80.0s
[18:56] [kb] Query exited non-zero rc=-15 (timed_out=True)     # 80s, KILLED
[18:57] [kb] Query start:    kb='hopen' timeout=80.0s
[18:58] [kb] Query exited non-zero rc=-15 (timed_out=True)     # 80s, KILLED
[18:58] [kb] Query start:    kb='hopen' timeout=80.0s
[18:58] [telegram] Chat timed out after 240s                   # outer timeout fires
[18:58] [kb] Query complete:  kb='hopen' reply_len=2615        # too late, parent dead
```

### Root Causes

1. **Adjutant agent splits work it should batch** — despite the "one query per message" rule in `adjutant.md:42`, the LLM still issues multiple sequential calls.
2. **KB write queries are inherently slow** — the sub-agent must read context, reason about multiple files, and make sequential tool calls internally.
3. **Writes block the chat session** — the adjutant agent waits for each `kb query` to complete before proceeding, eating into the 240s budget.

## Changes

### Change 1: Add `kb write` CLI command — fire-and-forget writes

The biggest win. Currently, KB writes piggyback on `kb query`, which blocks the adjutant agent for the entire duration. Since acknowledgment-with-details is sufficient (user confirmed), writes can be non-blocking.

**New command:** `./adjutant kb write <name> "<instruction>"`

**How it works:**
- Spawns the KB sub-agent subprocess via `asyncio.create_task` wrapping `opencode_run` without timeout
- Immediately returns a confirmation message to the caller
- The sub-agent runs to completion in the background, no timeout pressure
- Logs start/complete/error events to `adjutant.log` under `[kb]` context

**Files to change:**

| File | Change |
|------|--------|
| `src/adjutant/capabilities/kb/query.py` | Add `kb_write()` / `kb_write_by_path()` — similar to `kb_query_by_path()` but detached, returns immediately |
| `src/adjutant/cli.py` | Add `kb write` Click command |
| `.opencode/agents/adjutant.md` | Add `kb write` command docs, instruct agent to use it for writes |
| `src/adjutant/messaging/telegram/commands.py` | Add `/kb write` handler in `cmd_kb()` |

**Design decisions:**
- Background subprocess logs results but does NOT send Telegram notifications on failure
- Failures visible via `/status` or log inspection
- Start simple with `asyncio.create_task` wrapping `opencode_run` — escalate to process-level detachment only if needed

### Change 2: Strengthen the prompt in `adjutant.md`

The current rule at line 42 says "one query per message" but the agent still splits work. Make it more explicit about:
1. Why splitting is catastrophic (timeout budget)
2. Concrete batching examples
3. Separate read vs write instructions — reads use `kb query`, writes use `kb write`

### Change 3: Add write-awareness to KB sub-agent template

The KB sub-agent template (`templates/kb/agents/kb.md`) currently has read-only instructions. Write-capable KBs need guidance on efficient multi-file edits:
- Plan all edits first, then execute in rapid succession
- Minimize tool calls — combine related changes into single Edit operations
- Don't re-read files just to confirm writes succeeded

### Not proposed

- **Raising any timeout** — hard constraint
- **Parallel KB queries via `asyncio.gather`** — helps pulse/review (multiple KBs) but not the hopen case (single KB, multiple writes). Follow-up candidate.
- **Caching** — KB queries are stateful writes, not cacheable
- **Telegram notification on write failure** — adds coupling between KB layer and messaging layer
