# Phase 1 Implementation — Security & Stability

**Date**: March 17, 2026  
**Status**: ✅ Complete  
**Tests**: 94/94 passing (was 87)

---

## Plan → Result

| Planned Task | Status | Notes |
|---|---|---|
| Fix image position storage (localStorage → server) | ✅ | New `images` field in `.adjutant-web.json`, API endpoints, useImages hook rewritten |
| Use UUIDs for section/sticky IDs | ✅ | `section-<uuid>` / `sticky-<uuid>`, `nextSectionId`/`nextStickyId` deprecated |
| Add sidecar backups | ✅ | Last 3 backups retained, atomic writes via temp+rename |
| Fix filename collision race condition | ✅ | Atomic `O_EXCL` file creation prevents concurrent duplicates |
| Add image content-type validation | ✅ | Done in Phase 0; multer fileFilter rejects non-images |
| Fix debounce stale closures | ✅ | `updateImageSize` no longer depends on `images` state array |
| Add concurrency tests | ✅ | 7 new tests (concurrent note creation, backups, image positions) |
| Add optimistic concurrency control | ⏭️ Deferred | Adds complexity without immediate need for single-user; revisit in Phase 3 |

---

## Changes in Detail

### 1. Image Positions Server-Side

**Problem**: Image positions stored in `localStorage` — lost on browser clear, can't sync across devices.

**Solution**:
- Added `images: Record<string, ImageMeta>` field to `.adjutant-web.json` sidecar schema
- Added `ImageMeta` type: `{ position?, width?, height? }`
- Added API endpoints: `PUT/GET/DELETE /api/folders/images?kb=&path=&id=`
- Added `folderService` methods: `updateImagePosition`, `getImagePosition`, `deleteImagePosition`
- Rewrote `useImages` hook: fetches positions from folder meta, debounced server sync
- Removed all `localStorage` usage from image management

**Files**: `api/src/types/folder.ts`, `api/src/services/folderService.ts`, `api/src/routes/folders.ts`, `web/src/hooks/useImages.ts`, `web/src/types/index.ts`, `web/src/App.tsx`

### 2. UUID-Based Section/Sticky IDs

**Problem**: Auto-incrementing `section-1`, `section-2` creates collisions in concurrent operations.

**Solution**:
- `createSection` → `section-<uuidv4()>`
- `createSticky` → `sticky-<uuidv4()>`
- `nextSectionId`/`nextStickyId` marked optional/deprecated in schema
- Removed increment logic from `useFolder` hook
- All existing sidecars with old IDs continue to work (backward compatible)

**Files**: `api/src/services/folderService.ts`, `api/src/types/folder.ts`, `web/src/hooks/useFolder.ts`, `web/src/types/index.ts`

### 3. Sidecar Backups

**Problem**: Corrupted `.adjutant-web.json` = complete layout loss, no recovery.

**Solution**:
- Before every write, copy existing sidecar to `.adjutant-web.json.backup-<timestamp>`
- Keep last 3 backups, prune older ones
- Atomic writes: write to `.tmp-<unique>`, then `rename()` to final path
- Prevents corruption from interrupted writes

**Files**: `api/src/services/folderService.ts`

### 4. Filename Collision Race Condition

**Problem**: `ensureUniqueFilename()` used check-then-act (TOCTOU): two concurrent creates could both see filename available, both write to same path.

**Solution**:
- Use `fs.open(path, 'wx')` — `O_CREAT | O_EXCL` flag
- Atomic: kernel guarantees only one process succeeds
- Loser gets `EEXIST`, tries next filename (`-2`, `-3`, etc.)
- Creates empty placeholder; caller overwrites with real content

**Files**: `api/src/services/fileNoteService.ts`

### 5. Stale Closure Fix

**Problem**: `updateImageSize` in `useImages` had `images` state array in its dependency list, causing unnecessary re-creation and stale reads.

**Solution**: Extract position from `imageMetaCache` ref or from state updater callback instead of closed-over state.

**Files**: `web/src/hooks/useImages.ts`

### 6. Review Fixes (from Phase 0 audit)

| Fix | Detail |
|---|---|
| `spawn()` timeout | `spawn` options don't support `timeout` — replaced with manual kill timer |
| Double response guard | Both `error` and `exit` events can fire on spawn — added `responded` flag |
| CORS for Tailscale | Allow `.ts.net` hosts, `100.x.x.x` (Tailscale), RFC 1918 private IPs |
| `updateMeta` merge | Was missing `images` field in the merge logic |
| Web types | `Adjutant WebSidecar` now includes `images`, `nextSectionId`/`nextStickyId` optional |

---

## New Tests (7 added)

| Test | File | Validates |
|---|---|---|
| `creates unique filenames for 10 concurrent notes` | `fileNoteService.test.ts` | Atomic `O_EXCL` prevents race conditions |
| `creates unique filenames for rapid sequential notes` | `fileNoteService.test.ts` | Sequential dedup works correctly |
| `creates a backup on write` | `folderService.test.ts` | Backup created on second write |
| `keeps only the last 3 backups` | `folderService.test.ts` | Old backups pruned |
| `stores and retrieves image position` | `folderService.test.ts` | Server-side image meta round-trip |
| `deletes image position` | `folderService.test.ts` | Clean removal from sidecar |
| `returns false when deleting nonexistent image position` | `folderService.test.ts` | Graceful not-found |

**Total test count**: 94 (was 87)

---

## Breaking Changes

**API**:
- New `images` field in `.adjutant-web.json` — existing sidecars parse correctly (defaults to `{}`)
- Section/sticky IDs now UUID-based — existing integer IDs continue to work, new ones are UUIDs
- `nextSectionId`/`nextStickyId` no longer incremented — may be absent from new sidecars

**Web**:
- `useImages` now requires `{ kb, path }` instead of `{ kb }` — updated in `App.tsx`
- `Adjutant WebSidecar.nextSectionId`/`nextStickyId` now optional in web types

---

## Files Changed

```
api/src/types/folder.ts              — ImageMeta type, images field, deprecated next*Id
api/src/services/folderService.ts    — UUID IDs, image helpers, backup + atomic writes
api/src/services/fileNoteService.ts  — Atomic O_EXCL filename creation
api/src/routes/folders.ts            — Image position API endpoints
api/src/routes/config.ts             — Spawn timeout fix, double-response guard
api/src/index.ts                     — CORS allow Tailscale + private IPs
web/src/types/index.ts               — ImageMeta, optional deprecated fields
web/src/hooks/useImages.ts           — Server-side positions, stale closure fix
web/src/hooks/useFolder.ts           — Remove deprecated nextId increments
web/src/App.tsx                      — Pass path to useImages
api/src/services/folderService.test.ts   — 5 new tests
api/src/services/fileNoteService.test.ts — 2 new tests + updated existing
api/src/routes/routes.test.ts            — Updated for UUID IDs
```
