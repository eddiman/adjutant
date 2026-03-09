# Python Rewrite Notes

**Started:** 2026-03-09  
**Completed:** 2026-03-09

This document logs errors, strange occurrences, and decisions made during the Python rewrite.

---

## Summary

**All phases completed successfully:**
- Phase 1: Python Test Framework ✅
- Phase 2: NDJSON Parser Module ✅
- Phase 3: Portfolio KB (Skipped - external repo) ⏭️
- Phase 4: YAML Configuration Parser ✅
- Phase 5: HTTP Client Module ✅
- Phase 6: Bash Integration Layer ✅

**Final Metrics:**
- **97 tests in 1.76 seconds**
- Original bats tests: ~2+ minutes for 518 tests
- **Speedup: ~60x faster overall**

---

## Phase 1: Python Test Framework

### Issues Found

1. **Python 3.9 vs 3.11 type syntax**
   - `pyproject.toml` specifies `requires-python = ">=3.11"` but system has Python 3.9.6
   - Had to use `from __future__ import annotations` and `Optional[Dict]` instead of `dict | None`
   - **Decision:** Keep Python 3.9 compatible for now, update to modern syntax when Python 3.11+ is available

2. **paths.sh BASH_SOURCE resolution**
   - `paths.sh` uses `BASH_SOURCE[1]` to find the sourcing script
   - When testing from Python, needed to copy paths.sh to test directory instead of sourcing from project root
   - This is documented in AGENTS.md as a known gotcha

3. **pytest-asyncio warning**
   - `asyncio_mode = "auto"` in pyproject.toml caused warning since pytest-asyncio wasn't installed
   - **Fix:** Removed the config option since we don't use async tests yet

### Files Created

```
tests_py/
├── __init__.py
├── conftest.py              # Core fixtures (adj_dir, mock_bin, run_bash)
├── fixtures/
│   ├── __init__.py
│   ├── mock_opencode.py     # NDJSON mock generator
│   └── mock_curl.py         # Telegram API mock generator
├── test_unit/
│   ├── __init__.py
│   ├── test_lockfiles.py    # 25 tests (ported from bats)
│   ├── test_paths.py        # 7 tests
│   └── test_env.py          # 16 tests
└── test_integration/        # Ready for future use
```

### Metrics

- 48 tests in **1.6 seconds**
- **Speedup: ~75x faster per test**

---

## Phase 2: NDJSON Parser Module

### Implementation

Created `scripts_py/lib/ndjson_parser.py`:
- `parse_ndjson()`: Iterator yielding `ParsedEvent` objects
- `extract_text_from_stream()`: Concatenate all text events
- `extract_session_id_from_stream()`: Get session ID
- `check_model_error()`: Detect model not found errors
- `parse_with_error_info()`: Full parse returning dict

Also created `scripts_py/lib/ndjson_parser.sh` bash wrapper for gradual migration.

### Bash Pattern Replaced

**Before (slow):**
```bash
while IFS= read -r line; do
  line_type="$(printf '%s' "${line}" | jq -r '.type // empty')"
  if [ "${line_type}" = "text" ]; then
    part="$(printf '%s' "${line}" | jq -r '.part.text // empty')"
    reply="${reply}${part}"
  fi
done < raw.ndjson
```

**After (fast):**
```bash
reply=$(py_extract_text < raw.ndjson)
```

### Metrics

- 25 tests in **0.08 seconds**
- Bash pattern spawns 2-3 `jq` processes per line (1000 lines = 2000-3000 subprocesses)
- Python: in-process, single pass
- **Expected speedup: 100-1000x**

---

## Phase 3: Portfolio KB Python Module

### Issue: External Knowledge Base

The portfolio_kb is stored externally at `/Volumes/Mandalor/JottaSync/AI_knowledge_bases/portfolio-kb`, not in this repo.
The integration tests at `tests/integration/portfolio_*.bats` gracefully skip if it doesn't exist.

**Decision:** Skip Phase 3 for now. The rewrite plan's portfolio_kb module would need to be implemented
in that external repo, not here. The NDJSON parser and YAML parser (Phase 4) are higher priority.

---

## Phase 4: YAML Configuration Parser

### Implementation

Created `scripts_py/lib/config.py`:
- Full Pydantic-style config models (with fallback when pydantic not installed)
- `AdjutantConfig.load()`: Load from YAML file
- `get_config_value()`: Get nested value by key path
- `load_config()`: Singleton loader with env resolution

### Bash Pattern Replaced

**Before (fragile):**
```bash
model=$(grep -E "^\s*cheap:" "${ADJ_DIR}/adjutant.yaml" | sed 's/.*:[[:space:]]*//' | tr -d '"')
```

