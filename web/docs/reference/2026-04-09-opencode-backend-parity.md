# 2026-04-09 — OpenCode backend parity plan for `/chat`

Scope: make the `/chat` module work against `opencode` as a drop-in replacement for `claude-cli`, so flipping `llm.backend` in `adjutant.yaml` from `claude-cli` → `opencode` gives the same user-facing functionality.

**Status:** exploration + plan only. No code changes in this document.

---

## TL;DR

The backend abstraction is **in better shape than expected**:

- `web/api/src/services/cliAdapter.ts` already has a working `runOpenCode()` branch that spawns `opencode run --format json` and parses NDJSON events. I verified the event shape matches live output (`{type:"error", error:{data:{message:"..."}}}` etc.).
- `web/api/src/services/backendDetector.ts` already supports both `claude-cli` and `opencode` via `llm.backend` in `adjutant.yaml`.
- OpenCode actually exposes **better** session primitives than Claude CLI does: `opencode session list --format json`, `opencode export <id>`, `opencode run -s <id>` — no JSONL scraping needed. Titles, cwd, tokens and cost are all first-class.

The blockers are two files and three UI tweaks:

1. `web/api/src/routes/sessions.ts` — **100% Claude-CLI–specific** session discovery and history replay. This is the only real engineering work.
2. `web/api/src/ws/sessionHandler.ts` — hardcodes `readCliSessionMessages` on session resume, needs to branch by backend.
3. `web/api/src/services/cliAdapter.ts:425` — hardcodes `costUsd: null` for OpenCode despite OpenCode tracking cost.
4. `web/app/src/components/CodeSession/SessionHeader.tsx:26` — gates cost badge behind `name === 'claude-cli'`; should flip to `costUsd != null`.
5. `web/app/src/components/CodeSession/CodeSession.tsx:235-240` — error banner has Claude-only install hint.

Plus one known parity gap that we should explicitly **not** try to fill:
- Claude CLI's nested `subagents/*.jsonl` sub-agent discovery has no OpenCode equivalent. OpenCode doesn't persist sub-agent invocations as separate sessions — they're just message parts inside a parent session. This is a genuine feature delta, not something the adapter can paper over.

---

## What OpenCode gives us (verified live against v1.3.17)

### CLI surface
- `opencode run --format json [-s <sessionId>] [--continue] [-m provider/model] [--dir <cwd>] [--agent <name>] <prompt>`
  — streams NDJSON events; already wired in `cliAdapter.ts:337-446`.
- `opencode session list --format json -n <N>` — returns structured array:
  ```json
  [
    {
      "id": "ses_29d8346e7ffeQjJUuMCEGdi7jo",
      "title": "New session - 2026-04-06T11:10:34.265Z",
      "updated": 1775473855150,
      "created": 1775473834265,
      "projectId": "aee55dc378e469354e1c05d145726f02cf1c3542",
      "directory": "/Users/edvardpiresbjorgen/Documents/Projects/adjutant"
    },
    ...
  ]
  ```
- `opencode export <sessionId>` — returns full session JSON with `info`, `messages[].info`, `messages[].parts[]`. Includes per-message `tokens.{input,output,cache.read,cache.write}`, per-message `cost`, cwd, model, provider, title, timestamps. This is a single-shot history replay that dwarfs Claude CLI's JSONL parsing in both ease of use and data completeness.
- `opencode session delete <sessionId>` — delete support.
- `opencode stats` — aggregated token and cost totals.

### On-disk storage
- `~/.local/share/opencode/opencode.db` — SQLite database.
- Relevant tables: `session(id, project_id, parent_id, slug, directory, title, time_created, time_updated, ...)`, `message(id, session_id, data, ...)`, `part(id, message_id, session_id, data, ...)`.
- `part.data` is a JSON blob like `{"type":"text","text":"Hello! How can I help you today?"}` or `{"type":"step-start",...}`.

We can safely prefer the **CLI commands** over direct SQLite access for this integration. The JSON shapes are stable contracts, the subprocess cost is negligible at list sizes we're dealing with (hundreds of sessions), and we avoid introducing a SQLite driver dependency. Direct SQLite remains a viable optimization if listing ever becomes a bottleneck.

