# Adjutant Design Specification

> **Purpose**: A complete screen-by-screen spec for redesigning Adjutant's web app and documentation site with a unified visual language. Hand this document to a design AI or designer to produce mockups/screens.

---

## Global Design System

> **Full design system specification**: See **[design-system.md](./design-system.md)** for the complete design system including glassmorphic surface treatments, animation system, color palette, typography, and component patterns.
>
> **Key characteristics**: Frosted glass surfaces (`backdrop-filter: blur`), fluid animated transitions between all states/views/sizes, spring-based micro-interactions, ambient gradient backgrounds, layered depth hierarchy.

---

## SCREENS — WEB APPLICATION

---

### Screen 1: Home / Prompt

**Route**: `/`
**Purpose**: The entry point. A focused, centered prompt that invites the user to start a conversation. Typing and sending a message seamlessly transitions into the full chat view without a perceptible route change.

**Layout**:
- Full viewport height, vertically and horizontally centered content
- Animated gradient background (subtle blue-tinted blobs drifting slowly)
- Sidebar collapsed or minimal (icon-only) — the prompt is the hero
- No chrome, no clutter — the entire screen funnels attention to the input

**Elements**:
1. **App Title** (above prompt, centered)
   - "Adjutant" in display heading (Jost 700, 36-48px)
   - Subtitle below: one-line tagline, muted text (e.g., "Your personal AI assistant")
   - Title and subtitle should fade/scale up gently on page load (spring entrance, 500ms)

2. **Prompt Box** (center of screen)
   - Glass surface card (elevated glass: `backdrop-filter: blur(32px)`, `rgba(255,255,255,0.7)`)
   - Large pill-shaped or rounded-rectangle input area (~600px wide, radius-xl or radius-2xl)
   - Multi-line textarea that auto-grows (starts as single-line height, grows to ~4 lines max)
   - Placeholder: "Ask anything..." in muted text
   - Send button: icon-only (arrow-up), appears inside the input on the right when text is present — fades in with scale (150ms)
   - On focus: glass surface gains a faint primary-blue glow ring
   - Below the input: subtle hint text (e.g., keyboard shortcut "Enter to send, Shift+Enter for new line")

3. **Quick Actions** (below prompt, optional)
   - Small row of pill chips for common starting actions (e.g., "Resume last chat", recent session names)
   - Glass chips, muted text, hover: fill with primary-bg tint
   - Only shown if previous sessions exist; otherwise this area is empty

4. **Background**
   - Animated gradient blobs (same system as design-system.md: 5 blobs, 20-40s cycle, blue/pink at low opacity)
   - The background persists across the transition to `/chat` — it does not restart or flash

**The Seamless Transition** (Home → Chat):

This is the most critical interaction in the entire app. When the user types a message and hits Enter/send:

