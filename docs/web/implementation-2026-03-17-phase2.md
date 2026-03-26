# Phase 2 Implementation — Adjutant Integration

**Date**: March 17, 2026  
**Adjutant Version**: 0.2.0  
**Status**: ✅ Complete  
**Tests**: 94/94 passing

---

## Plan → Result

| Planned Task | Status | Notes |
|---|---|---|
| Read Adjutant KB registry | ✅ | New `registryService` reads `knowledge_bases/registry.yaml` |
| Add access control middleware | ✅ | Blocks writes to read-only KBs |
| Add session token auth | ✅ | Optional Bearer token via `ADJUTANT_WEB_SESSION_TOKEN` env var |
| Add Adjutant status endpoint | ✅ | `GET /api/adjutant/status` — mode, lifecycle state |
| Add `adjutant web` CLI commands | ⏭️ Deferred to Adjutant repo | Requires changes in Adjutant's `cli.py`, not Adjutant Web |

---

## Architecture

### Dual-Mode KB Discovery

Adjutant Web now has two modes of operation, selected automatically:

```
┌──────────────────────────────┐
│       kbService.list()       │
│                              │
│  Is Adjutant registry found? │
│  (ADJUTANT_DIR / ADJ_DIR /   │
│   ~/.adjutant)               │
│                              │
│   YES → registryService      │
│         reads registry.yaml  │
│         returns KbMeta[]     │
│                              │
│   NO  → configService        │
│         scans kbRoot dir     │
│         returns KbMeta[]     │
└──────────────────────────────┘
```

**Adjutant mode** (registry found):
- Reads `knowledge_bases/registry.yaml` directly
- KBs have absolute paths (can be on any volume)
- Access levels from registry are authoritative
- No `~/.adjutant-web/config.json` needed

**Standalone mode** (no registry):
- Scans `kbRoot` directory for `kb.yaml` files
- Access levels from individual `kb.yaml` files
- Configured via `~/.adjutant-web/config.json`

### Adjutant Directory Resolution

The registry service checks three locations in order:

