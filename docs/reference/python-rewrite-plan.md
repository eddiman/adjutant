# Adjutant Python Rewrite Plan

**Version:** 1.0  
**Date:** 2026-03-08  
**Status:** Draft

---

## Executive Summary

This document evaluates the feasibility, costs, and benefits of rewriting adjutant from bash to Python. The current codebase consists of **53 bash scripts (~10,600 lines)**, **518 bats tests (~7,100 lines)**, and the **portfolio_kb knowledge base (~2,800 lines)**.

**Recommendation:** A full rewrite is a **high-risk, high-effort** undertaking. However, a **targeted migration of the test suite and performance-critical components** would yield significant benefits with manageable risk.

---

## Validation of Previous Pros/Cons

### Claims Made Earlier

| Claim | Verdict | Evidence |
|-------|---------|----------|
| "Tests would run faster in Python" | **VALID** | pytest runs tests in-process (1-5ms overhead vs 10-50ms for bats). 518 tests x 40ms savings = ~20 seconds saved per run. |
| "NDJSON parsing would be faster" | **VALID** | Per-line `jq` calls spawn 1000 subprocesses = 3-5 seconds. Python `json.loads()` in-process = 5-20ms. **100-1000x faster**. |
| "yfinance fetches would be faster" | **VALID** | Current: 1 Python process per ticker (serial). Python native: batch fetch or `ThreadPoolExecutor`. **5-10x faster**. |
| "Inline `python3 -c` calls add overhead" | **VALID** | Each inline call pays Python startup (~20-50ms). In-process = 0ms. |
| "Agent would use less RAM" | **MIXED** | Bash baseline: ~1-2MB. Python baseline: ~10-30MB. Python uses **more** RAM for the interpreter, but **fewer child processes**. Net effect: similar or slightly higher. |
| "YAML parsing would be more reliable" | **VALID** | Bash grep/sed YAML parsing cannot handle anchors, multi-line strings, or nested structures reliably. PyYAML is spec-compliant. |
| "HTTP requests would be faster" | **PARTIALLY VALID** | Single requests: same speed (network-bound). Multiple requests: Python wins due to connection pooling and async. **2-10x faster for batch**. |

### Revised Summary

| Category | Python Advantage | Magnitude |
|----------|------------------|-----------|
| Test execution speed | **Significant** | 5-10x faster |
| NDJSON parsing | **Significant** | 100-1000x faster |
| Batch HTTP requests | **Moderate** | 2-10x faster |
| YAML parsing reliability | **Significant** | Correctness, not speed |
| RAM usage | **Negative** | +10-30MB baseline |
| Startup time | **Negative** | +50-200ms interpreter load |
| Maintainability | **Significant** | Type hints, IDE support, debugging |

---

## Migration Strategy Options

### Option A: Full Rewrite

Rewrite all 53 scripts and 518 tests in Python.

**Pros:**
- Unified codebase
- Maximum performance gains
- Full pytest test coverage
- Type safety, IDE support

**Cons:**
- ~3-6 months effort
- High risk of regressions
- Must maintain bash version during migration
- Learning curve for bash-specific patterns

**Estimated Effort:** 400-800 hours

### Option B: Hybrid Approach (Recommended)

Keep bash for orchestration, rewrite performance-critical components as Python modules called from bash.

**Pros:**
- Lower risk
- Incremental migration
- Preserves working orchestration
- Targets actual bottlenecks

**Cons:**
- Two languages to maintain
- Some subprocess overhead remains
- Less unified architecture

**Estimated Effort:** 80-160 hours

### Option C: Test Suite Only

Rewrite only the test suite in pytest, keep bash scripts unchanged.

**Pros:**
- Solves timeout problem directly
- Lowest effort
- No production code changes
- Better debugging experience

**Cons:**
- Tests now test bash scripts from Python (acceptable but not ideal)
- No performance gains in production code

**Estimated Effort:** 60-120 hours

---

## Recommended Approach: Option B (Hybrid)

Migrate in phases, prioritizing by impact.

### Phase 1: Python Test Framework (Week 1-2)

Create pytest infrastructure that can test bash scripts.

