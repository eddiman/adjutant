# Adjutant Design System

> The visual language for Adjutant across web app and documentation site. Every surface, component, and interaction should feel like it belongs to the same product.

---

## 1. Design Philosophy

**Glassmorphic, fluid, alive.** Adjutant's UI feels like looking through frosted glass panels floating over a softly moving background. Surfaces are translucent, edges glow faintly, and every state change is animated — nothing snaps, everything flows. The design communicates intelligence and calm precision without feeling cold.

**Core principles:**
- **Layered depth** — UI elements exist on distinct depth planes, separated by blur, opacity, and shadow. Background layer, content layer, overlay layer.
- **Translucency over opacity** — Cards, sidebars, toolbars, and modals use frosted glass (`backdrop-filter: blur`) rather than solid fills. The background bleeds through, creating a sense of spatial continuity.
- **Continuous motion** — Transitions between states, sizes, and views are always animated. No hard cuts. Elements slide, scale, and fade between states using spring-like easing.
- **Quiet until needed** — Decorative elements (gradients, blobs, glows) are subtle and ambient. They enhance without distracting. Interactive elements announce themselves on hover/focus with gentle scale and glow changes.

---

## 2. Glass & Surface Treatment

### Glass Surfaces

The primary surface treatment across the entire system. Used for: cards, sidebars, toolbars, modals, dropdowns, status bars, and any floating UI.

```css
/* Standard glass surface */
background: rgba(255, 255, 255, 0.55);
backdrop-filter: blur(20px) saturate(1.4);
-webkit-backdrop-filter: blur(20px) saturate(1.4);
border: 1px solid rgba(255, 255, 255, 0.25);
box-shadow: 0 4px 24px rgba(0, 0, 0, 0.06), inset 0 1px 0 rgba(255, 255, 255, 0.4);
```

```css
/* Elevated glass (modals, popovers) */
background: rgba(255, 255, 255, 0.7);
backdrop-filter: blur(32px) saturate(1.6);
border: 1px solid rgba(255, 255, 255, 0.35);
box-shadow: 0 8px 40px rgba(0, 0, 0, 0.1), 0 2px 8px rgba(0, 0, 0, 0.04), inset 0 1px 0 rgba(255, 255, 255, 0.5);
```

```css
/* Subtle glass (toolbars, status bars) */
background: rgba(255, 255, 255, 0.35);
backdrop-filter: blur(12px) saturate(1.2);
border: 1px solid rgba(255, 255, 255, 0.15);
```

```css
/* Dark mode glass */
background: rgba(20, 20, 30, 0.6);
backdrop-filter: blur(20px) saturate(1.4);
border: 1px solid rgba(255, 255, 255, 0.08);
box-shadow: 0 4px 24px rgba(0, 0, 0, 0.2), inset 0 1px 0 rgba(255, 255, 255, 0.05);
```

### Surface Hierarchy

| Layer | Blur | Opacity | Use |
|-------|------|---------|-----|
| **Background** | none | 100% | Page background, canvas, gradient |
| **Ground glass** | 12px | 35% white | Toolbar, status bar, sidebar |
| **Standard glass** | 20px | 55% white | Cards, panels, list items |
| **Elevated glass** | 32px | 70% white | Modals, dialogs, editors |
| **Overlay** | 40px | 80% white | Critical dialogs, full-screen overlays |

### Edge Glow

Glass surfaces have a faint inner highlight along their top edge (`inset 0 1px 0 rgba(255,255,255,0.4)`) that simulates light catching the edge of glass. This is essential to the frosted glass illusion.

---

## 3. Color Palette

### Primary & Accent

| Token | Light Mode | Dark Mode | Usage |
|-------|-----------|-----------|-------|
| **Primary** | `#3B67F6` | `#8DADEE` | CTAs, links, active states, focus rings |
| **Primary Hover** | `#2952E0` | `#6B93E4` | Hover states |
| **Primary Background** | `rgba(59,103,246, 0.08)` | `rgba(141,173,238, 0.12)` | Active nav items, selection tint |
| **Accent (Pink)** | `#F7A9F1` | `#E8A4D4` | Highlights, badges, decorative glow |
| **Accent Light** | `#FEF5FD` | dark equivalent | Accent backgrounds |

