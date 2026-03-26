# Future Features

Planned features that are not part of the current implementation scope.

## File Watching

**Priority**: Medium  
**Context**: KB Explorer rewrite (2026-03)

The API should watch the filesystem for external changes to KB files (e.g., Adjutant or other tools modifying files). This would allow the canvas to auto-refresh when files are added, modified, or deleted outside of Adjutant Web.

**Possible approach**:
- Use `fs.watch` or `chokidar` to watch the active KB directory
- Emit events via WebSocket or SSE to connected clients
- Client receives events and refetches affected folder data
- Debounce rapid changes (e.g., git operations touching many files)

**Why deferred**: For v1 of the KB explorer, manual refresh on navigation is sufficient. The user navigates between folders which triggers a fresh fetch each time.
