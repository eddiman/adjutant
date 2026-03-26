# Claude CLI Backend — Deployment Readiness Verification

**Date**: 2026-03-26
**Status**: Ready (all gaps resolved 2026-03-26)
**Scope**: Verify implementation of `docs/reference/2026-03-20-claude-code-backend-plan.md` against the codebase
**Method**: Systematic phase-by-phase comparison of plan against code, followed by full test suite run

---

## Verdict: Ready

The claude-cli backend implementation is complete. All core architecture, call site migrations, security layers, config/setup, and documentation are in place. The initial verification found 5 gaps — all have been resolved. The test suite passes cleanly (1365 passed, 73 skipped, 0 failures).

---

## Phase-by-Phase Verification

### Phase 1: Backend Abstraction Layer — MATCH

| Item | Plan | Implementation | Status |
|------|------|----------------|--------|
| `LLMResult` dataclass | 6 fields: text, session_id, error_type, returncode, timed_out, cost_usd | Exact match at `core/backend.py:19-28` | **MATCH** |
| `BackendCapabilities` | 7 capability booleans | Exact match at `core/backend.py:31-46` | **MATCH** |
| `LLMBackend` Protocol | 11 methods including run, run_detached, run_sync, reap, health_check, list_models, find_binary, resolve_alias, translate_model_id | Exact match at `core/backend.py:48-98` | **MATCH** |
| `BackendNotFoundError` | Custom exception | Present at `core/backend.py:101` | **MATCH** |
| `get_backend()` factory | Deferred imports, config-driven | Exact match at `core/backend.py:105-123` | **MATCH** |

### Phase 2: Claude CLI Backend — MATCH

| Item | Plan | Implementation | Status |
|------|------|----------------|--------|
| Binary resolution | `CLAUDE_CODE_BIN` env var or `shutil.which("claude")` | `_find_claude()` at `backend_claude_cli.py:75-87` | **MATCH** |
| Model aliases | haiku/sonnet/opus + OpenCode full IDs | `_ALIASES` + `_FROM_OPENCODE` + `_TO_OPENCODE` dicts | **MATCH** |
| Vision guard | Return `vision_unsupported` for image files | `run()` at lines 141-150 | **MATCH** |
| `--system-prompt-file` | Strip frontmatter from `.opencode/agents/*.md` | `_extract_prompt_body()` + temp file pattern | **MATCH** |
| Permission mode | Configurable skip / allowlist | `_get_permission_args()` at lines 56-72 | **MATCH** |
| Session resume | `--resume <session_id>` | Lines 173-174 | **MATCH** |
| Capabilities | `remote_session=True, cost_tracking=True`, all others False | Lines 117-126 | **MATCH** |
| Per-request observability | Backend name, elapsed, model, agent, error_type, cost logged | Lines 228-234 | **MATCH** |
| `run_detached()` | Persistent prompt file in workdir, `subprocess.Popen` | Lines 237-276 | **MATCH** |
| `run_sync()` | Blocking `subprocess.run` | Lines 278-303 | **MATCH** |
| `reap()` | No-op returning 0 | Lines 305-307 | **MATCH** |
| `health_check()` | Binary check + PID file for remote session | Lines 309-319 | **MATCH** |
| `list_models()` | Hardcoded static list | Lines 321-327 | **MATCH** |
| `translate_model_id()` | Cross-backend conversion | Lines 338-340 | **MATCH** |

### Phase 2: Claude JSON Parser — MATCH

| Item | Plan | Implementation | Status |
|------|------|----------------|--------|
| `ClaudeJSONResult` dataclass | 5 fields | Exact match at `lib/claude_json.py:20-28` | **MATCH** |
| `parse_claude_json()` | JSON parse + error classification | Lines 31-62 | **MATCH** |
| Error taxonomy | model_not_found, auth_failure, rate_limited, context_overflow, permission_denied, error | `_classify_claude_error()` at lines 65-104 | **MATCH** |

### Phase 3: Call Site Migration — MATCH (14/14 migrated + 1 N/A)