### Blue Scale
`50: #EEF2FE` · `100: #DFE6FD` · `200: #C5D2FB` · `300: #9FB4F9` · `400: #6B8DF7` · `500: #3B67F6` · `600: #2952E0` · `700: #2142B8` · `800: #1A3491` · `900: #152A73` · `950: #0D1A4A`

### Pink Scale
`50: #FEF5FD` · `100: #FDEBFB` · `200: #FBD7F8` · `300: #F9C3F4` · `400: #F7A9F1` · `500: #F07BE6` · `600: #E34DD6` · `700: #C733B8` · `800: #A32B97` · `900: #7E2375` · `950: #55174F`

### Neutrals

| Token | Light | Dark | Usage |
|-------|-------|------|-------|
| **Background** | `#F5F5F5` | `#0E0E14` | Page fill behind glass |
| **Card** | `#FFFFFF` at 55% opacity | `#1A1A2E` at 60% opacity | Glass surface base |
| **Text** | `#1A1A1A` | `#E8E8EE` | Primary text |
| **Text Secondary** | `#666666` | `#9999AA` | Labels, captions |
| **Text Muted** | `#999999` | `#666677` | Placeholders, disabled |
| **Border** | `rgba(255,255,255, 0.25)` | `rgba(255,255,255, 0.08)` | Glass panel borders |
| **Border Solid** | `#E0E0E0` | `#2A2A3A` | Dividers, input borders |

### Semantic

| Token | Value | Usage |
|-------|-------|-------|
| **Success** | `#2ECC71` | Health OK, connected, saved |
| **Warning** | `#E67E22` | Degraded, caution |
| **Danger** | `#C0392B` | Error, destructive, offline |
| **Info** | `#3B67F6` (primary) | Informational callouts |

---

## 4. Typography

| Role | Font | Weight | Size | Line Height |
|------|------|--------|------|-------------|
| **Display** | Jost | 700 | 40px (2.5rem) | 1.1 |
| **H1** | Jost | 700 | 32px (2rem) | 1.2 |
| **H2** | Jost | 600 | 24px (1.5rem) | 1.2 |
| **H3** | Jost | 600 | 20px (1.25rem) | 1.3 |
| **Body** | Jost | 400 | 14px (0.875rem) | 1.5 |
| **Body Small** | Jost | 400 | 13px (0.8125rem) | 1.5 |
| **Label** | Jost | 500 | 12px (0.75rem) | 1.3 |
| **Caption** | Jost | 500 | 11px (0.6875rem) | 1.3 |
| **Code** | system monospace | 400 | 13px (0.8125rem) | 1.6 |

**Loading**: Jost via Google Fonts (weights 300, 400, 500, 600, 700). Jost via Google Fonts (weights 400, 500, 600).

---

## 5. Spacing

Base unit: **4px**. All spacing derives from this scale.

| Token | Value | Px |
|-------|-------|----|
| `spacing-0` | 0 | 0 |
| `spacing-0.5` | 0.125rem | 2 |
| `spacing-1` | 0.25rem | 4 |
| `spacing-1.5` | 0.375rem | 6 |
| `spacing-2` | 0.5rem | 8 |
| `spacing-3` | 0.75rem | 12 |
| `spacing-4` | 1rem | 16 |
| `spacing-5` | 1.25rem | 20 |
| `spacing-6` | 1.5rem | 24 |
| `spacing-8` | 2rem | 32 |
| `spacing-10` | 2.5rem | 40 |
| `spacing-12` | 3rem | 48 |
| `spacing-16` | 4rem | 64 |
| `spacing-20` | 5rem | 80 |
| `spacing-24` | 6rem | 96 |

---

## 6. Border Radius

| Token | Value | Usage |
|-------|-------|-------|
| `radius-xs` | 6px | Badges, tags, inline chips |
| `radius-sm` | 8px | Buttons, inputs, small elements |
| `radius-md` | 10px | Small cards, list items |
| `radius` | 12px | Standard cards, panels |
| `radius-lg` | 16px | Large cards, modals |
| `radius-xl` | 20px | Hero cards, feature panels |
| `radius-2xl` | 28px | Large floating containers |
| `radius-pill` | 999px | Pill buttons, search bars, chips |

