# Monorepo Consolidation + Rename Execution Plan

**Date**: 2026-03-26
**Status**: Approved — executing
**Supersedes**: `2026-03-18-monorepo-consolidation-plan.md`

Consolidate Adjutant (Python framework), Mariposa (web dashboard), and adjutant-docs (Docusaurus site) into a single repository. Rename "Mariposa" to "adjutant-web" throughout.

---

## Decisions

- **Git history**: Clean break. Old repos become read-only archives.
- **Rename scope**: Everything — package names, env vars, sidecar filenames, config dirs, UI strings, docs, comments.
- **Sidecar files**: `.mariposa.json` → `.adjutant-web.json` (with migration logic for existing data).
- **Config dir**: `~/.mariposa/` → `~/.adjutant-web/` (with migration).
- **Asset dir**: `<kb>/.mariposa/assets/` → `<kb>/.adjutant-web/assets/` (with migration).
- **Source field**: `"mariposa"` → `"adjutant-web"` in `active_operation.json`.
- **localStorage keys**: `mariposa-*` → `adjutant-web-*` (with one-time migration).
- **Mariposa base**: `feature/kb-explorer` branch (commit dirty changes first). `main` is a strict ancestor.
- **owui filter**: Moves to `integrations/openwebui/`, files renamed.
- **analysis/ dir**: Moves to `docs/web/analysis/` for historical reference.
- **notes/ dir**: Dropped (personal data).

---

## Phase 0: Preparation

### 0.1 — Commit dirty work on mariposa
On `mariposa/` (branch `feature/kb-explorer`), commit the 8 uncommitted files (Adjutant dashboard work), then push.

### 0.2 — Create consolidation branch
On `adjutant/`, create `feature/monorepo` from `main`.

### 0.3 — Verify both repos are clean
`git status` on both repos should show clean working trees.

---

## Phase 1: Move Mariposa into Adjutant as `web/`

### 1.1 — Copy directories into adjutant
```
mariposa/api/          → adjutant/web/api/
mariposa/web/          → adjutant/web/app/     (renamed to avoid web/web)
mariposa/docs/         → adjutant/docs/web/
mariposa/analysis/     → adjutant/docs/web/analysis/
mariposa/AGENTS.md     → (merge content into adjutant/AGENTS.md — Phase 5)
```

### 1.2 — Move owui filter
```
mariposa/owui-mariposa-filter/  → adjutant/integrations/openwebui/
```

### 1.3 — Do NOT copy
- `mariposa/src/` — empty, untracked artifact
- `mariposa/notes/` — personal data
- `mariposa/.git/` — history stays in archived repo
- `mariposa/node_modules/`, `mariposa/api/node_modules/`, `mariposa/web/node_modules/`

### 1.4 — Create workspace root `web/package.json`
```json
{
  "name": "adjutant-web",
  "private": true,
  "workspaces": ["api", "app"]
}
```

---

## Phase 2: Rename "Mariposa" → "adjutant-web" (Complete)

### 2.1 — Package/Config files

| File | Change |
|------|--------|
| `web/api/package.json` | `"name": "mariposa"` → `"name": "adjutant-web-api"`, bin `"mariposa"` → `"adjutant-web"` |
| `web/api/package-lock.json` | Regenerate via `npm install` |
| `web/app/package.json` | `"name": "web"` → `"name": "adjutant-web-app"` |
| `web/app/index.html` | `<title>Mariposa</title>` → `<title>Adjutant Web</title>`, iOS title same |
| `web/app/public/manifest.json` | `"name"` and `"short_name"` → `"Adjutant Web"` |

### 2.2 — Environment variables

| Old | New | Files |
|-----|-----|-------|
| `MARIPOSA_PORT` | `ADJUTANT_WEB_PORT` | `web/api/src/config.ts` |
| `MARIPOSA_HOST` | `ADJUTANT_WEB_HOST` | `web/api/src/config.ts` |
| `MARIPOSA_SESSION_TOKEN` | `ADJUTANT_WEB_SESSION_TOKEN` | `web/api/src/middleware/auth.ts` |
| `~/.mariposa` | `~/.adjutant-web` | `web/api/src/config.ts` |

