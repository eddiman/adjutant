# Testing

How to run the Adjutant test suite and understand its structure.

---

## Overview

Adjutant uses [bats-core](https://github.com/bats-core/bats-core) as its test framework, with [bats-support](https://github.com/bats-core/bats-support) and [bats-assert](https://github.com/bats-core/bats-assert) helper libraries installed as git submodules.

Tests are organized into three tiers based on isolation requirements:

| Tier | Scope | Mocking | Status |
|------|-------|---------|--------|
| 1 | Unit tests (pure logic) | None — only `ADJUTANT_HOME` isolation | Complete (210 tests) |
| 2 | Integration tests | Mock `curl`/`opencode` via PATH injection | Complete (319 tests) |
| 3 | System tests | Full process isolation | Planned |

---

## CI Policy

CI automation is **intentionally absent**. The 529-test bats suite spawns subprocesses heavily and runs in 60–90 seconds locally. GitHub Actions runners would consume disproportionate minutes for a single-maintainer project.

**Pre-release gate**: before tagging a release, run the full suite locally and confirm it is clean:

```bash
bats tests/unit/ tests/integration/
```

All 529 tests must pass. Any failure blocks the release. This is enforced by discipline, not automation. See [Design Decisions](../architecture/design-decisions.md) for the rationale.

---

## Prerequisites

- `bats` (v1.13+) — `brew install bats-core` on macOS
- Git submodules initialized — `git submodule update --init --recursive`

---

## Running Tests

**First-time setup:**

```bash
brew install bats-core
git submodule update --init --recursive
```

**Common commands (from project root):**

```bash
# Run all unit tests
bats tests/unit/

# Run all integration tests
bats tests/integration/

# Run full suite (recommended: use --jobs for parallelism)
bats --jobs 4 tests/unit/ tests/integration/

# Run a single test file
bats tests/unit/paths.bats

# Filter by test name (regex)
bats --filter "load_env succeeds" tests/unit/env.bats

# TAP output (machine-readable)
bats --tap tests/unit/
```

**Recommended workflow:**

```bash
# During development — run only affected files
bats tests/unit/wizard.bats tests/integration/wizard.bats

# Debug a specific test
bats --filter "repair: healthy" tests/integration/wizard.bats

# Full regression check
bats --jobs 4 tests/unit/ tests/integration/
```

Use `--jobs 4` (or higher) for full-suite runs. Each test uses its own isolated temp directory, so parallel execution is safe.

---

## Directory Structure

```
tests/
├── test_helper/
│   ├── setup.bash              # Common setup/teardown helpers
│   ├── mocks.bash              # Mock creators, assertion helpers, state seeders
│   └── lib/
│       ├── bats-support/       # Git submodule
│       └── bats-assert/        # Git submodule
├── unit/                       # Tier 1 (210 tests)
│   ├── paths.bats
│   ├── env.bats
│   ├── lockfiles.bats
│   ├── logging.bats
│   ├── platform.bats
│   ├── adaptor.bats
│   ├── lifecycle.bats
│   ├── wizard.bats
│   ├── journal_rotate.bats
│   └── kb.bats
├── integration/                # Tier 2 (319 tests)
│   ├── notify.bats
│   ├── reply.bats
│   ├── send.bats
│   ├── chat.bats
│   ├── photos.bats
│   ├── commands.bats
│   ├── dispatch.bats
│   ├── fetch.bats
│   ├── analyze.bats
│   ├── briefing.bats
│   ├── vision.bats
│   ├── screenshot.bats
│   ├── status.bats
│   ├── usage_estimate.bats
│   ├── wizard.bats
│   ├── journal_rotate.bats
│   └── kb.bats
└── system/                     # Tier 3 (planned)
```

---

## Tier 1 — Unit Tests

Covers scripts that contain pure bash logic with zero external dependencies. Every test runs in full isolation: a temp directory is created per test, `ADJUTANT_HOME` is pointed at it, and it is torn down afterward.

The shared helper (`tests/test_helper/setup.bash`) provides:
- **`setup_test_env`** — Creates `$TEST_ADJ_DIR`, exports `ADJUTANT_HOME`, seeds a minimal `adjutant.yaml` and `.env`, creates `state/`, `journal/`, `identity/` subdirectories.
- **`teardown_test_env`** — Removes the temp directory and unsets all env vars.

Scripts covered: `scripts/common/` (paths, env, lockfiles, logging, platform), `scripts/messaging/adaptor.sh`, `scripts/lifecycle/pause.sh`, `scripts/lifecycle/resume.sh`, `scripts/setup/`, `scripts/observability/journal_rotate.sh`, `scripts/capabilities/kb/manage.sh`.

---

## Tier 2 — Integration Tests

Covers scripts that call external tools (`curl`, `opencode`, `npx`, `crontab`). Mocking is done by placing stub scripts earlier in `$PATH`.

The mock infrastructure (`tests/test_helper/mocks.bash`) provides:
- **`setup_mocks`** — Creates `mock_bin/` and `mock_log/`, prepends to `$PATH`, creates expected directories.
- **`teardown_mocks`** — Restores `$PATH`, cleans up background processes.
- **Script copying** — `setup.bash` uses `cp -R` (not symlinks) to copy `scripts/` into the test directory. Tests can safely overwrite scripts with stubs without affecting production files.

Mock creators write executable scripts to `$MOCK_BIN/` that log all invocations and return canned responses. See [Testing Appendix](../reference/testing-appendix.md) for the full mock creator and assertion helper reference.

Scripts covered: all Telegram adaptor scripts, news pipeline (`fetch.sh`, `analyze.sh`, `briefing.sh`), capabilities (`vision.sh`, `screenshot.sh`), observability (`status.sh`, `usage_estimate.sh`), and setup/KB/journal rotation.

---

## Tier 3 — System Tests (Planned)

Covers lifecycle and daemon scripts that manage real processes, manipulate crontab, use interactive prompts, or run infinite loops with signal handlers. These require full process isolation (Docker container or dedicated test user).

Scripts planned: `emergency_kill.sh`, `startup.sh`, `restart.sh`, `service.sh`, `listener.sh`.

---

## Interpreting Output

```
ok 1 lockfiles: set_paused creates PAUSED file       # passed
not ok 2 lockfiles: is_paused returns 0 when paused   # failed
# (in test file tests/unit/lockfiles.bats, line 42)   # failure location
#   `run is_paused' failed                             # failing command
```

A successful run ends with all `ok` lines and exit code 0. Any `not ok` line is a failure — the comment lines below it show the file, line number, and the assertion that failed.
