# Testing

How to run the Adjutant test suite and understand its structure.

---

## Overview

Adjutant uses [pytest](https://pytest.org) as its test framework. Tests are organized into two tiers:

| Tier | Location | Tests | Runtime | Description |
|------|----------|-------|---------|-------------|
| Unit | `tests/unit/` | ~1420+ | ~75s | Fast, fully mocked, no external calls |
| Integration | `tests/integration/` | ~20 | ~5s | Real process spawning, mocked external services |

---

## CI Policy

CI automation is **intentionally absent**. The suite runs in ~75 seconds locally. GitHub Actions runners would consume disproportionate minutes for a single-maintainer project.

**Pre-release gate**: before tagging a release, run the full suite and confirm it is clean:

```bash
.venv/bin/pytest tests/ -q
```

All tests must pass. Any failure blocks the release. This is enforced by discipline, not automation. See [Design Decisions](../architecture/design-decisions.md) for the rationale.

---

## Prerequisites

- Python 3.11+ with a `.venv` set up:
  ```bash
  python3 -m venv .venv
  .venv/bin/pip install -e ".[dev]"
  ```

---

## Running Tests

```bash
# Full suite (unit + integration)
.venv/bin/pytest tests/ -q

# Unit tests only
.venv/bin/pytest tests/unit/ -q

# Integration tests only
.venv/bin/pytest tests/integration/ -q

# Single file
.venv/bin/pytest tests/unit/test_kb_run.py -q

# Filter by test name (substring match)
.venv/bin/pytest tests/unit/ -k "test_runs_operation"

# Verbose output
.venv/bin/pytest tests/unit/test_kb_run.py -v

# Stop on first failure
.venv/bin/pytest tests/unit/ -x
```

---

## Directory Structure

```
tests/
└── unit/                    # All tests (~61 files, ~1420+ tests)
    ├── test_lockfiles.py
    ├── test_env.py
    ├── test_paths.py
    ├── test_logging.py
    ├── test_platform.py
    ├── test_model.py
    ├── test_config.py
    ├── test_kb_manage.py
    ├── test_kb_query.py
    ├── test_kb_run.py
    ├── test_schedule_manage.py
    ├── test_schedule_install.py
    ├── test_messaging_dispatch.py
    ├── test_messaging_adaptor.py
    ├── test_status.py
    ├── test_usage_estimate.py
    ├── test_journal_rotate.py
    ├── test_screenshot.py
    ├── test_search.py
    └── ... (61 files total)
```

---

## Isolation Model

Every test creates its own `tmp_path` (via pytest's built-in fixture). There is no shared global state between tests.

Common patterns:

```python
def test_something(tmp_path: Path) -> None:
    # Set up a minimal adjutant directory
    adj_dir = tmp_path / "adjutant"
    adj_dir.mkdir()
    (adj_dir / ".adjutant-root").touch()
    (adj_dir / "adjutant.yaml").write_text("...")

    # Run the code under test
    result = my_function(adj_dir)

    # Assert
    assert result == "expected"
```

For tests that invoke subprocesses (e.g. `kb_run`, schedule operations), patch `subprocess.run` at the module level:

```python
from unittest.mock import patch

def test_kb_run(tmp_path: Path) -> None:
    with patch("adjutant.capabilities.kb.run.subprocess.run") as mock_run:
        mock_run.return_value = type("R", (), {"returncode": 0, "stdout": "ok\n", "stderr": ""})()
        result = kb_run(tmp_path, "mydb", "fetch")
    assert result == "ok\n"
```

---

## Writing a New Test File

Every new module must have a corresponding `tests/unit/test_<module>.py`. Structure:

```python
"""Tests for src/adjutant/capabilities/<name>/<name>.py"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from adjutant.capabilities.<name>.<name> import run_<name>


class TestRun<Name>:
    def test_returns_result_on_success(self, tmp_path: Path) -> None:
        ...

    def test_raises_on_invalid_input(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="..."):
            run_<name>(tmp_path, "bad_input")
```

Group tests in classes named after the function/class under test. Each test method tests one behaviour.

---

## Interpreting Output

```
PASSED tests/unit/test_kb_run.py::TestKbRun::test_runs_operation_and_returns_output
FAILED tests/unit/test_kb_run.py::TestKbRun::test_raises_kb_run_error_on_nonzero_exit
  AssertionError: assert "Something broke" in str(exc_info.value)
```

A successful run ends with all `PASSED` and exit code 0. Any `FAILED` line is a failure — pytest shows the assertion that failed and the values that didn't match.

Quick triage workflow:

```bash
# See only failures
.venv/bin/pytest tests/unit/ -q --tb=short 2>&1 | grep -A 5 "FAILED"

# Re-run only failed tests
.venv/bin/pytest tests/unit/ --lf

# Run with full tracebacks
.venv/bin/pytest tests/unit/ -v --tb=long
```

## Durable operation tests

The operation layer requires failure-boundary tests in addition to normal result tests. Keep these cases covered when changing the worker or delivery code:

- Duplicate Telegram update acceptance returns the original operation and advances the offset monotonically.
- Concurrent workers claim a queued operation once.
- Result text and all outbound delivery chunks commit together.
- A restart delivers a persisted result without invoking the backend again.
- Expired read-only work can be queued again, while a possible mutation enters reconciliation.
- Cancellation reaches the running backend task and ends in a terminal state.
- Runtime timeout persists a terminal result and user-visible delivery.
- An ambiguous Telegram failure records `uncertain` and follows the bounded retry policy.
- Long text is delivered in complete chunks instead of being truncated.
- Inline KB acceptance creates one claimed attempt atomically and is invisible to daemon claims.
- A child deadline derives from the parent's frozen deadline and restart does not extend either deadline.
- Expired recovery closes the current attempt, and a late stale completion fails its ownership fence.
- Parent cancellation reaches execution children without cancelling conversational follow-ups.
- The OpenCode hook extends recognized standalone KB calls, accepts quoted arguments, rejects compound commands, and leaves unrelated shell timeouts unchanged.
- CLI receipt output exposes the child ID before inline backend execution returns.

Use fake handlers and fake Telegram senders for deterministic unit tests. Process cleanup, server reconnect, and memory-soak tests belong in integration tests because they require actual subprocess ownership and resource sampling.

### Persistent OpenCode release trial

Run the persistent transport trial with the same installed OpenCode version, model, prompt, and work directory for both samples. Record at least three cold `opencode run` calls and three warm `opencode run --attach` calls. Exclude server startup from the warm per-operation timing, but record startup separately. The release record must include:

- cold and attached durations plus their medians;
- successful output equivalence;
- server version, root PID, and root-plus-descendant RSS before and after repeated work;
- process count after repeated work;
- recovery after terminating the owned server;
- native abort and uncertain-disconnect fixture results;
- soft and hard memory-policy outcomes;
- KB permission fixtures and proof that KB operation kinds do not use the shared server.

The 2026-09-24 trial on OpenCode 1.18.0 used six identical `openai/gpt-5.6-luna` prompts. Cold durations were 4.595, 7.150, and 4.859 seconds. Attached durations were 2.747, 3.092, and 5.812 seconds. The median fell from 4.859 to 3.092 seconds, a 36.4 percent reduction, and all six results returned `OK`.

The server process tree used 381 MB before model work and 693 MB after five additional attached calls. The five calls completed in 3.190, 4.609, 2.706, 3.815, and 1.923 seconds. One transient RSS sample exposed a disappearing-child accounting race; the sampler now skips that child instead of returning zero for the whole tree. A 600 MB soft limit then stopped the 666 MB idle server cleanly. A forced server death produced a new healthy instance with one root process and 379 MB RSS.

Persistent reuse remains disabled for `kb_query` and `kb_write`. The KB permission and dual-workdir fixtures verify distinct process sessions, no `--attach` argument, external-directory denial, and read-only edit/write/bash denial.
