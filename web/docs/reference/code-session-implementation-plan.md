# Interactive Code Session Module — Implementation Record

## Context

Adjutant web currently serves as a visual knowledge base explorer. The user wants to add an interactive code session module — a chat-based coding assistant interface embedded in the web app. This must support both Claude Code CLI and OpenCode CLI backends, stream responses in real-time, support session management, and feature a terminal-style dark UI. A global dark mode theme should also be added across all of adjutant web.

The original plan (`web/docs/reference/code-session-module-plan.md`) has the right high-level structure but contains **21 pitfalls** ranging from incorrect CLI invocation formats, missing error states, route conflicts, to security gaps. This revision addresses all of them.

---

## Critical Corrections to Original Plan

| # | Pitfall | Original Plan Claim | Correction |
|---|---------|---------------------|------------|
| 1 | **Claude CLI stream-json** | "NDJSON parsing" (no event type details) | Must parse `content_block_delta` for text, `result` for metadata. Project's own docs (`backend-migration-log.md:51`) say stream-json isn't supported yet — need fallback to `json` mode |
| 2 | **OpenCode NDJSON format** | Conflated with Claude's format | Completely different: `type:"text"` with `part.text` vs Claude's `content_block_delta` |
| 3 | **Binary not found** | Not addressed | Return `BACKEND_NOT_FOUND` error; UI shows install instructions |
| 4 | **Process lifecycle** | Not addressed | Timeout, malformed-line skipping, tree-kill on WS disconnect |
| 5 | **OpenCode orphans** | Not addressed | PID snapshot before/after via `pgrep`, kill new language-server PIDs (matches Python pattern in `opencode.py:63-73`) |
| 6 | **Permission mode** | Not addressed | Read `llm.permission_mode` from adjutant.yaml; use `--dangerously-skip-permissions` or `--allowedTools` |
| 7 | **Cost tracking** | Not addressed | `costUsd: null` for OpenCode; UI conditionally renders cost |
| 8 | **Model ID translation** | Not addressed | Claude CLI uses aliases (haiku/sonnet/opus); OpenCode uses full IDs. Adapter translates per `_ALIASES` map in `backend_claude_cli.py:27-35` |
| 9 | **WebSocket auth** | "handles auth" (no details) | Auth during HTTP `upgrade` event via query param token, BEFORE connection established |
| 10 | **WS reconnection** | Phase 5 polish item | Kill process on disconnect; client reconnects and resumes via CLI `--resume` |
| 11 | **Concurrent sessions** | Not addressed | Cap at 3 active processes; return `CONCURRENCY_LIMIT` error |
| 12 | **Message ordering** | Not addressed | TCP guarantees order; no sequence numbers needed |
| 13 | **Route conflict** | `/code` route | `/code` would be matched by `/:kb` as `kb="code"`. Use `/session` instead |
| 14 | **Theme scope** | Dark mode = code session aesthetic | Code session uses OWN scoped CSS variables (always dark); global dark theme is independent |
| 15 | **Shiki bundle** | Phase 3 with lazy load | Defer to Phase 5. Use plain `<pre>` with CSS in v1 |
| 16 | **Input handling** | Not addressed | `<textarea>` with Enter/Shift+Enter, Up for history, Escape close palette |
| 17 | **Markdown rendering** | "parses markdown" (no library) | Use `react-markdown` + `remark-gfm` (lightweight). NOT TipTap (which is a full editor) |
| 18 | **In-memory sessions** | Not addressed | Acceptable for v1; CLI sessions persist on disk via `--resume`/`--session` |
| 19 | **CWD for CLI** | Not specified | Claude CLI: `spawn({cwd})`. OpenCode: `--dir <path>` flag AND `spawn({cwd})`. Validate via `explorerService.isPathAllowed()` |
| 20 | **Concurrent YAML reads** | Not addressed | Read-only, cached at startup. No race with Python backend |
| 21 | **Port conflicts** | Not addressed | No conflict — code session uses CLI subprocess mode (`claude -p`, `opencode run`), NOT web server mode |

---

## Phase 1: Dark Mode Across All Adjutant Web

### 1.1 Extend Theme type
**File: `web/app/src/types/index.ts`**
```typescript
type Theme = 'default' | 'bauhaus' | 'dark';
```

### 1.2 Add dark palette
**File: `web/app/src/index.css`** — Add `[data-theme="dark"]` block after bauhaus:
- `--color-bg: #111118`, `--color-card: #1a1b26`, `--color-text: #c8c8d0`
- `--color-text-secondary: #8888a0`, `--color-border: #2a2b3d`
- `--color-primary: #7c8cf5`, `--color-hover-bg: #222233`
- Keep shadows and radius from default theme (not flat like bauhaus)

### 1.3 Add dark option to settings
**File: `web/app/src/components/SettingsDialog/SettingsDialog.tsx`** — Add `<option value="dark">Dark</option>`

### Why separate
Dark mode is global and independent. The code session component has its OWN scoped dark palette via CSS Module variables (always dark regardless of global theme).

---

## Phase 2: Backend Infrastructure

### 2.1 Dependencies
**File: `web/api/package.json`** — Add `ws@^8.18.0`, `@types/ws@^8.5.10` (dev)

### 2.2 Types
**New: `web/api/src/types/session.ts`**

Key types:
- `CliBackendName = 'claude-cli' | 'opencode'`
- `CliBackendInfo { name, binary, permissionMode?, models: { cheap, medium, expensive } }`
- `CodeSession { id, cliSessionId, backend, cwd, model, messages, createdAt, lastActiveAt, totalCostUsd }`
- `ChatMessage { id, role, content, timestamp, model?, durationMs?, costUsd?, inputTokens?, outputTokens?, error? }`
- `WsClientMessage` — Zod-validated discriminated union: `session.create`, `session.resume`, `session.list`, `message.send`, `message.cancel`
- `WsServerMessage` — tagged union: `session.created`, `session.resumed`, `session.list`, `message.delta`, `message.complete`, `message.error`, `backend.info`, `error`
- `NormalizedStreamEvent` — internal adapter output: `text_delta`, `complete`, `error`

