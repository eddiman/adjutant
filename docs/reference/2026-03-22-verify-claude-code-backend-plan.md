# Verification Prompt: Claude Code Backend Plan

**Purpose:** Systematically verify that `docs/reference/2026-03-20-claude-code-backend-plan.md` accurately covers the current codebase state and has no gaps, contradictions, or stale assumptions.

---

## Instructions

Read the plan at `docs/reference/2026-03-20-claude-code-backend-plan.md` in full. Then perform each verification task below. For each task, report:

- **MATCH** — plan accurately reflects the code
- **GAP** — something in the code is not covered by the plan
- **STALE** — plan describes something that doesn't match current code
- **CONTRADICTION** — plan contradicts itself across sections

Collect all findings into a summary at the end with recommended plan edits.

---

## 1. Coupling Inventory Verification

The plan (Section 1 + Section 4) claims specific coupling counts and file lists. Verify each one against the actual codebase:

- [ ] Count all direct `opencode_run()` callers. Compare to plan's claim of 6 files. List any missing or extra.
- [ ] Count all direct `subprocess.run`/`subprocess.Popen` callers that invoke `opencode` (bypassing `opencode_run`). Compare to plan's claim of 3 files.
- [ ] Count all `opencode_reap()` callers. Compare to plan's claim of 2 files.
- [ ] Count all `parse_ndjson()` callers. Compare to plan's claim of 5 files.
- [ ] Count all `shutil.which("opencode")` checks. Compare to plan's claim of 7 files.
- [ ] Check for any `_find_opencode()` callers beyond cron.py.
- [ ] Check for any opencode references the plan misses entirely (grep for `opencode` across all `.py` files and compare to the plan's inventory).

## 2. CLI Arguments Verification

The plan (Section 4.2) lists exact CLI arguments constructed per call site. Verify each one:

- [ ] `chat.py` — read the actual `opencode_run()` call. Do the args match the plan's table?
- [ ] `commands.py` (pulse/reflect) — verify args match.
- [ ] `commands.py` (model list) — verify it calls `opencode models`.
- [ ] `query.py` (read path) — verify args match.
- [ ] `query.py` (write path) — verify the detached subprocess pattern matches.
- [ ] `vision.py` — verify `-f` flag usage and args match.
- [ ] `analyze.py` — verify args match.
- [ ] `cron.py` — verify args match.
- [ ] `identity.py` — verify args and model match.
- [ ] `control.py` — verify `opencode web --mdns` invocation matches.
- [ ] Check if any call sites construct args the plan doesn't document.

## 3. Session Management Verification

The plan (Section 4.3) describes session management in chat.py. Verify:

- [ ] Session file path: is it actually `state/telegram_session.json`?
- [ ] Session fields: does it store `{session_id, epoch, model}` or different fields?
- [ ] Session timeout: is it actually 2 hours? Where is the timeout configured?
- [ ] Model mismatch invalidation: does the code actually check this?
- [ ] Session cleared on `/model` switch: verify this behavior in commands.py.

## 4. NDJSON Parser Verification

The plan (Section 4.4 + Section 6.2) describes the NDJSON format and proposes a Claude JSON parser. Verify:

- [ ] Read `lib/ndjson.py`. Does the parse format match what the plan describes?
- [ ] Does `parse_ndjson` currently detect only `model_not_found` errors, as the plan claims?
- [ ] Does `identity.py` actually have a custom NDJSON parser (not using the lib)?

## 5. Backend Protocol Completeness

The plan (Section 5.1) proposes an `LLMBackend` protocol with specific methods. Verify that every current opencode usage pattern is covered:

- [ ] `run()` — covers all async `opencode_run()` call sites?
- [ ] `run_detached()` — covers all `subprocess.Popen` fire-and-forget patterns?
- [ ] `run_sync()` — covers the cron.py `subprocess.run` pattern?
- [ ] `reap()` — covers `opencode_reap()`?
- [ ] `health_check()` — covers `opencode_health_check()`?
- [ ] `list_models()` — covers `opencode models`?
- [ ] `find_binary()` — covers all `shutil.which("opencode")` checks?
- [ ] Are there any invocation patterns in the current code that don't map to any protocol method?

## 6. Config Schema Verification

The plan (Section 11) proposes changes to `adjutant.yaml` and `core/config.py`. Verify:

- [ ] Read `core/config.py`. Does `LLMConfig` currently exist? What fields does it have?
- [ ] Read `adjutant.yaml`. What is the current `llm:` section structure?
- [ ] Does the plan's proposed `llm.backend` field conflict with anything existing?
- [ ] Are the model alias mappings (haiku, sonnet, opus) consistent with what's in the current config?

## 7. Migration Table Completeness

The plan (Section 7.1) lists every file that changes. Verify:

- [ ] For each file in the migration table, confirm the file exists at the stated path.
- [ ] Search for any `.py` file that imports from `core.opencode` or `lib.ndjson` that is NOT in the migration table.
- [ ] Search for any `.py` file that calls `shutil.which("opencode")` that is NOT in the migration table.
- [ ] Check `setup/uninstall.py` — does it have process kill patterns as the plan claims?
- [ ] Check `cli.py` — does it reference `OpenCodeNotFoundError`?
- [ ] Check `setup/steps/features.py` — does it check for opencode?

## 8. KB Inventory Verification

The plan (Section 9.1) claims a specific KB inventory with config states. Verify:

- [ ] Read `knowledge_bases/registry.yaml`. Are all 6 KBs listed? Any missing or extra?
- [ ] For each KB, check if the claimed `opencode.json` exists at the KB path.
- [ ] For each KB, check if the claimed `.opencode/agents/kb.md` exists.
- [ ] For each KB, check if any `.claude/` directory already exists.
- [ ] Verify the model drift claims: does ixda's `kb.yaml` say `inherit`? Does portfolio's say `medium`?
- [ ] Verify fagkomite is actually missing `kb.yaml` and `opencode.json`.
- [ ] Verify portfolio-kb's `opencode.json` actually lacks `.env` deny rules.

## 9. Security Model Verification

The plan (Section 19) describes a three-layer defense for `.env` protection. Verify:

- [ ] Read `opencode.json`. Do the deny rules match what the plan describes?
- [ ] Are there any `.env` bypass vectors in the current `opencode.json` that the plan doesn't address?
- [ ] Does the agent definition (`adjutant.md`) contain the "don't read .env" instruction?
- [ ] Check if any KB's `opencode.json` is missing `.env` deny rules (plan claims portfolio-kb).

## 10. Process Lifecycle Verification

The plan (Sections 15-16) describes process lifecycle and switch detection. Verify against `lifecycle/control.py`:

- [ ] Does `startup()` currently start `opencode web`? How?
- [ ] Does `emergency_kill()` currently kill opencode processes? What patterns does it use?
- [ ] Does `restart()` currently stop and start services? What's the sequence?
- [ ] Is there any existing backend switch detection? Or is `state/backend.txt` entirely new?
- [ ] Does `listener.py` currently have a web watchdog? What's the cycle interval?
- [ ] Does `listener.py` currently run `opencode_reap()`? What's the cycle interval?

## 11. Remote Session (`claude remote-control`) Verification

The plan adds `claude remote-control` as the Claude CLI equivalent of `opencode web`. Verify internal consistency:

- [ ] Section 6 describes remote session lifecycle. Does Section 15 match?
- [ ] The capabilities table (Section 5.1) lists `remote_session: Yes` for claude-cli. Is this referenced consistently in call site migration and doctor checks?
- [ ] The `start_backend_service()` function in Section 15 dispatches to `_start_opencode_web()` or `_start_claude_remote()`. Does the switch detection in Section 16 also handle stopping both?
- [ ] The risk register has a risk about internet dependency. Is the watchdog restart behavior documented in Section 6 and Section 15 consistently?
- [ ] `control.py` migration entry (Section 7.1) says "Backend-conditional: opencode web or claude remote-control". Does the `listener.py` entry's watchdog also reflect this?

## 12. Test Coverage Verification

The plan (Section 12) proposes test organization. Verify against current tests:

- [ ] Does `test_opencode.py` exist? What does it test?
- [ ] Does `test_ndjson.py` exist? What does it test?
- [ ] Does `conftest.py` exist? What fixtures does it provide?
- [ ] For each consumer test the plan says to update (test_telegram_chat.py, test_kb_query.py, etc.), verify the file exists and currently mocks `opencode_run`.
- [ ] Check if there are test files the plan doesn't mention that also mock `opencode_run` or reference opencode.

## 13. Documentation Cross-Reference

The plan (Section 20) lists docs to create and update. Verify:

- [ ] For each existing doc the plan says to update, verify the file exists.
- [ ] Read `AGENTS.md`. Does it currently mention opencode in the ways the plan claims?
- [ ] Are there docs referencing opencode that the plan doesn't list for update?

## 14. Internal Consistency Check

Verify the plan doesn't contradict itself across sections:

- [ ] Section 5.1 defines `BackendCapabilities` with specific fields. Does the capabilities table in the same section use all those fields? Are `remote_session` and `web_server` both present?
- [ ] Section 6 says Claude CLI uses `--system-prompt-file`. Section 8 says agent prompts come from `.opencode/agents/*.md` with frontmatter stripped. Are these consistent?
- [ ] Section 7.1 migration table lists `control.py` complexity as "Medium". Does this match the scope of changes described in Sections 15-16?
- [ ] Section 17 (Migration Checklist) lists 11 new source files. Count the actual new files described across all phases — do they match?
- [ ] Section 21 (Implementation Order) references all phases. Is every phase mentioned? Are the step numbers sequential and complete?
- [ ] The `BackendCapabilities` dataclass (Section 5.1) has `remote_session` and `web_server` as separate booleans. Is this the right split? OpenCode has web_server=True/remote_session=False, Claude CLI has web_server=False/remote_session=True. Are these used consistently in call sites?

## 15. Edge Cases and Missing Coverage

Look for things the plan should address but doesn't:

- [ ] What happens if both `opencode` and `claude` binaries are installed but the wrong one is configured?
- [ ] What happens if `adjutant.yaml` specifies `claude-cli` but the user hasn't run `claude login`?
- [ ] Does the plan address how `core/model.py` interacts with the backend? (Read model.py to check.)
- [ ] Does the plan address `core/platform.py`'s opencode references?
- [ ] Does the plan address `capabilities/schedule/install.py`'s opencode references?
- [ ] Does the plan address `messaging/dispatch.py` — does it reference opencode?
- [ ] Does the plan address the `observability/` module — does it reference opencode?
- [ ] Does `core/process.py` have opencode-specific logic that needs migration?

---

## Output Format

After completing all checks, produce:

1. **Summary table** — one row per check item, with status (MATCH/GAP/STALE/CONTRADICTION) and a one-line note.
2. **Critical gaps** — anything that would cause the migration to fail if not addressed.
3. **Recommended plan edits** — specific changes to make to the plan document, with section references.
4. **Files the plan misses** — any source files that reference opencode but aren't in the migration table.