1. **URL changes** from `/` to `/chat` silently (via `history.replaceState` or React Router's navigate with no transition — no page reload, no flash)
2. **The prompt box** smoothly animates from its centered position to the bottom of the screen (where the chat input lives). This is a FLIP animation:
   - Record the prompt's current rect (center of screen)
   - The chat view mounts with the input at the bottom
   - Animate from the old position to the new position (300ms, smooth easing)
   - The glass surface, border radius, and width may subtly adjust during the animation
3. **The title and subtitle** fade out and scale down (200ms, starts immediately)
4. **The message area** fades in above the now-repositioned input (200ms, delayed 150ms) — the user's sent message appears as the first bubble
5. **The sidebar** expands to its full width (if on desktop) with a slide animation (300ms)
6. **The session header** slides in from the top (200ms, delayed 100ms)
7. **The background gradient continues** — it does not reset. The chat view inherits the same animated background (or transitions to a subtler version)

The user should perceive this as "the prompt moved to the bottom and the chat opened around it" — not as a page navigation.

---

### Screen 2: Chat

**Route**: `/chat`
**Purpose**: The primary chat interface. WebSocket-based conversation with the AI backend. Can also be entered from the Home prompt transition or by resuming a previous session.

**Layout**:
- Full height, vertical flex layout
- Session header at top
- Message list (scrollable, takes remaining space)
- Input area pinned to bottom
- Status bar at very bottom
- Animated gradient background (subtle, dimmer than Home — or solid with glass surfaces floating over it)

**Elements**:

1. **Session Header** (top bar, glass surface — ground glass)
   - Left: Back arrow (navigates to `/`, animates the reverse of the home→chat transition)
   - Center-left: Session name (editable inline on click — text becomes input with save on blur/enter)
   - Center: Model badge (colored glass chip showing current model tier, e.g., "Sonnet" in blue, "Opus" in purple)
   - Right: Cost display (e.g., "$0.024" — running total, monospace, muted)
   - Far right: "New Chat" button (ghost button with + icon, starts fresh session)

2. **Message List** (main scrollable area)
   - Messages appear with staggered entrance animations:
     - **User messages**: slide in from right + fade (200ms)
     - **Assistant messages**: slide in from left + fade (200ms), with a slight delay after the typing indicator
   - **User message bubble**:
     - Right-aligned
     - Primary-blue glass surface (blue at ~85% opacity, blur 12px)
     - White text
     - Radius-lg, max-width ~70%
   - **Assistant message bubble**:
     - Left-aligned
     - Standard glass surface (white at 55% opacity, blur 20px)
     - Dark text
     - Radius-lg, max-width ~80%
     - Contains rendered markdown: headings, lists, bold, italic, links
   - **Timestamps**: small, muted, below each bubble (appears on hover or always visible — subtle)
   - **Typing indicator**: three dots in a glass bubble, staggered opacity pulse animation (0.3→1.0, 1.2s cycle, each dot delayed 0.2s)
   - Auto-scroll to bottom on new messages (smooth scroll, 300ms)
   - Scroll-to-bottom button appears when scrolled up (floating, bottom-right of message area, glass circle with down-arrow icon, fade in 150ms)

3. **Code Blocks** (within assistant messages)
   - Dark background glass (`rgba(30,30,30,0.95)`, blur 8px)
   - Language label: top-left, muted small text
   - Copy button: top-right, ghost icon button, appears on hover (fade in 150ms)
   - Line numbers: optional, muted left column
   - Syntax highlighting (standard dark theme)
   - Horizontal scroll for long lines
   - Radius-md (10px), slightly inset from the bubble edges

4. **Input Area** (bottom, above status bar)
   - Glass surface card (standard glass, full-width with horizontal padding)
   - Multi-line textarea: auto-resize from 1 line up to ~6 lines, then scroll
   - Placeholder: "Message Adjutant..." in muted text
   - Send button: right side, inside the input card — primary-blue circle icon (arrow-up)
     - Hidden when input is empty, appears with scale+fade (150ms) when text is present
     - Press animation: scale 0.9 → 1.0 (100ms)
   - Slash command trigger: typing "/" at the start of input opens the command palette
   - Attachment button (optional, left side): for future file/image upload support
   - Focus state: glass surface gains primary glow ring

5. **Slash Command Palette** (above input, when "/" is typed)
   - Elevated glass dropdown, radius-md
   - List of commands: each row has command name (bold, monospace) + description (muted)
   - Keyboard navigable (up/down, enter to select, escape to dismiss)
   - Filters live as user types after "/"
   - Max height ~200px, scrollable
   - Entrance: scale-Y from 0.95 + fade, origin bottom, 200ms

6. **Status Bar** (very bottom, thin bar — subtle glass)
   - Left: Current working directory path (monospace, truncated with ellipsis)
   - Center: Backend name (e.g., "claude-cli")
   - Right: Connection state — colored dot (green=connected, red=disconnected, yellow=connecting) + label
   - Height: ~28px
   - Subtle glass surface (ground glass: blur 12px, 35% white)

**Session Management** (accessed via sidebar or header actions):

7. **Session List** (in sidebar, under "Chats" nav section)
   - Grouped by knowledge base (or ungrouped if no KB context)
   - Each session: name, model chip, last-active relative time
   - Click to resume (navigates to `/chat` with that session loaded — crossfade transition 200ms)
   - Swipe-to-delete on mobile, or hover-reveal delete icon on desktop
   - Active session: highlighted with primary-bg tint

8. **Model Picker** (dropdown or modal, triggered from header model badge click)
   - Three tier options as glass cards: Cheap / Medium / Expensive
   - Each shows: model name, short description, relative cost icon
   - Selected option: primary border + checkmark
   - Dropdown entrance: scale + fade from the badge position

9. **Working Directory Picker** (modal, accessible from status bar CWD click)
   - Same FolderExplorer modal as Screen 9

---

### Screen 3: Canvas (Knowledge Base)

**Route**: `/:kb` and `/:kb/*`
**When shown**: A knowledge base is selected from the sidebar

**Layout**:
- Full viewport, infinite canvas (pan and zoom)
- Sidebar visible on left
- Floating toolbar at top-center
- Canvas has a dot-grid background that adapts density based on zoom level

**Elements**:
1. **Canvas Background**
   - Dot grid pattern (color: `#D2D1CC`)
   - At low zoom: coarser grid. At high zoom: finer grid with sub-grids
   - Smooth crossfade transition between grid densities (200ms)

2. **Floating Toolbar** (top-center, above canvas — ground glass surface)
   - Horizontal pill-shaped glass bar with 3 buttons:
     - "Section" (S shortcut) — creates a section container
     - "Sticky" (T shortcut) — creates a sticky note
     - "Note" (N shortcut) — creates a markdown note (primary/emphasized button)
   - Keyboard shortcut hints shown as small badge on each button
   - Toolbar fades to 60% opacity when not hovered, full opacity on hover (200ms)

3. **Note Nodes** (on canvas)
   - Glass card: 200px wide x ~283px tall (standard glass surface)
   - Shows: title (bold), first few lines of content preview (rendered markdown), tag pills at bottom
   - Double-click to open in Note Editor modal
   - Drag to reposition (scale 1.03 + deeper shadow while dragging, 150ms)
   - Selected state: primary-blue glow ring
   - Hover: subtle lift (translate-Y -1px, shadow increase, 150ms)

4. **Section Nodes** (on canvas)
   - Resizable rectangular containers with glass fill (very subtle: 15-25% opacity, blur 8px)
   - Customizable background color tint (from a preset palette)
   - Title label at top-left (label style text)
   - 1px border matching the color tint
   - Resize handles on corners and edges (appear on hover, 150ms fade)

5. **Sticky Nodes** (on canvas)
   - Small square glass cards (~150px)
   - Color-tinted glass (yellow, pink, blue, green — each a tinted glass surface)
   - Inline text editing on double-click
   - No title — just body text

6. **Image Nodes** (on canvas)
   - Display embedded images with glass-style border/shadow
   - Aspect-ratio-preserving resize handles (appear on hover)

7. **Ghost Previews** (during placement mode)
   - Semi-transparent glass preview of the node type following the cursor
   - Note ghost: smaller than actual (120x160px), 40% opacity
   - Sticky/section ghosts: appropriately sized
   - Desktop only (mouse follow), fades out when placed (200ms)

8. **Snap Guides**
   - Thin primary-blue lines that appear when dragging a node near alignment with another
   - Fade in 100ms, fade out 100ms
   - Horizontal and vertical

9. **Selection Toolbar** (appears when 2+ nodes selected)
   - Floating glass bar near selection with alignment icon buttons:
     - Align left, right, top, bottom
     - Distribute horizontally/vertically
     - Space evenly
   - Slides in from top with fade (200ms spring)

10. **Context Menu** (right-click on canvas or node)
    - Elevated glass surface, radius-md
    - Items with hover highlight, dividers, and optional sub-menus
    - Color swatches shown inline for "Change color" options
    - Keyboard shortcut hints right-aligned in muted text
    - Entrance: scale-Y + fade from click origin, 200ms

**Interactions**:
- Pan: click and drag on empty space (or two-finger on trackpad), with momentum/inertia
- Zoom: scroll wheel / pinch, smooth interpolated (not stepped)
- Place node: click toolbar button → placement mode → click canvas to place (node pops in with spring scale 0.8→1.0)
- Touch devices: dedicated pan/select mode toggle (ToolSwitcher floating button)
- Placement hint toast: "Tap to place note" (glass pill, appears 300ms, auto-hides after 3s)

---

### Screen 4: Note Editor Modal

**Trigger**: Double-click a note on canvas, or create new note
**Type**: Modal overlay — uses a FLIP animation expanding from the source note's position

**Layout**:
- Elevated glass modal, max width ~700px, ~80vh height
- Backdrop overlay (dark, `rgba(0,0,0,0.4)`, blurred: `backdrop-filter: blur(8px)`)
- Animated open: FLIP from note's bounding rect → modal center (300ms smooth)
- Animated close: reverse FLIP back to note position (250ms)

**Elements**:
1. **Title Input** (top)
   - Large text input, borderless (just a bottom rule or minimal underline on focus)
   - Placeholder: "Note title"
   - Font: heading style (Jost 600, 22px)

2. **Tag Input** (below title)
   - Inline glass tag pills with "x" remove buttons
   - Text input that creates tags on Enter or comma
   - Tags: pill radius, primary-bg tint glass

3. **Rich Text Editor** (main area, scrollable)
   - TipTap-based markdown editor
   - Supports: headings, bold, italic, code blocks, lists, links, images
   - Paste image support (auto-upload)
   - Syntax highlighting for code blocks
   - Minimal chrome — focus on content
   - Editor toolbar: hidden by default, appears on text selection (floating glass bar with format buttons)

4. **Footer Bar** (bottom of modal)
   - Left: "Last saved: [relative time]" in muted text, with a subtle checkmark animation on save
   - Left: "Delete" button (danger ghost button)
   - Right: "Done" button (primary filled) — closes modal
   - Auto-save with debounce; no explicit save needed

**Interactions**:
- Auto-saves with debounce
- Escape or clicking backdrop closes (reverse FLIP animation)
- Delete shows confirmation dialog first
- Images can be pasted or dragged in

---

### Screen 5: Adjutant Dashboard

**Route**: `/adjutant`
**Purpose**: System monitoring and control panel for the Adjutant agent backend

**Layout**:
- Two-column layout (main ~65% + sidebar ~35%) on desktop, stacked on mobile
- Top navigation bar within the dashboard (glass surface)
- Subtle animated gradient background (dimmer than Home)

**Top Navigation Bar** (glass surface):
- Left: Adjutant logo/icon
- Center: Tab buttons — "Pulse" | "Schedules" | "System Logs"
  - Active tab: underline indicator in primary color, slides between tabs (300ms smooth)
- Right: Settings gear icon

**Left Column (Main Content)**:

5. **System Status Card** (hero — elevated glass with gradient tint)
   - Lifecycle state as large display text (e.g., "RUNNING", "PAUSED", "STOPPED")
   - State-specific glass tint (green-tinted = running, yellow = paused, red = stopped)
   - Subtle pulse glow on border when running (2s cycle, ambient)
   - Uptime or time-in-state below
   - Status badges: backend type, model, as glass chips

6. **Activity Feed** (glass card, scrollable)
   - Structured log entries, newest first
   - Each entry: timestamp (monospace, muted) | level badge (colored glass pill) | component (bold) | message
   - New entries slide in from top with fade (200ms)
   - "New entries" indicator if scrolled down

7. **Identity Display** (glass card with tabs)
   - 3 tabs: "Soul" | "Heart" | "Registry" — glass pill tab buttons
   - Tab content crossfades on switch (200ms)
   - Content: monospace, read-only, scrollable

**Right Column**:

8. **Health Checks Card** (glass card)
   - Vertical list: each row has status icon (animated checkmark for OK, X for fail) + label + status
   - Status icon color: success green / danger red
   - Card header: "System Health" in label text

9. **Quick Actions Card** (glass card)
   - 2x2 grid of action buttons:
     - Pause (warning-tinted glass), Resume (success-tinted glass), Stop (neutral glass), Kill (danger-tinted glass)
   - Each: icon + label, glass button style
   - Disabled state: reduced opacity (0.4), no hover effect
   - Press: scale 0.96 (100ms)

10. **Last Pulse Card** (glass card)
    - Latest heartbeat timestamp, summary text, observation type
    - Compact, single card

11. **Schedules Manager** (glass card, or full-panel when "Schedules" tab active)
    - List rows: schedule name | cron expression (monospace chip) | toggle switch (animated) | "Run" ghost button
    - Add schedule: ghost button at bottom with + icon

---

### Screen 6: Sidebar (Persistent Navigation)

**Type**: Persistent left panel, present on all views
**Width**: 280px collapsed to icon-only ~48px
**Surface**: Ground glass (blur 12px, 35% white)

**Elements**:

1. **Header**
   - "Adjutant" wordmark (Jost 600, 18px)
   - Collapse/expand toggle button (hamburger icon, animated: morphs between hamburger ↔ X, 200ms)

2. **Navigation Links**
   - Home (icon + label) → `/`
   - Chat (icon + label) → `/chat`
   - Dashboard (icon + label) → `/adjutant`
   - Active item: primary-bg glass tint, bold text, left accent bar (2px primary, animated slide-in)
   - Hover: subtle glass fill (150ms)
   - Icons animate on route change (subtle scale pulse)

3. **Chats Section** (below nav, when on `/chat`)
   - Section header: "Recent Chats" with count badge
   - List of recent sessions: name + relative time
   - Click to switch session (crossfade, 200ms)
   - Active session highlighted

4. **KB List** (below nav or chats section)
   - Section header: "Knowledge Bases"
   - Each KB: folder icon + name, clickable → navigates to `/:kb`
   - Active KB: highlighted with primary tint
   - When a KB is selected, expands with animated height transition (300ms):
     - Breadcrumb path
     - Recursive folder tree with animated expand/collapse arrows (rotate 90°, 200ms)
     - Note files listed under folders
     - "Focus" button per folder (pans canvas to that section)

5. **Footer**
   - Settings button (gear icon + "Settings" label)
   - Pinned to bottom of sidebar

**Responsive behavior**:
- Desktop: always visible, collapsible with smooth width animation (300ms)
- Mobile: drawer overlay sliding from left (300ms smooth), blurred backdrop behind
- Collapsed state: only icons visible, tooltips on hover (150ms delay)

---

### Screen 7: Settings Dialog

**Trigger**: Settings button in sidebar
**Type**: Elevated glass modal, centered

**Layout**:
- Max width ~400px
- Blurred backdrop overlay

**Elements**:
1. **KB Root Path**
   - Label: "Knowledge Base Root"
   - Glass input showing current path
   - "Browse" button → opens FolderExplorer modal
   - Validation: green checkmark or red X with message, animated fade (150ms)

2. **Theme Selector**
   - Label: "Theme"
   - Two glass cards (radio selection):
     - "Default" — blue/white preview swatch
     - "Bauhaus" — red/yellow/blue preview swatch
   - Selected card: primary border + checkmark (animated scale-in, 200ms)

3. **Action Buttons**
   - "Save" (primary filled glass) and "Cancel" (ghost)
   - Modal entrance: scale 0.9→1.0 + fade (300ms)
   - Modal exit: scale→0.95 + fade out (200ms)

---

### Screen 8: Folder Explorer Modal

**Trigger**: "Browse" button in Settings or Working Directory Picker
**Type**: Elevated glass modal

**Elements**:
- Current path breadcrumbs at top (glass pills, clickable)
- Directory tree: folders with animated expand/collapse (height + rotate arrow, 200ms)
- "Select" button (primary) and "Cancel" (ghost)
- KB validation status indicator for relevant folders
- Entrance/exit: same as Settings Dialog

---

### Screen 9: Confirmation Dialog

**Type**: Small elevated glass modal
**Variants**: Default (neutral) and Danger (red-tinted glass)

**Elements**:
- Title text (Jost 600, 18px)
- Description text (body, muted)
- Two buttons: Cancel (ghost) and Confirm (primary filled, or danger-red filled)
- Danger variant: confirm button has danger-red glass surface, modal border has faint red tint
- Entrance: scale 0.95→1.0 + fade (200ms, spring)
- Exit: fade out (150ms)

---

### Screen 10: Error Boundary Fallback

**When shown**: When a component crashes

**Elements**:
- Centered glass card on the ambient background
- Icon: warning or error illustration (outlined style)
- Message: "Something went wrong" (heading)
- "Retry" button (primary outlined glass)
- Compact, non-alarming — feels recoverable

---

## SCREENS — DOCUMENTATION SITE (Docusaurus)

---

### Screen 11: Docs Landing Page

**Route**: `/` (site root)
**Purpose**: Marketing/introduction page for the Adjutant project

**Layout**:
- Full-width, no sidebar
- Sections stack vertically
- Navbar at top, footer at bottom
- Glass surface treatment on cards and navbar

**Sections**:

1. **Navbar** (sticky top, glass surface — ground glass)
   - Left: Logo (SVG) + "Adjutant" wordmark
   - Center/Right: Nav links — "Docs" | "Guides" | "Architecture" | "Contribute"
   - Far right: GitHub icon link
   - Mobile: hamburger → glass drawer overlay
   - Active link: underline indicator, slides to active position (300ms)

2. **Hero Section** (first viewport)
   - Two columns: text left (~55%), visual right (~45%)
   - Left column:
     - Small label: "Personal AI Agent Framework" (uppercase, muted, letter-spaced)
     - Large title: "Adjutant" (Jost 700, 48-56px, with subtle text-shadow in primary blue)
     - Subtitle paragraph (~2 lines)
     - Two CTA buttons: "Get Started" (primary filled glass) + "Learn More" (outlined glass)
     - Install snippet: `$ git clone ...` in a dark glass code block
   - Right column:
     - 3D interactive wobbling sphere (Three.js/React Three Fiber)
     - Responds to mouse movement
   - Background: animated gradient blobs (same system as web app Home, but can be tuned for docs)
   - Elements stagger-fade in on load (title 0ms, subtitle 100ms, buttons 200ms, code 300ms)

3. **Features Section**
   - Section heading: centered (Jost 600, 28px)
   - 6 feature glass cards in 3x2 grid:
     - Each: icon (top, outlined, 32px), title (bold), description paragraph
     - Glass surface with hover lift + glow (200ms)
     - Features: Telegram Interface, Knowledge Bases, Autonomous Monitoring, Multi-Backend LLM, Web Canvas, Long-Term Memory

4. **How It Works Section**
   - 3-step horizontal flow (vertical on mobile):
     - Step 1: "Install" — numbered glass circle + description
     - Step 2: "Configure" — numbered glass circle + description
     - Step 3: "Chat" — numbered glass circle + description
   - Steps connected by thin lines with animated dash pattern
   - Glass cards for each step

5. **Bottom CTA Section**
   - Centered: "Ready to get started?" (heading)
   - "Get Started" button (primary filled glass, large)
   - Below: link to documentation

6. **Footer** (glass surface or solid)
   - Three columns:
     - Getting Started: Installation, Setup Wizard, First Message
     - Guides: Commands, Knowledge Bases, Configuration
     - More: GitHub link
   - Copyright line at bottom

---

### Screen 12: Documentation Page (Standard Layout)

**Route**: `/docs/*` (all 27+ documentation pages)
**Purpose**: Standard docs reading experience

**Layout**:
- Three columns: sidebar (left, 250px) + content (center, fluid) + TOC (right, 200px)
- Navbar at top (same as landing page)
- Footer at bottom
- Content area on clean background (no animated blobs — readability first)

**Elements**:

1. **Docs Sidebar** (left, glass surface)
   - Collapsible category groups with animated expand/collapse (200ms):
     - **Intro** (single page)
     - **Getting Started** (4 pages): Installation, Telegram Setup, Setup Wizard, First Message
     - **User Guides** (11 pages): Configuration, Commands, Knowledge Bases, Backends, Schedules, Autonomy, Lifecycle, Memory, News, Web, Troubleshooting
     - **Architecture** (7 pages): Overview, Messaging, Identity, State, Autonomy, Backends, Design Decisions
     - **Development** (6 pages): Contributing, Adaptor Guide, Plugin Guide, Backend Guide, Testing, Setup Wizard
   - Active page: primary-blue left border (2px) + bg tint, animated slide indicator (300ms)
   - Category headers: bold, with rotate-animated collapse chevron

2. **Content Area** (center)
   - Breadcrumbs at top (glass pills, clickable)
   - Page title (h1, Jost 700, 32px)
   - Rendered markdown with:
     - Headings (h2-h4) with hover-reveal anchor links
     - Code blocks: dark glass surface, syntax highlighting, copy button (hover-reveal)
     - Tables with alternating row tint
     - Admonitions/callouts: glass cards with colored left border (tip=green, warning=yellow, info=blue, danger=red)
     - Inline code: glass pill with primary-bg tint
   - Previous/Next navigation at bottom (two glass buttons, full width)
   - "Edit this page" link (muted, right-aligned)
   - Page content fades in on navigation (200ms)

3. **Table of Contents** (right, sticky)
   - Auto-generated from h2/h3 headings
   - Sticky positioning
   - Active section: bold with primary-blue dot indicator (animated slide between sections, 200ms)
   - Thin left border line

---

### Screen 13: 404 Page

**Route**: Any unmatched route

**Elements**:
- Centered layout on animated gradient background
- Large "404" number (Jost 700, 80px, muted)
- "Page not found" subtitle
- "Go to docs" button (primary filled glass)
- Minimal, clean — not alarming

---

## CROSS-CUTTING DESIGN NOTES

### The Home → Chat Transition (Critical)

This is the signature interaction of the app. It must feel like a single continuous surface transforming, not a page navigation. Key technical requirements:
- Both `/` and `/chat` share the same root layout component
- The prompt input component is the **same React component instance** across both routes (use layout-level state, not route-level mounting)
- Use `framer-motion`'s `layoutId` or the CSS View Transition API to animate the input's position
- The animated gradient background is rendered at the layout level, not per-route, so it persists
- The URL update uses `navigate()` with no scroll reset and no page transition

### Unified Elements Between Web App and Docs Site

1. **Same font stack**: Jost for headings, Montserrat for body
2. **Same color palette**: Blue primary `#3B67F6`, pink accent `#F7A9F1`
3. **Same glass treatment**: `backdrop-filter: blur` on cards, navbars, and floating UI
4. **Same border radius system**: 12px default, full scale from 6px to pill
5. **Same button styles**: Primary filled glass, outlined glass, ghost, danger
6. **Same code block style**: Dark glass, syntax highlighting, copy button
7. **Same shadow + glow system**: Diffuse shadows + colored glow on interactive elements
8. **Same icon style**: Outlined, 1.5px stroke, 20-24px, consistent set (Lucide/Phosphor)
9. **Same animation curves**: Shared easing tokens, spring physics, staggered entrances

### Accessibility
- Focus rings: 2px solid primary with glow, visible on all interactive elements
- Glass surfaces must maintain WCAG AA contrast against worst-case backgrounds
- Touch targets: minimum 44px
- Keyboard navigable: tab order, arrow keys in lists, Escape closes modals, focus trapping
- `prefers-reduced-motion`: disable ambient/decorative animation, reduce transitions to 0-100ms

### Dark Mode
- Both platforms support light/dark
- Glass surfaces: white-tinted in light mode, dark-tinted (`rgba(20,20,30,0.6)`) in dark mode
- All colors via semantic tokens
- Mode switch: 300ms crossfade on all themed tokens

---

## SCREEN INDEX

| # | Screen | Platform | Route | Type |
|---|--------|----------|-------|------|
| 1 | Home / Prompt | Web App | `/` | Page |
| 2 | Chat | Web App | `/chat` | Page |
| 3 | Canvas (Knowledge Base) | Web App | `/:kb` | Page |
| 4 | Note Editor | Web App | — | Modal (FLIP) |
| 5 | Adjutant Dashboard | Web App | `/adjutant` | Page |
| 6 | Sidebar | Web App | — | Persistent panel |
| 7 | Settings Dialog | Web App | — | Modal |
| 8 | Folder Explorer | Web App | — | Modal |
| 9 | Confirmation Dialog | Web App | — | Modal |
| 10 | Error Boundary | Web App | — | Fallback |
| 11 | Docs Landing Page | Docs Site | `/` | Page |
| 12 | Documentation Page | Docs Site | `/docs/*` | Page (template) |
| 13 | 404 Page | Docs Site | — | Fallback |

**Total: 13 distinct screens/views to design.**
