# Adjutant Web

A visual knowledge base editor that runs in your browser. Open any KB as a spatial canvas — arrange notes, add sections and sticky notes, upload images, and edit markdown. When running alongside Adjutant, it also gives you a live dashboard to monitor status, control the lifecycle, and manage schedules.

---

## Starting the web app

```bash
adjutant web
```

This starts both the API server and the frontend, then opens `https://localhost:3021` in your browser. Both processes shut down together on `Ctrl+C`.

**Options:**

```
--port, -p  API port (default: 3020)
--host      API host (default: 0.0.0.0)
--no-open   Don't open the browser automatically
```

The frontend always runs on port 3021. The API port is configurable.

**First run:** If `web/node_modules/` is missing, `adjutant web` installs npm dependencies automatically before starting.

---

## Two modes

The web app detects which context it's running in and adapts:

**Adjutant mode** (default when an Adjutant directory is found)
- Reads KBs from your `knowledge_bases/registry.yaml`
- Respects per-KB access levels (read-only vs read-write)
- Enables the Adjutant dashboard (status, lifecycle, schedules)

**Standalone mode** (fallback when Adjutant isn't configured)
- Scans a directory you specify for KB folders (any folder containing `kb.yaml`)
- No Adjutant dashboard features
- Configure the KB root via Settings or the first-run prompt

---

## The canvas

Each KB folder opens as a 2D canvas. Files appear as note cards you can drag anywhere. You can also add sections, stickies, and images.

**Navigation:**
- Pan — click and drag on empty canvas, or hold `Space` + drag
- Zoom — scroll wheel or trackpad pinch
- Switch between Pan and Select tools in the toolbar

**Note cards:**
- Click to open and edit
- Drag to reposition
- Right-click for a context menu (edit, delete, copy)
- Position is saved automatically to a `.adjutant-web.json` sidecar file alongside your markdown files

**Creating notes:**
- Click **+ Note** in the toolbar, then click on the canvas to place it
- Give it a title and start writing
- The file is saved as a `.md` file in the current KB folder

**Editing notes:**
The editor supports standard markdown — headings, bold, italic, lists, code blocks, blockquotes, and inline images. Your first `# heading` becomes the note title shown on the canvas card.

**Tags:**
Add tags to notes from the editor. Tags appear on the canvas card and are searchable.

**Search:**
Use the search bar in the toolbar to fuzzy-search all notes in the current KB by title, filename, tags, or content. Click a result to jump to it on the canvas.

---

## Sections

Sections are resizable grouping boxes you can use to organise related notes spatially.

- Click **+ Section** in the toolbar, then click to place it
- Drag to move, drag the edge/corner to resize
- Double-click the label to rename
- Right-click to set a colour or delete

Notes dragged into a section are logically associated with it (stored in the sidecar).

---

## Sticky notes

Sticky notes are free-form text annotations — not markdown files, just canvas annotations.

- Click **+ Sticky** in the toolbar, then click to place it
- Double-click to edit text
- Choose from 9 colours: white, yellow, pink, blue, green, purple, orange, mint, peach
- Drag to reposition, right-click to delete

Stickies are stored in the folder's `.adjutant-web.json` sidecar, not as separate files.

---

## Images

You can upload images into a KB and place them on the canvas.

- Drag an image file onto the canvas, or use the upload button in the toolbar
- Accepts: JPEG, PNG, GIF, WebP, SVG, HEIC, HEIF (max 10 MB)
- Images are converted to WebP and stored in `<kb-root>/<kb-name>/.adjutant-web/assets/`
- Thumbnails are generated automatically
- Drag to reposition, drag the corner to resize
- Right-click to delete

Rate limit: 20 uploads per 15 minutes per client.

---

## Folder navigation

Use the sidebar to navigate between KBs and subfolders. The breadcrumb at the top of the sidebar shows your current location. Click any folder to open it as a new canvas.

Each folder has its own independent canvas (its own `.adjutant-web.json`). Positions and annotations in one folder don't affect other folders.

---

## Read-only KBs

KBs registered with `access: read-only` in Adjutant's registry are opened in read-only mode. You can view notes and navigate the canvas, but creating, editing, deleting, and uploading are blocked. The toolbar edit buttons are disabled.

---

## Adjutant dashboard

Accessible via the **Adjutant** link in the sidebar (only shown in Adjutant mode).

**Status panel** — shows whether Adjutant is running, its lifecycle state (OPERATIONAL / PAUSED / KILLED), and any currently active operation (pulse or review in progress).

**Health checks** — confirms the Adjutant directory is found, config is present, the CLI is executable, and the listener process is alive.

**Quick actions:**
- Pause / Resume — immediately pause or resume the Telegram listener
- Run pulse — trigger a pulse run in the background (same as `adjutant pulse`)
- Run review — trigger a review run in the background (same as `adjutant review`)
- Pulse and review run detached; the dashboard shows their progress via `state/active_operation.json`

**Schedules** — lists all scheduled jobs from `adjutant.yaml`. You can toggle them on/off and trigger a manual run from here.

**Identity** — shows short excerpts from `identity/soul.md`, `identity/heart.md`, and `identity/registry.md`.

**Activity feed** — shows the last 20 entries from `journal/adjutant.log`, newest first.

---

## KB queries

From any KB view, you can query the KB via Adjutant's sub-agent using the query bar (if available in the sidebar). This runs `adjutant kb query <name> "<question>"` and returns the answer inline. Timeout: 60 seconds.

---

## Settings

Open Settings from the toolbar or sidebar.

| Setting | Description |
|---|---|
| KB root | Directory to scan for KBs (standalone mode only) |
| Theme | `default` or `bauhaus` |
| Snap to object | Snap notes/stickies/sections to each other while dragging |
| Show snap guides | Show alignment guide lines while dragging |

Settings are saved to `~/.adjutant-web/config.json`.

---

## Data and files

The web app never modifies your markdown files except when you explicitly edit or create a note.

**What it writes:**

| File | Location | Purpose |
|---|---|---|
| `.adjutant-web.json` | Per folder in each KB | Canvas positions, sections, stickies, image metadata |
| `<id>.webp` | `<kb>/.adjutant-web/assets/` | Uploaded image (full resolution) |
| `<id>-thumb.webp` | `<kb>/.adjutant-web/assets/` | Uploaded image thumbnail |
| `config.json` | `~/.adjutant-web/` | App config (KB root path) |

**Backups:** Before overwriting a `.adjutant-web.json`, the API keeps the last 3 backup copies. Writes are atomic (temp file + rename) to prevent corruption.

---

## Authentication

By default the API has no authentication — it's designed for local or Tailscale use. To require a Bearer token on all API requests, set the environment variable before starting:

```bash
ADJUTANT_WEB_SESSION_TOKEN=your-secret-token adjutant web
```

CORS is restricted to localhost, Tailscale (`*.ts.net`, `100.x.x.x`), and private network ranges (`10.x`, `172.16-31.x`, `192.168.x`). The `/health` endpoint is always public.

---

## Ports

| Service | Port | Configurable |
|---|---|---|
| API (Express) | 3020 | `--port` flag or `ADJUTANT_WEB_PORT` |
| Frontend (Vite) | 3021 | No |

The frontend proxies all `/api/*` requests to the API port. If you change `--port`, the API moves but the frontend stays on 3021.

---

## Running without `adjutant web`

If you need to start the two processes independently (e.g. to run them as system services):

```bash
# API
cd web/api && npm run dev        # development (tsx watch)
cd web/api && npm start          # production (requires npm run build first)

# Frontend
cd web/app && npm run dev        # development (Vite)
cd web/app && npm run build      # production build → web/app/dist/
```

Production: build the frontend with `npm run build`, then serve `web/app/dist/` as static files with any HTTP server. The API must be reachable at the same host on port 3020 (or proxied from the same origin).
