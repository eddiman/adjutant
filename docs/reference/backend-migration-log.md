# Backend Migration Log

Record of the Claude Code CLI backend implementation.

---

## Timeline

| Date | Step | Description | Commit |
|------|------|-------------|--------|
| 2026-03-20 | Plan | Claude Code backend implementation plan created | `0eee29a` |
| 2026-03-23 | Step 0 | Pre-migration remediation: model drift, KB config fixes | `3f0de11` |
| 2026-03-23 | Step 1 | Backend abstraction layer: protocol, factory, OpenCode wrapper | `3f0de11` |
| 2026-03-23 | Step 2 | First call site migration: analyze.py | `b8847ba` |
| 2026-03-23 | Step 3 | Claude CLI backend: backend_claude_cli.py, claude_json.py | `3f0de11`, `8cfb340` |
| 2026-03-23 | Step 4 | Migrate all remaining call sites (18 files) | `8c904d7` |
| 2026-03-23 | Step 5 | KB migration: Claude scaffold for all KBs + templates | `73619a8` |
| 2026-03-23 | Step 6 | Config, setup wizard, switch detection, backend services | `b456b43` |
| 2026-03-23 | Step 7 | Backend-aware test infrastructure, markers, auto-skip | `a627e82` |
| 2026-03-23 | Step 8 | Documentation: guides, architecture, developer docs | — |
| 2026-03-23 | Step 9 | Final verification: security hooks, contract tests | — |

---

## Metrics

- **Net code change (Steps 2-4):** -319 lines. The backend abstraction simplified call sites significantly.
- **New source files:** `backend.py`, `backend_opencode.py`, `backend_claude_cli.py`, `claude_json.py`, `setup/steps/backend.py`
- **New test files:** `test_backend.py`, `test_claude_json.py`, `test_backend_switch.py`, `test_security_hooks.py`, `test_backend_contract.py`
- **Files modified for migration:** 18 source files across core, capabilities, lifecycle, messaging, setup

---

## Design Decisions Made During Implementation

1. **Protocol over ABC:** Used `typing.Protocol` for `LLMBackend` rather than an abstract base class. This allows structural subtyping without inheritance coupling.

2. **Stateless backends:** `get_backend()` creates a new instance per call. Session state lives in filesystem (`state/`) not in backend objects.

3. **Shared error taxonomy:** Both backends map errors to the same set of `error_type` strings. Call sites handle errors identically regardless of backend.

4. **Hooks over permissions for Claude CLI:** `--dangerously-skip-permissions` is required for non-interactive subprocess mode, which bypasses `.claude/settings.json` deny rules. Hooks in `.claude/hooks/` are the primary technical defense.

5. **Single prompt source:** Both backends read agent prompts from `.opencode/agents/*.md`. The Claude CLI backend strips YAML frontmatter and passes the body via `--system-prompt-file`.

---

## Known Limitations

- **Vision:** Claude CLI has no native image input. The backend returns `vision_unsupported` rather than attempting workarounds.
- **Streaming:** Claude CLI does not support `--output-format stream-json` yet. If added in the future, the backend can be updated to use it.
- **Model listing:** Claude CLI returns a static hardcoded list rather than querying available models dynamically.
