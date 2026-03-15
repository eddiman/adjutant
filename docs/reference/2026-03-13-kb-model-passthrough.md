# 2026-03-13 — KB Run Model Pass-Through

**Status**: Complete

---

## What Changed

`kb_run()` now resolves the KB's model tier from the registry and passes `--model <resolved>` to the KB's CLI subprocess. Previously, the model field in `registry.yaml` was only used for KB **queries** — KB **run** operations never received it, causing KBs to fall back to their own hardcoded defaults.

The immediate trigger: portfolio-kb's `analyze` command was running with `opencode-go/glm-5` (a hardcoded default) instead of the intended `anthropic/claude-haiku-4-5` (the `cheap` tier configured in the registry).

---

## Problem

When `kb_run()` invoked a KB's CLI subprocess for scheduled operations (e.g. `adjutant kb run portfolio analyze`), it never passed `--model`. The data flow had a gap:

```
crontab → notify_wrap.py → adjutant kb run portfolio analyze
  → kb_run() loaded registry entry (model: "cheap" — available but UNUSED)
  → subprocess: .venv/bin/python -m src.cli --mock analyze  (no --model)
  → Click default: model="opencode-go/glm-5"               (hardcoded fallback)
```

Three layers of hardcoded defaults in portfolio-kb compounded the issue:

| File | Line | Default |
|------|------|---------|
| `src/cli.py` | 51 | `default="opencode-go/glm-5"` |
| `src/pipeline/analyze.py` | 131 | `model: str = "opencode-go/glm-5"` |
| `src/pipeline/analyze.py` | 192 | `model: str = "opencode-go/glm-5"` |

The model tier resolution system (`resolve_kb_model()` in `core/model.py`) existed and worked correctly — it was just never called from `kb_run()`.

---

## Solution

### Adjutant: `src/adjutant/capabilities/kb/run.py`

After `_get_kb()` returns the registry entry, `kb_run()` now:

1. Reads `entry["model"]` from the registry (e.g. `"cheap"`)
2. Checks whether `--model` is already present in the caller's `args`
3. If not, calls `resolve_kb_model()` to resolve the tier to a concrete model ID
4. Prepends `["--model", resolved_model]` to the extra args passed to the subprocess

This applies to both the Python CLI path and the bash fallback path.

### Portfolio-KB: hardcoded defaults removed

| File | Before | After |
|------|--------|-------|
| `src/cli.py:51` | `default="opencode-go/glm-5"` | `required=True` |
| `src/pipeline/analyze.py:131` | `model: str = "opencode-go/glm-5"` | `model: str` (no default) |
| `src/pipeline/analyze.py:192` | `model: str = "opencode-go/glm-5"` | `model: str` (keyword-only, no default) |

---

## Data Flow (After)

```
crontab → notify_wrap.py → adjutant kb run portfolio analyze
  → kb_run() reads entry["model"] = "cheap"
  → resolve_kb_model("cheap", ...) → "anthropic/claude-haiku-4-5"
  → "--model" not in args → prepend ["--model", "anthropic/claude-haiku-4-5"]
  → subprocess: .venv/bin/python -m src.cli --mock analyze --model anthropic/claude-haiku-4-5
  → Click: analyze(model="anthropic/claude-haiku-4-5")
  → _call_llm(prompt, model="anthropic/claude-haiku-4-5")
```

Manual override still works:

```
adjutant kb run portfolio analyze --model opencode-go/glm-5
  → args=["--model", "opencode-go/glm-5"]
  → kb_run() sees "--model" already in args → skips resolution
  → subprocess runs with glm-5
```

---

## Scope

- Only KBs with a `model` field in `registry.yaml` are affected
- KBs without `--model` CLI support will receive it and error — this is intentional (signals they should add `--model` support if they use LLM calls)
- Currently only `portfolio` has `cli_module` set; other KBs use bash scripts or have no run operations
- The schedule system (`_resolve_command()`, `notify_wrap.py`) is transparent — no changes needed there

---

## Backward Compatibility

- `adjutant kb run portfolio analyze --model X` — explicit args still take precedence
- KBs without a `model` field in registry — no `--model` passed (no change in behavior)
- portfolio-kb's `--model` is now required — running the CLI directly without `--model` will fail explicitly rather than silently using glm-5

---

## Test Results

- Adjutant: 1106 passed (full unit suite)
- Portfolio-KB: 152 passed (full test suite)
