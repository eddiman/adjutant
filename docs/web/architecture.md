# Architecture

System design documentation for Adjutant Web — a KB (knowledge base) explorer.

## System Overview

```
┌─────────────────────────────────────────────────────────┐
│                        Browser                          │
│                                                         │
│  ┌───────────────────────────────────────────────────┐  │
│  │              React + React Flow                   │  │
│  │                                                   │  │
│  │  ┌─────────┐  ┌──────────┐  ┌────────────────┐   │  │
│  │  │  Home   │  │  Canvas  │  │  Editor (overlay)│  │  │
│  │  │ (KB     │  │ (folder  │  │  (TipTap,       │  │  │
│  │  │ browser)│  │  canvas) │  │  (TipTap)        │  │  │
│  │  └─────────┘  └──────────┘  └────────────────┘   │  │
│  │                    │                              │  │
│  │  ┌─────────────────┼────────────────────────┐     │  │
│  │  │  Custom Hooks   │   Contexts             │     │  │
│  │  │  useKbs         │   EditorContext        │     │  │
│  │  │  useFolder      │   PlacementContext     │     │  │
│  │  │  useNotes       │                        │     │  │
│  │  │  useCanvas      │   localStorage         │     │  │
│  │  │  useSettings    │   (theme, snap)        │     │  │
│  │  │  useImages      │                        │     │  │
│  │  └─────────────────┼────────────────────────┘     │  │
│  └────────────────────┼──────────────────────────────┘  │
│                       │ REST API calls                  │
└───────────────────────┼─────────────────────────────────┘
                        │
          ┌─────────────┼─────────────────┐
          │     Express API (:3020)        │
          │                               │
          │  ┌─────────────────────────┐  │
          │  │ Routes                  │  │
          │  │ /api/config             │  │
          │  │ /api/kbs                │  │
          │  │ /api/folders            │  │
          │  │ /api/notes              │  │
          │  │ /api/assets             │  │
          │  └────────┬────────────────┘  │
          │           │                   │
          │  ┌────────┴────────────────┐  │
          │  │       Services          │  │
          │  │  configService          │  │
          │  │  kbService              │  │
          │  │  folderService          │  │
          │  │  fileNoteService        │  │
          │  │  imageService (Sharp)   │  │
          │  └──────────┬──────────────┘  │
          └─────────────┼─────────────────┘
                        │ File I/O
          ┌─────────────┼─────────────────┐
          │   KB Root Directory           │
          │   (user-configured)           │
          │                               │
          │  <kb-root>/                   │
          │  ├── ixda/                    │
          │  │   ├── kb.yaml             │
          │  │   ├── .adjutant-web.json      │
          │  │   ├── data/               │
          │  │   │   ├── .adjutant-web.json  │
          │  │   │   ├── current.md      │
          │  │   │   └── events/         │
          │  │   └── knowledge/          │
          │  ├── fagkomite/              │
          │  │   ├── kb.yaml             │
          │  │   └── ...                 │
          │  └── ...                     │
          │                               │
          │  ~/.adjutant-web/config.json      │
          └───────────────────────────────┘
```

## Data Model

### Knowledge Base (KB)

A KB is a directory containing a `kb.yaml` file. Adjutant Web discovers KBs by scanning the user-configured root directory for subdirectories with this file.

**kb.yaml format** (Adjutant standard):

```yaml
name: "ixda"
description: "IxDA Stavanger chapter operations..."
model: "anthropic/claude-sonnet-4-6"
access: "read-write"
created: "2026-02-27"
```

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | KB identifier (matches directory name) |
| `description` | string | Human-readable description |
| `model` | string | LLM model hint (not used by Adjutant Web) |
| `access` | string | Access level hint (Adjutant Web supports read-write) |
| `created` | string | Creation date |

### Folder

Every directory within a KB is a navigable folder on the canvas. Folders can contain `.md` files (notes), subfolders, and other files.

### .adjutant-web.json (Canvas Sidecar)