---

## Current coupling map (inherited from the exploration pass)

### Backend-aware files already in good shape
| File | What it does | OpenCode support |
|------|---|---|
| `web/api/src/services/backendDetector.ts` | Reads `llm.backend` from `adjutant.yaml`, finds binary | ✅ Both |
| `web/api/src/services/cliAdapter.ts` | Spawns backend process, parses NDJSON stream | ✅ Both (minor cost gap) |
| `web/api/src/services/sessionService.ts` | In-memory session store | ✅ Both (neutral) |
| `web/api/src/ws/sessionHandler.ts` | WS message router | ⚠️ Mostly — resume path is Claude-only |
| `web/app/src/hooks/useCodeSession.ts` | WS client hook | ✅ No branching, backend-agnostic |
| `web/app/src/components/CodeSession/MessageBubble.tsx` | Renders cost/tokens if present | ✅ Graceful null handling |
| `web/app/src/components/CodeSession/StatusBar.tsx` | Shows backend name string | ✅ No branching |

### Backend-aware files that need work
| File | Coupling | Severity |
|------|---|---|
| `web/api/src/routes/sessions.ts` | `scanClaudeCliSessions()`, `readCliSessionMessages()`, `/api/sessions` endpoint all 100% Claude-CLI-specific | 🔴 Blocker |
| `web/api/src/ws/sessionHandler.ts` (lines 69-84) | Resume flow calls `readCliSessionMessages` directly without checking backend | 🟠 Must branch |
| `web/api/src/services/cliAdapter.ts` (line 425) | `costUsd: null` hardcoded for OpenCode even though it tracks cost | 🟡 Wrong data |
| `web/app/src/components/CodeSession/SessionHeader.tsx` (line 26) | Cost badge gated on `name === 'claude-cli'` | 🟡 UI papering over backend gap |
| `web/app/src/components/CodeSession/CodeSession.tsx` (lines 235-240) | Error banner tells user to install Claude Code — biased install hint | 🟢 Cosmetic |

### Type definitions that are already backend-agnostic
- `web/api/src/types/session.ts:5` — `CliBackendName = 'claude-cli' | 'opencode'` already declared
- `CliSessionSummary` interface — the name is misleading; the shape (`id`, `name`, `cwd`, `model`, `timestamp`, `messageCount`, `source`) works fine for OpenCode too. Rename deferred to a later cleanup.

### Feature × backend support matrix (current state)
| Feature | Claude CLI | OpenCode | Gap |
|---|---|---|---|
| List existing sessions | ✅ filesystem scan | ❌ not implemented | Blocker |
| Session titles | ✅ parsed from JSONL | ❌ N/A | Blocker (but OpenCode has native titles) |
| Resume session | ✅ `readCliSessionMessages` + `--resume` | ❌ history loader missing; `-s` flag passes through | Blocker |
| KB grouping by cwd | ✅ cwd from JSONL | ❌ no cwd plumbing | Falls out for free once discovery works |
| Auto-discovered workspaces (Fix 9) | ✅ | ❌ | Same |
| Sub-agent visibility (Fix 12) | ✅ nested `subagents/*.jsonl` | 🟥 concept doesn't exist in OpenCode | Document as intentional gap |
| Streaming chat | ✅ | ✅ | Already works |
| Cancel mid-stream | ✅ | ✅ | Already works |
| Cost display | ✅ | 🟡 backend tracks it, adapter throws it away | Minor fix |
| Token display | ✅ | 🟡 same — backend has it, adapter doesn't propagate | Minor fix |
| Model switching | ✅ (aliases) | ✅ (`provider/model` strings) | Already works |
| Permission mode | ✅ `--allowedTools` / `--dangerously-skip-permissions` | ❓ OpenCode uses `--agent` + MCP — different model | Document semantic difference |

---

## Plan

### Phase 1 — Unblock session discovery for OpenCode (the real work)

**File: `web/api/src/routes/sessions.ts`**