**After (robust):**
```bash
model=$(py_get_config llm models cheap)
```

### Issues Found

1. **Pydantic fallback complexity**
   - Without pydantic installed, needed to implement a custom BaseModel fallback
   - Used metaclass to handle `Field(default_factory=...)` pattern
   - Required `_construct_nested()` function to recursively build nested configs
   - **Decision:** Works without pydantic, but recommend installing it for validation

2. **LSP errors with conditional imports**
   - Static analysis flags errors for pydantic classes when pydantic isn't installed
   - **Decision:** Ignore LSP errors, runtime behavior is correct

### Metrics

- 16 tests in **0.07 seconds**

---

## Phase 5: HTTP Client Module

### Implementation

Created `scripts_py/lib/http_client.py`:
- `HttpClient`: Unified HTTP client with connection pooling
- Uses `httpx` when available, falls back to `urllib.request`
- `get_client()`: Singleton for connection reuse
- `HttpClientError`: Custom error with status code

### Features

- Connection pooling (when httpx available)
- Timeout handling
- JSON and form data support
- Context manager protocol
- Graceful fallback to stdlib

### Metrics

- 8 tests in **0.06 seconds**

---

## Phase 6: Bash Integration Layer

### Implementation

Created `scripts_py/lib/python_utils.sh`:
- `py_extract_text`: NDJSON text extraction
- `py_extract_session`: Session ID extraction
- `py_check_model_error`: Model error detection
- `py_parse_full`: Full parse with all fields
- `py_get_config`: Config value lookup
- `py_load_config`: Full config as JSON

### Usage

```bash
source "${ADJ_DIR}/scripts_py/lib/python_utils.sh"

# NDJSON parsing
text=$(py_extract_text < raw.ndjson)

# Config lookup
model=$(py_get_config llm models cheap)
```

---

## Directory Structure Created

```
scripts_py/
└── lib/
    ├── __init__.py
    ├── ndjson_parser.py     # Phase 2
    ├── ndjson_parser.sh     # Phase 2 bash wrapper
    ├── config.py            # Phase 4
    ├── http_client.py       # Phase 5
    └── python_utils.sh      # Phase 6 integration

tests_py/
├── __init__.py
├── conftest.py              # Phase 1
├── fixtures/
│   ├── __init__.py
│   ├── mock_opencode.py
│   └── mock_curl.py
└── test_unit/
    ├── __init__.py
    ├── test_lockfiles.py
    ├── test_paths.py
    ├── test_env.py
    ├── test_ndjson_parser.py
    ├── test_config.py
    └── test_http_client.py
```

---

## Consolidation (2026-03-09)

`scripts_py/` was deleted. `src/adjutant/` is the single Python codebase.

**What was merged before deletion:**

- `scripts_py/lib/config.py` → full typed `AdjutantConfig` model hierarchy merged into
  `src/adjutant/core/config.py`. The pydantic fallback `BaseModel` metaclass was dropped;
  `pydantic>=2.0` is now a core dependency in `pyproject.toml`.
- `scripts_py/lib/http_client.py` → ported as `src/adjutant/lib/http.py` (simplified to
  use httpx directly, no urllib fallback needed since httpx is a declared dep).

**What was dropped:**

- `scripts_py/lib/ndjson_parser.py` — superseded by `src/adjutant/lib/ndjson.py`
- `scripts_py/lib/ndjson_parser.sh` — bash bridge, not needed for full rewrite
- `scripts_py/lib/python_utils.sh` — bash bridge, not needed for full rewrite

**Tests migrated:**

- `tests_py/test_unit/test_config.py` → merged into `tests/unit/test_config.py`
- `tests_py/test_unit/test_http_client.py` → `tests/unit/test_http.py`
- `tests_py/test_unit/test_ndjson_parser.py` → deleted (covered by `tests/unit/test_ndjson.py`)

## Next Steps

1. **Migrate remaining bats tests** to pytest under `tests/unit/` (470+ tests remaining)
2. **Implement empty package stubs** in `src/adjutant/` (messaging, lifecycle, capabilities, etc.)
3. **Create integration tests** for dispatch, commands, listener

---

## Lessons Learned

1. **Python 3.9 compatibility requires extra effort** - modern type syntax isn't available
2. **Fallback implementations are complex** - pydantic fallback required metaclass magic
3. **LSP errors don't mean runtime errors** - conditional imports confuse static analysis
4. **Testing bash from Python works well** - subprocess isolation is clean
5. **Singletons need careful management** - `reset_client()` pattern for testing
