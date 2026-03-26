# KB Explorer Rewrite Plan

**Branch**: `feature/kb-explorer`  
**Status**: In Progress  
**Last Updated**: 2026-03-16

## Summary

Transform Adjutant Web from a single-notes-directory app into a **knowledge base explorer** that discovers KBs by scanning a user-configured parent directory for folders containing `kb.yaml` (Adjutant KB format). Flat categories become recursive folders. Note metadata moves from YAML frontmatter to a per-folder `.adjutant-web.json` sidecar so `.md` files stay pure content. All KBs are read-only (no editing from Adjutant Web). MCP integration is removed.

## Design Decisions

- **KB discovery**: Scan a user-configured parent directory for subdirectories containing `kb.yaml`
- **Read-write notes**: Users can create, edit, and delete notes (.md files) within KBs
- **Metadata sidecar**: `.adjutant-web.json` per folder stores positions, tags, timestamps, sections, stickies for canvas layout
- **Sections & stickies**: Kept as canvas organizational tools, stored in `.adjutant-web.json`
- **URL routing**: `/:kb/*path` wildcard — e.g. `/ixda/data/events`
- **Note identity**: Filename is the ID (not auto-generated slugs)
- **Title extraction**: First `# heading` in file > filename sans extension
- **Home page**: KB browser with cards showing name + description from `kb.yaml`
- **KB root config**: Set via web UI settings dialog, persisted server-side
- **Clean break**: No migration from old Adjutant Web data model
- **File watching**: Future feature (see future-features.md)

## What Gets Deleted

- `api/src/mcp/` directory (MCP server)
- `api/src/routes/mcp.ts`
- MCP route registration in `api/src/index.ts`
- `@modelcontextprotocol/sdk` dependency
- `api/src/utils/frontmatter.ts` (YAML frontmatter — no longer needed)
- `api/src/utils/slugGenerator.ts` (auto-incrementing slugs — replaced by filename-based IDs)
- `gray-matter` dependency
- `api/src/services/noteService.ts` (replaced by `fileNoteService.ts` + `folderService.ts`)
- `api/src/services/sectionService.ts` (sections live in `.adjutant-web.json`)
- `api/src/services/stickyService.ts` (stickies live in `.adjutant-web.json`)
- `api/src/routes/categories.ts` (replaced by KB + folder endpoints)
- `api/src/routes/sections.ts` (managed via folder meta)
- `api/src/routes/stickies.ts` (managed via folder meta)
- `api/src/types/section.ts`, `api/src/types/sticky.ts` (merged into folder types)
- `web/src/hooks/useCategoryNotes.ts`

## Data Model

### KB Root Structure

```
<kb-root>/                  (user-configured, e.g. /Volumes/.../AI_knowledge_bases/)
  ixda/                     (KB — has kb.yaml)
    kb.yaml
    .adjutant-web.json          (canvas metadata for this folder)
    data/
      .adjutant-web.json
      current.md
      events/
        .adjutant-web.json
        2026-events-calendar.md
    knowledge/
      .adjutant-web.json
      strategy.md
  fagkomite/                (KB — has kb.yaml)
    kb.yaml
    ...
```

### kb.yaml Format (Adjutant standard)

```yaml
name: "ixda"
description: "IxDA Stavanger chapter operations..."
model: "anthropic/claude-sonnet-4-6"
access: "read-write"
created: "2026-02-27"
```

### .adjutant-web.json Format (per folder)

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

## API Endpoints

### Config

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/config` | Get current config (kbRoot path) |
| PUT | `/api/config` | Update config (set kbRoot path, validates directory exists + contains kb.yaml dirs) |

### KBs

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/kbs` | List discovered KBs (scan kbRoot for dirs with `kb.yaml`) |
| GET | `/api/kbs/:kbName` | Get KB metadata (parsed from `kb.yaml`) |

### Folders

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/folders?kb=:kb&path=:path` | List folder contents (files + subfolders) with `.adjutant-web.json` |
| GET | `/api/folders/meta?kb=:kb&path=:path` | Get `.adjutant-web.json` for a folder |
| PUT | `/api/folders/meta?kb=:kb&path=:path` | Update `.adjutant-web.json` for a folder |

### Notes (read-write)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/notes?kb=:kb&path=:filePath` | Get note content + metadata |
| POST | `/api/notes` | Create a new note (body: `{ kb, folder?, title, content?, tags?, position? }`) |
| PUT | `/api/notes?kb=:kb&path=:filePath` | Update a note (body: `{ content?, title?, tags?, position?, section? }`) |
| DELETE | `/api/notes?kb=:kb&path=:filePath` | Delete a note |
| GET | `/api/notes/search?kb=:kb&q=:query` | Search notes within a KB |

