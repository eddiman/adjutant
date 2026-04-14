# 2026-04-09 — Chat/Code Session bug audit & fix plan

Scope: `web/app/src/components/CodeSession/`, `web/app/src/hooks/useCodeSession.ts`, `web/api/src/routes/sessions.ts`, `web/app/vite.config.ts`.

## Reported symptoms

1. Sessions intermittently don't load.
2. In Safari PWA (installed from `:3021`), **no sessions load at all**, including when creating a new session from Home.
3. Clicking the "New" button next to a workspace accordion creates the session on the backend but navigates the user to a **different** (most recent) session.
4. Sub-agent sessions the orchestrator spawns into KB cwds never show up in the session list.

## Root causes

### Bug A — Stale `activeSession` on new-session redirect
`CodeSession.tsx:59-67` navigates to `/chat/${activeSession.id}` the moment `pendingRedirect` becomes true, but `createSession` (`useCodeSession.ts:239-244`) never clears `activeSession`. If the user had previously opened a session and returned to `/chat`, `activeSession` still holds the old session — so the redirect effect fires immediately with the *old* id before the new `session.created` message arrives. The new session is created on the backend (visible in the list), but the user lands on the previous one.

### Bug B — Safari PWA session loading
Four compounding issues:

1. **Silent `Promise.all` failure** (`SessionList.tsx:323-343`): three parallel fetches combined with `.catch(() => {})`. If any single endpoint fails, all state stays empty, `loading` flips to false, and nothing is displayed or logged.
2. **Self-signed HTTPS in dev** (`vite.config.ts:7` — `@vitejs/plugin-basic-ssl`). Safari PWA in standalone mode is stricter than regular Safari about self-signed certs. `wss://` and `https://` requests can silently fail in the installed PWA even when they work in the browser that installed it. This is the single largest PWA-breakage cause.
3. **No reconnect on PWA wake**: `useCodeSession` only reconnects via `ws.onclose` backoff. When iOS suspends the PWA, `onclose` may not fire; on resume the list is stale and the WS is dead.
4. **`sessionStorage` for Home → chat handoff** (`CodeSession.tsx:72, 85`): Safari PWA can clear `sessionStorage` on relaunch, silently dropping the pending cwd/message from Home.

### Bug C — Lossy cwd decoding drops sub-agent KB sessions
`sessions.ts:30-52`:

```ts
function decodeCwdFromDirName(dirName: string): string {
  return dirName.replace(/^-/, '/').replace(/-/g, '/');
}
```

Claude CLI encodes `/` **and** `_` (and preserves existing `-`) all as `-`, so the decoding is lossy. Example (verified):

```
encoded dir → /Volumes/Mandalor/JottaSync/AI/knowledge/bases/munich/summer2026
actual cwd  → /Volumes/Mandalor/JottaSync/AI_knowledge_bases/munich-summer2026
```

The real cwd is already stored inside each JSONL record (`cwd:` field on `user`/`assistant` records) — we just aren't reading it. Because the decoded path doesn't match any KB path, `groupSessions` (`SessionList.tsx:282-288`) can't attach the CLI sessions to any KB. Then the orphan bucket at `SessionList.tsx:300` **only includes web sessions, not CLI sessions** — so unmatched CLI sessions are dropped from the UI entirely.

### Bug D — No refresh of session list after creation/sub-agent writes
`ChatSessionList` (`SessionList.tsx:323-343`) only fetches on mount. Even after the decoder is fixed, new sub-agent sessions written to `~/.claude/projects/` while the UI is open won't appear until a manual reload.

---

## Fix plan

| # | Bug | File(s) | Approach |
|---|-----|---------|----------|
| 1 | A | `useCodeSession.ts` | `createSession()` clears `activeSession` so the redirect effect waits for the new `session.created` payload. |
| 2 | B.1 | `SessionList.tsx` | Split `Promise.all` into independent fetches with per-call error state. Surface errors in an inline banner. |
| 3 | B.2 | `vite.config.ts` | Make `basicSsl()` opt-in via `VITE_HTTPS=1`. Default to HTTP so Safari PWA stops failing on self-signed wss/https. |
| 4 | B.3 | `useCodeSession.ts` | On `visibilitychange → visible` or `online`, force a reconnect (reset backoff counter and call `connect()`). |
| 5 | B.4 | `CodeSession.tsx` | Swap `sessionStorage` → `localStorage` for `adjutant-pending-cwd` / `adjutant-pending-message` (single-shot, removed on read). |
| 6 | C | `web/api/src/routes/sessions.ts` | Extract real `cwd` from first JSONL record that carries it; fall back to lossy decode. Skip sidechain records when picking preview text. |
| 7 | C | `SessionList.tsx` | Include unmatched `cliSessions` in the "Other" orphan bucket so nothing is silently dropped. |
| 8 | D | `CodeSession.tsx` + `SessionList.tsx` | Bump `listRefreshKey` after `session.created`. Add `visibilitychange` + `focus` refetch inside `ChatSessionList`. |

