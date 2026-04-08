# Component Library Extraction

**Date**: 2026-04-07
**Status**: Complete — Phase 1 (7 batches) + Phase 2 (5 batches) done

## Context

The redesign introduced a glass-morphic design system with `--glass-*` CSS tokens, but the same surface/button/overlay patterns got copy-pasted into 12+ CSS modules and several TSX files use hardcoded inline styles. This makes visual consistency fragile — changing one card means hunting down every copy. This plan extracts the duplicated patterns into a small set of shared CSS utilities and two React components under `src/components/ui/`.

## What gets extracted (3+ duplications only)

### 1. `GlassSurface.module.css` — CSS utility (no React component)

**Why not a component**: Glass is applied to structurally different elements (sidebar, input card, note card, context menu). A wrapper div would break layouts.

**Classes**:
- `.glass` — standard: bg, blur, webkit-blur, border, shadow, radius, overflow hidden, position relative, plus `::before` (top highlight) and `::after` (left highlight)
- `.glassElevated` — elevated variant (dialogs, menus): higher opacity bg, stronger blur/shadow, brighter border
- `.glassSubtle` — subtle variant (toolbars, status bars): lower opacity, less blur
- `.glassFocusGlow` — `:focus-within` adds primary glow ring

**Replaces duplicate CSS in** (8 files):
- `Sidebar.module.css` (.sidebar + ::before + ::after) ~22 lines
- `NoteNode.module.css` (.note-node + ::before + ::after) ~22 lines
- `Home.module.css` (.promptCard + highlights + .setupCard) ~44 lines
- `InputArea.module.css` (.inputCard + ::before + ::after) ~22 lines
- `SessionList.module.css` (.folderCard + ::before) ~14 lines
- `ContextMenu.module.css` (.context-menu) ~8 lines
- `Dialog.module.css` (.dialog-container + ::before) ~12 lines
- `SettingsDialog.module.css` (.settings-dialog + ::before) ~16 lines

### 2. `Overlay` — React component

Handles modal backdrop: fixed inset, rgba bg, blur, centering, click-to-close, Escape key.

**Props**: `open`, `onClose`, `layer?` ('dialog' | 'dialog-above'), `children`

**Replaces duplicate code in** (5 files):
- `Dialog.tsx` / `Dialog.module.css` — overlay CSS + Escape handler
- `SettingsDialog.tsx` / `SettingsDialog.module.css` — identical overlay CSS
- `FolderExplorer.tsx` / `FolderExplorer.module.css` — overlay CSS
- `ModelPicker.tsx` — inline-style overlay (4 lines)
- `WorkingDirPicker.tsx` — inline-style overlay + Escape handler

### 3. `DashboardCard.module.css` — CSS utility

**Classes**: `.card`, `.cardTitle`

**Replaces identical CSS in** (6 files):
- `ActivityFeed.module.css`, `HealthChecks.module.css`, `QuickActions.module.css`, `SchedulesManager.module.css`, `LastPulse.module.css`, `IdentityDisplay.module.css`

### 4. `PageShell` — React component

Handles full-page layout: fixed inset, sidebar offset transition, AnimatedBackground pinning, content max-width wrapper.

**Props**: `sidebarOpen`, `background?`, `maxWidth?`, `className?`, `children`

**Replaces duplicate layout in** (2 files):
- `AdjutantDashboard.tsx` / `.module.css` — root + sidebarOpen + bg pinning + content
- `CodeSession.tsx` / `.module.css` — identical pattern

### 5. `Button.module.css` — CSS utility

**Classes**: `.btn` (base), sizes `.sm`/`.md`/`.lg`, variants `.primary`/`.ghost`/`.outlined`/`.danger`, shapes `.iconBtn`/`.iconBtnMd`/`.iconCircle`

**Replaces inconsistent button styles in** (6+ files):
- `SettingsDialog.module.css` (close btn, save btn, browse btn)
- `FolderExplorer.module.css` (close btn, select btn)
- `Dialog.module.css` (confirm/cancel buttons)
- `CodeSession.module.css` (headerBackBtn, newSessionBtn, headerBtn)
- `Home.module.css` (setupButton)
- `InputArea.module.css` (sendBtn, cancelBtn)

### 6. `Badge.module.css` — CSS utility

**Classes**: `.badge` (base), variants `.success`/`.danger`/`.info`/`.muted`/`.dark`

**Replaces in** (4 files): SystemStatus, ActivityFeed, CodeSession headerBadge, MessageBubble errorBadge

## What NOT to extract

- **Input fields** — only 3 similar, each structurally different (textarea vs input vs select)
- **Animation keyframes** — CSS `@keyframes` can't be shared via `composes`, duplication is 3-5 lines each
- **Canvas node colors** — only used in 2 files, canvas-specific
- **ContextMenu items** — only used in one place

## File structure

```
src/components/ui/
  GlassSurface.module.css
  DashboardCard.module.css
  Button.module.css
  Badge.module.css
  Overlay/
    Overlay.tsx
    Overlay.module.css
    index.ts
  PageShell/
    PageShell.tsx
    PageShell.module.css
    index.ts
  index.ts              # barrel: re-export Overlay, PageShell
```

## Migration batches

Each consumer migration: replace local CSS with `composes: className from '../ui/File.module.css'`, delete the now-redundant local rules. For React components (Overlay, PageShell), replace the JSX wrapper.

| Batch | Scope | Files | Status |
|-------|-------|-------|--------|
| 1 | Create all shared files | 10 new files | Done |
| 2 | Dashboard cards | 6 CSS files | Done |
| 3 | Glass surfaces | 8 CSS files + 1 TSX | Done |
| 4 | Buttons | 6 CSS files | Done |
| 5 | Badges | 3 CSS files | Done |
| 6 | Overlay component | 5 TSX + CSS files | Done |
| 7 | PageShell component | 2 TSX + CSS files | Done |

## Verification

After each batch:
1. `npx tsc --noEmit` — type check
2. `npx vite build` — production build
3. Visual check: Home, Canvas with notes, Settings dialog, Chat session list, Chat active session, Dashboard — all should look identical to before