Each folder can have a `.adjutant-web.json` file storing canvas layout metadata. This is the only file Adjutant Web writes to KB directories.

```json
{
  "items": {
    "current.md": {
      "position": { "x": 100, "y": 200 },
      "tags": ["status", "active"]
    },
    "events": {
      "position": { "x": 400, "y": 100 }
    }
  },
  "sections": {
    "section-1": {
      "name": "Active Work",
      "position": { "x": 50, "y": 50 },
      "width": 500,
      "height": 400,
      "color": "blue",
      "createdAt": "...",
      "updatedAt": "..."
    }
  },
  "stickies": {
    "sticky-1": {
      "text": "Remember to update",
      "color": "yellow",
      "position": { "x": 300, "y": 500 },
      "createdAt": "...",
      "updatedAt": "..."
    }
  },
  "nextSectionId": 2,
  "nextStickyId": 1
}
```

| Section | Description |
|---------|-------------|
| `items` | Per-file and per-subfolder canvas metadata (position, tags) |
| `sections` | Grouping rectangles on the canvas for this folder |
| `stickies` | Sticky notes on the canvas for this folder |
| `nextSectionId` | Auto-increment counter for section IDs |
| `nextStickyId` | Auto-increment counter for sticky IDs |

### Note (File)

Notes are `.md` files within KB directories. Users can create, edit, and delete notes. File content is the markdown body. Adjutant Web-specific metadata (position, tags, title override) is stored in the parent folder's `.adjutant-web.json`.

**Title extraction priority**: First `# heading` in file > filename sans extension.

### Image

Images found within KB directories are displayed on the canvas. Stored in `<kb>/.adjutant-web/assets/` for KB-scoped image management.

| File | Purpose |
|------|---------|
| `<uuid>.webp` | Full-size image (Sharp, quality 80) |
| `<uuid>-thumb.webp` | 300px-wide thumbnail (quality 75) |
| `<uuid>.meta.json` | Category metadata sidecar |

### Section

Grouping rectangles on the canvas. Stored in the folder's `.adjutant-web.json` under the `sections` key. No separate files.

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Editable display label |
| `position` | `{x, y}` | Canvas position |
| `width` | number | Rectangle width |
| `height` | number | Rectangle height |
| `color` | string | Color variant name |
| `createdAt` | ISO date | Creation timestamp |
| `updatedAt` | ISO date | Last modification timestamp |

### Sticky

Colored sticky notes on the canvas. Stored in the folder's `.adjutant-web.json` under the `stickies` key. No separate files.

| Field | Type | Description |
|-------|------|-------------|
| `text` | string | Sticky content |
| `color` | string | One of 9 color variants |
| `position` | `{x, y}` | Canvas position |
| `createdAt` | ISO date | Creation timestamp |
| `updatedAt` | ISO date | Last modification timestamp |

## App Configuration

Config persisted at `~/.adjutant-web/config.json`:

```json
{
  "kbRoot": "/Volumes/Mandalor/JottaSync/AI_knowledge_bases"
}
```

| Setting | Default | Description |
|---------|---------|-------------|
| Port | 3020 | HTTP server port |
| Host | `0.0.0.0` | Bind address |
| `kbRoot` | none | User-configured path to parent directory containing KBs |

The `kbRoot` is set via the web UI settings dialog and validated on save (directory must exist and contain at least one subdirectory with `kb.yaml`).

## Web Application

### Routing

React Router manages views via wildcard paths:

| Route | Component | Description |
|-------|-----------|-------------|
| `/` | `Home` | KB browser — cards for each discovered KB showing name and description from `kb.yaml`. Search bar searches across all KBs. Prompts to set KB root if not configured. |
| `/:kb` | `Canvas` | KB root folder canvas. Shows files and subfolders as nodes. |
| `/:kb/*path` | `Canvas` | Subfolder canvas within a KB (e.g. `/ixda/data/events`). |

Note opening: Double-click a note node opens the editor overlay. Note identified by `kb + path`. Optional `?note=path` query param for shareable links.

### State Architecture

All state lives in `App.tsx` and is managed through custom hooks:

