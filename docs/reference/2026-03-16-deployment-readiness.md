# Deployment Readiness Assessment — 2026-03-16

Adjutant v0.2.0-dev (post-v0.1.0 Python rewrite). Assessed against on-disk codebase.

Generated using the evaluation prompt in `docs/reference/deployment-readiness.md`.

---

## 1. Deployment Readiness Verdict

**Verdict: Conditionally Ready**

The system is functionally complete, well-tested (1,257 tests, all passing), and has a working release pipeline — but **51 mypy --strict errors, 24 unused imports, and a fail-open feature gate in the security-critical dispatch path** need resolution before a public v0.2.0 tag.

**Deployment context**: GitHub release (tarball + SHA256 checksum), installed via Python-based installer or `git clone`, running as a macOS LaunchAgent or Linux systemd user service with cron-scheduled autonomy.

---

## 2. Completeness Audit

### A. Core Runtime — Implemented

| Component | Location | Status |
|-----------|----------|--------|
| Telegram long-polling listener | `messaging/telegram/listener.py` | Implemented |
| Message dispatch (auth + rate-limit + routing) | `messaging/dispatch.py` (389 lines) | Implemented |
| Command handlers (20+ slash commands) | `messaging/telegram/commands.py` | Implemented |
| Claude sub-agent integration | `core/opencode.py` | Implemented |
| Pause/resume/restart/kill lifecycle | `lifecycle/control.py` (639 lines) | Implemented |
| Cron-based pulse/review autonomy | `lifecycle/cron.py` | Implemented |
| PID management + process tree kill | `core/process.py` | Implemented |
| Lockfile state machine (KILLED/PAUSED) | `core/lockfiles.py` | Implemented |
| Natural-language model switching | `dispatch.py:46-52` regex | Implemented |
| In-flight job cancellation | `dispatch.py:125-135` | Implemented |

**Gap**: `control.py` duplicates PID checks (`_pid_alive` at line 98) and process killing (`_kill_by_pattern` at line 73, `_kill_pidfile` at line 89) that also exist in `core/process.py` with psutil-based implementations. Tech debt from the bash port.

### B. Setup & Onboarding — Implemented

| Component | Location | Status |
|-----------|----------|--------|
| Interactive setup wizard | `setup/wizard.py` + `setup/steps/` | Implemented |
| Python-based installer | `setup/install.py` | Implemented |
| Repair/doctor health checks | `setup/repair.py` | Implemented |
| Uninstaller (platform-aware) | `setup/uninstall.py` (382 lines) | Implemented |
| Service installation (launchd + systemd) | `setup/steps/service.py` (344 lines) | Implemented |

**Gap**: Installer checks Python `>= 3.9` (`install.py:76-81`) but `pyproject.toml:10` requires `>= 3.11`. Users on 3.9/3.10 pass the installer check but fail at runtime.

### C. Security Posture — Implemented, one concern

#### Controls in place

| Control | Evidence | Mechanism |
|---------|----------|-----------|
| Authentication | `dispatch.py:189-191` | `str(from_id) != str(chat_id)` comparison |
| Silent rejection | `dispatch.py:190` | Unauthorized senders get no response |
| Rate limiting | `dispatch.py:77-122` | Rolling-window, file-backed, configurable |
| Credential handling | `core/env.py` (97 lines) | Line-by-line parser, no exec/source/eval |
| Log injection prevention | `core/logging.py:34-45` | Control character sanitization |
| KB sandbox (read-only) | `capabilities/kb/manage.py` | Denies bash/edit/write/glob(.env) |
| KB sandbox (all) | `capabilities/kb/manage.py` | Denies external_directory |
| KB input validation | `capabilities/kb/run.py:65` | Regex `^[a-z][a-z0-9_-]*$` prevents path traversal |
| YAML parsing | `core/config.py` | `yaml.safe_load` only |
| Update checksum verification | `lifecycle/update.py` | SHA256 validated on download |

#### Subprocess safety — 46 calls total, 3 with `shell=True`

| Location | Source of command | Risk |
|----------|-------------------|------|
| `cli.py:870` | `_resolve_command()` → schedule config YAML | Low — operator-controlled |
| `schedule/install.py:218` | Schedule entry from config YAML | Low — operator-controlled |
| `schedule/notify_wrap.py:82` | Script path from config YAML | Low — operator-controlled |

All 3 `shell=True` calls draw input from `adjutant.yaml`, which is local and operator-authored. The remaining 43 subprocess calls use list arguments (no shell). No path exists from Telegram messages to any shell call.

#### Concerns

| Risk | Severity | Location | Detail |
|------|----------|----------|--------|
| **Fail-open feature gating** | Medium | `dispatch.py:238-239` | `except Exception: pass` allows disabled features if config parsing fails |
| Rate-limit race condition | Low | `dispatch.py:77-122` | Concurrent file read/write; mitigated by sequential long-polling |