---

## 7. Shadows

Shadows work **in concert with glass blur** to create depth. Glass surfaces use softer, more diffuse shadows than solid surfaces.

### Light Mode

| Token | Value | Usage |
|-------|-------|-------|
| `shadow-sm` | `0 1px 2px rgba(0,0,0,0.05)` | Subtle lift for small elements |
| `shadow-card` | `0 2px 8px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.03)` | Glass cards |
| `shadow-card-hover` | `0 8px 32px rgba(0,0,0,0.1), 0 2px 8px rgba(0,0,0,0.05)` | Hovered glass cards |
| `shadow-glass` | `0 4px 24px rgba(0,0,0,0.06), inset 0 1px 0 rgba(255,255,255,0.4)` | Standard glass panels |
| `shadow-elevated` | `0 8px 40px rgba(0,0,0,0.1), 0 2px 8px rgba(0,0,0,0.04)` | Modals, dialogs |
| `shadow-overlay` | `0 16px 56px rgba(0,0,0,0.15)` | Full overlays |

### Dark Mode
All shadow opacities increase by ~50% (e.g., `0.06 → 0.15`). Inner glass highlights reduce to `rgba(255,255,255,0.05)`.

### Glow Effects
Interactive elements can use colored glow on hover/focus:
```css
/* Primary glow (buttons, active inputs) */
box-shadow: 0 0 0 3px rgba(59, 103, 246, 0.2), 0 4px 16px rgba(59, 103, 246, 0.15);

/* Accent glow (decorative, badges) */
box-shadow: 0 0 20px rgba(247, 169, 241, 0.3);

/* Danger glow (destructive actions on hover) */
box-shadow: 0 0 0 3px rgba(192, 57, 43, 0.2);
```

---

## 8. Animation & Transitions

**Everything moves. Nothing teleports.** State changes, layout shifts, view transitions, and appearance/disappearance are always animated. The UI should feel physically grounded — elements have weight, momentum, and settle into place.

### Transition Tokens

| Token | Duration | Easing | Usage |
|-------|----------|--------|-------|
| `transition-fast` | 150ms | `ease` | Hover states, opacity toggles, color changes |
| `transition-normal` | 200ms | `ease` | Button presses, input focus, small layout shifts |
| `transition-medium` | 250ms | `ease` | Card expand/collapse, sidebar toggle |
| `transition-smooth` | 300ms | `cubic-bezier(0.4, 0, 0.2, 1)` | View transitions, modal enter, panel slides |
| `transition-spring` | 500ms | `cubic-bezier(0.34, 1.56, 0.64, 1)` | Bouncy entrances, toolbar pop-in, notification appear |
| `transition-slow` | 600ms | `cubic-bezier(0.16, 1, 0.3, 1)` | Full view changes, page transitions, large layout shifts |

### View Transitions

When navigating between major views (Home → Canvas, Canvas → Dashboard, etc.):
- **Outgoing view**: fades out + scales down slightly (0.98) over 300ms
- **Incoming view**: fades in + scales up from 0.98 to 1.0 over 300ms, delayed 50ms
- Use CSS `view-transition-api` or `framer-motion`'s `AnimatePresence` for route transitions
- Sidebar persists across transitions (does not animate with the view)

### Size & Layout Animations

When elements change size (sidebar collapse, card expand, panel resize):
- Animate `width`, `height`, `max-height` using `transition-smooth` (300ms)
- Content within resizing containers fades in after the resize completes (staggered 50ms)
- Use `will-change: transform` on animating elements for GPU acceleration
- **Never use `display: none` toggling** — use opacity + height/max-height transitions or `framer-motion` layout animations

### Modal & Overlay Transitions

| Animation | Enter | Exit |
|-----------|-------|------|
| **Modal/Dialog** | Scale from 0.9 → 1.0 + fade in, 300ms smooth | Scale to 0.95 + fade out, 200ms |
| **Note Editor** | Expands from source note's bounding rect (FLIP animation) | Collapses back to source rect |
| **Dropdown/Menu** | Scale Y from 0.95 + fade, origin top, 200ms | Fade out 150ms |
| **Sidebar drawer** | Slide from left -280px → 0, 300ms smooth | Slide out 250ms |
| **Toast/Notification** | Slide up + fade in from bottom, 300ms spring | Fade + slide down 200ms |
| **Backdrop overlay** | Fade in 200ms | Fade out 150ms |