**Goal:** the `/api/sessions` endpoint returns OpenCode sessions in the same `cliSessions` array shape the frontend already renders, so the session list "just works" when `llm.backend: opencode`.

**Approach:** split the Claude-CLI-specific path into one function and add a parallel OpenCode path, then have the route dispatch on `backendDetector.detect()` (or call both and merge — see below).

Concretely:

1. Extract the current `scanClaudeCliSessions()` + `scanSessionFile()` + `readSubagentMeta()` + `decodeCwdFromDirName()` family unchanged. Rename the public entry point to `scanClaudeCliSessionsImpl` or leave as-is — stability matters more than naming.

2. Add `scanOpenCodeSessions()`:
   - Spawn `opencode session list --format json -n 500`.
   - Parse the JSON array.
   - Map each entry to the existing `CliSessionSummary` shape:
     ```
     id          ← entry.id
     name        ← entry.title || 'Untitled session'
     cwd         ← entry.directory
     model       ← ''                       // not in list response; filled on resume
     timestamp   ← new Date(entry.updated).toISOString()
     messageCount ← 0                       // list endpoint doesn't count; optional — see below
     source      ← 'cli'
     ```
   - Return the array, capped at 500 for consistency with the Claude path.
   - If `messageCount` is important for UI parity, follow up with a single `opencode export <id>` per session — but this is O(N) subprocess spawns and should be opt-in. **Recommendation:** leave `messageCount: 0` for the list view; it's cosmetic.

3. Add `readOpenCodeSessionMessages(sessionId)`:
   - Spawn `opencode export <sessionId>`.
   - Parse the JSON — note the CLI prints a leading `"Exporting session: ..."` line before the JSON, strip that.
   - Walk `messages[]`. For each message:
     - `info.role` is `'user' | 'assistant'`.
     - `parts[]` contains blocks with `type: 'text'` (the useful ones), `type: 'step-start'`, `type: 'step-finish'`, `type: 'tool_use'`, etc.
     - Join all `type: 'text'` parts' `.text` fields.
     - Map to the existing `ChatMessage` shape: `{id, role, content, timestamp, model?, costUsd?, inputTokens?, outputTokens?}`.
     - `info.id` → `ChatMessage.id`.
     - `info.time.created` (epoch ms) → ISO timestamp.
     - `info.model.modelID` / `info.modelID` → `model`.
     - `info.cost` → `costUsd`.
     - `info.tokens.input` / `info.tokens.output` → `inputTokens` / `outputTokens`.
   - Return the list of `ChatMessage`.

4. Rewrite the `GET /api/sessions` handler to:
   ```
   const backend = await backendDetector.detect();
   if (backend?.name === 'opencode') {
     const cliSessions = await scanOpenCodeSessions();
     res.json({ sessions: sessionService.list(), cliSessions });
     return;
   }
   // default / claude-cli
   const cliSessions = await scanClaudeCliSessions();
   res.json({ sessions: sessionService.list(), cliSessions });
   ```
   Or — cleaner — introduce a small `SessionSource` interface later (see Phase 5). For Phase 1 the branch is fine.

5. Export `readOpenCodeSessionMessages` alongside `readCliSessionMessages` so `sessionHandler.ts` can pick the right one.

**Open question for Phase 1:** should `scanOpenCodeSessions` scope to the current cwd or return everything? `opencode session list` returns all sessions across all projects by default — that's what Claude-CLI currently does too, so parity-wise we should keep that behaviour.

---

### Phase 2 — Route the resume flow through the right history reader

**File: `web/api/src/ws/sessionHandler.ts`**

Currently (lines 69-84) this is hardcoded:
```ts
session.cliSessionId = msg.cliSessionId;
const history = await readCliSessionMessages(msg.cliSessionId);
for (const m of history) session.messages.push(m);
```

Change to:
```ts
session.cliSessionId = msg.cliSessionId;
const history = backend.name === 'opencode'
  ? await readOpenCodeSessionMessages(msg.cliSessionId)
  : await readCliSessionMessages(msg.cliSessionId);
for (const m of history) session.messages.push(m);
```

