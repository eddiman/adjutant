# DESIGN.md — Adjutant Web Design Language

> How to build UI that looks and feels like Adjutant. Read this before creating any new component, view, or visual feature.

---

## Philosophy

Adjutant's UI is **glassmorphic, fluid, and quiet**. Surfaces are translucent frosted glass floating over animated gradients. Every state change is animated — nothing teleports. Interactive elements are subtle until hovered or focused. The design conveys calm intelligence.

**Four rules:**
1. **Glass over solid** — use `backdrop-filter: blur` surfaces, not opaque cards.
2. **Animate everything** — hover, focus, open, close, resize. Use the transition tokens.
3. **Tokens over hardcoded values** — every color, spacing, radius, and shadow comes from a CSS variable.
4. **Compose from `ui/`** — use the shared component library. Don't re-implement glass, buttons, badges, overlays, or page shells.

---

## Component Library (`src/components/ui/`)

All shared visual primitives live here. **Always use these instead of writing your own.**

### Glass Surfaces — `GlassSurface.module.css`

Every floating surface (cards, panels, inputs, menus) uses glass. Apply via CSS `composes`:

```css
/* Standard glass — cards, panels, input wrappers */
.myCard {
  composes: glass from '../ui/GlassSurface.module.css';
  position: relative;  /* required for ::before/::after edge highlights */
}

/* Elevated glass — dialogs, menus, popovers (more opaque, readable) */
.myDialog {
  composes: glassElevated from '../ui/GlassSurface.module.css';
  position: relative;
}

/* Glass with focus glow — input containers that need glow on focus-within */
.myInputCard {
  composes: glass glassFocusGlow from '../ui/GlassSurface.module.css';
  position: relative;
}
```

**Important:** Add `position: relative` locally when using `.glass` or `.glassElevated`. The shared class does not set position (to avoid overriding `position: fixed` on elements like sidebars). The `::before`/`::after` highlights need a positioned ancestor.

**Do not** use `.glass` via `composes` on `position: fixed` elements — inline the glass properties instead (see Sidebar for example). CSS module load order can override `position: fixed`.

**Variants:**
| Class | When to use |
|-------|-------------|
| `.glass` | Cards, panels, input wrappers, sidebar, note nodes |
| `.glassElevated` | Dialogs, settings panels, context menus, dropdowns |
| `.glassSubtle` | Toolbars, status bars, thin chrome |
| `.glassFocusGlow` | Add to glass containers with inputs — adds blue glow ring on `:focus-within` |

### Buttons — `Button.module.css`

Compose base + size + variant. Never write button styles from scratch.

```css
/* Primary action button */
.myButton {
  composes: btn md primary from '../ui/Button.module.css';
}

/* Small outlined button */
.mySecondaryButton {
  composes: btn sm outlined from '../ui/Button.module.css';
}

/* Icon-only ghost button (close, back, etc.) */
.myCloseButton {
  composes: btn iconBtn ghost from '../ui/Button.module.css';
}

/* Circular primary icon button (send, fab) */
.mySendButton {
  composes: btn iconCircle primary from '../ui/Button.module.css';
}
```

**Sizes:** `sm` (4/12px padding, 12px font), `md` (8/16px, 13px), `lg` (12/24px, 14px)
**Variants:** `primary` (blue fill), `ghost` (transparent), `outlined` (border), `danger` (red fill)
**Shapes:** `iconBtn` (28px square), `iconBtnMd` (32px square), `iconCircle` (36px circle)

Add local overrides after `composes` for one-off adjustments (e.g., `white-space: nowrap`, hover transforms).

### Badges — `Badge.module.css`

Status indicators, model tags, level labels.

```css
.myBadge {
  composes: badge info from '../ui/Badge.module.css';
}
```

**Variants:** `success` (green), `danger` (red), `info` (blue), `muted` (gray), `dark` (dark bg)

All badges are uppercase, 11px, semibold by default. Override locally if needed (e.g., `text-transform: none` for model badges).

### Dashboard Cards — `<Card>` component

Opaque white cards for the Dashboard's data panels (not glass — these need full readability). Pass `title` and optional `headerAction` for the header row.

```tsx
import { Card } from '../ui';

<Card title="Observer Telemetry" headerAction={<button>Refresh</button>} className={styles.card}>
  <div className={styles.checksList}>...</div>
</Card>
```

Use `className` for local padding overrides. Don't compose from `DashboardCard.module.css` directly — `Card` handles it.

### Modal — `<Modal>` component

Generic dialog shell with glass surface, header (title + close), scrollable content, and optional footer. **Use this for every dialog and picker.**