### Assets

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/assets?kb=:kb` | List images for a KB |
| GET | `/api/assets/:filename?kb=:kb` | Serve image file |

### Health

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |

## Frontend Routing

| URL | View |
|-----|------|
| `/` | Home — KB browser (cards for each KB) |
| `/:kb` | KB root folder canvas |
| `/:kb/*path` | Subfolder canvas (e.g. `/ixda/data/events`) |

Note opening: Editor overlay triggered by double-click. Note identified by `kb + path`. Optional `?note=path` query param for shareability.

## Services (API)

### New

- **`configService.ts`** — Read/write `~/.adjutant-web/config.json`
- **`kbService.ts`** — Discover KBs, parse `kb.yaml`
- **`folderService.ts`** — List contents, read/write `.adjutant-web.json`
- **`fileNoteService.ts`** — Read `.md` files, extract titles, search

### Modified

- **`imageService.ts`** — Parameterized by KB path

### Deleted

- `noteService.ts`, `sectionService.ts`, `stickyService.ts`

## Frontend Hooks

### New

- **`useKbs.ts`** — Fetch + cache KB list
- **`useFolder.ts`** — Fetch folder contents + meta, manages sections/stickies/positions via meta API

### Rewritten

- **`useCanvas.ts`** — Parse `kb` + folder path from URL, navigate between folders
- **`useNotes.ts`** — Simplified: read note content by kb+path
- **`useSettings.ts`** — Add kbRoot setting (server-side)
- **`useImages.ts`** — Parameterized by KB

### Deleted

- `useCategoryNotes.ts`

## Frontend Components

### New

- **`FolderNode`** — Canvas node for subfolders (name, icon, file count, double-click navigates)

### Rewritten

- **`Home`** — KB browser with cards (name, description from kb.yaml) + search
- **`Sidebar`** — Recursive folder tree per KB
- **`SettingsDialog`** — Add KB root directory text input

### Modified

- **`Canvas`** — Folder-scoped, shows files + subfolders + sections + stickies
- **`NoteNode`** — ID = filename, title from content/meta
- **`App.tsx`** — Wildcard routing, KB-scoped state

## Implementation Phases

| # | Phase | Status |
|---|-------|--------|
| 1 | Delete MCP + old dependencies, clean `index.ts` | Done |
| 2 | New config system + types | Done |
| 3 | KB discovery service + routes + tests (9 tests) | Done |
| 4 | Folder service + `.adjutant-web.json` read/write + tests (15 tests) | Done |
| 5 | File note service (read-only) + routes + tests (18 tests) | Done |
| 6 | Update image service for KB-scoping | Done |
| 7 | Wire up all new API routes in `index.ts` + route tests (19 tests) | Done |
| 8 | Frontend types | Done |
| 9 | Frontend hooks (`useKbs`, `useFolder`, rewrite `useCanvas`, `useNotes`, `useSettings`, `useImages`) | Done |
| 10 | Frontend routing (`App.tsx`, wildcard routes) | Done |
| 11 | Home page — KB browser with cards + search | Done |
| 12 | Sidebar — recursive folder tree with breadcrumbs | Done |
| 13 | Canvas + NoteNode updates (slug -> id/filename) | Done |
| 14 | Settings dialog — KB root config + validation | Done |
| 15 | NoteEditor — kb+path model with autosave/delete/tags | Done |
| 16 | Editor — KB-scoped image upload (paste/drop/button) | Done |
| 17 | Full web build verification | Done |

### Test Summary

- **87 tests** across 5 test files, all passing
- `configService.test.ts` — 6 tests (config read/write, kbRoot validation)
- `kbService.test.ts` — 9 tests (KB discovery, path traversal prevention)
- `folderService.test.ts` — 15 tests (folder listing, sidecar CRUD, sections, stickies)
- `fileNoteService.test.ts` — 33 tests (note reading, title extraction, search, create, update, delete)
- `routes.test.ts` — 24 tests (integration tests for all API endpoints including note CRUD)