### Micro-interactions

| Element | Trigger | Animation |
|---------|---------|-----------|
| **Button** | Hover | Scale 1.02, shadow increase, 150ms |
| **Button** | Press | Scale 0.98, 100ms |
| **Card** | Hover | Translate Y -2px, shadow card-hover, 200ms |
| **Card** | Press | Scale 0.99, 100ms |
| **Toggle/Switch** | State change | Thumb slides with spring easing, bg color fades, 300ms |
| **Input** | Focus | Border glows primary blue, 200ms |
| **Checkbox** | Check | Checkmark draws in (stroke-dashoffset animation), 250ms |
| **Tab indicator** | Tab change | Underline slides to new position, 300ms smooth |
| **Glass surface** | Appear | Blur ramps from 0 → full, opacity 0 → 1, 300ms |
| **Tooltip** | Hover (delay 400ms) | Fade in + scale from 0.95, 150ms |

### Canvas-Specific Animations

| Action | Animation |
|--------|-----------|
| **Node place** | Node pops in from scale 0.8 → 1.0 with spring easing, ghost fades out |
| **Node drag** | Slight scale up (1.03) + deeper shadow while dragging, snap guides fade in 100ms |
| **Node delete** | Scale to 0.8 + fade out, 200ms |
| **Zoom** | Smooth interpolated zoom (not stepped), grid density crossfades |
| **Pan** | Momentum/inertia after release (deceleration curve) |
| **Selection** | Blue selection ring fades in 150ms, selection toolbar slides in from top 200ms |
| **Snap guide** | Fade in 100ms when aligned, fade out 100ms when released |

### Ambient/Decorative Animation

- **Home background gradient**: Blobs drift slowly (20-40s cycle), using CSS keyframe animations on `translate` and `scale`
- **Dashboard status glow**: Subtle pulse on the status card border (2s cycle, only when "running")
- **Loading states**: Morphing glass shape (smooth blob deformation), not a spinner
- **Typing indicator**: Three dots with staggered opacity pulse (0.3 → 1.0, 1.2s cycle)

### Reduced Motion

When `prefers-reduced-motion: reduce` is active:
- All decorative/ambient animations stop
- Transitions reduce to 0ms or instant opacity fades
- Layout animations still occur but at reduced duration (100ms max)
- No spring/bounce easing — use linear or ease
- Canvas pan/zoom remains smooth (functional, not decorative)

---

## 9. Component Patterns

### Buttons

**Filled Primary** (main CTA):
- Glass-style: `background: rgba(59,103,246, 0.9)`, `backdrop-filter: blur(8px)`
- White text, radius-sm (8px)
- Hover: full opacity + primary glow + scale 1.02
- Press: scale 0.98, darker shade

**Outlined** (secondary):
- Glass surface background + primary-colored border
- Primary-colored text
- Hover: primary-bg tint fills the glass

**Ghost** (tertiary):
- Transparent background, primary text
- Hover: subtle glass surface appears (fade in 150ms)

**Danger**:
- Same patterns as above but with danger-red

### Cards

All cards are glass surfaces:
- Standard glass background + radius (12px)
- 1px border (white at 25% opacity)
- Inner top-edge highlight
- Hover: translate Y -2px + shadow increase (animated 200ms)
- Content padding: spacing-4 (16px) to spacing-6 (24px)

### Inputs

- Glass surface background (lighter, ~40% white)
- 1px solid border (border-solid token)
- Radius-sm (8px)
- Focus: border transitions to primary blue + glow ring (animated 200ms)
- Placeholder text uses text-muted color

### Badges/Chips

- Small pill shape (radius-pill)
- Semi-transparent background tinted with badge color
- Backdrop-filter: blur(8px)
- Small text (11-12px), medium weight

### Dropdowns/Menus

- Elevated glass surface
- Radius-md (10px)
- Items have hover highlight (glass tint, 150ms transition)
- Menu appears with scale-Y + fade animation (200ms)
- Keyboard-navigable with visible focus indicator