```tsx
import { Modal } from '../ui';

<Modal open={isOpen} onClose={handleClose} title="Settings" width="25rem">
  <div>...scrollable content...</div>
</Modal>

{/* With footer actions */}
<Modal open={isOpen} onClose={handleClose} title="Browse" width="36rem" footer={
  <button className={styles.selectBtn}>Select</button>
}>
  <div>...file browser...</div>
</Modal>

{/* Nested modal (e.g. folder picker inside settings) */}
<Modal ... layer="dialog-above">...</Modal>
```

**Never** write your own overlay, header+close button, or Escape key handler. Modal handles all of it.

### Overlay — `<Overlay>` component

Low-level backdrop primitive. **Use `<Modal>` instead** for any dialog with a title. Only use `<Overlay>` directly for non-standard overlays (e.g., the confirmation Dialog which has a different layout).

```tsx
import { Overlay } from '../ui';

<Overlay open={isOpen} onClose={handleClose}>
  <div className={styles.customOverlayContent}>...</div>
</Overlay>
```

### TextInput — `TextInput.module.css`

Styled input/select with border, radius, focus glow. CSS-only utility.

```css
.myInput {
  composes: input from '../ui/TextInput.module.css';
  flex: 1;
}

.mySelect {
  composes: select from '../ui/TextInput.module.css';
  min-width: 8rem;
}
```

### Collapsible — `Collapsible.module.css`

Animated expand/collapse via `grid-template-rows`. CSS-only utility.

```css
.myWrapper {
  composes: wrapper from '../ui/Collapsible.module.css';
}

.myWrapperExpanded {
  composes: expanded from '../ui/Collapsible.module.css';
}

.myInner {
  composes: inner from '../ui/Collapsible.module.css';
}
```

```tsx
<div className={`${styles.myWrapper} ${isOpen ? styles.myWrapperExpanded : ''}`}>
  <div className={styles.myInner}>
    {/* collapsible content */}
  </div>
</div>
```

### PageShell — `<PageShell>` component

Full-page layout for scrollable views (Dashboard, Chat list). Handles sidebar offset, background pinning, content max-width.

```tsx
import { PageShell } from '../ui';
import { AnimatedBackground } from '../Home/AnimatedBackground';

<PageShell sidebarOpen={sidebarOpen} background={<AnimatedBackground />}>
  <nav>...</nav>
  <main>...</main>
</PageShell>
```

**Do not** use PageShell for the active chat session view or the canvas — those have their own fixed-height flex layouts.

---

## Design Tokens (`index.css`)

All values come from CSS custom properties. **Never hardcode colors, spacing, or shadows.**

### Colors

Use semantic tokens, not raw values:
- `var(--color-primary)` / `var(--color-primary-hover)` — CTAs, links, active states
- `var(--color-text)` / `var(--color-text-secondary)` / `var(--color-text-muted)` — text hierarchy
- `var(--color-bg)` / `var(--color-card)` — page and surface fills
- `var(--color-border)` / `var(--color-border-light)` — dividers
- `var(--color-success)` / `var(--color-warning)` / `var(--color-danger)` — semantic states
- `var(--color-hover-bg)` / `var(--color-active-bg)` — interaction states

### Glass

- `var(--glass-bg)` / `var(--glass-blur)` / `var(--glass-border)` / `var(--glass-shadow)` — standard
- `var(--glass-elevated-bg)` / `var(--glass-elevated-blur)` / `var(--glass-elevated-shadow)` — dialogs
- `var(--glass-subtle-bg)` / `var(--glass-subtle-blur)` — toolbars
- `var(--glass-highlight-top)` / `var(--glass-highlight-left)` — edge highlight gradients
- `var(--glass-radius)` — standard glass border-radius (20px)

### Spacing

4px base unit: `var(--spacing-1)` = 4px through `var(--spacing-24)` = 96px. Use these for all padding, margins, and gaps.

### Typography

- `var(--font-heading)` — Jost (headings)
- `var(--font-body)` — Jost (body text)
- Sizes: `var(--font-size-xxs)` (11px) through `var(--font-size-5xl)` (40px)
- Weights: `var(--font-weight-normal)` (400), `var(--font-weight-medium)` (500), `var(--font-weight-semibold)` (600), `var(--font-weight-bold)` (700)

### Transitions

- `var(--transition-fast)` — 150ms ease (hovers, color changes)
- `var(--transition-normal)` — 200ms ease (input focus, small shifts)
- `var(--transition-medium)` — 250ms ease (sidebar toggle, card expand)
- `var(--transition-smooth)` — 300ms cubic-bezier (modals, view transitions)
- `var(--transition-bounce)` — 500ms spring (entrances, pop-ins)

### Z-index stack

`var(--z-dropdown)` (10) < `var(--z-toolbar)` (100) < `var(--z-sidebar)` (201) < `var(--z-dialog)` (300) < `var(--z-context-menu)` (1000)