**Deliverables:**
```
tests/
├── conftest.py           # Fixtures: ADJ_DIR, mock binaries, env setup
├── test_unit/
│   ├── test_paths.py
│   ├── test_env.py
│   ├── test_lockfiles.py
│   └── ...
├── test_integration/
│   ├── test_dispatch.py
│   ├── test_commands.py
│   └── ...
└── fixtures/
    ├── mock_opencode.py  # NDJSON generator
    ├── mock_curl.py      # Telegram API responses
    └── mock_nordnet.py   # Portfolio API responses
```

**Key Fixtures:**
```python
@pytest.fixture
def adj_dir(tmp_path, monkeypatch):
    """Create isolated adjutant directory structure."""
    adj_dir = tmp_path / ".adjutant"
    adj_dir.mkdir()
    (adj_dir / "state").mkdir()
    (adj_dir / "scripts").mkdir()
    monkeypatch.setenv("ADJUTANT_HOME", str(adj_dir))
    return adj_dir

@pytest.fixture
def mock_opencode(tmp_path, monkeypatch):
    """Create mock opencode binary returning NDJSON."""
    mock_bin = tmp_path / "bin"
    mock_bin.mkdir()
    script = mock_bin / "opencode"
    script.write_text('#!/bin/bash\necho \'{"type":"text","text":"OK"}\'')
    script.chmod(0o755)
    monkeypatch.setenv("PATH", f"{mock_bin}:{os.environ['PATH']}")
```

**Migration Ratio:** 1 bats test ~= 0.5-1 pytest test (less boilerplate)

### Phase 2: NDJSON Parser Module (Week 3)

Replace the line-by-line `jq` NDJSON parsing with a Python module.

**Current (slow):**
```bash
while IFS= read -r line; do
  type=$(echo "$line" | jq -r '.type // empty')
  # ...more jq calls per line
done < <(opencode run ...)
```

**New (fast):**
```python
# scripts/lib/ndjson_parser.py
import json
from typing import Iterator, Dict, Any

def parse_ndjson(stream) -> Iterator[Dict[str, Any]]:
    """Parse NDJSON stream, yielding parsed records."""
    for line in stream:
        line = line.strip()
        if line:
            yield json.loads(line)

def extract_text_from_opencode(stream) -> str:
    """Extract concatenated text from OpenCode NDJSON output."""
    text_parts = []
    for record in parse_ndjson(stream):
        if record.get("type") == "text":
            text_parts.append(record.get("text", ""))
    return "".join(text_parts)
```

**Bash Wrapper:**
```bash
# scripts/lib/ndjson_parser.sh
parse_opencode_output() {
    python3 "${ADJ_DIR}/scripts/lib/ndjson_parser.py" --extract-text
}
```

### Phase 3: Portfolio KB Python Module (Week 4-5)

Rewrite portfolio_kb scripts as a Python package.

**Structure:**
```
portfolio_kb/
├── __init__.py
├── fetch.py              # Replace fetch.sh
├── analyze.py            # Replace analyze.sh
├── trade.py              # Replace trade.sh
├── nordnet/
│   ├── __init__.py
│   ├── api.py            # Replace lib/nordnet_api.sh
│   ├── auth.py           # Replace lib/nordnet_auth.sh
│   └── models.py         # Pydantic models for API responses
├── signals.py            # Replace lib/signals.sh
├── portfolio_state.py    # Replace lib/portfolio_state.sh
└── yfinance_fetch.py     # Batch yfinance with threading
```

**Key Improvements:**
- `yfinance_fetch.py`: Fetch all tickers in parallel with `ThreadPoolExecutor`
- `nordnet/api.py`: Use `httpx` with connection pooling
- `signals.py`: In-process JSON manipulation, no `jq` subprocesses
- `portfolio_state.py`: Single Python process for all rendering

### Phase 4: YAML Configuration Parser (Week 6)

Replace grep/sed YAML parsing with PyYAML.

**Current (fragile):**
```bash
yaml_value=$(grep "^key:" file.yaml | sed 's/key: *//')
```

**New (robust):**
```python
# scripts/lib/config.py
import yaml
from pathlib import Path
from pydantic import BaseModel

class AdjutantConfig(BaseModel):
    instance_name: str
    messaging_backend: str = "telegram"
    # ...full schema

    @classmethod
    def load(cls, path: Path) -> "AdjutantConfig":
        with open(path) as f:
            data = yaml.safe_load(f)
        return cls(**data)
```

### Phase 5: HTTP Client Module (Week 7)

