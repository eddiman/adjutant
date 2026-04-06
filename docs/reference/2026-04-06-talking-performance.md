# Talking Performance Improvements

**Created**: 2026-04-06
**Status**: Complete

---

## Issue 1: Framework write protection [x]

Adjutant had no guardrail preventing it from editing its own source code, prompts, or config files. The sandbox hook blocks access outside the project, and the KB hook blocks KB dirs, but nothing stopped the LLM from writing to `src/`, `.opencode/`, `prompts/`, `.claude/`, or `tests/`.

**Fix:** Added a "Writable scope" section to `adjutant.md` whitelisting only `identity/`, `journal/`, `memory/`, `insights/`, `state/`. Added the same one-liner to `pulse.md` and `review.md` under the security block.

**Files changed:**
- `.opencode/agents/adjutant.md` — new "Writable scope" section after Security
- `prompts/pulse.md` — writable-scope line after injection guard
- `prompts/review.md` — writable-scope line after injection guard

---

## Issue 2: Natural status notifications [x]

`_format_heartbeat()` in `cron.py` produced mechanical, log-style output ("Pulse completed / Checked: kb1, kb2 / Issues: ..."). Read like a machine report, not a briefing.

**Fix:** Rewrote `_format_heartbeat()` to produce natural-language summaries. All-clear pulses now say "Checked ixda. All clear." Single issues get inlined ("Found one issue: ..."). Multiple issues still get bullets but no "Checked:" or "Source:" boilerplate. Escalations say "Flagged for your attention." instead of referencing internal paths.

**Files changed:**
- `src/adjutant/lifecycle/cron.py` — `_format_heartbeat()` rewritten
- `tests/unit/test_cron.py` — `TestFormatHeartbeat` and `TestNotifyCompletion` assertions updated to match new format, added `test_single_issue_inlined` case

---

## Issue 3: KB awareness via query hints [x]

Pulse and review used one generic query string for every KB regardless of what it tracks. The registry only stored name, path, description, model, access. Adjutant had no idea what topics or questions were meaningful per KB.

**Fix:** Added `query_hint` field to `KBEntry` dataclass, registry parser, and registry writer. The field is optional and only serialized when non-empty (backward compatible). Updated `kb_register()` and `kb_create()` to accept `query_hint`. Updated pulse and review prompts to read each KB's `query_hint` and formulate targeted queries. Added a "KB query hints" paragraph to `adjutant.md` so live chat also benefits.

**Files changed:**
- `src/adjutant/capabilities/kb/manage.py` — `KBEntry.query_hint`, parser, writer, `kb_register()`, `kb_create()`
- `.opencode/agents/adjutant.md` — "KB query hints" paragraph in Knowledge Bases section
- `prompts/pulse.md` — step 3 rewritten to use per-KB hints
- `prompts/review.md` — step 4 rewritten to use per-KB hints

**To populate hints on existing KBs:** Edit `knowledge_bases/registry.yaml` and add a `query_hint:` line to each entry, e.g.:
```yaml
  - name: "hopen"
    ...
    query_hint: "Ask about open issues, room measurements, and renovation deadlines"
```

---

## Issue 4: Token-aware pulse loading [x]

Memory index loaded on every first message even for trivial interactions. Pulse journal entries listed every KB individually even when all were clear.

**Fix:** Deferred `memory/memory.md` loading in `adjutant.md` from startup to on-demand (only when conversation touches past decisions, corrections, preferences, or needs memory capture). Rewrote pulse journal format: all-clear pulses write a single "All clear across N KBs." line instead of listing each one. Only KBs with findings get individual entries.

**Files changed:**
- `.opencode/agents/adjutant.md` — startup lazy-load section revised, memory deferred
- `prompts/pulse.md` — step 5 journal format split into all-clear vs. findings paths