Assumptions locked in during implementation:
- ~~HTTPS default OFF in dev (opt-in via `VITE_HTTPS=1`). Easy to revert.~~ **Reversed mid-implementation** — user needs HTTPS for the iOS clipboard API (which requires a secure context). Fix 3 was skipped; the Safari PWA loading issue is addressed by Fixes 2, 4, and 5 instead.
- Unmatched CLI sessions land in the existing "Other" bucket.
- Refresh is visibility/focus only — no interval polling.

---

## Implementation log

Status is updated after each fix is actually applied.

### Fix 1 — `createSession` clears active session
**Status:** ✅ Done
**File:** `web/app/src/hooks/useCodeSession.ts`
**Change:** Added `setActiveSession(null)` at the top of `createSession()` with a comment explaining why. The `pendingRedirect` effect in `CodeSession.tsx:62-67` now has no `activeSession` to navigate to when the button is clicked, so it blocks until the backend's `session.created` arrives and sets the *new* session. Eliminates the race where the old session id was being used.

### Fix 2 — Independent session-list fetches with error surfacing
**Status:** ✅ Done
**Files:** `web/app/src/components/CodeSession/SessionList.tsx`, `SessionList.module.css`
**Change:** Replaced the `Promise.all` + swallowed `catch` with a `loadData()` function inside `ChatSessionList` that awaits `/api/sessions`, `/api/kbs`, and `/api/adjutant/status` independently. Each fetch has its own try/catch; failures are collected into a new `errors: string[]` state (best-effort `/api/adjutant/status` stays silent). The sessions endpoint no longer blocks the others — one failure doesn't blank out the list. Added `.errorBanner`, `.errorBannerBody`, `.errorBannerTitle`, `.errorBannerDismiss` classes to the CSS module and render a dismissible banner above the list (and as a sibling when the empty state is shown) so Safari PWA failures are visible instead of silent. Also introduced a 2-second debounce ref (`lastLoadRef`) reused by Fix 8.

### Fix 3 — Vite HTTPS opt-in  —  **SKIPPED**
**Reason:** User needs HTTPS to keep the iOS Clipboard API (`navigator.clipboard`) working, which requires a secure context. Reversing `basicSsl()` would break that capability. The Safari PWA loading issue is addressed by Fix 2 (stop swallowing errors), Fix 4 (reconnect on PWA wake), and Fix 5 (localStorage for Home handoff) instead — all of which target root causes that would have been hidden behind the HTTPS switch.

### Fix 4 — Reconnect on visibility/online
**Status:** ✅ Done
**File:** `web/app/src/hooks/useCodeSession.ts`
**Change:** Added a new `useEffect` that registers `visibilitychange`, `focus`, and `online` listeners. On each event it bails if the tab isn't visible or the WS is already `OPEN`; otherwise it clears any pending reconnect timeout, resets `reconnectAttemptRef` to 0 (so we don't stack backoff delays after a long suspend), closes any stale socket in CONNECTING/CLOSING state, and calls `connect()` directly. iOS Safari PWA suspension doesn't reliably fire `ws.onclose`, so the pure `onclose`-driven exponential backoff wasn't enough — this gives an immediate deterministic reconnect on wake. Also widened `reconnectTimeoutRef`'s type to `ReturnType<typeof setTimeout> | undefined` so we can explicitly clear it (which also dropped a pre-existing TS error).

### Fix 5 — Home handoff via localStorage
**Status:** ✅ Done
**Files:** `web/app/src/components/CodeSession/CodeSession.tsx`, `web/app/src/components/Home/Home.tsx`
**Change:** `adjutant-pending-cwd` and `adjutant-pending-message` now use `localStorage` instead of `sessionStorage`. Both values are still read-and-removed on the chat side (`CodeSession.tsx:72-91`), so they stay single-shot, but they now survive Safari PWA relaunches that wipe `sessionStorage`. Updated the two setters in `Home.tsx:41, 51` to match. Comments added at both sides explaining *why* we chose localStorage.