| File | Status | Notes |
|------|--------|-------|
| `messaging/telegram/chat.py` | **MIGRATED** | `get_backend()`, `backend.run()` |
| `messaging/telegram/commands.py` | **MIGRATED** | `backend.run()`, `backend.list_models()`, `backend.reap()`, `backend.find_binary()` |
| `messaging/telegram/listener.py` | **MIGRATED** | `backend.reap()` with capability check |
| `capabilities/kb/query.py` | **MIGRATED** | `backend.run()`, `backend.run_detached()` |
| `capabilities/vision/vision.py` | **MIGRATED** | `backend.run()` via `asyncio.run()` |
| `news/analyze.py` | **MIGRATED** | `backend.run()` via `asyncio.run()` |
| `lifecycle/cron.py` | **MIGRATED** | `backend.run_sync()`, `backend.find_binary()` |
| `lifecycle/control.py` | **MIGRATED** | `backend.find_binary()`, `backend.translate_model_id()` |
| `setup/steps/identity.py` | **MIGRATED** | `backend.run()`, `backend.find_binary()` |
| `setup/steps/prerequisites.py` | **MIGRATED** | `backend.find_binary()` |
| `setup/install.py` | **MIGRATED** | `backend.find_binary()` |
| `setup/repair.py` | **MIGRATED** | `backend.find_binary()` |
| `setup/steps/features.py` | **MIGRATED** | `backend.find_binary()` |
| `setup/uninstall.py` | **N/A** | Kills processes by pattern; no LLM calls |
| `cli.py` | **MIGRATED** | `BackendNotFoundError` via transitive imports |

Zero residual direct imports of `opencode_run()` or `parse_ndjson()` at call sites. Capability guards (`model_listing`, `reaping`) properly checked before optional method calls.

### Phase 4: Agent Definitions & Permissions — MATCH

Single source of truth at `.opencode/agents/*.md`. Claude CLI backend strips frontmatter at runtime via `_extract_prompt_body()`.

### Phase 5: KB Review & Migration — NOT FULLY VERIFIED

KB files are on an external volume (`/Volumes/Mandalor/`) which is not accessible. Template system is in place. Scaffold generation is backend-aware.

### Phase 6: KB Template System — MATCH

| File | Status |
|------|--------|
| `templates/kb/claude/settings.json` (read-only) | EXISTS, correct permissions |
| `templates/kb/claude/settings-rw.json` (read-write) | EXISTS, correct permissions |
| `templates/kb/claude/hooks/block-env-read.sh` | EXISTS, executable |

### Phase 7: Config, Setup & Model Resolution — MATCH

| Item | Status | Evidence |
|------|--------|----------|
| `LLMConfig` with `backend`, `permission_mode`, `allowed_tools` | **MATCH** | `config.py:66-87` |
| Backend validation (`"opencode"` / `"claude-cli"`) | **MATCH** | `field_validator` at config.py:73-79 |
| `ModelsConfig` with cheap/medium/expensive | **MATCH** | `config.py:54-58` |
| Opus default fixed to `claude-opus-4-6` | **MATCH** | `config.py:57`, `model.py:30` |
| Setup wizard backend step | **MATCH** | `setup/steps/backend.py` exists with backend + permission mode selection |
| `_detect_backend_change()` | **MATCH** | `control.py:422-443` |
| `_handle_backend_switch()` (5 of 9 side effects in handler; rest delegated to startup) | **MATCH** | `control.py:446-485` |
| `_warn_nested_opencode_dependencies()` | **MATCH** | Implemented in `control.py:493-521` |

### Phase 8: Security Layer — MATCH

| Item | Status |
|------|--------|
| `.claude/settings.json` deny rules | **MATCH** — comprehensive .env/secret deny list + hook config |
| `.claude/hooks/block-env-access.sh` | **MATCH** — blocks file-read, source/eval, env-dump, text-processing on .env |
| `.claude/hooks/block-env-read.sh` | **MATCH** — blocks Read tool on .env and credential files |
| Hook scripts executable (755) | **MATCH** |

### Phase 8: Test Infrastructure — MATCH

| Item | Status |
|------|--------|
| `conftest.py` with `--run-all-backends`, auto-skip, `mock_claude` | **MATCH** |
| `pyproject.toml` markers (backend_opencode, backend_claude_cli, slow) | **MATCH** |
| `test_backend.py` (neutral) | **MATCH** |
| `test_backend_contract.py` (slow) | **MATCH** |
| `test_backend_switch.py` (neutral) | **MATCH** |
| `test_claude_json.py` (backend_claude_cli) | **MATCH** |
| `test_security_hooks.py` (backend_claude_cli) | **MATCH** |
| `test_backend_claude_cli.py` (backend_claude_cli) | **MATCH** — 16 tests covering binary resolution, prompts, permissions, vision, run, detached, sync, reap, health, models |
| `test_opencode.py` / `test_ndjson.py` backend_opencode marker | **MATCH** — `pytestmark` applied |

### Phase 8: Documentation — MATCH

