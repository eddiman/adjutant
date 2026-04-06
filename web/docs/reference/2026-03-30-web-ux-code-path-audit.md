# Adjutant Web — Code Path Analysis & UX Risk Audit

**Date:** 2026-03-30
**Scope:** `web/app/src/` — all components, hooks, utilities, and interaction paths
**Method:** Full static code-path analysis of every user-facing feature

**Fix status updated:** 2026-03-30 — 14 of 23 issues fixed across 4 implementation batches.

---

## 1. Undo/Redo System — History Integrity

### Code Path
`useCanvasHistory.ts` → `Canvas.tsx:applyHistoryState` → position persistence callbacks

### Risks

**1.1 Undo returns `null` due to async state lag (Severity: Medium)** — ✅ FALSE POSITIVE
`useCanvasHistory.undo()` reads `past` from a `useState` setter callback but returns the action variable set *inside* the setter. Verified that the local variable captures the value correctly before `setState` executes — this is not a bug.

- **File:** `useCanvasHistory.ts:78-92`
- **Status:** No fix needed — verified as false positive.

**1.2 History only tracks moves — deletes, creates, resizes are not undoable (Severity: Medium)**
`historyPush` is only called from `handleNodeDragStop`. Section resize, sticky text edits, note creation/deletion, and section creation/deletion never push to history. Users who resize a section or delete a sticky have no undo path.

- **Files:** `useCanvasNodeDrag.ts:186`, `Canvas.tsx:updateNodePositions`
- **Impact:** Users lose work with no recovery for non-move operations.

**1.3 Undo does not restore contained-node positions from section drag (Severity: Low)**
When a section is dragged and contained nodes move with it, both the section and contained nodes are recorded in history snapshots. However, if a user undoes and then manually moves a contained node before redoing, the redo applies stale positions.

---

## 2. Snap-to-Guides — Dimension Mismatch

### Code Path
`useSnapToGuides.ts:getNodeBounds` → `calculateSnap`

### Risks

**2.1 Hardcoded dimensions ignore actual node sizes (Severity: High)** — ✅ FIXED
`useSnapToGuides` used a fixed `NODE_DIMENSIONS` map with only `note` (200x283) and `folder` (220x100). Sections, stickies, and images all fell through to the `note` default.

- **File:** `useSnapToGuides.ts`
- **Fix applied:** Expanded `DEFAULT_DIMENSIONS` to include section (500×400), sticky (150×150), image (300×200). Rewrote `getNodeDimensions()` to prefer `node.measured` → `node.data.displayWidth/Height` → `node.data.width/height` → type-specific fallbacks.

**2.2 First-match-wins short-circuits alignment checks (Severity: Low)**
The snap loops use `if/else if` chains — once a left-to-left snap is found, right-to-right, center-to-center, etc. are skipped for that target node. If two edges are both within threshold, only the first enumerated alignment wins, which may not be the closest.

- **File:** `useSnapToGuides.ts:72-121`

---

## 3. Section Containment — Dual Implementations

### Code Path
`sectionPositioning.ts:isNodeInsideSection` vs `useCanvasKeyboard.ts:isNodeInsideSection` (local)

### Risks

**3.1 Two independent `isNodeInsideSection` implementations can diverge (Severity: Medium)** — ✅ FIXED
`useCanvasKeyboard.ts` had its own local copy of `isNodeInsideSection` that diverged from the canonical version in `sectionPositioning.ts`.

- **Fix applied:** Deleted local copy in `useCanvasKeyboard.ts`, replaced with import from `sectionPositioning.ts`.

**3.2 Section containment uses center-point, not area overlap (Severity: Low)**
A note whose center is 1px outside a section boundary is not considered contained, even if 99% of its area overlaps visually. This is a design choice but can confuse users who see a note visually inside a section yet it doesn't move with the section.

---

## 4. Node Position Persistence — Race Conditions

### Code Path
`useRecursiveFolder.ts` → debounced `saveMeta` → `PUT /api/folders/meta`

### Risks

**4.1 Debounced save can merge stale partial updates (Severity: High)**
`pendingMetaRef.current` accumulates updates between debounce flushes using spread: `{ ...pendingMetaRef.current, items: { ...existing, [key]: update } }`. If two different items are updated within 300ms, both are correctly batched. But if the *same* item is updated twice (e.g., rapid drag), the second update overwrites the first in `pendingMetaRef` before the save fires — this is correct. However, if a save fires *between* two updates to the same item, the first update is sent, then `pendingMetaRef` is cleared, and the second update starts a new pending batch. If the server processes the first PUT *after* the second PUT arrives, the first (stale) position wins.

