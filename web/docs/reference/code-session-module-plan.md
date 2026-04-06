# Plan: Interactive Code Session Module for Adjutant Web

## Context

Adjutant web currently serves as a visual knowledge base explorer with canvas-based note organization. The user wants to add an interactive code session module — a chat-based coding assistant interface (like Claude Code / OpenCode) embedded directly in the web app. This should auto-detect whether adjutant runs on Claude CLI or OpenCode, stream responses in real-time, support session management, and feature a terminal-style UI inspired by OpenCode's design. Dark mode must also be added across all of adjutant web.

---

## Phase 1: Dark Mode Across All Adjutant Web

Add `[data-theme="dark"]` to the existing CSS variable system.

### Changes
- **`web/app/src/index.css`** — Add `[data-theme="dark"]` block with dark palette:
  - `--color-bg: #0f1117`, `--color-card: #1a1b2e`, `--color-text: #e0e0e6`
  - `--color-border: #2a2b3d`, `--color-hover-bg: #252640`
  - Adapted shadows, semantic colors, gradients
- **`web/app/src/types/index.ts`** — Extend `Theme` type to include `'dark'`
- **`web/app/src/components/SettingsDialog/SettingsDialog.tsx`** — Add dark option to theme select

### Dependencies
None.

---

## Phase 2: Backend Infrastructure (WebSocket + CLI Communication)

### New dependencies (API)
- `ws` + `@types/ws`

### New files

| File | Purpose |
|------|---------|
| `web/api/src/types/session.ts` | `ChatMessage`, `CodeSession`, `WsClientMessage`, `WsServerMessage` types |
| `web/api/src/services/backendDetector.ts` | Reads `adjutant.yaml` → detects `claude-cli` or `opencode`, finds binary path |
| `web/api/src/services/sessionService.ts` | In-memory session store (create, get, list, addMessage) |
| `web/api/src/services/cliAdapter.ts` | Spawns CLI processes, streams responses. **Claude CLI**: `claude -p --output-format stream-json [--resume ID]` with NDJSON parsing. **OpenCode**: piped stdin/stdout or proxy to `:4096` web API. Common interface with `onDelta`/`onComplete`/`onError` callbacks. |
| `web/api/src/ws/index.ts` | Creates `WebSocketServer` on path `/ws/session`, handles auth |
| `web/api/src/ws/sessionHandler.ts` | Routes WS messages → sessionService + cliAdapter, streams deltas back |
| `web/api/src/routes/sessions.ts` | REST: `GET /api/sessions`, `GET /api/sessions/:id`, `DELETE /api/sessions/:id`, `GET /api/sessions/backend` |

### Modified files
- **`web/api/src/index.ts`** — Create `http.Server` explicitly, attach WebSocket server, register sessions route
- **`web/app/vite.config.ts`** — Add `/ws` proxy with `ws: true`

### WebSocket Protocol
```
Client → Server:
  session.create { cwd }
  session.resume { sessionId }
  session.list
  message.send  { sessionId, content }
  message.cancel { sessionId }

Server → Client:
  session.created  { session }
  session.resumed  { session }
  session.list     { sessions }
  message.delta    { sessionId, content }
  message.complete { sessionId, message (with metadata: model, tokens, cost, duration) }
  message.error    { sessionId, error }
```

### CLI Adapter Details
- **Claude CLI**: `claude -p --output-format stream-json --resume <id>` → parse NDJSON events → extract text deltas and result metadata (model, tokens, cost). Cancel via `SIGINT`.
- **OpenCode**: Piped subprocess or proxy to built-in web server at `:4096`. `--session <id>` for resumption.
- Backend detected from `adjutant.yaml` (`llm.backend` field) via `registryService.resolveAdjutantDir()`.

---

## Phase 3: Frontend Code Session Module

### New dependencies (App)
- `shiki` (syntax highlighting, VS Code quality)

### New files

