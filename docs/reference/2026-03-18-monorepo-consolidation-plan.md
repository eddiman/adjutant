# Monorepo Consolidation Plan

**Date**: 2026-03-18
**Status**: Planned — awaiting approval to implement

Consolidate Adjutant (Python framework), Mariposa (web dashboard), and adjutant-docs (Docusaurus site) into a single repository for streamlined development.

---

## Current State

Three separate git repos, two separate directories:

```
~/Documents/Projects/
├── adjutant/                     # Git repo: eddiman/adjutant
│   ├── src/adjutant/             # Python framework (hatchling, py>=3.11)
│   ├── tests/                    # 1289 pytest tests
│   ├── docs/                     # Source-of-truth markdown
│   ├── adjutant-docs/            # Git repo: eddiman/adjutant-docs (gitignored clone)
│   │   └── docs/                 # Docusaurus site, deployed to GH Pages
│   └── ...                       # prompts, templates, identity, state, etc.
│
├── mariposa/                     # Git repo: eddiman/mariposa
│   ├── api/                      # Express API (vitest, 94 tests)
│   ├── web/                      # React/Vite frontend
│   └── docs/                     # Mariposa-specific docs
```

---

## Pain Points

1. **Cross-repo changes** — changing Adjutant's state format requires commits in 2-3 repos
2. **Duplicated docs** — docs in `adjutant/docs/` must be manually mirrored to `adjutant-docs/docs/`
3. **adjutant-docs is a nested git repo** — gitignored inside adjutant, separate remote, easy to forget to push
4. **`ADJUTANT_DIR` env wiring** — Mariposa needs to know where Adjutant lives at runtime, currently hardcoded in `api/.env`
5. **Separate AGENTS.md** — each repo has its own, context is split across sessions
6. **No shared types** — Mariposa's TypeScript types for Adjutant state (`ActiveOperation`, `LastHeartbeat`) are manually kept in sync with Python

---

## Proposed Structure

```
adjutant/                                 # Single git repo: eddiman/adjutant
├── AGENTS.md                             # Unified builder guide
├── pyproject.toml                        # Python build (hatchling, unchanged)
├── adjutant                              # CLI shim (unchanged)
├── adjutant.yaml.example
├── .env.example
│
├── src/adjutant/                         # Python framework (unchanged)
│   ├── cli.py
│   ├── core/
│   ├── lifecycle/
│   ├── messaging/
│   ├── capabilities/
│   └── ...
│
├── web/                                  # ← Mariposa moved here (renamed)
│   ├── api/                              # Express API
│   │   ├── src/
│   │   ├── package.json
│   │   └── vitest.config.ts
│   ├── app/                              # React frontend (was "web/")
│   │   ├── src/
│   │   ├── package.json
│   │   └── vite.config.ts
│   └── package.json                      # Workspace root (npm workspaces)
│
├── docs/                                 # Single source of truth (unchanged)
│   ├── architecture/
│   ├── guides/
│   ├── development/
│   └── web/                              # ← Mariposa docs moved here
│       └── architecture.md
│
├── site/                                 # ← adjutant-docs moved here (was separate repo)
│   ├── docs -> ../docs                   # Symlink to source of truth
│   ├── docusaurus.config.ts
│   ├── sidebars.ts
│   ├── src/
│   │   ├── pages/
│   │   └── css/
│   └── package.json
│
├── tests/                                # Python tests (unchanged)
│   ├── unit/
│   └── integration/
│
├── prompts/
├── templates/
├── identity/                             # (gitignored)
├── knowledge_bases/                      # (gitignored)
├── state/                                # (gitignored)
└── ...
```

---

## Key Decisions

### 1. Git History Strategy

**Chosen approach: Clean break (Option C).**

Move files manually into the monorepo. Old repos become read-only archives on GitHub with READMEs pointing to the monorepo. History for each project stays in its original remote.

Alternatives considered:
- **Subtree merge** (`git subtree add`) — preserves history but adds merge complexity
- **Fresh start** — loses all history

The clean break is simplest. Old repos remain available for historical reference.

### 2. Web Directory Layout — `web/api/` + `web/app/`

Currently Mariposa has:
```
mariposa/
├── api/      → Express
├── web/      → React
```

In the monorepo, the top-level `web/` is the Mariposa root. Inside:
```
web/
├── api/      → Express (same as before)
├── app/      → React (renamed from "web" to avoid web/web)
├── package.json  → npm workspace root
```

The workspace root `package.json` uses npm workspaces:
```json
{
  "name": "adjutant-web",
  "private": true,
  "workspaces": ["api", "app"]
}
```

This gives you:
```bash
cd web && npm install          # installs both api + app deps
cd web/api && npm test         # run API tests
cd web/app && npm run dev      # run Vite dev
```

### 3. Docs Site — `site/` with Symlinks

The current dual-doc problem: `docs/` is source of truth, `adjutant-docs/docs/` is a manual copy.

**Solution**: `site/` directory contains the Docusaurus config, custom pages, and CSS. The actual doc content comes from `docs/` via symlink:

```
site/
├── docs -> ../docs              # Symlink to source of truth
├── docusaurus.config.ts
├── sidebars.ts
├── src/
│   ├── pages/
│   └── css/
└── package.json
```

No more copying. Edit `docs/guides/lifecycle.md` once → Docusaurus picks it up.