- **File:** `useRecursiveFolder.ts:218-284`
- **Impact:** Under high server latency, node positions can revert to stale values.

**4.2 Subfolder item positions bypass debouncing entirely (Severity: Medium)** — ✅ FIXED
`updateItemPosition` for notes inside subdirectories fired an immediate `fetch()` with no debounce.

- **File:** `useRecursiveFolder.ts`
- **Fix applied:** Added per-subfolder debounce system (`subfolderPendingRef`, `subfolderDebouncersRef`) with 300ms debounce matching the root-level pattern. Debouncer map cleared on `kb`/`folderPath` change.

**4.3 `pendingMetaRef.current` is cleared before the save completes (Severity: Medium)** — ✅ FIXED
`saveMeta` cleared `pendingMetaRef.current = {}` before the `await fetch`, so failed saves silently lost updates.

- **File:** `useRecursiveFolder.ts`
- **Fix applied:** `pendingMetaRef` is now only cleared on successful save. On failure, pending data is deep-merged back and a retry is scheduled (max 3 attempts).

---

## 5. Clipboard / Paste — Broken Duplicate Handlers

### Code Path
`useCanvasClipboard.ts` → `onNoteDuplicate` / `onImageDuplicate` → `App.tsx`

### Risks

**5.1 Note and image duplicate handlers are no-ops (Severity: High)** — ✅ FIXED
Both `onNoteDuplicate` and `onImageDuplicate` in `App.tsx` were empty `async () => {}` no-ops.

- **File:** `App.tsx`
- **Fix applied:** `onNoteDuplicate` now fetches source note via `getNote()`, creates a copy with "(copy)" title suffix at the new position, copies content and tags. `onImageDuplicate` fetches the source image blob and re-uploads at the new position.

**5.2 Image paste from clipboard works, node paste does not (Severity: Low)**
Pasting an image file from system clipboard (e.g., screenshot) correctly calls `onImagePaste` → `uploadImage`. But pasting previously-copied *nodes* routes through the broken duplicate handlers above. Users may think paste is "partially broken" without understanding why.

---

## 6. Section Drag — Note Section-Change Detection

### Code Path
`useCanvasNodeDrag.ts:handleNodeDragStop` → `onNoteSectionChange` → `App.tsx:handleNoteSectionChange` → move dialog

### Risks

**6.1 Dragging a section over unsectioned notes triggers unexpected move dialogs (Severity: Medium)** — ✅ FIXED
After a section drag, the code iterated all notes and fired `onNoteSectionChange` for any note now inside the section, triggering unwanted move dialogs.

- **File:** `useCanvasNodeDrag.ts`
- **Fix applied:** Removed the section-drag note membership check block. Note-drag section-change detection (the intentional case) is preserved.

**6.2 `revertPosition` is always `{x:0, y:0}` (Severity: Low)**
In `App.tsx:332`: `revertPosition: { x: 0, y: 0 }`. The cancel handler calls `refetchFolder()` instead of using this value, so it's harmless, but the dead field suggests incomplete implementation.

---

## 7. Sidebar Navigation — Folder Click Ambiguity

### Code Path
`Sidebar.tsx:handleFolderClick` → `onFolderFocus` (pan to section) vs `onFolderOpen` (navigate into folder)

### Risks

**7.1 Single-click on folder only focuses section, never navigates (Severity: Medium)** — ✅ FIXED
When the canvas was active, clicking a folder always called `onFolderFocus` (pan) instead of `onFolderOpen` (navigate).

- **File:** `Sidebar.tsx`
- **Fix applied:** Folder click now calls `onFolderOpen` (navigate) by default. Added a separate crosshair/focus button for panning to the section on canvas.

**7.2 Mobile: "Enter" button requires hover, inaccessible on touch (Severity: Medium)** — ✅ FIXED
The folder enter button only appeared on `:hover`, invisible on touch devices.

- **File:** `Sidebar.module.css`
- **Fix applied:** Added `@media (hover: none)` block setting both enter and focus buttons to `opacity: 0.6` for permanent visibility on touch devices.

---

## 8. Note Editor — Timing-Based Workflows

### Code Path
`App.tsx:onNoteOpen` (sidebar) → `focusOnNode` → `setTimeout(650)` → `handleNoteOpen`

### Risks

**8.1 Hardcoded 650ms timeout for opening notes from sidebar (Severity: Medium)** — ✅ FIXED
A hardcoded `setTimeout(650)` was used after the 600ms pan animation.

- **File:** `App.tsx`
- **Fix applied:** Extracted `FOCUS_ANIMATION_MS = 600` constant. Now uses `setTimeout(FOCUS_ANIMATION_MS)` + `requestAnimationFrame` for the note open call.

