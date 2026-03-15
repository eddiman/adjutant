# 2026-03-15 — Plan Alignment Review

**Status**: Complete  
**Context**: After the codebase audit and architecture hardening, reviewed all plan documents against the current state of the codebase to identify stale references, collisions, and genuinely remaining work.

---

## Documents Reviewed

| Document | Path | Original Date |
|----------|------|---------------|
| Framework Plan | `docs/reference/framework-plan.md` | 2026-03-01 |
| Phase 8 — Scheduling | `docs/development/phase-8.md` | Pre-rewrite |
| KB Runtime Hardening | `docs/reference/kb-runtime-hardening-plan.md` | 2026-03-06 |
| Codebase Audit | `docs/reference/2026-03-15-codebase-audit.md` | 2026-03-15 |

---

## Key Finding: Plans Were Written for Bash, Codebase Is Now Python

All three plan documents were written before the Python rewrite (PR #1, `f3f7d88`, 2026-03-13). They describe the architecture in terms of bash scripts under `scripts/`. The entire codebase now lives under `src/adjutant/` as Python modules.

**Updated**: All three plan docs now have post-rewrite notes and bash-to-Python mapping tables (commit `ebd2d36`).

---

## What the Codebase Audit Advanced

The audit (commits `c9c8bec`, `85eef60`) directly addressed items from the framework plan:

| Plan Item | What the Audit Did |
|-----------|-------------------|
| Security fixes (Part 8.7) | Prompt injection guards on all prompts, scoped `emergency_kill`, SHA256 tarball verification |
| Eliminate duplication (Part 1.3) | Deduplicated `_sanitize`, `_read_env_cred`, registry parsers, colour/TTY helpers |
| Rate limiting configurability (Part 8.7) | `rate_limit.window_seconds` now configurable via `adjutant.yaml` |
| CLI entrypoint testing (Part 8.6) | Added `test_cli.py` — smoke tests for all 22 commands + 13 subcommands |
| Configuration layer (Part 4) | Added `chat_timeout_seconds`, `rate_limit.window_seconds` to Pydantic config models |
| Dead code (Part 1.8) | Removed `reply.py` (dead module), fixed version inconsistency |

---

## What Remains

These items from the framework plan are genuinely not yet done:

### 1. Multi-Instance Support (Low Priority)

`adjutant.yaml` has an `instance.name` field but there is no CLI support for managing multiple instances. Would require:

- `adjutant --instance <name>` flag or `ADJUTANT_INSTANCE` env var
- Instance-scoped `ADJ_DIR` resolution
- Per-instance LaunchAgent/systemd service
- Per-instance PID lock files

**Blocked by**: Nothing. Low demand — single-instance covers all current use cases.

### 2. Additional Messaging Backends (Low Priority)

`src/adjutant/messaging/adaptor.py` defines the interface. `TelegramSender` in `send.py` is the only implementation. Adding Slack/Discord would require:

- New `src/adjutant/messaging/slack/` or `discord/` directory
- Implementing `msg_send_text`, `msg_send_photo`, `msg_typing_start/stop`
- OAuth flow for Slack (vs Telegram's simpler bot token)
- Webhook vs polling decision for each backend

**Blocked by**: No demand. Telegram covers the current use case.

### 3. LaunchAgent Plist Hardening (Medium Priority)

The wizard generates a basic macOS LaunchAgent plist. The framework plan's checklist:

- `KeepAlive: true` (unconditional) — **needs verification** that the wizard sets this correctly
- `ThrottleInterval` should be >= 30 seconds — **not verified**
- Listener must never send startup notification itself — only `startup.sh`/`control.py` sends "I'm online" — **needs verification** to prevent notification spam on launchd restarts

**Where to check**: `src/adjutant/setup/steps/service.py` (plist generation), `src/adjutant/messaging/telegram/listener.py` (startup message logic).

### 4. Tier 3 System/Integration Tests (Low Priority)

Only unit tests exist (1139 tests in `tests/unit/`). No process isolation or integration tests. Would cover:

- Listener start/stop lifecycle
- PID lock acquisition/release
- LaunchAgent install/uninstall
- End-to-end message flow (mock Telegram API)
- Schedule crontab install/remove

**Blocked by**: Test infrastructure design. pytest fixtures for process management would need careful cleanup.

### 5. Plugin/Capability Discovery (Low Priority)

Capabilities exist as Python modules (`screenshot/`, `vision/`, `search/`, `kb/`, `schedule/`) but there's no formal discovery system. The framework plan proposed `capability.yaml` files per capability. Would enable:

- Dynamic capability listing (`adjutant capabilities list`)
- Wizard auto-discovery of available features
- Runtime capability enable/disable without code changes

**Blocked by**: Not clear this is needed. Current approach (Python module imports + feature flags in `adjutant.yaml`) works fine.

---

## Same-Day Changes Not in Original Audit Scope

These were committed on 2026-03-15 but were separate from the audit:

| Commit | Change | Audit Doc Updated? |
|--------|--------|-------------------|
| `1399151` | Typing indicator stuck on hung opencode — added timeouts, `try/finally`, `max_duration` ceiling | Yes (added to audit doc) |
| `75c254f` | Multi-image vision (`run_vision_multi`), `HttpClient.get_text()`, RSS fetch fix | Yes (added to audit doc) |
| `9940457` | Missing reference doc for KB model pass-through (2026-03-13) | N/A — doc commit only |

---

## Collision Analysis

No destructive collisions were found. The audit changes are purely additive/corrective and don't conflict with any planned work. Specific interactions:

| Area | Audit Change | Plan Impact |
|------|-------------|-------------|
| `send.py` | Extracted `sanitize_message()`, typing `max_duration` | Compatible with future messaging backends — `sanitize_message` is backend-agnostic |
| `dispatch.py` | Configurable rate limit window | Compatible with multi-instance — config is per-`adjutant.yaml` |
| `listener.py` | Process all updates per batch | No plan dependency |
| `wizard.py` | `WizardContext` dataclass | Helps future plugin discovery (context can carry capability flags) |
| `config.py` | Added `chat_timeout_seconds`, `window_seconds` | Extends the Pydantic config model — compatible with any future config additions |
| `update.py` | SHA256 checksum verification | Release workflow updated — future releases automatically get checksums |
| `control.py` | Scoped `emergency_kill` | Compatible with multi-instance (pattern already includes `adj_dir`) |

---

## Summary

The framework plan is architecturally complete through Phase 7 (Python rewrite + audit). Five items remain, all low-to-medium priority. No collisions exist between the audit changes and any planned work. The codebase is in a healthy state for continued development.