### D. Test Coverage — Strong

| Metric | Value |
|--------|-------|
| Total tests | **1,257** (all passing) |
| Unit test files | 53 |
| Integration test files | 2 |
| Test runtime | ~117 seconds |
| Fixtures | `tests/conftest.py` (92 lines), `tests/integration/conftest.py` (80 lines) |
| Isolated | Tests use tmpdir-based `adj_dir` with injected env vars; never touch real state |

#### Coverage by area

| Area | Test file(s) | Patterns tested |
|------|-------------|----------------|
| Dispatch auth | `test_messaging_dispatch.py` | Unauthorized rejection (text + photo), silent drop |
| Feature gating | `test_feature_gating.py` | Disabled commands rejected, ungated always pass |
| Credential parsing | `test_env.py` | Quoted/unquoted, `=` in values, empty, missing file |
| KB CRUD | `test_kb_manage.py` (551 lines) | Path traversal blocked, missing KB/dir/script errors |
| Lockfile state machine | `test_lockfiles.py` | Full cycle: operational → paused → operational → killed → operational |
| Config | `test_config.py` | Dict + Pydantic APIs, missing files, defaults |
| Commands | `test_telegram_commands.py` (386 lines) | All slash command handlers |
| Process management | `test_process.py` | PID files, process tree killing |
| News pipeline | `test_news_fetch.py`, `test_news_analyze.py`, `test_news_briefing.py` | All 3 stages |
| Memory | `test_memory.py`, `test_memory_classify.py` | CRUD + keyword classification |
| Scheduling | `test_schedule_manage.py`, `test_schedule_install.py` | CRUD + crontab manipulation |
| Self-update | `test_update.py` | Version comparison, download, backup, checksum |

#### Test gaps

- No fuzz/property-based testing (Hypothesis) for hand-rolled parsers (.env, NDJSON)
- No race-condition tests for rate limiting or inflight job tracking
- No end-to-end tests (would require Telegram API mock server)
- `addopts = "-x --tb=short"` fails fast — masks the total number of failures

### E. Distribution Infrastructure — Implemented

| Component | Location | Status |
|-----------|----------|--------|
| GitHub Actions release workflow | `.github/workflows/release.yml` | Implemented |
| Tarball build with exclusions | `.github/workflows/release.yml` | Implemented |
| SHA256 checksum generation | `.github/workflows/release.yml` | Implemented |
| GitHub Release creation | `softprops/action-gh-release@v2` | Implemented |
| Python-based installer | `setup/install.py` | Implemented |
| Self-update with checksum | `lifecycle/update.py` (405 lines) | Implemented |
| Pre-release detection | Tag contains `-` → pre-release | Implemented |
| VERSION file | Project root | Implemented |

**Gap**: No CI pipeline — tests are run manually before tagging.

### F. Documentation — Implemented

48 files across `docs/`:

| Category | Count | Content |
|----------|-------|---------|
| Architecture | 6 | Overview, state, identity, messaging, autonomy, design decisions |
| Guides | 10 | Getting started, config, commands, KBs, memory, schedules, lifecycle, news, troubleshooting, autonomy |
| Development | 5 | Testing, plugin guide, setup wizard, adaptor guide, phase-8 |
| Reference | 25+ | Framework plan, rewrite plans, audit notes, dated records |
| Plans | 1 | Memory system |

External Docusaurus site (`adjutant-docs/`) deployed to GitHub Pages.

**Gap**: 25+ reference docs include many historical artifacts from the bash era. Worth pruning.

### G. Cross-Platform Support — Implemented

| Platform | Service | Cron | Status |
|----------|---------|------|--------|
| macOS | LaunchAgent (`setup/steps/service.py:150-196`) | crontab | Primary, well-exercised |
| Linux | systemd user unit (`setup/steps/service.py:220-260`) | crontab | Supported, less exercised |

Platform detection via `sys.platform` in `core/platform.py` (154 lines). Portable utilities replace platform-specific shell commands. Uninstaller (`setup/uninstall.py`) handles both platforms.

**Gap**: `ensure_path()` in `platform.py` is macOS-focused (prepends Homebrew paths) but harmless on Linux. No Linux integration test suite.

---

## 3. Code Quality Deep Dive

### Unused code