**8.2 `handleHomeNoteSelect` uses 100ms timeout to set focused note (Severity: Low)**
`App.tsx:283-286`: After navigating to a folder from the home page, a 100ms timeout sets the focused note. If folder data hasn't loaded in 100ms, the editor opens with stale or missing data.

---

## 9. React Flow Node Sync — Multiple `setNodes` Cascades

### Code Path
`Canvas.tsx` — 7 separate `useEffect` hooks that call `setNodes`

### Risks

**9.1 Multiple effects trigger cascading re-renders on every data change (Severity: Medium)** — ✅ FIXED
Six independent `useEffect` hooks each called `setNodes`, causing cascading re-renders.

- **File:** `Canvas.tsx`
- **Fix applied:** Consolidated data sync, resize callback sync, pan mode sync, and highlighted node sync into a single combined `useEffect`. Structural sync and section focus remain separate. Worst-case re-renders reduced from 6 to 2.

**9.2 `initialNodes` useMemo includes `onSectionResize` and `onStickyTextChange` callbacks (Severity: Low)**
Since these callbacks are recreated when dependencies change, `initialNodes` recalculates unnecessarily. The node structure key effect then detects no change (IDs/sizes haven't changed), but the memo work was already done.

- **File:** `Canvas.tsx:270-339`

---

## 10. Keyboard Shortcuts — Conflict & Accessibility

### Code Path
`useCanvasKeyboard.ts` — global `keydown` listener

### Risks

**10.1 `S` and `T` keys conflict with text input if focus escapes (Severity: Medium)** — ✅ FIXED
After editing a sticky and clicking the canvas, pressing S/T immediately entered placement mode.

- **File:** `useCanvasKeyboard.ts`
- **Fix applied:** Added `lastEditableBlurRef` tracking when INPUT/TEXTAREA/contentEditable elements lose focus. S/T handlers are guarded with a 200ms cooldown after the last editable blur.

**10.2 No keyboard shortcut for creating notes (Severity: Low)**
Notes require clicking the toolbar or using placement mode. Sections (`S`) and stickies (`T`) have shortcuts but notes do not, despite being the most common creation action.

**10.3 Backspace as delete conflicts with browser back navigation (Severity: Low)**
On some browsers/OS combinations, Backspace triggers browser back navigation. The handler calls `e.preventDefault()` which blocks this, but only when items are selected. If nothing is selected, Backspace falls through and may navigate away, losing canvas state.

- **File:** `useCanvasKeyboard.ts:182-191`

---

## 11. Touch Support — Incomplete Gesture Handling

### Code Path
`useCanvasTouchGestures.ts`, `Canvas.tsx` touch-specific logic

### Risks

**11.1 Pan mode is permanently on for touch devices (Severity: Medium)** — ✅ FIXED
`App.tsx` always passed `activeTool="pan"` and never rendered the `ToolSwitcher` component.

- **File:** `App.tsx`
- **Fix applied:** Added `activeTool` state with `useState<CanvasTool>('pan')`. `ToolSwitcher` is now conditionally rendered on `isTouchDevice()`. Touch users can switch between pan and select modes.

**11.2 Context menu long-press (500ms) can conflict with scroll/pan (Severity: Low)**
If a user starts a long-press but moves their finger slightly during the 500ms window, both the pan gesture and the context menu timer are active. The context menu may appear mid-pan.

---

## 12. Section Resize — Position Delta for Non-BR Corners

### Code Path
`SectionNode.tsx:computeResize` → `finishResize` → `Canvas.tsx:handleSectionResizeWithDelta`

### Risks

**12.1 Resize from TL/TR/BL corners shifts node position but doesn't move contained nodes (Severity: Medium)** — ✅ FIXED
When resizing from non-BR corners, the section position shifted but contained nodes stayed in place.

- **File:** `Canvas.tsx`
- **Fix applied:** `handleSectionResizeWithDelta` now finds contained nodes before shifting and applies the same (dx, dy) offset to them. Shifted positions are persisted via existing position change callbacks.

---

## 13. Directory Section Auto-Layout

### Code Path
`sectionPositioning.ts:layoutDirectoryTree` → `flattenDirLayouts` → `useRecursiveFolder.ts`

### Risks

**13.1 Fixed 3-column grid doesn't adapt to section width (Severity: Low)**
`layoutDirectoryTree` always uses 3 columns for notes regardless of how wide the user has resized the section. A very wide section wastes space; a narrow section has notes overflowing its bounds.

- **File:** `sectionPositioning.ts:287, 361-373`

**13.2 Depth-3 tree limit silently truncates deeply nested folders (Severity: Low)**
`useRecursiveFolder.ts:127`: `depth: '3'`. Folders nested 4+ levels deep are invisible on the canvas. No UI indication that content is missing.

---

## 14. Route/State Management

### Code Path
`App.tsx` routes → `useCanvas.ts` → URL-based state

### Risks

**14.1 Every route mounts a new `AppWithProviders` — full state reset (Severity: Low)**
All routes render `<AppWithProviders />` independently. Navigating between `/` and `/:kb` unmounts and remounts the entire component tree, including all providers. This causes:
- Canvas position/zoom resets
- Sidebar state flashes
- History stack is lost
- All pending debounced saves are abandoned

**14.2 No loading state or error boundary for lazy-loaded components (Severity: Low)** — ✅ FIXED
`NoteEditor` and `SettingsDialog` used `<Suspense fallback={null}>` with no error handling for chunk load failures.

- **File:** `App.tsx`, new `components/ErrorBoundary/ErrorBoundary.tsx`
- **Fix applied:** Created class-based `ErrorBoundary` component with retry button UI. Both `Suspense` blocks are now wrapped with `<ErrorBoundary>`.

---

## 15. Delete Confirmation — Inconsistent Node ID Handling

### Code Path
`Canvas.tsx:getDeleteDialogMessage` → note lookup

### Risks

**15.1 Delete dialog shows "Untitled" for notes with paths (Severity: Low)** — ✅ FIXED
The delete dialog used `note-${n.filename}` for lookup but node IDs use `note-${n.path}`, causing subfolder notes to show "Untitled".

- **File:** `Canvas.tsx`
- **Fix applied:** Changed to `note-${n.path}`.

---

## 16. Image Upload & Display

### Code Path
`useImages.ts` → `uploadImage` → `Canvas.tsx` ImageNode rendering

### Risks

**16.1 No file size validation on upload (Severity: Low)**
`handleImageInputChange` checks `file.type.startsWith('image/')` but has no size limit. A user can paste/upload a 500MB image, causing the upload to hang and the browser to struggle with rendering.

---

## Summary — Risk Priority Matrix

| # | Issue | Severity | User Impact | Status |
|---|-------|----------|-------------|--------|
| 5.1 | Copy/paste handlers are no-ops | **High** | Core feature completely broken | ✅ Fixed |
| 2.1 | Snap guides use wrong dimensions for sections/images/stickies | **High** | Alignment feature misleads users | ✅ Fixed |
| 4.1 | Debounced save race condition | **High** | Positions silently revert | Open |
| 11.1 | Touch devices locked in pan mode | **Medium** | Selection/drag disabled on mobile | ✅ Fixed |
| 4.2 | Subfolder notes flood server on drag | **Medium** | Performance degradation | ✅ Fixed |
| 1.1 | Undo can skip actions on rapid press | **Medium** | Lost undo capability | False positive |
| 1.2 | Only moves are undoable | **Medium** | No undo for deletes/resizes | Open |
| 3.1 | Dual `isNodeInsideSection` implementations | **Medium** | Inconsistent containment results | ✅ Fixed |
| 6.1 | Section drag triggers unwanted move dialogs | **Medium** | Confusing prompts | ✅ Fixed |
| 7.1 | Folder click pans instead of navigating | **Medium** | Non-intuitive navigation | ✅ Fixed |
| 7.2 | Mobile: folder enter button inaccessible | **Medium** | Navigation broken on touch | ✅ Fixed |
| 8.1 | Hardcoded 650ms timeout for note open | **Medium** | Jarring animation on slow devices | ✅ Fixed |
| 9.1 | 6 cascading `setNodes` effects | **Medium** | Frame drops on large canvases | ✅ Fixed |
| 10.1 | S/T keys conflict with typing | **Medium** | Unexpected mode changes | ✅ Fixed |
| 12.1 | Non-BR resize doesn't move contained nodes | **Medium** | Visual disconnect | ✅ Fixed |
| 4.3 | Failed save silently loses updates | **Medium** | Data loss on network errors | ✅ Fixed |
| 15.1 | Delete dialog shows "Untitled" for subfolder notes | **Low** | Cosmetic confusion | ✅ Fixed |
| 13.1 | Fixed 3-column layout ignores section width | **Low** | Suboptimal space use | Open |
| 13.2 | Depth-3 limit truncates deep folders | **Low** | Missing content | Open |
| 14.1 | Route change resets all state | **Low** | State flash on navigation | Open |
| 14.2 | No error boundary for lazy components | **Low** | Silent failure | ✅ Fixed |
| 10.2 | No keyboard shortcut for note creation | **Low** | Workflow gap | Open |
| 16.1 | No image upload size limit | **Low** | Performance risk | Open |