```
App.tsx
├── useCanvas()          → kb, folderPath, navigation between folders
├── useKbs()             → discovered KBs list
├── useFolder()          → folder entries, .adjutant-web.json, sections, stickies
├── useNotes()           → read note content by kb+path
├── useImages()          → images for current KB
├── useSettings()        → theme, snap, kbRoot (server-side)
├── useCanvasHistory()   → undo/redo stack
├── useSnapToGuides()    → snap alignment lines
├── useCanvasNodeDrag()  → drag lifecycle
├── useCanvasClipboard() → copy/paste
├── useCanvasKeyboard()  → keyboard shortcuts
└── useCanvasTouchGestures() → long-press, two-finger tap
```

Contexts provide cross-cutting state:

| Context | Purpose |
|---------|---------|
| `EditorContext` | Controls editor overlay: animation origin rect, initial note data |
| `PlacementContext` | Controls placement mode: active state, type (section/sticky), ghost preview |

### Canvas Implementation

The canvas uses `@xyflow/react` (React Flow) with custom node types:

- **NoteNode**: Shows title (extracted from `# heading` or filename) + TipTap preview of markdown content. Double-click opens the full editor overlay.
- **FolderNode**: Shows folder name, icon, and file count. Double-click navigates into the folder. Draggable, position saved to parent's `.adjutant-web.json`.
- **ImageNode**: Renders images with states (uploading, error, ready). Corner resize handle maintains aspect ratio.
- **SectionNode**: Colored rectangle with editable name label. 4-corner resize handles.
- **StickyNode**: Colored sticky note with inline text editing. 9 color variants.

### Interactions

**Drag & Drop**: `useCanvasNodeDrag` manages the full lifecycle — auto-selects node on drag start, calculates snap guides during drag, persists positions on drag stop (to `.adjutant-web.json` via folder meta API).

**Snap-to-Guides**: `useSnapToGuides` calculates alignment lines by comparing the dragged node's edges and center to all other visible nodes. 8px threshold.

**Undo/Redo**: `useCanvasHistory` maintains a stack of up to 50 operations.

**Clipboard**: `useCanvasClipboard` copies node data to system clipboard as JSON with in-memory fallback.

**Keyboard Shortcuts** (`useCanvasKeyboard`):

| Key | Action |
|-----|--------|
| Cmd/Ctrl+Z | Undo |
| Cmd/Ctrl+Shift+Z | Redo |
| Cmd/Ctrl+C | Copy selected nodes |
| Cmd/Ctrl+V | Paste |
| Delete / Backspace | Delete selected nodes |
| Escape | Clear selection / exit placement mode |
| S | Enter section placement mode |
| T | Enter sticky placement mode |

**Touch Gestures** (`useCanvasTouchGestures`):
- Long-press (500ms) opens context menu
- Two-finger tap opens context menu

### Editor

The editor is a full-screen overlay that slides in from the note's canvas position. Inside, TipTap provides rich text editing with extensions for headings, lists, code blocks, highlighting, and images. Supports autosave (1.5s debounce), image paste/drop upload, title editing, tag management, and note deletion.

### Sidebar

Recursive folder tree showing the KB structure. Expandable folders show subfolders and notes. Click a folder to navigate to its canvas. Click a note to focus/open it.

## API Server

### Service Layer

- **ConfigService** (`configService.ts`): Reads/writes `~/.adjutant-web/config.json`. Validates kbRoot path exists and contains KB directories.
- **KbService** (`kbService.ts`): Scans kbRoot for directories containing `kb.yaml`. Parses KB metadata.
- **FolderService** (`folderService.ts`): Lists folder contents (files + subfolders). Reads/writes `.adjutant-web.json` sidecar files. Manages sections and stickies within the sidecar.
- **FileNoteService** (`fileNoteService.ts`): Reads `.md` files. Extracts titles from first `# heading`. Combines file content with `.adjutant-web.json` metadata. Provides search within a KB.
- **ImageService** (`imageService.ts`): Manages images scoped to KBs. Stored in `<kb>/.adjutant-web/assets/`.