### 2.3 Backend Detector
**New: `web/api/src/services/backendDetector.ts`**

- Reads `adjutant.yaml` from `registryService.resolveAdjutantDir()` (reuse existing service)
- Extracts `llm.backend` (`"claude-cli"` | `"opencode"`)
- Extracts `llm.models` map and `llm.permission_mode`
- Binary discovery: Claude CLI checks `CLAUDE_CODE_BIN` env then `which claude`; OpenCode checks `OPENCODE_BIN` env then `which opencode` (mirrors `backend_claude_cli.py:75-87` and `opencode.py:42-60`)
- Returns `CliBackendInfo | null` (null = not configured / binary not found)
- **Cached** on first call; stale reads acceptable (Pitfall #20)

### 2.4 CLI Adapter (MOST CRITICAL FILE)
**New: `web/api/src/services/cliAdapter.ts`**

Interface:
```typescript
interface RunHandle {
  cancel(): void;     // SIGINT → wait 2s → SIGTERM → wait 2s → SIGKILL
  promise: Promise<void>;
}

function runCli(params: {
  backend: CliBackendInfo;
  prompt: string;
  cwd: string;
  model?: string;
  cliSessionId?: string;
  onDelta: (text: string) => void;
  onComplete: (event: CompleteEvent) => void;
  onError: (event: ErrorEvent) => void;
}): RunHandle
```

#### Claude CLI Adapter

**Primary invocation (streaming):**
```
claude -p --output-format stream-json [--model <alias>] [--resume <sessionId>] --dangerously-skip-permissions "<prompt>"
```

**Fallback invocation (non-streaming, if stream-json unsupported):**
```
claude -p --output-format json [--model <alias>] [--resume <sessionId>] --dangerously-skip-permissions "<prompt>"
```

**stream-json NDJSON event parsing:**
- `{"type":"content_block_delta","delta":{"type":"text_delta","text":"..."}}` → call `onDelta(delta.text)`
- `{"type":"result","session_id":"...","cost_usd":...,"usage":{"input_tokens":N,"output_tokens":N},"duration_ms":N}` → call `onComplete`
- Tool use events (`content_block_start` with `type:"tool_use"`) → forward as formatted text delta: `\n> Using tool: ToolName\n`
- Skip all other event types (`system`, `assistant`, `content_block_start` for text, `content_block_stop`, `message_delta`, `message_stop`)
- Malformed lines: `console.warn` and skip (matches `ndjson.py:53-54`)

**json fallback parsing (if stream-json fails):**
- Single JSON response: `{ result, session_id, is_error, cost_usd, usage }` (matches `claude_json.py:5-12`)
- Send entire `result` as one `onDelta` call, then `onComplete`

**Permission mode (Pitfall #6):** Read from `backendInfo.permissionMode`:
- `"skip"` (default) → `--dangerously-skip-permissions`
- `"allowlist"` → `--allowedTools Read,Glob,Grep,Edit,Write,Bash(*)` (matches `backend_claude_cli.py:53-72`)

**Model translation (Pitfall #8):** Use alias map matching `_ALIASES` in `backend_claude_cli.py:27-35`:
```
anthropic/claude-haiku-4-5 → haiku
anthropic/claude-sonnet-4-6 → sonnet
anthropic/claude-opus-4-6 → opus
```

#### OpenCode Adapter

**Invocation:**
```
opencode run --dir <cwd> --format json [--model <modelId>] [--session <sessionId>] "<prompt>"
```

**NDJSON parsing (matches `ndjson.py:29-97`):**
- `{"type":"text","part":{"text":"..."}}` or `{"type":"text","part":"..."}` → call `onDelta(part.text || part)`
- `{"type":"session.create","properties":{"sessionID":"..."}}` → store session ID
- `{"type":"error","error":{"name":"...","data":{"message":"..."}}}` → call `onError` with classified error
- Top-level `sessionID` field on any event → store session ID (first one wins)
- On process exit: call `onComplete` with extracted session ID; `costUsd: null` (Pitfall #7)

**Orphan cleanup (Pitfall #5):** Replicate PID-snapshot pattern from `opencode.py:63-73`:
```typescript
// Before spawn: snapshot language-server PIDs via execSync('pgrep -f "bash-language-server|yaml-language-server"')
// After process exit: find new PIDs, SIGTERM then SIGKILL
```

#### Common Process Lifecycle (Pitfall #4)

- Spawn via `child_process.spawn()` with `{ cwd, stdio: ['pipe', 'pipe', 'pipe'] }`
- Read stdout line-by-line via `readline.createInterface({ input: proc.stdout })`
- **Cancel**: SIGINT → wait 2s → SIGTERM → wait 2s → SIGKILL
- **Timeout**: Default 5 minutes per message. Kill process after timeout.
- **WS disconnect**: `sessionHandler` calls `handle.cancel()` for all active processes on `ws.close`

### 2.5 Session Service
**New: `web/api/src/services/sessionService.ts`**

- In-memory `Map<string, CodeSession>` keyed by UUID v4
- Methods: `create()`, `get()`, `list()`, `delete()`, `addMessage()`, `updateCliSessionId()`
- **Concurrency cap (Pitfall #11)**: Track active `RunHandle`s in `Map<string, RunHandle>`. Max 3 concurrent. Return error for 4th.
- **Persistence (Pitfall #18)**: In-memory for v1. CLI sessions persist on disk — `--resume`/`--session` still work after server restart.

### 2.6 WebSocket Server
**New: `web/api/src/ws/index.ts`**

**Auth during upgrade (Pitfall #9):**
```typescript
server.on('upgrade', (request, socket, head) => {
  // Only handle /ws/code-session path
  // If SESSION_TOKEN is set, check ?token=xxx query param
  // Reject with 401 if token mismatch
  // Otherwise: wss.handleUpgrade(request, socket, head, callback)
});
```

Client connects with: `new WebSocket('ws://host/ws/code-session?token=xxx')`
If no token configured (dev mode): connects freely — mirrors REST auth behavior in `middleware/auth.ts:30-35`.

### 2.7 WebSocket Session Handler
**New: `web/api/src/ws/sessionHandler.ts`**

On connection open:
1. Detect backend via `backendDetector.detect()`
2. Send `backend.info` message (or `error` with code `BACKEND_NOT_FOUND` if null — Pitfall #3)

Message routing:
- `session.create` → validate `cwd` via `explorerService.isPathAllowed()` (reuse security logic), create in sessionService
- `message.send` → spawn CLI via adapter, pipe `onDelta`→`message.delta`, `onComplete`→`message.complete`
- `message.cancel` → call `RunHandle.cancel()`
- `session.resume` → look up session, send history
- `session.list` → return all sessions

On `ws.close`: cancel ALL active RunHandles for this connection (Pitfall #10)

### 2.8 REST Routes
**New: `web/api/src/routes/sessions.ts`**

- `GET /api/sessions` → list sessions
- `GET /api/sessions/:id` → get session
- `DELETE /api/sessions/:id` → delete session
- `GET /api/sessions/backend-info` → detect backend info

### 2.9 Server Modification
**File: `web/api/src/index.ts`**

Change `app.listen()` to `http.createServer(app)` + `attachWebSocket(server)`:
```typescript
import { createServer } from 'http';
import { attachWebSocket } from './ws/index.js';

// In start():
const server = createServer(app);
attachWebSocket(server);
server.listen(config.port, config.host, async () => { ... });
```

### 2.10 Vite WebSocket Proxy
**File: `web/app/vite.config.ts`**

Add BEFORE `/api` proxy:
```typescript
'/ws': {
  target: 'http://localhost:3020',
  ws: true,
  changeOrigin: true,
},
```

---

## Phase 3: Frontend Code Session Module

### 3.1 Dependencies
**File: `web/app/package.json`** — Add `react-markdown@^9.0.1`, `remark-gfm@^4.0.0`

NO Shiki in Phase 3 (Pitfall #15). Use plain `<pre><code>` with dark CSS.

### 3.2 Route Setup (Pitfall #13)
**File: `web/app/src/App.tsx`**

The current routing renders `<AppWithProviders />` for all routes. Follow the same pattern:

```tsx
const CodeSession = lazy(() => import('./components/CodeSession/CodeSession'));

// In App():
<Route path="/session" element={<AppWithProviders />} />  // BEFORE /:kb routes
```

In `AppContent()`:
```tsx
const isSessionPage = location.pathname === '/session';

// Render order: session → adjutant → canvas/home
{isSessionPage ? (
  <Suspense fallback={null}><CodeSession /></Suspense>
) : isAdjutantPage ? (
  <AdjutantDashboard ... />
) : (
  <main ...>...</main>
)}
```

React Router v7 ranks static routes above dynamic — `/session` wins over `/:kb`.

### 3.3 WebSocket Hook
**New: `web/app/src/hooks/useCodeSession.ts`**

State:
```typescript
{
  connected: boolean;
  backendInfo: CliBackendInfo | null;
  backendError: string | null;
  activeSession: CodeSession | null;
  messages: ChatMessage[];
  streamingContent: string;
  isStreaming: boolean;
  error: string | null;
}
```

Features:
- WebSocket lifecycle with exponential backoff reconnection (1s, 2s, 4s, 8s, max 30s)
- Token from auth context (or none if auth disabled)
- Streaming accumulation: `message.delta` appends to `streamingContent`; `message.complete` moves to `messages[]`
- Methods: `createSession(cwd, model?)`, `resumeSession(id)`, `sendMessage(content)`, `cancelMessage()`, `clearMessages()`

### 3.4 Slash Commands Hook
**New: `web/app/src/hooks/useSlashCommands.ts`**

Commands: `/help`, `/clear`, `/sessions`, `/browse`, `/model`, `/cost`, `/new`
- Provides `filteredCommands(prefix)`, keyboard nav state, `selectCurrent()`

### 3.5 Component Tree
**New directory: `web/app/src/components/CodeSession/`**

| File | Purpose |
|------|---------|
| `CodeSession.tsx` | Full-page layout: header + message list + input + status bar |
| `CodeSession.module.css` | **Scoped dark palette** (Pitfall #14): `--cs-bg: #111118`, `--cs-accent: #7c5cbf`, etc. Always dark. |
| `MessageList.tsx` | Scrollable container, auto-scroll on new content |
| `MessageBubble.tsx` | User: purple accent bar. Assistant: `react-markdown` + `remark-gfm`. Metadata footer (model, duration, cost if available). |
| `MessageBubble.module.css` | Message styling |
| `InputArea.tsx` | `<textarea>` with auto-resize. Enter=send, Shift+Enter=newline, Up=fill last message, Escape=close palette (Pitfall #16). Disabled during streaming with cancel button. |
| `InputArea.module.css` | Input styling |
| `SessionHeader.tsx` | Session name, model selector, cost total |
| `StatusBar.tsx` | CWD path, backend indicator, connection status |
| `SlashCommandPalette.tsx` | Popup above input when "/" typed, keyboard nav |
| `SlashCommandPalette.module.css` | Palette styling |
| `index.ts` | Barrel export |

### 3.6 Sidebar Navigation
**File: `web/app/src/components/Sidebar/Sidebar.tsx`**

Add "Code" link between "Adjutant" and KB list with terminal icon (`>_`). Links to `/session`.

### 3.7 Cost Display (Pitfall #7)
MessageBubble conditionally renders cost:
```tsx
{message.costUsd != null && <span>${message.costUsd.toFixed(4)}</span>}
```
OpenCode messages simply don't show cost. SessionHeader shows total cost only when backend is `claude-cli`.

---

## Phase 4: Session Management + Working Directory

### 4.1 Session List
**New: `web/app/src/components/CodeSession/SessionList.tsx`**
- Modal listing past sessions: timestamp, message count, backend, last message preview
- Click to resume, delete button
- Triggered by `/sessions` slash command or SessionHeader button

### 4.2 Working Directory Picker
**New: `web/app/src/components/CodeSession/WorkingDirPicker.tsx`**

**Reuses** existing `FolderExplorer` component (`web/app/src/components/FolderExplorer/FolderExplorer.tsx`) and `useExplorer` hook. The existing component already has breadcrumbs, root shortcuts, directory listing, and security.

Wrap as thin adapter that:
- Changes title to "Select Working Directory"
- Removes KB validation UI (the "N KBs found" indicator)
- Returns selected path for session creation

CWD is passed to CLI via `spawn({ cwd })` option + OpenCode's `--dir` flag (Pitfall #19).

### 4.3 Model Picker
**New: `web/app/src/components/CodeSession/ModelPicker.tsx`**

Reads model tiers from `backendInfo.models` (cheap/medium/expensive from adjutant.yaml). Simple dropdown. Applied to next message via `--model` flag.

---

## Phase 5: Polish

### 5.1 Shiki Syntax Highlighting
- Add `shiki` to app dependencies, use `shiki/bundle/web` for smaller bundle
- Add Vite manual chunk: `'shiki': ['shiki']`
- `CodeBlock.tsx`: lazy-init highlighter on first render, show plain `<pre>` until ready
- Theme: `tokyo-night` or `one-dark-pro`
- Grammars: typescript, javascript, python, bash, json, yaml, css, html, go, rust

### 5.2 Reconnection UI
Banner: "Connection lost. Reconnecting..." with spinner. Auto-reconnect via hook. Brief "Reconnected" on success.

### 5.3 Keyboard Shortcuts
`Ctrl+L` clear, `Ctrl+C` cancel (streaming), `Up` last message, `Escape` close palette, `Ctrl+N` new session

### 5.4 Error Boundary
Wrap `<CodeSession>` in existing `<ErrorBoundary>` component.

### 5.5 Claude CLI stream-json Fallback
**Risk (Pitfall #1):** Project's own docs (`backend-migration-log.md:51`) say `stream-json` may not be supported. Implementation strategy:
1. First message attempt uses `--output-format stream-json`
2. If process exits with error and stderr contains "unknown format" or similar → set flag `streamingSupported = false`
3. Subsequent messages use `--output-format json` (single response, no streaming)
4. Log warning on fallback

---

## File Creation Order

**Phase 1** (3 files modified):
1. `web/app/src/types/index.ts`
2. `web/app/src/index.css`
3. `web/app/src/components/SettingsDialog/SettingsDialog.tsx`

**Phase 2** (7 new, 2 modified):
1. `web/api/src/types/session.ts`
2. `web/api/src/services/backendDetector.ts`
3. `web/api/src/services/cliAdapter.ts`
4. `web/api/src/services/sessionService.ts`
5. `web/api/src/ws/index.ts`
6. `web/api/src/ws/sessionHandler.ts`
7. `web/api/src/routes/sessions.ts`
8. `web/api/src/index.ts` (modify: `http.createServer` + WS attach)
9. `web/app/vite.config.ts` (modify: `/ws` proxy)

**Phase 3** (12 new, 2 modified):
1. `web/app/src/hooks/useCodeSession.ts`
2. `web/app/src/hooks/useSlashCommands.ts`
3. `web/app/src/components/CodeSession/CodeSession.tsx`
4. `web/app/src/components/CodeSession/CodeSession.module.css`
5. `web/app/src/components/CodeSession/MessageList.tsx`
6. `web/app/src/components/CodeSession/MessageBubble.tsx`
7. `web/app/src/components/CodeSession/MessageBubble.module.css`
8. `web/app/src/components/CodeSession/InputArea.tsx`
9. `web/app/src/components/CodeSession/InputArea.module.css`
10. `web/app/src/components/CodeSession/SessionHeader.tsx`
11. `web/app/src/components/CodeSession/StatusBar.tsx`
12. `web/app/src/components/CodeSession/SlashCommandPalette.tsx`
13. `web/app/src/components/CodeSession/SlashCommandPalette.module.css`
14. `web/app/src/components/CodeSession/index.ts`
15. `web/app/src/App.tsx` (modify: add `/session` route + conditional render)
16. `web/app/src/components/Sidebar/Sidebar.tsx` (modify: add Code link)

**Phase 4** (3 new):
1. `web/app/src/components/CodeSession/SessionList.tsx`
2. `web/app/src/components/CodeSession/WorkingDirPicker.tsx`
3. `web/app/src/components/CodeSession/ModelPicker.tsx`

**Phase 5** (2 new, 1 modified):
1. `web/app/src/components/CodeSession/CodeBlock.tsx`
2. `web/app/vite.config.ts` (modify: shiki chunk)

---

## Key Reuse Points

| Existing Code | Reuse In |
|---------------|----------|
| `registryService.resolveAdjutantDir()` (`web/api/src/services/registryService.ts`) | backendDetector: find adjutant.yaml |
| `explorerService.isPathAllowed()` (`web/api/src/services/explorerService.ts`) | sessionHandler: validate CWD security |
| `FolderExplorer` component + `useExplorer` hook | WorkingDirPicker |
| `authenticate` middleware pattern (`web/api/src/middleware/auth.ts`) | WS upgrade auth (same token, same opt-in logic) |
| `data-theme` CSS variable system (`web/app/src/index.css`) | Dark mode theme |
| `ErrorBoundary` component | Wrap CodeSession |
| Model alias map (`backend_claude_cli.py:27-35`) | cliAdapter model translation |
| NDJSON parsing patterns (`lib/ndjson.py`, `lib/claude_json.py`) | cliAdapter response parsing |
| Orphan PID management (`opencode.py:63-73`) | cliAdapter OpenCode cleanup |

---

## Verification Plan

1. **Dark mode**: Toggle to dark in Settings → verify Home, Canvas, Dashboard render correctly
2. **Backend detection**: `GET /api/sessions/backend-info` → returns correct backend name and binary path
3. **Backend not found**: Remove CLI binary from PATH → verify error message in UI with install instructions
4. **WebSocket auth**: With `ADJUTANT_WEB_SESSION_TOKEN` set → verify WS rejects without token, accepts with token
5. **WebSocket (no auth)**: Without token env → verify WS connects freely
6. **Chat flow (Claude CLI)**: Navigate to `/session` → create session → send message → verify streaming response
7. **Chat flow (OpenCode)**: Switch backend in adjutant.yaml → restart API → verify OpenCode streaming works
8. **Cost display**: Claude CLI response shows cost; OpenCode response shows no cost
9. **Session resume**: Send message → note session ID → close browser → reopen → resume session → verify history
10. **Cancel**: Send long message → click cancel → verify process killed and UI shows "cancelled"
11. **Slash commands**: Type "/" → verify popup → select `/clear` → verify messages cleared
12. **Working directory**: Click browse → navigate → select directory → new session in that directory → verify CWD in status bar
13. **Concurrent limit**: Open 4 sessions → send messages → verify 4th returns concurrency error
14. **Reconnection**: Kill API server → verify disconnect banner → restart API → verify auto-reconnect
15. **Error handling**: Send message with invalid model → verify error message displayed
16. **Route conflict**: Create a KB named "session" → verify `/session` still goes to code session (not KB)

---

## Implementation Log

### Phase 1: Dark Mode — DONE

**Files modified:**
- `web/app/src/types/index.ts` — Added `'dark'` to Theme union type
- `web/app/src/index.css` — Added complete `[data-theme="dark"]` block (60+ CSS variables) after bauhaus theme: dark backgrounds (#111118), soft indigo primary (#7c8cf5), dark card (#1a1b26), adapted home gradients, shadows with higher opacity, Jost/Montserrat fonts matching default theme
- `web/app/src/components/SettingsDialog/SettingsDialog.tsx` — Added `<option value="dark">Dark</option>` to theme select

### Phase 2: Backend Infrastructure — DONE

**Dependencies added:** `ws@^8.18.0`, `@types/ws@^8.5.10` (dev)

**New files created:**
- `web/api/src/types/session.ts` — Full type system: `CliBackendName`, `CliBackendInfo`, `CodeSession`, `ChatMessage`, `WsClientMessage` (Zod-validated discriminated union), `WsServerMessage` (tagged union), `CompleteEvent`, `ErrorEvent`
- `web/api/src/services/backendDetector.ts` — Reads `adjutant.yaml` via `registryService.resolveAdjutantDir()`, extracts `llm.backend`/`llm.models`/`llm.permission_mode`, finds binary via env var then `which`. Cached results.
- `web/api/src/services/cliAdapter.ts` — **Most critical file.** Spawns CLI subprocesses with readline-based NDJSON parsing. Claude CLI: `stream-json` primary with `json` fallback (auto-detected). OpenCode: NDJSON with `type:"text"` parsing. Includes 3-phase cancel (SIGINT→SIGTERM→SIGKILL), 5-min timeout, malformed-line skipping, and OpenCode orphan PID cleanup via `pgrep` snapshot before/after.
- `web/api/src/services/sessionService.ts` — In-memory session store with UUID keys, concurrent RunHandle tracking (max 3), cancel-all on disconnect.
- `web/api/src/ws/index.ts` — WebSocket server at `/ws/code-session` with upgrade-time auth via query param token. Mirrors REST auth opt-in behavior.
- `web/api/src/ws/sessionHandler.ts` — Message router: `session.create`→`message.send`→`message.cancel`. Sends `backend.info` on connect. Cancels all processes on `ws.close`.
- `web/api/src/routes/sessions.ts` — REST: `GET /api/sessions`, `GET /api/sessions/:id`, `DELETE /api/sessions/:id`, `GET /api/sessions/backend-info`

**Files modified:**
- `web/api/src/index.ts` — Changed `app.listen()` to `http.createServer(app)` + `attachWebSocket(server)` + registered sessions router
- `web/app/vite.config.ts` — Added `/ws` proxy with `ws: true` before `/api` proxy

### Phase 3: Frontend Code Session Module — DONE

**Dependencies added:** `react-markdown@^9.0.1`, `remark-gfm@^4.0.0`

**New files created:**
- `web/app/src/hooks/useCodeSession.ts` — WebSocket lifecycle with exponential backoff (1s→30s), streaming accumulation, typed message dispatch, session CRUD methods
- `web/app/src/hooks/useSlashCommands.ts` — 7 commands (/help, /clear, /sessions, /browse, /model, /cost, /new) with prefix filtering and keyboard nav
- `web/app/src/components/CodeSession/CodeSession.tsx` — Main layout with session/no-session/error states, slash command routing, keyboard shortcuts (Ctrl+L clear, Ctrl+C cancel, Ctrl+N new)
- `web/app/src/components/CodeSession/CodeSession.module.css` — Scoped dark palette (always dark via --cs-* variables, independent of global theme)
- `web/app/src/components/CodeSession/MessageList.tsx` — Auto-scrolling message container
- `web/app/src/components/CodeSession/MessageBubble.tsx` — User messages with purple accent bar, assistant messages with react-markdown + Shiki code blocks, metadata footer (model, duration, cost, tokens)
- `web/app/src/components/CodeSession/MessageBubble.module.css` — Complete markdown styling for dark theme
- `web/app/src/components/CodeSession/InputArea.tsx` — Auto-resizing textarea with Enter/Shift+Enter, slash command detection, Up for history, cancel button during streaming
- `web/app/src/components/CodeSession/InputArea.module.css`
- `web/app/src/components/CodeSession/SlashCommandPalette.tsx` — Popup with keyboard nav (up/down/enter/escape)
- `web/app/src/components/CodeSession/SlashCommandPalette.module.css`
- `web/app/src/components/CodeSession/SessionHeader.tsx` — Session date/time, model badge, cost total, new/sessions buttons
- `web/app/src/components/CodeSession/StatusBar.tsx` — CWD path, backend name, connection indicator (green/yellow/red dot)
- `web/app/src/components/CodeSession/index.ts` — Barrel export

**Files modified:**
- `web/app/src/App.tsx` — Added `/session` route (static, before `/:kb`), lazy-loaded `CodeSession`, conditional render (session → adjutant → canvas/home), wrapped in ErrorBoundary
- `web/app/src/components/Sidebar/Sidebar.tsx` — Added "Code" link with terminal icon (`>_`) between Adjutant and KB list

### Phase 4: Session Management + Working Directory — DONE

**New files created:**
- `web/app/src/components/CodeSession/SessionList.tsx` — Modal listing past sessions with timestamp, message count, last message preview, resume/delete buttons. Fetches from REST API.
- `web/app/src/components/CodeSession/WorkingDirPicker.tsx` — Directory browser reusing `useExplorer` hook. Breadcrumbs, root shortcuts, single/double click navigation. No KB validation (unlike FolderExplorer).
- `web/app/src/components/CodeSession/ModelPicker.tsx` — Model tier selector (Fast/Balanced/Powerful) from `backendInfo.models`

### Phase 5: Polish — DONE

**Dependencies added:** `shiki@^3.0.0`

**New files created:**
- `web/app/src/components/CodeSession/CodeBlock.tsx` — Lazy-loaded Shiki highlighter with tokyo-night theme. Shows plain `<pre>` during init, replaces with highlighted HTML. 16 language grammars loaded.

**Files modified:**
- `web/app/src/components/CodeSession/MessageBubble.tsx` — Custom `code` renderer that routes code blocks to `CodeBlock` (Shiki), keeps inline code as `<code>`
- `web/app/vite.config.ts` — Added `'shiki': ['shiki']` to `manualChunks`

### Session Listing & Resumability — DONE

**Problem identified:** The original implementation had sessions hidden behind a "Resume Previous Session" button on the start screen. The WS `session.list` message handler in the frontend was dead code (never called). The `requestSessionList` hook method was exported but unused. Sessions were not visible at a glance.

**Changes made:**

1. **Start screen now shows recent sessions inline** — `RecentSessions` component (new, in `SessionList.tsx`) fetches up to 5 most recent sessions via `GET /api/sessions` and displays them directly below the "Start New Session" button. Each row shows: relative time, backend badge, message count, first user message preview, CWD (last 2 segments), model, and cost (if tracked).

2. **Session list modal enriched** — `SessionList` modal (opened via "View all" or `/sessions` command) now shows the same rich metadata per row plus a delete button with hover state. Sessions sorted by `lastActiveAt` (most recent first).

3. **Removed dead code from `useCodeSession` hook** — Deleted the unused `requestSessionList` method and the dead `session.list` case in `handleMessage`. The frontend consistently uses REST (`GET /api/sessions`) for listing, WS for resume. The WS `session.list` handler is kept on the backend as a valid protocol message but the frontend doesn't use it (REST is simpler for one-shot listing).

4. **Resume indicator in header** — `SessionHeader` now shows "Resumed" instead of "Session" when a session was resumed. Also displays the first 8 chars of the CLI session ID (if available) for debugging.

5. **Resume state tracking** — `CodeSession.tsx` tracks `isResumed` state. The `handleResume` callback sets this flag before calling `resumeSession`. New sessions reset the flag.

**Resume data flow (verified):**
```
Start screen shows RecentSessions (fetches GET /api/sessions)
→ User clicks a session row
→ handleResume(sessionId) called
→ setIsResumed(true)
→ resumeSession(sessionId) sends WS { type: 'session.resume', sessionId }
→ Backend sessionHandler looks up session in memory store
→ Sends { type: 'session.resumed', session } with full session + messages[]
→ Hook sets activeSession + populates messages[] from session.messages
→ UI renders SessionHeader (shows "Resumed — <date>") + MessageList (shows history)
→ User can continue chatting — next message.send includes session.cliSessionId for --resume/--session
```

### Sidebar Navigation — DONE

The Code Session is accessible from the sidebar as its own list item, positioned between "Adjutant" and the KB list. Uses a terminal icon (>`_`). Active state highlighted when on `/session` route.

### Bugfix: Claude CLI stream-json requires --verbose — DONE

**Error encountered:** `Error: When using --print, --output-format=stream-json requires --verbose`

**Root cause:** Claude CLI's `-p` (print/prompt) mode requires `--verbose` when using `--output-format stream-json`. Without it, the CLI refuses to stream.

**Fix:** Added `--verbose` to `buildClaudeArgs()` in `cliAdapter.ts` when `useStreamJson` is true. The full invocation is now:
```
claude -p --output-format stream-json --verbose [--model <alias>] [--resume <id>] --dangerously-skip-permissions "<prompt>"
```

This also means the `--verbose` flag adds extra diagnostic events to the NDJSON stream, but these are safely ignored by the parser (it only processes `content_block_delta` and `result` events).

### Mobile layout + sidebar offset + max-width — DONE

**Changes:**
- CodeSession now uses `position: fixed; inset: 0` with `transition: left` — same pattern as AdjutantDashboard
- `.sidebarOpen` class applies `left: var(--sidebar-width)` to shift content right when sidebar is open
- Content wrapped in `.content` div with `max-width: 1280px; margin: 0 auto` — matches Dashboard's content constraint
- `sidebarOpen` prop passed from `App.tsx` → `CodeSession`
- SessionHeader and StatusBar refactored to use CSS module classes (`.header`, `.statusBar`, etc.) instead of inline styles — proper responsive behavior
- Mobile breakpoint (768px):
  - `left: 0 !important` — sidebar overlays, doesn't push content
  - Header gets `padding-left: calc(var(--touch-target) + 0.5rem)` to avoid overlap with sidebar toggle button
  - Model badge hidden on mobile (`.headerBadge { display: none }`)
  - Input textarea `font-size: 1rem` to prevent iOS auto-zoom on focus
  - Bottom padding includes `env(safe-area-inset-bottom)` for notched devices

### Bugfix: WebSocket torn down on every streaming delta (React closure bug) — DONE

**Symptom:** After receiving a response, the input stayed permanently disabled ("Waiting for response..."). Firefox console showed repeated `wss://localhost:3021/ws/code-session` connection failures.

**Root cause:** `handleMessage` callback depended on `streamingContent` state (line 155: `}, [streamingContent]`). Every `message.delta` event updated `streamingContent` → React recreated `handleMessage` → recreated `connect` (which depended on `handleMessage`) → `useEffect` cleanup ran → **closed the WebSocket** → server-side `ws.close` handler fired → **killed the CLI process** → opened a new WebSocket. This cycle repeated on every single streaming chunk, destroying the connection mid-response.

**Fix:** Rewrote `useCodeSession` with a ref-based message handler pattern:
- `handleMessageRef` — a mutable ref updated on every render (always has fresh closures)
- `stableOnMessage` — a stable `useCallback(() => handleMessageRef.current?.(event), [])` wrapper assigned to `ws.onmessage`
- `connect` now depends only on `stableOnMessage` (which never changes)
- `streamingContentRef` — a ref synced from `streamingContent` state, used in the `message.error` handler to read current streaming content without adding it as a dependency
- `useEffect` cleanup only runs on unmount, not on every state change

**Result:** WebSocket stays open for the entire session lifetime. No more reconnection storms during streaming.

### Bugfix: "Waiting for response" stuck + session lost on refresh — DONE

**Symptom 1:** After receiving a response, the input stayed disabled showing "Waiting for response..." and the user couldn't type. The response text was visible but the UI never left streaming state.

**Root cause:** `onComplete` was only called inside `proc.on('close')`, but Claude CLI with `--verbose` + `stream-json` may not exit promptly after emitting the `result` event. The process lingered, so `close` never fired, so `message.complete` was never sent, so `isStreaming` stayed `true`.

**Fix:** Call `onComplete` immediately when the `result` event is received (with a `completeCalled` guard to prevent double-fire). The `proc.on('close')` handler now only handles error cases where no `result` event arrived. The `result` event IS the logical completion signal — process exit is just cleanup.

**Symptom 2:** On page refresh, the response was gone. The session existed on the server but the frontend didn't know about it.

**Root cause:** No persistence of the active session ID across page loads. Frontend state (messages, activeSession) was purely in-memory React state.

**Fix:**
- On `session.created` / `session.resumed`, save session ID to `localStorage` key `adjutant-code-session-id`
- On first WS connect, check localStorage for a saved session ID and auto-send `session.resume`
- If resume fails with `SESSION_NOT_FOUND` (server restarted), silently clear the stale localStorage entry
- Added `endSession()` method that clears both React state and localStorage

### Bugfix: Empty response text in streaming mode — DONE

**Symptom:** Messages sent and completed (metadata showed model, tokens, duration) but response text was invisible — empty content.

**Root cause:** The streaming parser only handled `content_block_delta` events for text extraction. Claude CLI's `stream-json` format may not emit these delta events (or uses a different structure). However, the `result` event always contains the full response text in its `result` field — but we only extracted metadata (session_id, cost, usage) from it, never the text.

**Fix:** Added a fallback in the `result` event handler: if no `content_block_delta` events were received during the stream (`!gotDelta`), emit the full `record.result` text as a single delta. This guarantees response text appears regardless of whether delta events fire. Added a `gotDelta` flag to track whether any real-time deltas arrived. Also added temporary debug logging of event types to diagnose the exact stream-json format.

**Result:** Responses now show text content. If delta events work, you get real-time streaming. If they don't, you get the full text when the result event arrives (same as json fallback, but within the stream-json pipeline).

### Bugfix: stdin pipe and operator precedence in cliAdapter — DONE

**Two bugs found** by auditing cliAdapter.ts against the Python backends:

1. **stdin pipe never closed** — All three spawn calls used `stdio: ['pipe', 'pipe', 'pipe']`, creating a stdin pipe that was never written to or closed. Claude CLI's `-p` mode tries to read stdin and warns after 3s: `"Warning: no stdin data received in 3s, proceeding without it"`. OpenCode could also hang. **Fix:** Changed all `stdio` to `['ignore', 'pipe', 'pipe']` — stdin is `/dev/null`, matching the Python daemon behavior.

2. **Operator precedence in stream-json fallback detection** (line 206) — The condition `code !== 0 && !gotResult && stderrBuf.includes('unknown') || stderrBuf.includes('Invalid value')` had wrong precedence: the `||` clause ran unconditionally due to `&&` binding tighter. If stderr contained "Invalid value" for any reason (even on success), it would incorrectly trigger the json fallback. **Fix:** Added parentheses: `(stderrBuf.includes('unknown') || stderrBuf.includes('Invalid value'))`.

**Audit results (OpenCode vs Claude CLI parity):**
- NDJSON text parsing: in sync with `ndjson.py`
- Session ID extraction: in sync (top-level `sessionID` + `session.create` event)
- Model alias translation: in sync with `_ALIASES` in `backend_claude_cli.py`
- Permission mode handling: in sync
- Orphan PID cleanup: uses `pgrep` instead of `psutil` (acceptable for Node.js)
- Error classification: TypeScript passes raw messages; Python classifies (model_not_found, auth_failure, etc.) — minor gap, acceptable for v1

### Chat bubble layout — user right, assistant left — DONE

User messages now render right-aligned with accent bar on the right edge. Assistant messages render left-aligned with border on the left edge. Both have asymmetric rounded corners (chat-bubble style). Width is `max-width: fit-content` (user-modified from the original 85%). On mobile (< 768px), max-width loosens to 92%.

### Typing indicator + streaming cursor — DONE

- **Typing indicator**: Three bouncing dots (`.typingDot`) appear on the left (assistant side) when `isStreaming` is true but no content has arrived yet. Dots have staggered `animation-delay` for a wave effect.
- **Streaming cursor**: Pulsing purple bar after the last character of streaming text. Uses smooth `ease-in-out` opacity animation instead of the original hard step blink.

### Message timestamps — DONE

Every message now shows a `dd.mm.yy HH:MM` timestamp in the meta line. For user messages, the timestamp is right-aligned. For assistant messages, it sits alongside model/duration/cost/tokens metadata. The timestamp is rendered with reduced opacity (0.7) to stay unobtrusive.

### Auto-rename sessions — DONE

Sessions start with the name "New session". When the first user message is sent, the backend (`sessionService.addMessage`) auto-renames the session to the first 60 characters of that message (with "..." appended if truncated, newlines replaced with spaces).

The updated name flows back to the frontend via the `message.complete` WS event's new `sessionName` field. The `useCodeSession` hook updates `activeSession.name` on receipt. The `SessionHeader` displays the session name instead of "Session — date time". Session list rows also show the auto-generated name.

**Changes:**
- `web/api/src/types/session.ts` — Added `name: string` to `CodeSession`, added `sessionName?: string` to `message.complete` WS message type
- `web/api/src/services/sessionService.ts` — `create()` sets `name: 'New session'`; `addMessage()` auto-renames on first user message
- `web/api/src/ws/sessionHandler.ts` — `onComplete` handler includes `sessionName` from updated session
- `web/app/src/hooks/useCodeSession.ts` — `SessionInfo` type has `name`; `message.complete` handler updates session name
- `web/app/src/components/CodeSession/SessionHeader.tsx` — Shows `session.name` as title
- `web/app/src/components/CodeSession/SessionList.tsx` — `SessionRow` displays `session.name`

### Slash commands cleanup — DONE

**Problem:** `/clear` only cleared the frontend window (misleading — didn't start a new session). `/cost` tried to send the cost as a chat message to the CLI. `/help` did nothing.

**Fix:**
- **`/clear` removed** — replaced by `/new` which opens the working directory picker to start a fresh session
- **`/cost`** — now inserts a local system message showing the session cost (or "No cost data available"). Never sends to the CLI.
- **`/help`** — now inserts a local system message listing all available commands with descriptions
- **System messages** — added `addSystemMessage()` helper in `CodeSession.tsx` that inserts a `role: 'system'` message into the local messages array

**Slash command registry (final):**
| Command | Description | Action |
|---------|-------------|--------|
| `/help` | Show available commands | Inserts system message with command list |
| `/new` | Start a new session | Opens working directory picker |
| `/sessions` | View past sessions | Opens session list modal |
| `/browse` | Change working directory | Opens directory picker |
| `/model` | Switch model tier | Opens model picker |
| `/cost` | Show cost summary | Inserts system message with cost |

### Model picker labels — DONE

Model picker labels now show `cheap`, `medium`, `expensive` matching the tier names in `adjutant.yaml` instead of the previous "Fast/Balanced/Powerful" labels.

### Pitfall Resolution Summary

All 21 pitfalls identified during planning have been addressed in the implementation:

| # | Pitfall | How Resolved |
|---|---------|-------------|
| 1 | Claude CLI stream-json | `cliAdapter.ts` tries stream-json first with `--verbose` flag (required by `-p` mode), auto-falls back to json if unsupported |
| 2 | OpenCode NDJSON format | Separate parsing path: `type:"text"` + `part.text` vs Claude's `content_block_delta` |
| 3 | Binary not found | `backendDetector.detect()` returns null → WS sends `BACKEND_NOT_FOUND` → UI shows install instructions |
| 4 | Process lifecycle | 3-phase cancel (SIGINT/SIGTERM/SIGKILL), 5-min timeout, malformed-line skip |
| 5 | OpenCode orphans | PID snapshot via `pgrep` before/after spawn, kills new language-server PIDs |
| 6 | Permission mode | Reads `llm.permission_mode` → `--dangerously-skip-permissions` or `--allowedTools` |
| 7 | Cost tracking | `costUsd: null` for OpenCode; UI conditionally renders cost fields |
| 8 | Model ID translation | `CLAUDE_ALIASES` map translates `anthropic/claude-*` → `haiku/sonnet/opus` |
| 9 | WebSocket auth | Auth during HTTP `upgrade` event via `?token=xxx` query param |
| 10 | WS reconnection | Exponential backoff (1s→30s), connection banner, kill processes on disconnect |
| 11 | Concurrent sessions | `sessionService` caps at 3 active RunHandles |
| 12 | Message ordering | TCP ordering sufficient — no sequence numbers |
| 13 | Route conflict | `/session` route (static) placed before `/:kb` (dynamic) |
| 14 | Theme scope | CodeSession uses scoped `--cs-*` CSS variables, always dark |
| 15 | Shiki bundle | Separate Vite chunk, lazy-loaded highlighter, plain `<pre>` fallback |
| 16 | Input handling | `<textarea>` with Enter/Shift+Enter, Up history, Escape close palette |
| 17 | Markdown rendering | `react-markdown` + `remark-gfm` (not TipTap) |
| 18 | In-memory sessions | Acceptable for v1; CLI sessions persist on disk |
| 19 | CWD for CLI | `spawn({cwd})` + OpenCode `--dir` flag |
| 20 | Concurrent YAML reads | Read-only, cached at startup |
| 21 | Port conflicts | Code session uses subprocess mode, not web server mode |