| File | Purpose |
|------|---------|
| `web/app/src/hooks/useCodeSession.ts` | WebSocket connection lifecycle, message state, streaming accumulation, `sendMessage()`, `cancelMessage()`, `createSession()`, `resumeSession()` |
| `web/app/src/hooks/useSlashCommands.ts` | Command registry (`/help`, `/clear`, `/sessions`, `/browse`, `/model`, `/compact`, `/cost`), prefix filtering, keyboard nav state |
| `web/app/src/components/CodeSession/CodeSession.tsx` | Main full-page chat layout: session header, message list, input area, status bar |
| `web/app/src/components/CodeSession/CodeSession.module.css` | Terminal-style dark UI: `#0f1117` bg, purple accent bars on user messages, bottom-pinned input, status strip |
| `web/app/src/components/CodeSession/MessageBubble.tsx` | Renders individual messages — parses markdown, extracts code blocks, shows metadata footer for assistant messages |
| `web/app/src/components/CodeSession/MessageBubble.module.css` | Message styling |
| `web/app/src/components/CodeSession/CodeHighlighter.tsx` | Shiki wrapper — lazy-loads grammars, dark theme (`tokyo-night`), memoized output |
| `web/app/src/components/CodeSession/SlashCommandPalette.tsx` | Popup above input when "/" typed — filtered list, keyboard nav (up/down/enter/esc), click to select |
| `web/app/src/components/CodeSession/SlashCommandPalette.module.css` | Command palette styling |
| `web/app/src/components/CodeSession/SessionHeader.tsx` | Top bar: session timestamp, token count, cost |
| `web/app/src/components/CodeSession/StatusBar.tsx` | Bottom bar: cwd path, git branch, backend indicator |
| `web/app/src/components/CodeSession/index.ts` | Barrel export |

### Modified files
- **`web/app/src/App.tsx`** — Add `/code` route, lazy-load `CodeSession`, render when `pathname === '/code'`
- **`web/app/src/components/Sidebar/Sidebar.tsx`** — Add "Code" navigation link (terminal icon)
- **`web/app/src/components/Sidebar/Sidebar.module.css`** — Style for nav item

### UI Design (from OpenCode screenshots)
- **Dark background**: `#0f1117` main, `#1a1b2e` cards/input
- **User messages**: Left purple accent bar (`3px solid #7c5cbf`), slightly tinted background
- **Assistant messages**: Plain text, code blocks with syntax highlighting
- **Input area**: Bottom-fixed, dark bg, accent bar on left, placeholder "Ask anything..."
- **Session header**: `# New session — <timestamp>`, token count + cost below
- **Metadata after responses**: `Build · claude-opus-4-6 · 5.1s` with colored square
- **Status bar**: Bottom strip with cwd, git branch, backend info
- **Slash commands**: Popup list above input with command name + description columns

---

## Phase 4: Session Management + Folder Navigation

### New files

| File | Purpose |
|------|---------|
| `web/app/src/components/CodeSession/SessionList.tsx` | Panel/modal listing past sessions — timestamp, message count, backend, last message preview. Click to resume, delete button. |
| `web/app/src/components/CodeSession/SessionList.module.css` | Session list styling |
| `web/app/src/components/CodeSession/WorkingDirPicker.tsx` | Filesystem browser for CWD selection — reuses existing `useExplorer` hook and `/api/explorer` endpoints |
| `web/app/src/components/CodeSession/WorkingDirPicker.module.css` | Dir picker styling |

### Integration
- Wire `/sessions` slash command → open SessionList
- Wire `/browse` slash command → open WorkingDirPicker
- "New Session" button opens WorkingDirPicker
- Session list accessible from session header

---

## Phase 5: Polish

1. **WebSocket reconnection** — exponential backoff, visual disconnect indicator, auto-resume
2. **Extended markdown** — tables, lists, blockquotes, clickable URLs, diff highlighting
3. **Keyboard shortcuts** — `Ctrl+L` clear, `Ctrl+C` cancel, `Up` for last message, `Escape` close palette
4. **Responsive design** — mobile-friendly layout
5. **Loading states** — skeleton UI while Shiki initializes, session creates
6. **Error boundaries** — wrap CodeSession in existing ErrorBoundary
7. **Shiki optimization** — lazy-load grammars, `shiki/bundle/web`, separate Vite chunk

---

## Verification Plan

1. **Dark mode**: Toggle to dark in Settings → verify all existing pages (Home, Canvas, Dashboard) render correctly
2. **Backend detection**: `GET /api/sessions/backend` → returns correct backend name and binary path
3. **WebSocket**: Open browser console → `new WebSocket('ws://localhost:3021/ws/session')` → verify connection
4. **Chat flow**: Navigate to `/code` → create session → send message → verify streaming response with syntax highlighting
5. **Slash commands**: Type "/" in input → verify popup appears → select command → verify action
6. **Session management**: Create multiple sessions → open session list → resume old session → verify message history
7. **Folder navigation**: Click browse → navigate filesystem → select directory → new session in that directory

## Key Reuse Points
- `registryService.resolveAdjutantDir()` — for finding adjutant config
- `explorerService` + `useExplorer` hook — for filesystem browsing in WorkingDirPicker
- Existing `data-theme` CSS variable system — for dark mode
- Existing component/hook patterns — folder structure, CSS modules, barrel exports
- Existing auth middleware — for WebSocket authentication