| Item | Location | Impact |
|------|----------|--------|
| 5 vestigial `main_*` wrappers | `lifecycle/control.py:596-639` | Only referenced by tests, not CLI. Bash port leftover. |
| 4 standalone `main()` entrypoints | `kb/run.py:296`, `kb/query.py:291`, `screenshot.py:222`, `search.py:136` | Reachable via `__name__ == "__main__"` but unwired from Click CLI. |
| `feedparser` dependency | `pyproject.toml:40` | Declared in `[project.optional-dependencies] news` but never imported in source. Dead dependency. |
| `MessagingAdaptor` ABC | `messaging/adaptor.py` (84 lines) | Defines interface but `dispatch.py` imports Telegram directly. Decorative abstraction. |
| Private `_resolve_command` imported publicly | `cli.py:858` | Naming convention violation. |

### Unused imports — 24 (ruff F401)

All auto-fixable. Key examples:

| File | Unused import |
|------|---------------|
| `core/opencode.py:25` | `adjutant.core.process.kill_graceful` |
| `messaging/dispatch.py:374` | `adjutant.messaging.telegram.send.msg_send_text` |
| `messaging/telegram/commands.py:1059` | `adjutant.capabilities.schedule.manage.schedule_get_field` |
| `core/logging.py:19` | `datetime.timezone` |
| `setup/wizard.py:19` | `shutil` |

Full list: 24 imports across 15 files.

### Error handling — 91 `except Exception` clauses

| Pattern | Count | Assessment |
|---------|-------|------------|
| Catch, log via `adj_log()`, return/continue | 42 | Acceptable — logged with context |
| Catch with `# noqa: BLE001` | 4 | Deliberate — acknowledged |
| Fail-open in security path | 1 | `dispatch.py:238` — must fix |
| Silent swallow (`pass`/return default, no logging) | 44 | Concerning — 44 locations silently discard errors |

The 44 silent-swallow sites are distributed across:
- `lifecycle/control.py`: 6 (during shutdown/startup — most consequential)
- `setup/` modules: 16 (wizard steps — more acceptable, user-facing with fallbacks)
- `messaging/telegram/`: 4 (typing indicators, service management)
- Capabilities: 6 (vision, screenshot — return fallback values)
- Other: 12 (news fetch, status, config loading)

### Code duplication

| Modules | Overlap |
|---------|---------|
| `lifecycle/control.py` ↔ `core/process.py` | PID alive check (`_pid_alive` vs `pid_is_alive`), process killing (`_kill_by_pattern`/`_kill_pidfile` vs psutil-based equivalents), PID file reading (`_read_pid` vs `PidLock`) |

### Type safety — 51 mypy --strict errors across 20 files

Notable categories:
- Missing generic type parameters (`dict` without `[K, V]`): ~20 errors in news/, commands.py, listener.py
- Missing return type annotations: 5 errors
- Real type bugs: 4

**Real bugs caught by mypy**:
| File | Line | Error |
|------|------|-------|
| `commands.py` | 874 | `Path` passed where `int` expected in `to_thread` |
| `listener.py` | 123 | `str` assigned to `int` variable |
| `update.py` | 245 | `Path` assigned to `str` variable |
| `identity.py` | 158 | Unknown keyword argument `cwd` passed to `opencode_run` |

### Dependency hygiene

| Issue | Detail |
|-------|--------|
| Dead optional dep | `feedparser>=6.0` declared but never imported |
| Version mismatch | Installer checks `>=3.9`, `pyproject.toml` requires `>=3.11` |
| Runtime deps | 6 packages — lean and appropriate |
| Dev deps | 9 packages — complete (test, lint, type check) |

### Maintenance discipline

| Marker | Count |
|--------|-------|
| TODO | 0 |
| FIXME | 0 |
| HACK | 0 |
| XXX | 0 |

Zero maintenance debt markers across 16,184 lines of source code.

---

## 4. Critical Path: P0 / P1 / P2

### P0 — Blocks release

| # | Item | Location | Action |
|---|------|----------|--------|
| 1 | Fail-open feature gating | `dispatch.py:238-239` | Change `except Exception: pass` to reject the command when config is unparseable. Add test. |
| 2 | Installer Python version mismatch | `setup/install.py:76-81` | Change check from `>=3.9` to `>=3.11` to match `pyproject.toml`. |
| 3 | 4 real type bugs | `commands.py:874`, `listener.py:123`, `update.py:245`, `identity.py:158` | Fix the type mismatches — these are runtime bugs, not just strictness violations. |

### P1 — Degrades quality

| # | Item | Location | Action | Effort |
|---|------|----------|--------|--------|
| 1 | 24 unused imports | 15 files | `ruff check --fix src/adjutant/` | Small |
| 2 | 47 mypy type annotation gaps | 20 files | Add missing generics, return types | Medium |
| 3 | 44 silent exception swallows | Spread across codebase | Add `adj_log` calls or `# noqa: BLE001` with rationale | Medium |
| 4 | Dead `feedparser` dependency | `pyproject.toml:40` | Remove or integrate | Small |
| 5 | 5 vestigial `main_*` wrappers | `control.py:596-639` | Remove, update tests | Small |
| 6 | Private import `_resolve_command` | `cli.py:858` | Rename to `resolve_command` in `schedule/manage.py` | Small |
| 7 | `control.py`/`process.py` duplication | `lifecycle/control.py` | Refactor to use `process.py` equivalents | Medium |
| 8 | VERSION file says `0.1.0` | `VERSION`, `pyproject.toml` | Update to `0.2.0` when ready to tag | Small |

