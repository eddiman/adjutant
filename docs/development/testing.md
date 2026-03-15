# Testing

How to run the Adjutant test suite and understand its structure.

---

## Overview

Adjutant uses [pytest](https://pytest.org) as its test framework. Tests are organized into two tiers:

| Tier | Location | Tests | Runtime | Description |
|------|----------|-------|---------|-------------|
| Unit | `tests/unit/` | ~1139 | ~75s | Fast, fully mocked, no external calls |
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
└── unit/                    # All tests (~52 files, ~1081 tests)
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
    └── ... (52 files total)
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