---

## 10. Backgrounds

### Home & Dashboard Background

Animated gradient with drifting blobs:
- Base: solid background color
- 5 overlapping radial gradients (blobs) using brand blue/pink at low opacity (8-25%)
- Each blob animates on a slow translate + scale loop (20-40s, different phases)
- Blobs are large (40-70vw) and heavily blurred
- Total effect: a gently breathing, color-shifting background under all glass surfaces

### Canvas Background

- Solid background color
- Dot-grid pattern overlay (dots: `#D2D1CC`, 1-2px, spaced 20-40px)
- Grid density adapts to zoom level (crossfade between densities, 200ms)

### Documentation Site Background

- Clean solid background (no animated blobs)
- Subtle noise texture overlay at very low opacity (optional, 2-3%)
- Landing page hero section can use the animated blob background

---

## 11. Iconography

- **Style**: Outlined, 1.5px stroke, rounded caps/joins
- **Size**: 20px default, 16px small, 24px large
- **Color**: Inherits from text color (currentColor)
- **Source**: Use a consistent icon set (e.g., Lucide, Phosphor, or Heroicons outline)
- **Animated icons**: Loading states use smooth rotation or morphing, not stepped frame animation

---

## 12. Responsive Behavior

| Breakpoint | Width | Layout Adaptations |
|------------|-------|-------------------|
| **Mobile** | < 480px | Sidebar becomes drawer overlay. Single-column layouts. Toolbar shrinks. Touch targets 44px+ |
| **Tablet** | 480-768px | Sidebar collapsible. Two-column where possible. Reduced padding |
| **Desktop** | > 1024px | Full sidebar. Multi-column layouts. All panels visible |

**Transition between breakpoints**: Layout changes animate (sidebar slides, columns reflow with 300ms smooth transition). No layout jumps.

---

## 13. Dark Mode

Dark mode inverts the luminance hierarchy but preserves the glass aesthetic:

- **Background**: Deep navy/charcoal (`#0E0E14`) instead of light gray
- **Glass surfaces**: Dark-tinted (`rgba(20,20,30, 0.6)`) with reduced white border opacity
- **Text**: Light values on dark surfaces (maintain same contrast ratios)
- **Shadows**: Deeper, higher opacity
- **Glass inner highlight**: Reduced to `rgba(255,255,255, 0.05)` (barely visible but still present)
- **Accent colors**: Slightly desaturated to avoid eye strain
- **Code blocks**: Same dark theme in both modes (dark bg is native)

**Mode switching**: Animate the transition between light and dark with a 300ms color fade on all themed tokens. No flash of unstyled content.

---

## 14. Alternate Theme: Bauhaus

A secondary theme that replaces the glass aesthetic with stark geometric modernism:

- **No glass effects** — solid opaque surfaces, no backdrop-filter
- **No shadows** — completely flat, depth via layering and color only
- **Hard borders**: 2px solid black on cards and sections
- **Primary palette**: Red `#DE1C24`, Blue `#1A47A8`, Yellow `#F5C623`, Black `#1A1A1A`
- **Background**: Warm cream `#F8F7F4`
- **Typography**: Same Jost headings, but bolder (700-800 weight)
- **Radius**: 0 everywhere — square corners only
- **Animations**: Same transition system but faster (reduce all durations by 30%), no spring easing
- **Grid emphasis**: Asymmetrical layouts, visible grid lines, primary-colored section dividers

---

## 15. Accessibility

- **Focus rings**: 2px solid primary blue with 2px offset, visible on all interactive elements. On glass surfaces the ring uses the glow effect for higher visibility.
- **Contrast**: All text meets WCAG AA (4.5:1 body, 3:1 large text). Glass surfaces must maintain readable contrast against the worst-case background behind them.
- **Touch targets**: Minimum 44px on all interactive elements
- **Keyboard navigation**: Full keyboard support — tab order, arrow keys in lists/menus, Escape closes modals, Enter activates
- **Focus trap**: Modals and dialogs trap focus within themselves
- **Reduced motion**: Full `prefers-reduced-motion` support (see Animation section)
- **Screen reader**: All interactive elements have accessible labels. Decorative animations use `aria-hidden`
