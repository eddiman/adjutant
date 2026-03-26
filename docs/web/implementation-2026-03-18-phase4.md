# Phase 4: Adjutant Dashboard Implementation

**Date:** 2026-03-18  
**Branch:** `feature/kb-explorer`  
**Status:** ✅ Completed

## Overview

Added a comprehensive Adjutant control center dashboard to Adjutant Web, providing visibility and control over Adjutant's lifecycle, schedules, identity, and system health. This phase integrates Adjutant Web deeply with Adjutant, turning it into a full-featured management UI.

## Objectives

1. **Schedules Management** — List, enable/disable, and manually trigger scheduled jobs
2. **System Status** — Display Adjutant mode, lifecycle state, and directory
3. **Quick Actions** — Pause, resume, pulse, and review controls
4. **Health Checks** — Verify Adjutant directory, config, and CLI accessibility
5. **Identity Display** — View excerpts from soul.md, heart.md, and registry.md
6. **Activity Feed** — Show recent journal entries

## Implementation

### Backend (API)

Extended `/api/adjutant` routes with new endpoints:

#### Schedules Management
- **`GET /api/adjutant/schedules`** — List all scheduled jobs from `adjutant.yaml`
  - Parses YAML manually to extract schedules block
  - Returns array of schedule objects with name, description, cron, enabled status
- **`POST /api/adjutant/schedules/toggle`** — Enable/disable a schedule
  - Body: `{ name: string, enabled: boolean }`
  - Calls `adjutant schedule enable/disable <name>`
- **`POST /api/adjutant/schedules/run`** — Manually trigger a schedule
  - Body: `{ name: string }`
  - Calls `adjutant schedule run <name>` in background (detached process)

#### Identity & Journal
- **`GET /api/adjutant/identity`** — Get excerpts from identity files
  - Returns first 1000 characters from soul.md, heart.md, registry.md
  - Gracefully handles missing files
- **`GET /api/adjutant/journal/recent`** — Get last 20 journal entries
  - Reads `journal/adjutant.log`
  - Returns entries in reverse order (newest first)

#### Health & Lifecycle
- **`GET /api/adjutant/health`** — Run health checks
  - Checks: Adjutant directory exists, config exists, CLI executable, process running
  - Process check reads PID files and verifies PID alive via `kill(pid, 0)`
  - Returns overall health status + individual check results
  - All four checks must pass for `healthy: true`
- **`POST /api/adjutant/lifecycle`** — Control Adjutant lifecycle
  - Body: `{ action: 'pause' | 'resume' | 'pulse' | 'review' }`
  - Calls corresponding `adjutant <action>` command
  - Returns command output

#### Existing Status Endpoint (Extended)
- **`GET /api/adjutant/status`** — Already existed from Phase 2, extended with process detection
  - Returns mode (adjutant/standalone), lifecycle state, Adjutant directory
  - Now includes `processRunning` (boolean) and `listenerPid` (number, if alive)
  - Lifecycle state detection: checks `KILLED`/`PAUSED` marker files + listener PID liveness
  - New `STOPPED` state: no marker files present and listener process is not alive
  - Process detection uses same priority as Adjutant's `service.py`:
    1. `state/listener.lock/pid` (authoritative — written by listener itself)
    2. `state/telegram.pid` (written by launcher)

### Frontend (Web)

Created comprehensive dashboard UI at `/adjutant`:

#### Component Structure

```
web/src/components/AdjutantDashboard/
├── AdjutantDashboard.tsx          # Main container, data fetching orchestration
├── AdjutantDashboard.module.css   # Grid layout, card base styles
├── SystemStatus.tsx               # Mode, state, directory display
├── SystemStatus.module.css
├── SchedulesManager.tsx           # Schedule list with expand/collapse, toggle, run
├── SchedulesManager.module.css
├── QuickActions.tsx               # Pause/Resume/Pulse/Review buttons
├── QuickActions.module.css
├── HealthChecks.tsx               # Health check results with refresh button
├── HealthChecks.module.css
├── IdentityDisplay.tsx            # Tabbed view: soul, heart, registry
├── IdentityDisplay.module.css
├── ActivityFeed.tsx               # Recent journal entries
├── ActivityFeed.module.css
└── index.ts                       # Barrel export
```

#### Features

**System Status Card:**
- Shows current mode (Adjutant vs Standalone)
- Displays lifecycle state with colored indicator:
  - OPERATIONAL (green) — no marker files, listener process alive
  - PAUSED (yellow) — PAUSED marker file present
  - KILLED (red) — KILLED marker file present
  - STOPPED (gray) — no marker files, listener process not alive
- Shows process status (running with PID or not running)
- Shows Adjutant directory path

**Schedules Manager (Full Width):**
- Lists all schedules from `adjutant.yaml`
- Expandable cards showing:
  - Name, description, cron expression
  - Enabled/disabled status badge
  - Script path or KB operation details
  - Log file path
- Actions per schedule:
  - Enable/Disable toggle
  - Run Now button (with confirmation)
- Shows count in header

**Quick Actions Card:**
- Pause button (visible when OPERATIONAL — hidden when PAUSED, KILLED, or STOPPED)
- Resume button (visible when PAUSED)
- Pulse button (always visible — standalone CLI operation, works without listener)
- Review button (always visible — standalone CLI operation, works without listener)
- Color-coded hover states
- Emoji icons for visual clarity