### 2.3 — Sidecar files and on-disk format

| Old | New | Files |
|-----|-----|-------|
| `.mariposa.json` | `.adjutant-web.json` | `web/api/src/services/folderService.ts` |
| `.mariposa.json.backup-*` | `.adjutant-web.json.backup-*` | `web/api/src/services/folderService.ts` |
| `<kb>/.mariposa/assets/` | `<kb>/.adjutant-web/assets/` | `web/api/src/services/imageService.ts` |

**Migration**: One-time rename logic on first access per KB.

### 2.4 — TypeScript types and schemas

| Old | New |
|-----|-----|
| `MariposaSidecar` | `WebSidecar` |
| `MariposaSidecarSchema` | `WebSidecarSchema` |

### 2.5 — localStorage keys

| Old | New |
|-----|-----|
| `mariposa-settings` | `adjutant-web-settings` |
| `mariposa-sidebar-open` | `adjutant-web-sidebar-open` |
| `mariposa-nodes` | `adjutant-web-nodes` |

**Migration**: One-time key migration on app init.

### 2.6 — UI strings

All visible "Mariposa" text → "Adjutant Web" (Home.tsx, Sidebar.tsx, index.html, manifest.json, server log).

### 2.7 — Test files

All `'mariposa-test-*'` temp dir prefixes → `'adjutant-web-test-*'`. All `.mariposa.json` assertions updated.

### 2.8 — Comments and docstrings

Bulk replace across all API/service files.

### 2.9 — integrations/openwebui/

Rename files: `mariposa_filter.py` → `adjutant_web_filter.py`, `mariposa_pipe.py` → `adjutant_web_pipe.py`. Update all internal references.

### 2.10 — Adjutant Python source

`source="mariposa"` → `source="adjutant-web"` in docstrings (`lockfiles.py`, `cron.py`).

### 2.11 — Adjutant tests

All `source="mariposa"` → `source="adjutant-web"` in `test_cron.py`, `test_lockfiles.py`.

### 2.12 — Adjutant docs

"Mariposa" → "adjutant-web" / "the web dashboard" in `docs/architecture/state.md`, `docs/guides/lifecycle.md`.

### 2.13 — Web docs (docs/web/)

Bulk find-replace across all moved docs (~15 files, ~150+ occurrences).

---

## Phase 3: Move adjutant-docs into `site/`

### 3.1 — Copy adjutant-docs into adjutant
```
adjutant/adjutant-docs/ → adjutant/site/
```
Remove `adjutant-docs/` from `.gitignore`.

### 3.2 — Replace `site/docs/` with symlink
```bash
rm -rf site/docs/
ln -s ../docs site/docs
```

### 3.3 — Test Docusaurus build
```bash
cd site && npm install && npm run build
```

### 3.4 — Update any "Mariposa" references in site custom pages/config.

---

## Phase 4: Update .gitignore and Config

### 4.1 — .gitignore additions
```
web/node_modules/
web/api/node_modules/
web/app/node_modules/
site/node_modules/
site/.docusaurus/
site/build/
integrations/openwebui/__pycache__/
```

### 4.2 — Remove `adjutant-docs/` from `.gitignore`

### 4.3 — Update ADJUTANT_DIR wiring
In `web/api/src/services/registryService.ts`, default to repo root in monorepo layout.

---

## Phase 5: Merge AGENTS.md

Merge Mariposa's AGENTS.md into adjutant's AGENTS.md as `## Web Dashboard (web/)` section. Adapt all references.

---

## Phase 6: Verify Everything

| Check | Command |
|-------|---------|
| Python tests | `.venv/bin/pytest tests/ -q` |
| API tests | `cd web/api && npm test` |
| TypeScript | `cd web/app && npx tsc -b --noEmit` |
| Docusaurus | `cd site && npm run build` |
| Stale refs | `rg -i "mariposa" --glob '!.git' --glob '!node_modules'` |

---

## Phase 7: Commit, Push, Archive

- Commit on `feature/monorepo`
- Test manually in browser
- Archive `eddiman/mariposa` and `eddiman/adjutant-docs` on GitHub