The auto-naming logic (lines 77-82) just reads `firstUser.content` and slices to 60 chars — that works for either backend, no change needed.

---

### Phase 3 — Fix cost and token tracking for OpenCode runtime streaming

**File: `web/api/src/services/cliAdapter.ts` lines 337-446**

Two problems in `runOpenCode()`:

1. `onComplete({ cliSessionId: sessionId, costUsd: null })` at line 425 — `costUsd: null` is hardcoded despite OpenCode tracking cost per message. The NDJSON stream from `opencode run --format json` should contain cost information somewhere (the sqlite data confirms it's tracked). Need to actually run a successful `opencode run` and capture the full event stream to find which event carries cost/tokens. (My probe hit a 429 auth error so I couldn't capture live output — this needs a live test.)

2. No `inputTokens` / `outputTokens` plumbing at all. The `CompleteEvent` interface already has those optional fields.

**Approach:**
- Log the full NDJSON stream from a successful `opencode run --format json` query, identify the terminal event that carries `cost`, `tokens.input`, `tokens.output`.
- Accumulate those in local vars during `rl.on('line', ...)`.
- Pass them in `onComplete({ cliSessionId, costUsd, inputTokens, outputTokens })`.

**Fallback:** if the live stream doesn't carry cost, we can post-hoc call `opencode export <sessionId>` after `onComplete` and pull the numbers from the last message. This adds one subprocess spawn per message but is strictly additive — the core chat flow isn't blocked on it.

---

### Phase 4 — UI fixes

**`web/app/src/components/CodeSession/SessionHeader.tsx:26`**
```diff
-{session.totalCostUsd != null && backendInfo?.name === 'claude-cli' && (
+{session.totalCostUsd != null && session.totalCostUsd > 0 && (
   <span className={styles.headerCost}>${session.totalCostUsd.toFixed(4)}</span>
 )}
```
Once Phase 3 fills `costUsd` from OpenCode, the badge will show for both backends without any other changes.

**`web/app/src/components/CodeSession/CodeSession.tsx:235-240`**

Current text:
> Install Claude Code (`npm i -g @anthropic-ai/claude-code`) or OpenCode, then configure `llm.backend` in adjutant.yaml.

Make the copy backend-neutral, or — better — read the detected state and render a specific hint. Low priority; it only shows when no backend is found at all.

---

### Phase 5 — Abstraction cleanup (deferred, optional)

Once Phase 1 works, the shape of the abstraction becomes obvious and we can introduce a clean interface. Not required for parity, but worth doing before we add a third backend.

```ts
// web/api/src/services/sessionSources.ts
interface SessionSource {
  name: CliBackendName;
  listSessions(opts?: { limit?: number }): Promise<CliSessionSummary[]>;
  readSessionMessages(sessionId: string): Promise<ChatMessage[]>;
}

class ClaudeCliSessionSource implements SessionSource { ... }
class OpenCodeSessionSource implements SessionSource { ... }
```

Then `GET /api/sessions` just resolves the active source via `backendDetector`, calls `listSessions()`, and the WS handler calls `readSessionMessages()`. The file-by-file coupling collapses to one factory.

This is a pure refactor — do it **after** Phase 1-3 are working and tested, so the interface is shaped by reality not speculation.

---

### Phase 6 — Document the intentional gaps

Add a short note to `web/CLAUDE.md` under the chat module section:

> `/chat` supports both `claude-cli` and `opencode` backends via `llm.backend` in `adjutant.yaml`. Parity differences:
> - **Sub-agent session discovery** is Claude-CLI-only. OpenCode doesn't persist sub-agent invocations as separate sessions — they're message parts within the parent session. The nested `subagents/*.jsonl` discovery path in `sessions.ts` is skipped when `llm.backend: opencode`.
> - **Permission mode** semantics differ. Claude-CLI's `--allowedTools` / `--dangerously-skip-permissions` have no direct OpenCode equivalent; OpenCode uses `--agent` + MCP permission model. The `permissionMode` field in `backendDetector` is Claude-specific and ignored by the OpenCode adapter.