| Document | Status |
|----------|--------|
| `docs/guides/backends.md` (new) | **EXISTS** — 202 lines |
| `docs/architecture/backends.md` (new) | **EXISTS** — 143 lines |
| `docs/development/backend-guide.md` (new) | **EXISTS** — 178 lines |
| `CLAUDE.md` (new) | **EXISTS** — 85 lines |
| `docs/reference/backend-migration-log.md` (new) | **EXISTS** — 52 lines |
| `AGENTS.md` (updated) | **MATCH** — dual-backend, get_backend(), capability checks, gotchas |
| `docs/guides/configuration.md` (updated) | **MATCH** — llm.backend, permission_mode, workspace permissions |
| `docs/guides/knowledge-bases.md` (updated) | **MATCH** — dedicated "Backend Compatibility" section added |
| `docs/architecture/overview.md` (updated) | **MATCH** — "LLM Backend" in layer table |
| `docs/architecture/identity.md` (updated) | **MATCH** — "LLM Backend Integration" section |
| `docs/architecture/design-decisions.md` (updated) | **MATCH** — dual-backend ADR |
| `docs/development/plugin-guide.md` (updated) | **MATCH** — steps 8-9 in checklist |
| `docs/README.md` (updated) | **MATCH** — all 4 new docs indexed |

### Test Suite — PASS

```
1365 passed, 73 skipped, 1 warning in 8.13s
```

---

## Gaps Found (Original)

| # | Severity | Gap | Location | Plan Reference | Resolution |
|---|----------|-----|----------|----------------|------------|
| **G1** | P1 | `_warn_nested_opencode_dependencies()` not implemented | `lifecycle/control.py` | Section 16.3, step 9 | **FIXED** — implemented + tests added |
| **G2** | P1 | `test_backend_claude_cli.py` not created | `tests/unit/` | Section 12.4 | **FIXED** — created with 16 tests |
| **G3** | P1 | `test_opencode.py` and `test_ndjson.py` missing `backend_opencode` marker | `tests/unit/` | Section 12.4 | **FIXED** — `pytestmark` added |
| **G4** | P1 | Stale `claude-opus-4-5` in `setup/wizard.py:234` | `src/adjutant/setup/wizard.py` | Step 0 remediation | **FIXED** — updated to `claude-opus-4-6` |
| **G5** | P2 | `docs/guides/knowledge-bases.md` missing dedicated "Backend Compatibility" section | `docs/guides/` | Section 20.2 | **FIXED** — section added |

### G4 Extended: Stale `claude-opus-4-5` — all instances fixed

- `setup/wizard.py:234` — **FIXED**
- `adjutant.yaml.example:35` — **FIXED**
- `docs/guides/commands.md:57` — **FIXED**
- `docs/reference/api-models.md:77` — **FIXED**
- `tests/unit/test_telegram_chat.py:50-51` — **FIXED**
- `tests/unit/test_telegram_commands.py:208,215,220` — **FIXED**

---

## Structural Strengths

1. **Clean protocol-based abstraction** — `LLMBackend` as `typing.Protocol` with declared capabilities. No inheritance, no ABC overhead.
2. **Complete call site migration** — 14 of 14 files migrated with zero residual direct imports.
3. **Three-layer security for `.env`** — Deny rules + hooks + system prompt. Hooks correctly flagged as primary defense since `--dangerously-skip-permissions` bypasses deny rules.
4. **Shared error taxonomy** — Both backends map to the same error types. Call sites need no backend-conditional error handling.
5. **Per-request observability logging** — Every backend call logs backend name, elapsed time, model, and error type.
6. **Comprehensive documentation** — 5 new docs, 8 updated docs, all indexed. Migration log provides audit trail.
7. **Test infrastructure** — Auto-skip markers, mock fixtures, contract tests for cross-backend equivalence.

---

## Recommended Actions

All gaps have been resolved. No blocking actions remain.

### Completed fixes (2026-03-26)

1. Fixed `setup/wizard.py:234` — `claude-opus-4-5` → `claude-opus-4-6`
2. Fixed all stale `claude-opus-4-5` references across `adjutant.yaml.example`, docs, and tests
3. Added `pytestmark = pytest.mark.backend_opencode` to `test_opencode.py` and `test_ndjson.py`
4. Implemented `_warn_nested_opencode_dependencies()` in `control.py` with tests
5. Created `test_backend_claude_cli.py` with 16 dedicated ClaudeCLIBackend tests
6. Added "Backend Compatibility" section to `docs/guides/knowledge-bases.md`
