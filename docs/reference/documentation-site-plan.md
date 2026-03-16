# Documentation Site Plan

**Status**: In progress
**Created**: 2026-03-16
**Target**: Docusaurus site deployed to GitHub Pages at `eddiman.github.io/adjutant`

---

## Overview

Build a Docusaurus-powered documentation site for Adjutant, deployed to GitHub Pages, in a separate repository (`eddiman/adjutant-docs`). The site targets both end users and developers, includes auto-generated Python API reference, and consolidates/fixes the existing 18+ markdown docs.

---

## Visual Identity

Adjutant's visual identity uses a **blue gradient palette** with **pink/rose accents**:

### Primary Palette (Blue Gradient — Light to Dark)

| Name | Hex | Usage |
|------|-----|-------|
| Ice | `#eef1ff` | Lightest background, hero subtle fill |
| Frost | `#e4e9ff` | Alternate section backgrounds |
| Mist | `#d4ddff` | Card backgrounds, sidebar hover |
| Sky | `#b4c6f7` | Borders, dividers, inactive elements |
| Azure | `#8dadee` | Secondary buttons, links, code backgrounds |
| Blue | `#6b93e4` | Primary interactive elements |
| Royal | `#4670cc` | Primary buttons, active nav, headings |
| Navy | `#2b4fa0` | Emphasis, dark accents |
| Deep | `#162d5e` | Dark mode backgrounds |
| Midnight | `#0e1f3f` | Darkest background, footer |

### Accent Palette (Pink/Rose)

| Name | Hex | Usage |
|------|-----|-------|
| Blush | `#f7d4ee` | Light accent, notifications, tags |
| Rose | `#e48dbf` | Accent buttons, highlights, badges |
| Pink | `#e8a4d4` | Secondary accent, callout borders |

### Color Strategy

- **Light mode**: Ice/Frost backgrounds, Royal for primary actions, Rose for accents
- **Dark mode**: Deep/Midnight backgrounds, Azure/Blue for primary actions, Pink for accents
- **Code blocks**: Mist background (light), Deep background (dark)
- **Admonitions**: Blue-tinted for info/note, Rose-tinted for warnings/danger

---

## Site Architecture

### Repository

Separate repository: `eddiman/adjutant-docs`

### Content Structure

```
docs/
├── intro.md                    # What is Adjutant?
├── getting-started/
│   ├── installation.md
│   ├── telegram-setup.md
│   ├── setup-wizard.md
│   └── first-message.md
├── guides/
│   ├── configuration.md
│   ├── commands.md
│   ├── knowledge-bases.md
│   ├── schedules.md
│   ├── autonomy.md
│   ├── lifecycle.md
│   ├── memory.md
│   ├── news.md
│   └── troubleshooting.md
├── architecture/
│   ├── overview.md
│   ├── messaging.md
│   ├── identity.md
│   ├── state.md
│   ├── autonomy.md
│   └── design-decisions.md
├── development/
│   ├── contributing.md
│   ├── adaptor-guide.md
│   ├── plugin-guide.md
│   ├── testing.md
│   └── setup-wizard-internals.md
└── api/
    └── index.md                # Auto-generated Python API reference
```

### Sidebar Navigation

```
What is Adjutant?
Getting Started
  ├── Installation
  ├── Telegram Setup
  ├── Setup Wizard
  └── First Message
User Guides
  ├── Configuration
  ├── Commands Reference
  ├── Knowledge Bases
  ├── Schedules
  ├── Autonomy
  ├── Lifecycle
  ├── Memory
  ├── News Briefings
  └── Troubleshooting
Architecture
  ├── Overview
  ├── Messaging
  ├── Identity & Agent
  ├── State & Lifecycle
  ├── Autonomy
  └── Design Decisions
Development
  ├── Contributing
  ├── Adaptor Guide
  ├── Plugin Guide
  ├── Testing
  └── Setup Wizard Internals
API Reference
```

---

## Execution Phases

### Phase 1: Fix Existing Docs (in adjutant repo)

1. Fix `guides/lifecycle.md` — KILLED recovery command (2 locations)
2. Fix `architecture/messaging.md` — Replace `claude_run` with `opencode_run` (4 locations)
3. Fix `architecture/identity.md` — Fix `heart.md` description and model tier default
4. Fix `architecture/state.md` — Fix KILLED recovery command
5. Fix `architecture/design-decisions.md` — Replace stale `claude_run`/`core/claude.py` references
6. Fix `architecture/overview.md` — Add memory capability to capabilities table
7. Write `docs/guides/memory.md`
8. Write `docs/guides/news.md`
9. Write `docs/guides/troubleshooting.md`

### Phase 2: Scaffold Docs Site (new repo)

10. Create `eddiman/adjutant-docs` repository
11. Initialize Docusaurus with TypeScript template
12. Configure `docusaurus.config.js` with visual identity colors
13. Configure `sidebars.js` with navigation structure
14. Set up custom CSS with the blue/pink palette
15. Install local search plugin
16. Create custom landing page

### Phase 3: Content Migration

17. Migrate all guide docs with Docusaurus frontmatter and admonitions
18. Migrate architecture docs
19. Migrate development docs
20. Write "What is Adjutant?" intro page
21. Split getting-started into 4 sub-pages
22. Convert ASCII diagrams to Mermaid where beneficial

### Phase 4: API Reference

23. Set up pydoc-markdown configuration
24. Generate API reference for core, messaging, and capabilities modules
25. Create API reference landing page

### Phase 5: Deploy

26. Set up GitHub Actions deployment workflow
27. Configure GitHub Pages
28. Deploy and verify

### Phase 6: Automation

29. Add sync workflow for doc changes (adjutant repo -> adjutant-docs)
30. Set up search (local initially, Algolia DocSearch later)

---

## Internal Docs Excluded from Site

The following `docs/reference/` files remain in the adjutant repo but are NOT published:

- All dated audit files (`2026-03-*`)
- `python-rewrite-*.md` (migration history)
- `agent-violations.md`, `inconsistencies.md`
- `phase7-autonomy-plan.md`, `kb-runtime-hardening-plan.md`
- `opencode-serve-approach.md`, `portfolio-kb-plan.md`
- `development/phase-8.md` (historical planning doc)

---

## Estimated Effort

| Phase | Time |
|-------|------|
| Phase 1: Fix + write docs | 3-4 hours |
| Phase 2: Scaffold site | 1-2 hours |
| Phase 3: Content migration | 3-4 hours |
| Phase 4: API reference | 2-3 hours |
| Phase 5: Deploy | 1-2 hours |
| Phase 6: Automation | 1-2 hours |
| **Total** | **~12-17 hours** |