Create unified HTTP client for Telegram, Brave Search, Nordnet.

**Structure:**
```python
# scripts/lib/http_client.py
import httpx
from typing import Optional, Dict, Any

class HttpClient:
    def __init__(self):
        self._client = httpx.Client(timeout=30.0)
    
    def get(self, url: str, **kwargs) -> Dict[str, Any]:
        response = self._client.get(url, **kwargs)
        response.raise_for_status()
        return response.json()
    
    def post(self, url: str, **kwargs) -> Dict[str, Any]:
        response = self._client.post(url, **kwargs)
        response.raise_for_status()
        return response.json()

# Singleton for connection reuse
_client: Optional[HttpClient] = None

def get_client() -> HttpClient:
    global _client
    if _client is None:
        _client = HttpClient()
    return _client
```

### Phase 6: Bash Orchestration Layer (Week 8)

Update bash scripts to call Python modules instead of inline processing.

**Pattern:**
```bash
# Before
result=$(echo "$json" | jq -r '.data[].value')

# After
result=$(python3 "${ADJ_DIR}/scripts/lib/json_utils.py" \
    --input "$json" \
    --extract '.data[].value')
```

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Regression in production | Medium | High | Comprehensive pytest suite before any migration |
| Python dependency conflicts | Low | Medium | Use `venv`, pin versions in requirements.txt |
| Performance regression | Low | Medium | Benchmark before/after for each module |
| Knowledge loss during migration | Medium | Medium | Document all bash patterns before rewriting |
| Increased complexity (2 languages) | High | Low | Clear module boundaries, Python for compute, bash for glue |

---

## Effort Estimation

| Phase | Hours | Dependencies |
|-------|-------|--------------|
| Phase 1: Test Framework | 40-60 | None |
| Phase 2: NDJSON Parser | 16-24 | Phase 1 |
| Phase 3: Portfolio KB | 60-100 | Phase 2 |
| Phase 4: YAML Parser | 16-24 | Phase 1 |
| Phase 5: HTTP Client | 24-40 | Phase 1 |
| Phase 6: Bash Integration | 40-60 | Phases 2-5 |
| **Total (Option B)** | **196-308** | - |
| **Option A (Full Rewrite)** | **400-800** | - |
| **Option C (Tests Only)** | **60-120** | - |

---

## Dependencies

```
requirements.txt:
  pytest>=7.0
  pytest-asyncio>=0.21
  pytest-xdist>=3.0
  httpx>=0.24
  pyyaml>=6.0
  pydantic>=2.0
  yfinance>=0.2
```

---

## Success Metrics

| Metric | Current | Target | How to Measure |
|--------|---------|--------|----------------|
| Test suite runtime | >2 min (timeouts) | <30 sec | `time pytest` |
| NDJSON parsing (1000 lines) | 3-5 sec | <50 ms | Benchmark script |
| yfinance fetch (10 tickers) | 10x Python startup | <2 sec | Benchmark script |
| RAM usage (idle) | ~5-10 MB | ~20-40 MB | `ps aux` |
| RAM usage (under load) | ~60 GB (bug) | ~50-100 MB | `ps aux` |

---

## Open Questions

1. **Should we use `asyncio` throughout?** 
   - Pros: Better I/O concurrency, single-threaded
   - Cons: More complex, requires async-compatible libraries
   - Recommendation: Start sync, add async where needed (HTTP, polling)

2. **Should we use a CLI framework like `click` or `typer`?**
   - Pros: Better argument parsing, help generation
   - Cons: Another dependency, bash already handles this
   - Recommendation: Yes, for Python entry points

3. **How to handle the existing 518 bats tests during migration?**
   - Option A: Delete and rewrite in pytest
   - Option B: Keep both during transition
   - Recommendation: Parallel implementation, delete bats after pytest coverage >90%

---

## Conclusion

The **hybrid approach (Option B)** offers the best risk/reward ratio:

- **Solves the test timeout problem** (pytest runs 5-10x faster)
- **Targets actual performance bottlenecks** (NDJSON, yfinance, YAML)
- **Preserves working orchestration** (bash remains the glue layer)
- **Incremental migration** (one module at a time, always deployable)
- **Estimated effort:** 200-300 hours over 8 weeks

A full rewrite (Option A) would be cleaner long-term but carries higher risk and requires 2-3x more effort.