1. `ADJUTANT_DIR` env var (explicit — set by user or Adjutant launcher)
2. `ADJ_DIR` env var (set by Adjutant's `core/paths.py` at runtime)
3. `~/.adjutant` (default fallback)

First candidate with a valid `knowledge_bases/registry.yaml` wins.

---

## Changes in Detail

### 1. Registry Service (`api/src/services/registryService.ts`) — NEW

Reads Adjutant's `knowledge_bases/registry.yaml` using `js-yaml`.

**Public API**:
```typescript
registryService.isAvailable()       → Promise<boolean>
registryService.list()              → Promise<KbMeta[]>
registryService.get(name)           → Promise<KbMeta | null>
registryService.resolveKbPath(name) → Promise<string | null>
registryService.resolveAdjutantDir() → Promise<string | null>
registryService.clearCache()        → void
```

**Validation**: Checks that each KB's `path` actually exists and contains `kb.yaml` before including it.

### 2. KB Service Rewrite (`api/src/services/kbService.ts`)

Now delegates to `registryService` when available, falls back to standalone scan.

```typescript
async list(): Promise<KbMeta[]> {
  if (await registryService.isAvailable()) {
    return registryService.list();
  }
  return this.listStandalone();
}

async getMode(): Promise<'adjutant' | 'standalone'> {
  return (await registryService.isAvailable()) ? 'adjutant' : 'standalone';
}
```

All existing callers (`folderService`, `fileNoteService`, `imageService`) work unchanged — they call `kbService.resolveKbPath(name)` which now resolves from registry or standalone transparently.

### 3. Access Control Middleware (`api/src/middleware/accessControl.ts`) — NEW

Blocks POST/PUT/DELETE on read-only KBs:

```typescript
// Applied to mutation routes
app.use('/api/notes', enforceAccess);
app.use('/api/folders', enforceAccess);
app.use('/api/assets', enforceAccess);
```

- Extracts KB name from `req.query.kb` or `req.body.kb`
- Calls `kbService.get(kb)` to check access level
- Returns `403` with clear message for read-only KBs
- GET/OPTIONS always pass through

### 4. Session Token Auth (`api/src/middleware/auth.ts`) — NEW

Optional Bearer token authentication:

```
# To enable (e.g., when started by Adjutant):
ADJUTANT_WEB_SESSION_TOKEN=<uuid> npm start

# To disable (development/standalone):
npm start  (no env var)
```

- When token is set: all `/api/*` requests require `Authorization: Bearer <token>`
- When not set: all requests pass through (no auth)
- `/health` is always public
- Logs auth mode on startup

### 5. Adjutant Status Route (`api/src/routes/adjutant.ts`) — NEW

```
GET /api/adjutant/status
```

Returns:
```json
{
  "mode": "adjutant",
  "available": true,
  "adjutantDir": "/Users/edvard/.adjutant",
  "lifecycleState": "OPERATIONAL"
}
```

Lifecycle state is read from filesystem markers:
- `state/KILLED` exists → `"KILLED"`
- `state/PAUSED` exists → `"PAUSED"`
- Neither → `"OPERATIONAL"`

### 6. Test Isolation

All test files updated to prevent `registryService` from finding the real `~/.adjutant`:

```typescript
beforeEach(async () => {
  originalHome = process.env.HOME;
  process.env.HOME = tempDir;          // Redirect HOME to temp
  delete process.env.ADJUTANT_DIR;     // Clear any env overrides
  delete process.env.ADJ_DIR;
  registryService.clearCache();
});

afterEach(async () => {
  process.env.HOME = originalHome;
  registryService.clearCache();
});
```

Route tests updated: test KB now `access: read-write` (was `read-only`) since access control middleware would block mutations on read-only KBs.

---

## Security Model

```
Request → CORS check → Auth middleware → Access control → Route handler
           │               │                  │
           │               │                  └─ 403 if read-only KB + write op
           │               └─ 401 if token set but missing/invalid
           └─ Block if origin not localhost/Tailscale/private
```

### Auth is optional by design:
- **Standalone mode**: No auth (local dev tool, protected by CORS + network)
- **Adjutant mode**: Token set by Adjutant at launch time via env var
- **Future**: Web UI sends token in Authorization header (stored in memory, not localStorage)

---

## Files Changed

### New Files
```
api/src/services/registryService.ts  — Adjutant registry reader
api/src/middleware/auth.ts            — Session token authentication
api/src/middleware/accessControl.ts   — Read-only KB enforcement
api/src/routes/adjutant.ts           — Adjutant status endpoint
```

### Modified Files
```
api/src/services/kbService.ts        — Dual-mode discovery (registry + standalone)
api/src/index.ts                     — Wire auth, access control, adjutant route
api/src/services/kbService.test.ts   — Test isolation for registry
api/src/services/folderService.test.ts — Test isolation for registry
api/src/services/fileNoteService.test.ts — Test isolation for registry
api/src/routes/routes.test.ts        — Test isolation + read-write KB
```

---

## Integration with Adjutant 0.2.0

### For Adjutant to start Adjutant Web (future `adjutant web start`):

```bash
# Adjutant generates token and sets env vars
export ADJUTANT_WEB_SESSION_TOKEN=$(uuidgen)
export ADJUTANT_DIR=$(pwd)  # or resolved by core/paths.py

# Start Adjutant Web API
cd /path/to/adjutant-web/api && npm start

# Start Adjutant Web Web (Vite dev or built)
cd /path/to/adjutant-web/web && npm run dev
```

### Registry format consumed:

```yaml
knowledge_bases:
  - name: "ixda"
    description: "..."
    path: "/Volumes/Mandalor/JottaSync/AI_knowledge_bases/ixda"
    model: "anthropic/claude-sonnet-4-6"
    access: "read-write"
    created: "2026-02-27"
```

Adjutant Web reads: `name`, `description`, `path`, `access`, `created`.  
Ignores: `model` (not needed for UI).

---

## Breaking Changes

None. All changes are additive:
- Standalone mode continues to work when no Adjutant directory found
- Auth is disabled by default (opt-in via env var)
- Access control only blocks writes — reads always work
- Adjutant status endpoint returns safe defaults when Adjutant unavailable
