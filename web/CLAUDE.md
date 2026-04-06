# CLAUDE.md — web/

> Scoped to `web/` only. Root `CLAUDE.md` rules (no AI attribution, no committing gitignored files) still apply.

## Structure

npm workspaces monorepo with two packages:

- **`app/`** — React 19 SPA (Vite, TypeScript, CSS Modules)
- **`api/`** — Express 4 backend (TypeScript, tsup)

No direct code imports between packages — they communicate via HTTP.

## Dev Commands

```bash
# From web/app/
npm run dev          # Vite dev server on :3021
npm run build        # tsc -b && vite build
npm run lint         # eslint .

# From web/api/
npm run dev          # tsx watch on :3020 (loads .env)
npm run build        # tsup → dist/index.js (ESM)
npm run test         # vitest run
npm run test:watch   # vitest watch
```

## Key Libraries

| Area | Library |
|------|---------|
| Canvas | `@xyflow/react` (React Flow) |
| Rich text | TipTap (`@tiptap/react`, `tiptap-markdown`) |
| Routing | React Router 7 |
| Image processing | sharp (API) |
| Fuzzy search | fuse.js (API) |
| Validation | zod (API) |
| File uploads | multer (API) |

## Patterns

### App (frontend)

- **State management**: React Context + custom hooks — no Redux/Zustand.
- **Styling**: CSS Modules (`.module.css`) per component. Global design tokens in `index.css` as CSS variables.
- **Components**: one folder per component with `Component.tsx`, optional `.module.css`, and `index.ts` barrel export.
- **Hooks**: business logic lives in `hooks/` (e.g. `useCanvas`, `useFolder`, `useNotes`). Keep hooks focused — one concern per hook.
- **API calls**: plain `fetch` through Vite proxy (`/api/*` → `localhost:3020`). No axios.
- **Canvas nodes**: `NoteNode`, `ImageNode`, `SectionNode`, `StickyNode` in `components/nodes/`.
- **Themes**: two themes (`default`, `bauhaus`) via `data-theme` attribute and CSS variable overrides.

### API (backend)

- **Route → Service**: routes are thin — business logic goes in `services/`.
- **Metadata persistence**: `.adjutant-web.json` sidecar files in each folder (positions, sections, stickies, images).
- **Auth**: token from env var `ADJUTANT_WEB_SESSION_TOKEN`, checked in `middleware/authenticate`.
- **Access control**: `enforceAccess` middleware blocks writes to read-only KBs.
- **Tests**: colocated as `*.test.ts` alongside source files. Use vitest + supertest.

## Hard Rules

1. **Never hardcode ports.** API: 3020, App: 3021 — configured in Vite proxy and API config.
2. **Never put business logic in route handlers.** Extract to a service.
3. **Never use `any`** — TypeScript strict mode is on in both packages.
4. **Never add global CSS outside `index.css`** — component styles go in CSS Modules.
5. **Never import between `app/` and `api/`** — they are separate packages.