### P2 — Acceptable to ship without

| Item | Rationale |
|------|-----------|
| No fuzz testing for parsers | Edge cases well-covered in existing tests |
| No CI pipeline | Single-developer, thorough local suite |
| No Linux integration tests | Linux code paths exist and are unit-tested |
| Adaptor ABC not wired at runtime | Single-backend system; ABC exists for future |
| 25+ historical reference docs | Worth pruning, not blocking |
| No end-to-end Telegram tests | Dispatch + command tests provide coverage |
| Standalone `main()` entrypoints in capabilities | Low-impact, alternative invocation paths |

---

## 5. Structural Strengths Worth Protecting

### Single-operator authentication with silent rejection
`dispatch.py:188-191`. String comparison, no error response to unauthorized senders. Simple, auditable, no information leakage. Never add error responses to unauthorized users.

### Sandboxed KB sub-agents
Each KB query spawns an isolated process scoped to its directory. Read-only KBs deny all mutation tools. The runtime agent never reads KB files directly. Do not merge KB access into the main agent.

### Deferred imports in CLI commands
Every Click command defers imports inside the function body. Keeps `adjutant --help` fast (~0.1s) and allows graceful degradation when optional deps are missing. Do not move to module-level.

### Line-by-line credential parser
`core/env.py` parses `.env` without exec/source/eval. Deliberate security decision. Do not replace with `python-dotenv`.

### Lockfile state machine
`core/lockfiles.py` uses atomic `touch()`/`unlink()`. KILLED takes precedence over PAUSED. Do not add database-backed state.

### Capability return convention
Functions return strings or raise. No stdout, no side effects, no messaging layer access. Testable in isolation, reusable across interfaces. Do not add side effects.

### Lean dependency surface
6 runtime packages. Stdlib used for RSS parsing, tarball handling, compression, subprocess. Minimizes attack surface and install friction.

---

## 6. Implementation Roadmap

### Immediate — before v0.2.0 tag

| Item | Effort | Dependency |
|------|--------|------------|
| Fix fail-open feature gate (`dispatch.py:238`) | Small | None |
| Fix installer version check (`install.py:76`) | Small | None |
| Fix 4 real type bugs (commands, listener, update, identity) | Small | None |
| Remove 24 unused imports (`ruff --fix`) | Small | None |
| Update VERSION + pyproject.toml to `0.2.0` | Small | After all fixes |

### Short-term — v0.2.x

| Item | Effort | Dependency |
|------|--------|------------|
| Resolve remaining 47 mypy errors (type annotations) | Medium | None |
| Audit and annotate 44 silent exception swallows | Medium | None |
| Remove dead `feedparser` dependency | Small | None |
| Remove 5 vestigial `main_*` wrappers | Small | Update tests first |
| Rename `_resolve_command` → `resolve_command` | Small | None |
| Refactor `control.py` to use `process.py` equivalents | Medium | None |

### Long-term — v0.3.0+

| Item | Effort | Dependency |
|------|--------|------------|
| Add property-based testing (Hypothesis) for parsers | Medium | None |
| Wire `MessagingAdaptor` ABC into dispatch | Large | Multi-backend requirement |
| CI pipeline (GitHub Actions) | Medium | None |
| Linux integration test suite | Medium | CI pipeline |
| Prune historical reference docs | Small | None |

---

## Summary Scorecard

| Dimension | Grade | Notes |
|-----------|-------|-------|
| Core runtime | Solid | Complete lifecycle, 20+ commands |
| Setup & onboarding | Solid | One version-check bug (P0) |
| Security | Good | One fail-open concern (P0) |
| Test coverage | Strong | 1,257 tests, all passing, 0 TODO/FIXME |
| Type safety | Needs work | 51 mypy errors, 4 real bugs |
| Import hygiene | Needs cleanup | 24 unused imports |
| Distribution | Complete | Release workflow, self-update, checksum |
| Documentation | Thorough | 48 files, external site |
| Cross-platform | Implemented | macOS primary, Linux supported |
| Unused code | Minimal | ~5 vestigial items + 1 dead dependency |
| Error handling | Mixed | 42 logged, 44 silent — ratio needs improvement |
| Source size | 16,184 lines | 72 source files, 55 test files |