**Fallback** if symlinks cause deploy issues: a build script that copies `docs/` → `site/docs/` before `npm run build`.

### 4. ADJUTANT_DIR at Dev Time

Currently Mariposa needs `ADJUTANT_DIR` in `api/.env` to find Adjutant. In the monorepo, the API can default to `../../` (the repo root) when `ADJUTANT_DIR` is not set.

Change in `registryService.ts`:
```typescript
// If ADJUTANT_DIR not set, try repo root (monorepo layout)
const repoRoot = path.resolve(__dirname, '..', '..', '..');
```

Or keep the `.env` approach with a relative path: `ADJUTANT_DIR=../..`

### 5. Unified AGENTS.md

Merge both AGENTS.md files into one:

```markdown
# AGENTS.md — Adjutant Builder Guide

## Python Framework (src/adjutant/)
[current Adjutant AGENTS.md content]

## Web Dashboard (web/)
[current Mariposa AGENTS.md content, adapted]

## Documentation Site (site/)
[brief section on docs workflow]
```

### 6. GitHub Repo Changes

| Current | After |
|---------|-------|
| `eddiman/adjutant` | **Primary repo** — monorepo |
| `eddiman/mariposa` | **Archived** — README points to adjutant/web/ |
| `eddiman/adjutant-docs` | **Kept for GH Pages deploy** OR switch to deploy from monorepo |

Docs site deploy options:
- **Option A**: Keep `eddiman/adjutant-docs` as the deploy target. Push `site/` build output there.
- **Option B**: Deploy from monorepo via GitHub Actions from `site/` directory.

---

## Migration Steps

1. **Prep**: Ensure all three repos are clean, committed, pushed
2. **Create branch**: `feature/monorepo` on adjutant
3. **Move Mariposa**:
   - Copy `mariposa/api/` → `adjutant/web/api/`
   - Copy `mariposa/web/` → `adjutant/web/app/`
   - Copy `mariposa/docs/` → `adjutant/docs/web/`
   - Copy `mariposa/AGENTS.md` content → merge into `adjutant/AGENTS.md`
   - Create `adjutant/web/package.json` workspace root
   - Update Vite proxy config (port, paths)
   - Update `api/.env` / `registryService.ts` for monorepo paths
4. **Move adjutant-docs**:
   - Copy `adjutant-docs/` → `adjutant/site/`
   - Replace `site/docs/` with symlink to `../docs/`
   - Remove `adjutant-docs/` from `.gitignore`
   - Test `cd site && npm run build`
5. **Update .gitignore**: Add `web/node_modules/`, `site/node_modules/`, `site/.docusaurus/`, `site/build/`
6. **Update AGENTS.md**: Merge both into unified guide
7. **Test everything**:
   - `.venv/bin/pytest tests/ -q` (Python: 1289 tests)
   - `cd web/api && npm test` (API: 94 tests)
   - `cd web/app && npx tsc -b --noEmit` (TypeScript)
   - `cd site && npm run build` (Docusaurus)
8. **Commit, push, test manually in browser**
9. **Archive old repos**: Add README badges pointing to monorepo

---

## What Doesn't Change

- Python source layout (`src/adjutant/`)
- `pyproject.toml` and hatchling build
- CLI shim (`adjutant`)
- All gitignored directories (`identity/`, `state/`, etc.)
- pytest configuration
- Express API internal code
- React component code
- Docusaurus config (just moved)

## What Changes

| Area | Before | After |
|------|--------|-------|
| Mariposa API location | `mariposa/api/` | `adjutant/web/api/` |
| Mariposa frontend location | `mariposa/web/` | `adjutant/web/app/` |
| Docs site location | `adjutant/adjutant-docs/` (gitignored) | `adjutant/site/` (tracked) |
| Docs content | Duplicated in `docs/` and `adjutant-docs/docs/` | Single source: `docs/`, symlinked into `site/` |
| AGENTS.md | Two files | One unified file |
| ADJUTANT_DIR wiring | Hardcoded in `api/.env` | Defaults to repo root in monorepo |
| Git repos | 3 repos | 1 repo (2 archived) |

---

## Risks

| Risk | Mitigation |
|------|-----------|
| Symlinks don't work on Windows | Not a concern — macOS only |
| Docusaurus can't follow symlinks | Test before committing. Fallback: build script copies docs/ |
| GitHub Pages deploy breaks | Keep adjutant-docs repo as deploy target initially |
| npm workspace conflicts | api and app have no shared deps — workspaces just hoist node_modules |
| Large repo size | .venv and node_modules are gitignored. Repo itself is small. |
| Adjutant runtime expects specific paths | Runtime paths use `$ADJ_DIR` which is the repo root — unchanged |

---

## Dev Workflow After Consolidation

```bash
# Start everything for development
cd adjutant
.venv/bin/pytest tests/ -q              # Python tests

cd web/api && npm run dev               # API on :3020
cd web/app && npm run dev               # Vite on :3021

cd site && npm start                    # Docusaurus on :3000

# Cross-cutting change (e.g., new state file format)
vim src/adjutant/core/lockfiles.py      # Python change
vim web/api/src/routes/adjutant.ts      # API change
vim web/app/src/hooks/useAdjutant.ts    # Frontend change
vim docs/architecture/state.md          # Docs (auto-picked up by site/)
git add -A && git commit -m "feat: ..."  # One commit, one repo
```