**Health Checks Card:**
- Overall health indicator (green/red dot)
- Individual checks with ✓/✗:
  - Adjutant Directory exists
  - Config file exists
  - CLI executable
  - Process running (listener PID alive)
- All four checks must pass for overall "healthy" status
- Refresh button (rotates on hover)

**Identity Display (Full Width):**
- Tabbed interface: Soul | Heart | Registry
- Shows first 1000 characters from each file
- Monospace font for markdown content
- Scrollable content area (max 400px height)

**Activity Feed (Full Width):**
- Last 20 journal entries
- Reverse chronological order (newest first)
- Monospace font with bullet points
- Scrollable (max 400px height)

#### Routing

Added route in `App.tsx`:
```tsx
<Route path="/adjutant" element={<AdjutantDashboard />} />
```

Updated `Sidebar.tsx`:
- Added "Adjutant" link between Home and KB list
- Uses control icon (gear/cog symbol)
- Active state when on `/adjutant` page
- Link-based navigation (doesn't trigger KB selection)

#### Error Handling

- Loading state while fetching all data
- Error state if Adjutant integration unavailable
- Graceful degradation if specific endpoints fail
- Confirmation dialogs for destructive actions (Run Now)
- Alert feedback for lifecycle actions

### Design

**Grid Layout:**
- Responsive grid (auto-fit, minmax 400px)
- Full-width cards: Schedules, Identity, Activity Feed
- Standard cards: System Status, Quick Actions, Health Checks
- Mobile: Collapses to single column

**Theming:**
- Supports both default and Bauhaus themes
- Uses existing design tokens
- Consistent card styles with rest of app
- Color-coded status indicators
- Smooth transitions and hover states

## Testing

- ✅ All 94 existing tests passing
- ✅ Frontend builds without TypeScript errors
- ✅ No regressions in existing functionality
- Manual testing needed:
  - Dashboard loads correctly when Adjutant is available
  - Schedules list populates from `adjutant.yaml`
  - Enable/disable toggles update correctly
  - Run Now triggers jobs in background
  - Quick actions execute and refresh status
  - Health checks run and display results
  - Identity tabs switch correctly
  - Activity feed shows journal entries

## Files Changed

### Backend
- `api/src/routes/adjutant.ts` — Added 6 new endpoints (~200 lines added)

### Frontend
- `web/src/App.tsx` — Added `/adjutant` route, imported dashboard component
- `web/src/components/Sidebar/Sidebar.tsx` — Added Adjutant link in navigation
- `web/src/components/AdjutantDashboard/` — 14 new files (7 components + 7 CSS modules + index)

### Documentation
- `docs/implementation-2026-03-18-phase4.md` — This file

## API Endpoint Summary

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/adjutant/status` | System status (existing, Phase 2) |
| GET | `/api/adjutant/schedules` | List scheduled jobs |
| POST | `/api/adjutant/schedules/toggle` | Enable/disable a schedule |
| POST | `/api/adjutant/schedules/run` | Manually trigger a schedule |
| GET | `/api/adjutant/identity` | Get identity file excerpts |
| GET | `/api/adjutant/journal/recent` | Get last 20 journal entries |
| GET | `/api/adjutant/health` | Run health checks |
| POST | `/api/adjutant/lifecycle` | Control lifecycle (pause/resume/pulse/review) |
| POST | `/api/adjutant/kb/query` | Query KB (existing, Phase 3) |

## Dependencies

**No new dependencies** — Uses existing libraries:
- Express (backend)
- React + React Router (frontend)
- Existing design system and theming

## Security Considerations

- Session token auth middleware applies to all `/api/adjutant/*` routes (from Phase 2)
- Lifecycle actions execute with Adjutant's permissions (no privilege escalation)
- Schedule runs are detached processes (non-blocking)
- Health checks are read-only (no system modifications)
- Journal reading limited to last 20 entries (prevents memory issues)

## Performance

- Dashboard fetches 5 endpoints in parallel on mount (Promise.all)
- Schedule list parses YAML on server (minimal parsing, no pyyaml dependency)
- Identity files limited to 1000 chars each (fast reads)
- Journal reads only last 20 lines (tail-like performance)
- No polling — manual refresh only

## Future Enhancements (Not Implemented)

1. **Real-time Updates** — WebSocket connection for live journal tailing
2. **Schedule Logs Viewer** — Modal to view full log file for a schedule
3. **Memory System Overview** — Stats from memory directory (facts, patterns, summaries)
4. **News Pipeline Status** — Last briefing timestamp, source stats
5. **Token Usage Graphs** — Charts showing usage over time
6. **KB Registry Management** — Add/remove/edit KBs from dashboard
7. **Resource Usage** — Disk usage, process stats
8. **Schedule Add Form** — Create new schedules via UI

## Conclusion

Phase 4 transforms Adjutant Web from a KB explorer into a full Adjutant control center. Users can now manage the entire Adjutant lifecycle, monitor system health, and control scheduled operations — all from a beautiful, intuitive web interface.

The implementation maintains the clean separation between Adjutant Web (UI) and Adjutant (agent), using the CLI as the communication boundary. All operations respect Adjutant's security model and configuration.

**Next Steps:** Manual testing in a real Adjutant environment, then commit and push.