### Fix 6 — Real cwd extraction from JSONL
**Status:** ✅ Done
**Files:** `web/api/src/routes/sessions.ts`, `web/api/src/routes/routes.test.ts`
**Change:** `scanClaudeCliSessions` now scans the first 20 lines of each JSONL and captures the first record that carries a `cwd` string field, using it as the authoritative cwd for the session summary. `decodeCwdFromDirName` is kept only as a fallback and gained a doc comment explaining the encoding is lossy (dashes/underscores cannot be distinguished). Also skips `isSidechain: true` records when selecting the first-user preview text, so a sub-agent's first prompt doesn't clobber the parent session's name. Added two new tests in `routes.test.ts`:
  1. Writes `-Volumes-Mandalor-knowledge-bases-my-kb/<uuid>.jsonl` with a real cwd of `/Volumes/Mandalor/knowledge_bases/my-kb` (underscore + dash combo the old decoder couldn't handle), hits `GET /api/sessions`, and asserts the returned `cwd` matches the real path.
  2. Writes a JSONL whose first user record is `isSidechain: true` with text "SIDECHAIN PROMPT" followed by a real user record; asserts the returned session name is "Real parent prompt", not the sidechain text.
  Both tests pass. Full API test suite still green (96/96).

### Fix 7 — Unmatched CLI sessions surface in "Other"
**Status:** ✅ Done
**File:** `web/app/src/components/CodeSession/SessionList.tsx`
**Change:** `groupSessions` now also returns `cliOrphans: CliSessionSummary[]` — CLI sessions that didn't match any KB, custom folder, or the adjutant dir. `ChatSessionList` renders `cliOrphans` inside the existing "Other" `FolderGroup` alongside the web orphans (previously the "Other" group only received web orphans and CLI orphans were silently dropped). The empty-state check and the Other-group visibility check now both consider `cliOrphans.length > 0`. With Fix 6 in place, most CLI sessions should now land in their correct KB; this is the safety net for anything that still doesn't match.

### Fix 12 — Remove 50-limit & scan sub-agent directories  (follow-up)
**Status:** ✅ Done
**Files:** `web/api/src/routes/sessions.ts`, `web/api/src/routes/routes.test.ts`
**Reported symptom:** "I know for a fact `/Users` has sessions used in Claude CLI, why are these not showing up?"
**Root causes (two independent bugs):**
  1. **Hard limit of 50** — `scanClaudeCliSessions(limit = 50)` sliced to the 50 most recent sessions. The filesystem has **246 top-level sessions** (100 adjutant, 47 portfolio-kb, 29 hopen, 24 ixda, 18 fagkomite, 16 smaabruksbryggeri, 5 munich, 3 home-dir, 2 adjutant-web, 1 ixda-svg, 1 fb-log-chat-viewer). Everything older than ~24 hours was truncated out, including all 3 home-dir sessions from March 22-26.
  2. **Nested sub-agent logs were completely invisible.** Claude CLI writes sub-agent session logs at `~/.claude/projects/<encoded-cwd>/<parent-session-id>/subagents/agent-<hash>.jsonl` with a sibling `agent-<hash>.meta.json` carrying the agentType and description. I found **89 such files** on disk (Explore/Plan/general-purpose agents spawned by various parent sessions). The old scan only listed top-level `.jsonl` files per project dir and never recursed. This was also what the user asked for earlier with *"I need the session from the kbs that the sub agents spawen when talking to it from the main orchestrator"*.
**Change:** Refactored `scanClaudeCliSessions` into three helpers:
  - `extractUserText(content)` — handles both string and array-of-blocks content shapes (consolidates Fix 11's logic).
  - `scanSessionFile(filePath, sessionId, fallbackCwd, overrideName?)` — reads one JSONL file, extracts cwd/model/timestamp/msgCount, picks a title. Also tracks a `sidechainUserText` as a **second-pass fallback** so sub-agent-only files (every record sidechain by design) still get a title instead of "Untitled session".
  - `readSubagentMeta(jsonlPath)` — reads the sibling `agent-<hash>.meta.json` and returns `"<agentType> · <description>"` (max 80 chars), or null if missing/unparseable.

  `scanClaudeCliSessions` now:
  - Iterates every project dir's top-level `.jsonl` files (as before) and calls `scanSessionFile`.
  - **Recurses one level deeper**: for each `<parent-uuid>/subagents/` subdirectory, reads every `agent-*.jsonl` and calls `scanSessionFile` with the meta.json title as `overrideName`. The sub-agent's cwd comes from the JSONL record itself (the parent's cwd).
  - Bumped the default `limit` from **50 → 500** as a safety ceiling (we still cap in case of pathological histories, but 500 comfortably fits months of typical activity).
**Tests:** Added two new tests in `routes.test.ts`:
  1. Writes a nested sub-agent JSONL under `<cwd>/<parent-uuid>/subagents/agent-<hash>.jsonl` plus a sibling meta.json with `{agentType: 'claude-code-guide', description: 'Remote session clearing'}`; asserts the returned session has `name === 'claude-code-guide · Remote session clearing'`.
  2. Same nested structure but with **no meta.json** — asserts the name falls back to the sidechain user record's text (`'Analyze the production logs'`), not "Untitled session".
**Verification:** 99/99 API tests pass (two new). Live check against the running API:
```
returned: 335 (was 50)
newest: 2026-04-09T19:46:32Z   oldest: 2026-03-22T17:11:29Z   (matches filesystem)
home dir (/Users/edvardpiresbjorgen) sessions: 7   (was 0)
  2026-03-26  <local-command-caveat>Caveat: The messages below were generated…
  2026-03-23  claudecodecli
  2026-03-22  Explore · Map adjutant codebase structure
  2026-03-22  claude-code-guide · Remote session resume after restart
  2026-03-22  claude-code-guide · Remote session clearing and flags
sub-agent sessions: 89
  Explore · Explore chat module codepaths
  Explore · Explore portfolio KB codebase
  Plan · Plan portfolio screener module
  general-purpose · Migrate modals to Modal component
  general-purpose · Migrate dashboard cards to Card
```
The home-dir sessions and all sub-agent sessions are now visible and properly titled.

### Fix 11 — CLI session titles (handle string content)  (follow-up)
**Status:** ✅ Done
**Files:** `web/api/src/routes/sessions.ts`, `web/api/src/routes/routes.test.ts`
**Reported symptom:** Every CLI session in the list showed as "Untitled session".
**Root cause:** The scan in `scanClaudeCliSessions` only handled `user.message.content` when it was an `Array` of content blocks. In practice Claude CLI commonly writes user content as a plain **string** (I verified by dumping the first user record of a fagkomite JSONL — its `content` is a string starting with `"Apply the following updates as of 2026-03-27:\n\n1. Conference guidelines:…"`). String-content records fell through both branches, so `firstUserText` stayed empty and every session was named "Untitled session". Note: `readCliSessionMessages` already handled both forms (that's why full history loads correctly when you resume), the bug was only in the title scan.
**Change:** Extract text from either shape — `typeof content === 'string'` → use directly; `Array.isArray(content)` → find first `{type:'text'}` block and use its `.text`. Collapse runs of whitespace (`\s+` → single space) and trim before slicing to 80 chars, so multi-line prompts show as clean single-line previews.
**Test:** Added a new routes test that writes a JSONL with string-content and asserts the session name is the collapsed preview (`'Apply the following updates: 1. Do a thing'`, not the raw string with newlines).
**Verification:** 97/97 API tests pass (one new test added). Live check against the running API: 50 CLI sessions returned, **0 untitled**, titles like `"in /web the dashboard needs to be visually aligned..."`, `"Current status of Munich Airbnb Jul 16-20 host approval?..."`, etc.

### Fix 10 — Loosen KB registry filter (kb.yaml no longer required)  (follow-up to Fix 9)
**Status:** ✅ Done
**File:** `web/api/src/services/registryService.ts`
**Reported symptom:** Even after Fix 9, `fagkomite` was showing up as an *auto-discovered* accordion (labelled from its path basename) instead of a proper KB accordion with the registered name/description. User asked "is it registered in the yaml?" — it was.
**Root cause:** `registryService.list()` had a **second gate** at line 123 that silently dropped any entry whose path didn't contain a `kb.yaml` file. `fagkomite` is fully registered in `knowledge_bases/registry.yaml` (with name, description, path, model, access, created) and the adjutant daemon happily queries it (confirmed via `/api/adjutant/status` — its heartbeat `kbs_checked` list includes fagkomite), but the directory itself has no `kb.yaml`. The web API was being stricter than the rest of the system.
**Change:** Replaced the `fs.access('kb.yaml')` check with a `fs.stat(entry.path)` directory check. An entry is now included if the registry lists it AND the path is an existing directory. This matches the daemon's behaviour and restores parity with the rest of adjutant. Comment added explaining *why* we don't require kb.yaml.
**Verification:** `npm run test` still passes 96/96. Live check: `GET /api/kbs` went from **5 → 6** KBs, with `fagkomite` now in the list.
**Effect:** fagkomite now appears as its proper named KB accordion with its registry description; Fix 9's auto-discovery pass no longer has any reason to pick it up (its sessions are claimed by the KB group before the discovery pass runs).

### Fix 9 — Auto-discover workspaces from session cwds  (follow-up)
**Status:** ✅ Done
**File:** `web/app/src/components/CodeSession/SessionList.tsx`
**Reported symptom:** "fagkomite KB is missing" — the `fagkomite` directory on disk at `/Volumes/Mandalor/JottaSync/AI_knowledge_bases/fagkomite` has a bunch of Claude CLI sessions in it, but it's **not registered** in the adjutant KB registry (the registry has 5 KBs: hopen, ixda, munich-summer2026, portfolio, smaabruksbryggeri). So its sessions had no KB to land in and fell into the ugly "Other" bucket. Same problem would hit any unregistered workspace, and any custom folder add wouldn't retroactively rescue them in a sensible way.
**Change:**
- `groupSessions` no longer returns orphan lists. Instead, after processing explicit groups (adjutant dir → KBs → custom folders), it walks any still-unclaimed sessions (web or CLI), groups them by exact `cwd` into a new `discoveredByCwd: Map<string, FolderEntry>`, and pushes those entries onto `groups` sorted alphabetically by label. Each auto-discovered entry gets `icon: 'folder'`, `label: pathLabel(cwd)`, and a new `discovered: true` flag.
- `FolderEntry` gained `discovered: boolean` so the UI can distinguish auto-discovered from user-added custom folders.
- `ChatSessionList` render no longer has an "Other" accordion — every session lands in *some* group. The remove button is suppressed for `g.isKb || g.discovered` (auto-discovered groups are not user-removable because they're derived from sessions on disk). The empty-state check now just tests `groups.length === 0`.
- Custom-folder "Add workspace" flow is unaffected: manually-added folders still take precedence over auto-discovered groups because custom folders run first in `groupSessions`, so a custom folder at the same path claims those sessions before the auto-discovery pass runs. No duplicates.
**Effect:** fagkomite sessions now appear under their own "fagkomite" accordion automatically, without the user having to touch anything. Any future sub-agent sessions written into an unregistered KB dir do the same. "Add workspace" still works for pinning dirs that don't yet have sessions.
**Verification:** `npx tsc -b` (5 pre-existing errors, none new), `npx eslint SessionList.tsx` (1 pre-existing `react-refresh/only-export-components` warning on `addCustomFolder`, none new), `npx vite build` (clean build).

### Fix 8 — Session list auto-refresh
**Status:** ✅ Done
**Files:** `web/app/src/components/CodeSession/SessionList.tsx`, `web/app/src/components/CodeSession/CodeSession.tsx`
**Change:**
- `ChatSessionList` registers `visibilitychange` and `focus` listeners that call `loadData()` when the tab/PWA returns to the foreground. `loadData` is debounced via `lastLoadRef` (2 s minimum between calls) to avoid hammering the API on rapid focus flips in a mobile browser.
- `CodeSession.tsx`'s `pendingRedirect` effect now bumps `listRefreshKey` whenever a new `activeSession` arrives, so navigating back to `/chat` after creating a session shows a fresh list without a manual reload.
Combined with Fix 6, sub-agent sessions the orchestrator spawns while the user is chatting now appear in the correct KB accordion as soon as the user returns to the list view.

Combined with Fix 6, sub-agent sessions written by the orchestrator now appear without requiring a full page reload.

---

## Verification checklist

- [x] `web/api` — `npm run build` passes (tsup + dts, no errors).
- [x] `web/api` — `npm run test` passes: **96/96 tests** green, including the two new CLI-discovery tests for lossy-path cwd and sidechain filtering.
- [x] `web/app` — `npx tsc -b` error count went from **6 → 5**; no new TypeScript errors introduced (actually removed one pre-existing `useRef` generic error as a side effect of Fix 4's type widening).
- [x] `web/app` — ESLint error count on touched files went from **6 → 5**; no new lint errors introduced. All 5 remaining errors are pre-existing project-wide rule violations on lines I did not author.
- [ ] Manual (user): from `/chat`, open session X, hit Back, click "New" on a different workspace → URL becomes the new session's id, not X.
- [ ] Manual (user): Install as PWA from Safari on the HTTPS dev URL → on cold launch, `/chat` shows sessions; when a subfetch fails, the red error banner appears instead of a blank list.
- [ ] Manual (user): In an orchestrator chat, spawn a sub-agent that targets a KB → after focus returns to `/chat`, the new CLI session appears under that KB's accordion (or falls into "Other" if the sub-agent spawned in an unexpected cwd).
- [ ] Manual (user): Background the PWA for > 30 s, foreground it → connection banner briefly shows "Reconnecting…" then disappears; sending a message works immediately without a page reload.
- [ ] Manual (user): iOS Clipboard API still works (HTTPS preserved).
