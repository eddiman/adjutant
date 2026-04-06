# Performance, Autonomy & Proactive Features Plan

**Date:** 2026-04-06
**Status:** In progress

## Problem

Adjutant's pulse/review cycle queries all 6 KBs sequentially via LLM tool calls. Each KB query takes 60-80s, making a full pulse take 6-8 minutes. There is no cross-KB intelligence, no proactive daily briefing, no self-assessment loop, and no graduated autonomy control.

## Goals

- Reduce pulse wall time from ~7 min to ~90s via parallel KB queries
- Add a morning brief prompt for daily proactive value
- Add a self-assessment prompt for weekly introspection
- Add cross-KB query capability for multi-domain synthesis
- Add graduated autonomy configuration
- Keep all changes generic and KB-agnostic

## Non-goals

- Embedding/vector store integration (future work)
- Webhook triggers (future work)
- Multi-channel messaging (future work)

## Issues

### Issue 1: Parallel KB queries — `kb query-all` command

**Status:** Done

**Problem:** Pulse prompt instructs the LLM agent to call `adjutant kb query` per KB sequentially. With 6 KBs at ~70s each, pulse takes ~7 minutes.

**Solution:** Add `kb_query_all()` async function that queries all registered KBs in parallel via `asyncio.gather()`, and a `kb query-all` CLI command. Update pulse prompt to call this once instead of iterating.

**Files changed:**

| File | Change |
|------|--------|
| `src/adjutant/capabilities/kb/query.py` | Add `kb_query_all()` — parallel query across all KBs |
| `src/adjutant/cli.py` | Add `kb query-all` CLI command |
| `prompts/pulse.md` | Use `kb query-all` instead of per-KB iteration |
| `tests/unit/test_kb_query.py` | Tests for `kb_query_all()` |

**What was done:** Added `kb_query_all()` function that loads the KB registry, builds per-KB query strings (using `query_hint` if set), and runs all queries concurrently with `asyncio.gather()`. Returns a formatted multi-KB result string. Added `kb query-all` CLI command with `--query` option for custom query text. Updated `prompts/pulse.md` step 3 to call `adjutant kb query-all` once. Added 4 unit tests covering parallel dispatch, partial failure, empty registry, and custom query text.

### Issue 2: Morning brief prompt

**Status:** Done

**Problem:** Adjutant has no proactive daily communication. Pulse is a system-level health check, not a user-facing daily planner.

**Solution:** Add `prompts/morning_brief.md` — a user-facing daily brief combining deadlines, overnight KB changes, unread insights, and priority suggestions. Add `brief` CLI command and `brief_cron()` entry point.

**Files changed:**

| File | Change |
|------|--------|
| `prompts/morning_brief.md` | New prompt — daily brief for the user |
| `src/adjutant/lifecycle/cron.py` | Add `brief_cron()` entry point |
| `src/adjutant/cli.py` | Add `brief` CLI command |
| `tests/unit/test_cron.py` | Tests for `brief_cron()` |

**What was done:** Created `morning_brief.md` prompt that queries all KBs via `kb query-all`, reads recent journal + insights, compiles deadlines, and produces a scannable Telegram-ready brief. Added `brief_cron()` and `brief` CLI command following the same pattern as pulse/review. Added test for `brief_cron()`.

### Issue 3: Self-assessment prompt

**Status:** Done

**Problem:** No feedback loop — adjutant never evaluates whether its own notifications were useful, its priorities are still accurate, or its behaviour should change.

**Solution:** Add `prompts/self_assess.md` — a weekly introspection prompt that reviews journal, notification outcomes, and memory, then proposes priority and behaviour adjustments.

**Files changed:**

| File | Change |
|------|--------|
| `prompts/self_assess.md` | New prompt — weekly self-assessment |
| `src/adjutant/lifecycle/cron.py` | Add `self_assess_cron()` entry point |
| `src/adjutant/cli.py` | Add `self-assess` CLI command |
| `tests/unit/test_cron.py` | Tests for `self_assess_cron()` |

**What was done:** Created `self_assess.md` prompt that reviews past week's journal, notification outcomes from `state/actions.jsonl`, memory patterns, and heart.md alignment. Outputs proposed changes to `insights/pending/self-assessment-YYYY-WNN.md` for user review. Added `self_assess_cron()` and `self-assess` CLI command. Added test.

### Issue 4: Autonomy configuration

**Status:** Done

**Problem:** No way to control what adjutant can do autonomously vs. what requires user approval. Binary choice between running and being paused.

**Solution:** Add `autonomy` section to `adjutant.yaml` with a graduated level system and per-action overrides.

**Files changed:**

| File | Change |
|------|--------|
| `src/adjutant/core/config.py` | Add `AutonomyConfig` model |
| `tests/unit/test_config.py` | Tests for new config section |

**What was done:** Added `AutonomyConfig` with `level` (1-4), `auto_approve` list, and `require_approval` list. Level 1 = notify-only, 2 = suggest+act-on-approval, 3 = act+notify, 4 = fully autonomous. Added to `AdjutantConfig`. Added tests for defaults and custom values.

### Issue 5: Cross-KB query command

**Status:** Done

**Problem:** KBs are isolated silos. No way to ask questions that span multiple domains (e.g., scheduling conflicts between IxDA events and Fagkomite conferences).

**Solution:** Add `kb_cross_query()` function and `kb cross-query` CLI command that queries multiple KBs in parallel, then feeds combined results into a synthesis prompt.

**Files changed:**

| File | Change |
|------|--------|
| `src/adjutant/capabilities/kb/query.py` | Add `kb_cross_query()` |
| `src/adjutant/cli.py` | Add `kb cross-query` CLI command |
| `tests/unit/test_kb_query.py` | Tests for `kb_cross_query()` |

**What was done:** Added `kb_cross_query()` that takes a list of KB names and a question, queries them in parallel, then runs a synthesis prompt through the backend to produce a unified answer. Added CLI command with `--kbs` option accepting comma-separated KB names. Added tests.

### Issue 6: Update documentation

**Status:** Done

**Files changed:**

| File | Change |
|------|--------|
| `docs/guides/commands.md` | Add new CLI commands |
| `docs/guides/lifecycle.md` | Document morning brief and self-assessment cycles |
| `CHANGELOG.md` | Add entries for all new features |

**What was done:** Updated commands guide with `kb query-all`, `kb cross-query`, `brief`, and `self-assess` commands. Updated lifecycle guide with morning brief and self-assessment cycles. Added changelog entries.

## Definition of done

- `kb query-all` queries all KBs in parallel, returns combined result
- `kb cross-query` synthesizes answers across selected KBs
- Morning brief prompt provides daily proactive value
- Self-assessment prompt enables weekly introspection
- Autonomy config gives graduated control
- All new code has unit tests
- All docs updated