### Security

- Adjutant Web never modifies `kb.yaml` or other KB config files
- Adjutant Web writes `.md` files (note create/edit), `.adjutant-web.json` sidecars (canvas metadata), and `.adjutant-web/assets/` (uploaded images)
- Path traversal protection on all file operations (KB and path params validated)

## Adjutant Integration

Adjutant Web includes an optional Adjutant agent dashboard at `/adjutant`. This provides a web UI for monitoring and controlling the Adjutant framework.

### How It Works

```
Adjutant Web Dashboard (browser)
  ↕ REST API calls
Adjutant Web API (Express)
  ↕ File I/O + subprocess spawn
Adjutant directory ($ADJ_DIR)
  ├── adjutant.yaml          → schedules, config
  ├── PAUSED / KILLED         → lifecycle state
  ├── state/
  │   ├── active_operation.json  → running pulse/review
  │   ├── last_heartbeat.json    → last pulse results
  │   └── adjutant.log           → journal entries
  └── identity/               → soul, heart, registry
```

### Directory Detection

`registryService.resolveAdjutantDir()` finds the Adjutant directory by checking:
1. `ADJUTANT_DIR` environment variable
2. `~/.adjutant` directory

A directory is valid if it contains `adjutant.yaml` or `knowledge_bases/registry.yaml`.

### API Endpoints (`/api/adjutant/`)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/status` | GET | Lifecycle state, active operation, last heartbeat |
| `/schedules` | GET | List scheduled jobs from `adjutant.yaml` |
| `/schedules/toggle` | POST | Enable/disable a schedule |
| `/schedules/run` | POST | Trigger a schedule (fire-and-forget) |
| `/identity` | GET | Soul, heart, registry excerpts |
| `/journal/recent` | GET | Last 20 log entries |
| `/health` | GET | Directory, config, CLI health checks |
| `/lifecycle` | POST | Pause, resume, pulse, review |
| `/kb/query` | POST | Query a KB via Adjutant sub-agent |

### Lifecycle Actions

**Pause/resume** are synchronous — the API waits for the `adjutant` CLI to complete and returns the result.

**Pulse/review** are fire-and-forget — the API spawns `adjutant pulse` as a detached process and returns immediately. Adjutant writes `state/active_operation.json` while running. The dashboard polls `/api/adjutant/status` every 3 seconds during an active operation to observe progress. No idle polling occurs.

### Dashboard Components

| Component | Data Source | Purpose |
|-----------|------------|---------|
| `SystemStatus` | `/status` | Mode, lifecycle state, directory |
| `QuickActions` | `/status` → `activeOperation` | Trigger and observe pulse/review/pause/resume |
| `LastPulse` | `/status` → `lastHeartbeat` | Show results from the last pulse or review |
| `HealthChecks` | `/health` | Directory, config, CLI validation |
| `SchedulesManager` | `/schedules` | View, toggle, and trigger scheduled jobs |
| `IdentityDisplay` | `/identity` | Tabbed view of soul, heart, registry |
| `ActivityFeed` | `/journal/recent` | Recent log entries |

### State Management (`useAdjutant` hook)

All dashboard state lives in the `useAdjutant()` hook, which is instantiated in `AppContent` (never unmounts). This means dashboard state survives navigation — visit a KB, come back, and the dashboard still shows the same data.

Button states (running/done/error) are derived from Adjutant's filesystem state, not in-memory tracking:
- `status.activeOperation?.action === 'pulse'` → Pulse button shows "Running..."
- No active operation + heartbeat timestamp changed → "Done" for 4 seconds
- HTTP POST failure → "Failed" for 4 seconds

---

## Development Setup

### Proxy Configuration

Vite dev server proxies `/api` to Express:

```
Browser → localhost:3021 (Vite) → /api/* → localhost:3020 (Express)
```

### Build Optimization

Vite splits large dependencies into separate chunks:
- `@xyflow/react` → vendor chunk
- TipTap packages → vendor chunk