---

## Risks & open questions

1. **Cost/token capture from live stream** — I couldn't validate this because `opencode run` hit a 429 auth error in my probe. Need a working query to capture the terminal event payload. If it's not in the stream, we fall back to post-run `opencode export` (Phase 3 fallback).

2. **`opencode run --dir <cwd>` vs spawn cwd** — the adapter currently passes `--dir` **and** sets `spawn({cwd})`. Need to confirm OpenCode actually honors `--dir` when `spawn cwd` differs, and that KB auto-grouping (Fix 9) picks up the right directory. Test by spawning an OpenCode session in a different cwd than the spawn process.

3. **Subprocess spawn overhead for list** — `opencode session list --format json -n 500` is a subprocess spawn per `/api/sessions` call. Should be fast (<100ms), but if the focus/visibility refetch from Fix 8 fires frequently, it could add up. Mitigation: SessionList.tsx already has a 2s debounce (`lastLoadRef`) from Fix 2. If needed, add a small in-memory cache in `sessions.ts` with a 5s TTL.

4. **Session message count in list view** — Claude-CLI computes `messageCount` during the JSONL scan. OpenCode `session list` doesn't return that. Options: (a) set it to 0 and let the UI hide it, (b) `opencode export <id>` per session (O(N) spawns — too expensive for 500 sessions), (c) read from sqlite directly (`SELECT COUNT(*) FROM message WHERE session_id = ?`). **Recommendation:** go with (a) for Phase 1, revisit if the count is genuinely useful in the list. It's purely cosmetic.

5. **Model alias translation** — Claude-CLI's `CLAUDE_ALIASES` map (haiku/sonnet/opus) is adapter-side. OpenCode expects full `provider/model` strings. The current `runOpenCode` passes the model through as-is, which is correct — but the `adjutant.yaml` `llm.models.*` fields should use the OpenCode format (`anthropic/claude-opus-4-6`) when `backend: opencode`. This is already the format in the current `adjutant.yaml` (verified line 16 `backend: claude-cli` and models default to `anthropic/claude-*-*` form). No code change needed; document the format expectation.

6. **Sub-agent visibility delta** — the user asked for sub-agent sessions (Fix 12) which is a claude-cli-specific feature with no OpenCode equivalent. When switching backends they will lose visibility of the ~89 sub-agent sessions we currently surface. This is data the user doesn't create — it's spawned by the orchestrator — so the impact depends on whether the user relies on inspecting them. **Document, don't fix.**

7. **`--continue` vs `-s <sessionId>`** — OpenCode has both; we currently only use `-s`. `--continue` resumes "the last session" which is slightly different semantics. Not a parity issue but worth knowing for slash commands like `/continue`.

---

## Effort estimate (qualitative)

| Phase | Complexity | Risk | Notes |
|---|---|---|---|
| 1 — `sessions.ts` | medium | low | Mostly mechanical; JSON shapes already validated |
| 2 — `sessionHandler.ts` resume branch | trivial | low | One-line dispatcher |
| 3 — cost/token capture in adapter | low | medium | Live-capture risk from Risk #1 |
| 4 — UI fixes | trivial | none | 2 lines total |
| 5 — `SessionSource` interface cleanup | medium | low | Pure refactor, do last |
| 6 — docs note | trivial | none | 1 paragraph in `web/CLAUDE.md` |

No phase requires touching the frontend React components meaningfully — the `useCodeSession` hook and `ChatSessionList` already render `cliSessions` generically.

---

## Recommendation

Implement in order Phase 1 → Phase 2 → Phase 4 → Phase 3 → Phase 6 → Phase 5. That order gets you a working OpenCode session list + resume flow first (which is the visible user pain), then cosmetics, then the cost plumbing that has open questions, then the documentation, then the optional refactor.

Phase 3 can be deferred entirely if cost tracking isn't a priority — the UI already gracefully handles null cost.

Before any of that: **run an actual `opencode run` against a configured account** to capture the live NDJSON stream, so Phase 3's open question is resolved before we plan against it.