---

## Building New Components

### Checklist

1. **Surface**: Use `composes: glass` or `composes: glassElevated` — don't write your own `backdrop-filter`.
2. **Buttons**: Use `composes: btn [size] [variant]` — don't write your own button base.
3. **Badges**: Use `composes: badge [variant]` — don't write your own badge base.
4. **Overlays**: Use `<Overlay>` — don't write your own backdrop or escape handler.
5. **Page layouts**: Use `<PageShell>` — don't write your own root/sidebarOpen/content shell.
6. **Colors**: Use `var(--color-*)` tokens — don't hardcode hex values.
7. **Spacing**: Use `var(--spacing-*)` tokens — don't hardcode px/rem values.
8. **Animations**: Use `var(--transition-*)` tokens — don't hardcode durations/easings.
9. **Icons**: Outlined SVG, 1.5px stroke, 18px default, `currentColor` fill.
10. **Accessibility**: 44px minimum touch targets, visible focus rings, `prefers-reduced-motion` support.

### File structure

One folder per component:
```
src/components/MyComponent/
  MyComponent.tsx
  MyComponent.module.css
  index.ts          # export { MyComponent } from './MyComponent';
```

### CSS module pattern

```css
/* MyComponent.module.css */
.root {
  composes: glass from '../ui/GlassSurface.module.css';
  position: relative;
  padding: var(--spacing-4);
  transition: box-shadow var(--transition-smooth);
}

.title {
  font-family: var(--font-heading);
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-semibold);
  color: var(--color-text);
  margin: 0;
}

.actionButton {
  composes: btn md primary from '../ui/Button.module.css';
}
```

### Dialog/modal pattern

```tsx
import { Overlay } from '../ui';

function MyDialog({ open, onClose }) {
  return (
    <Overlay open={open} onClose={onClose}>
      <div className={styles.dialog}>
        <header className={styles.header}>
          <h2>Title</h2>
          <button className={styles.closeBtn} onClick={onClose}>
            <svg>...</svg>
          </button>
        </header>
        <div className={styles.content}>...</div>
      </div>
    </Overlay>
  );
}
```

```css
.dialog {
  composes: glassElevated from '../ui/GlassSurface.module.css';
  position: relative;
  width: 28rem;
  max-width: 90vw;
  animation: slideIn 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.closeBtn {
  composes: btn iconBtn ghost from '../ui/Button.module.css';
}
```

---

## Themes

Two themes available via `data-theme` attribute on `<html>`:

### Default
Glass morphism, blue primary, rounded corners, subtle shadows. This is the main design.

### Bauhaus
Geometric modernism. No glass, no shadows, no border-radius. Solid surfaces, hard black borders, primary red/blue/yellow palette. All `var(--glass-*)` tokens still exist but resolve to opaque values. All `var(--radius-*)` tokens resolve to 0.

Themes switch via CSS variable overrides in `index.css`. Components don't need to know which theme is active — they use tokens.

---

## Animations

### Mandatory

Every component must animate these state changes:
- **Hover**: scale, shadow, or background shift (150ms)
- **Focus**: border glow or ring (200ms)
- **Open/close**: scale + fade (200-300ms)
- **Expand/collapse**: height transition (250ms)

### How

Use the transition tokens. For entries, use `@keyframes` with `cubic-bezier(0.34, 1.56, 0.64, 1)` (spring) for bouncy pop-in, or `cubic-bezier(0.4, 0, 0.2, 1)` for smooth slide-in.

### Reduced motion

Always wrap decorative animations:
```css
@media (prefers-reduced-motion: reduce) {
  .myElement {
    animation: none;
    transition-duration: 0ms;
  }
}
```

---

## For Adjutant (AI Agent) — generating UI

When Adjutant generates UI artifacts (web views, reports, data visualizations):

1. **Use the same token system** — reference `var(--color-*)`, `var(--spacing-*)`, `var(--font-*)`.
2. **Glass surfaces** for containers — apply `backdrop-filter: blur(30px)` with `rgba(255,255,255,0.15)` background.
3. **The blue/pink palette** — primary blue `#3B67F6`, accent pink `#F7A9F1`.
4. **Jost headings, Jost body** — load from Google Fonts.
5. **Rounded corners** — 20px for cards, 8px for buttons, 6px for badges.
6. **Subtle shadows** with inner highlight: `box-shadow: 0 8px 32px rgba(0,0,0,0.08), inset 0 1px 0 rgba(255,255,255,0.5)`.
7. **Animated backgrounds** — if appropriate, use slow-moving gradient blobs at low opacity.
8. **Never use solid opaque white cards** — always translucent.
9. **Content max-width 1280px**, centered with auto margins.
10. **Icons**: outlined SVG, 1.5px stroke weight, `currentColor`.
