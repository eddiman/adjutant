# Implementation Plan — Issues #9–#13

**Created**: 2026-03-15  
**Status**: Plan complete, ready for implementation  
**Scope**: 5 GitHub issues covering LaunchAgent hardening, integration tests, multi-instance support, messaging backends, and plugin discovery

---

## Issue #9: LaunchAgent Plist Hardening (Medium Priority)

### Current State

The wizard-generated plist (`src/adjutant/setup/steps/service.py:135-166`) has three problems:

1. **`KeepAlive` uses `SuccessfulExit: false`** — this means the listener is only restarted on non-zero exit. But the listener can exit cleanly (exit 0) in certain states (e.g., `KILLED` lockfile detected) and must still be restarted. The plan says to use `KeepAlive: true` (unconditional).

2. **No `ThrottleInterval`** — without this, macOS applies the default 10-second throttle. A crash loop will restart every 10 seconds. Should be >= 30 seconds.

3. **`ADJUTANT_HOME` vs `ADJ_DIR` mismatch** — the plist sets `ADJUTANT_HOME` but `listener.py` reads `ADJ_DIR`. The bridging was done by the old `listener.sh` bash script. Now that the listener is Python, the plist should set `ADJ_DIR` directly.

4. **`ProgramArguments` points to `listener.sh`** — should point to the Python listener (`python -m adjutant.messaging.telegram.listener`) since bash scripts are gone.

5. **No `WorkingDirectory`** — should be set to `adj_dir`.

### Startup Notification Status

**Already correct.** The listener (`listener.py`) sends NO startup notification. Only `control.py:startup()` sends "I'm online", which is invoked by `adjutant start`, not by launchd auto-restarts. So launchd crash-recovery does NOT spam notifications.

### Getting-started.md plist discrepancy

The docs example at `docs/guides/getting-started.md:127-153` shows a different plist that runs `adjutant start` instead of the listener directly, sets `ADJ_DIR` instead of `ADJUTANT_HOME`, and has a different label. This should be updated to match the wizard-generated plist.

### Implementation

1. Fix `_LAUNCHD_PLIST` in `service.py`:
   - Change `KeepAlive` from `{SuccessfulExit: false}` to `<true/>`
   - Add `<key>ThrottleInterval</key><integer>30</integer>`
   - Change `ADJUTANT_HOME` to `ADJ_DIR`
   - Change `ProgramArguments` to use Python: `[python3, -m, adjutant.messaging.telegram.listener]`
   - Add `<key>WorkingDirectory</key><string>{adj_dir}</string>`
2. Fix `_install_launchd()` to resolve the Python interpreter path (venv-aware)
3. Update `docs/guides/getting-started.md` plist example to match
4. Add test for plist content validation in `tests/unit/test_service.py`

### Files to change
- `src/adjutant/setup/steps/service.py` — plist template + install logic
- `docs/guides/getting-started.md` — plist example
- `tests/unit/test_service.py` — new or updated tests

---

## Issue #10: Integration/System Tests (Low Priority)

### Current State

1139 unit tests in `tests/unit/`. No `tests/integration/` directory. All external dependencies (Telegram API, crontab, launchctl, opencode) are mocked in unit tests.

### Test Areas

#### 10a. Listener Lifecycle Tests
- Start listener, verify PID file created at `state/listener.lock/`
- Stop listener, verify PID file removed and process terminated
- Start with `KILLED` lockfile present — listener should exit immediately
- Two simultaneous starts — only one acquires the lock

**What to mock**: Telegram API (httpx calls), opencode binary
**What NOT to mock**: PID lock acquisition, file I/O, subprocess spawning

#### 10b. Schedule Crontab Tests
- `schedule_install_all` writes correct crontab entries
- `schedule_uninstall_one` removes only the target entry
- Crontab markers (`# adjutant:<name>`) are correct
- Round-trip: install → verify → uninstall → verify clean

**What to mock**: Nothing (uses actual `crontab` command or a test harness)
**Challenge**: Tests modify real crontab. Need to save/restore crontab in fixture.

#### 10c. Service Start/Stop Tests
- `listener_start()` spawns a process and writes PID
- `listener_stop()` sends SIGTERM and cleans up
- `listener_status()` correctly reports running/stopped

**What to mock**: Telegram API, opencode
**What NOT to mock**: Process spawning, signal handling

#### 10d. End-to-End Message Flow
- Mock Telegram API server (simple HTTP responder)
- Send a `/status` message via the mock
- Verify dispatch routes to `cmd_status`
- Verify response is sent back to mock API

**What to mock**: LLM/opencode (for chat messages)
**What NOT to mock**: HTTP transport, dispatch routing

### Implementation

1. Create `tests/integration/` directory
2. Create `conftest.py` with fixtures:
   - `integration_adj_dir` — temp directory with full adjutant structure
   - `mock_telegram_api` — simple aiohttp server returning `{"ok": true}`
   - `crontab_backup` — saves and restores crontab around tests
3. Write test modules:
   - `test_listener_lifecycle.py`
   - `test_schedule_crontab.py`
   - `test_service_control.py`
   - `test_message_flow.py`
4. Mark all as `@pytest.mark.integration` so they can be skipped in CI
5. Add `pytest.ini` marker registration

### Files to create
- `tests/integration/__init__.py`
- `tests/integration/conftest.py`
- `tests/integration/test_listener_lifecycle.py`
- `tests/integration/test_schedule_crontab.py`
- `tests/integration/test_service_control.py`
- `tests/integration/test_message_flow.py`

---

## Issue #11: Multi-Instance Support (Low Priority)

### Current State

- `adjutant.yaml` has `instance.name` field (in `InstanceConfig` Pydantic model in `config.py`)
- `core/paths.py` resolves `ADJ_DIR` from env vars or `~/.adjutant` — no instance awareness
- `core/lockfiles.py` uses `adj_dir / "state" / "listener.lock"` — already instance-scoped via `adj_dir`
- PID locks, state files, journal, identity — all relative to `adj_dir`, already instance-safe
- LaunchAgent plist label is hardcoded `com.adjutant.telegram` — would collide

### Design

Each instance gets its own `ADJ_DIR`:
```
~/.adjutant/              # Default instance
~/.adjutant-work/         # "work" instance
~/.adjutant-personal/     # "personal" instance
```

### Implementation

1. **`core/paths.py`**: Add `get_adj_dir(instance: str | None = None)` that resolves:
   - `ADJUTANT_INSTANCE` env var → `~/.adjutant-{instance}/`
   - `--instance` CLI flag → sets `ADJUTANT_INSTANCE` env var
   - Default → `~/.adjutant/` (backward compatible)

2. **`cli.py`**: Add `--instance` global option to the Click group:
   ```python
   @click.group()
   @click.option("--instance", envvar="ADJUTANT_INSTANCE", default=None)
   @click.pass_context
   def main(ctx, instance):
       ctx.ensure_object(dict)
       ctx.obj["instance"] = instance
   ```

3. **`setup/steps/service.py`**: Make plist label instance-scoped:
   - `com.adjutant.telegram` → `com.adjutant.{instance}.telegram`
   - Each instance gets its own plist file

4. **`cli.py`**: Add `adjutant instances list` command that scans `~/.adjutant*` directories

5. **`lifecycle/control.py`**: No changes needed — already uses `adj_dir` parameter throughout

### Files to change
- `src/adjutant/core/paths.py` — instance-aware resolution
- `src/adjutant/cli.py` — `--instance` flag, `instances list` command
- `src/adjutant/setup/steps/service.py` — instance-scoped plist label
- `tests/unit/test_paths.py` — instance resolution tests

---

## Issue #12: Additional Messaging Backends (Low Priority)

### Current State

- `adaptor.py` defines `msg_send_text()`, `msg_typing_start()`, `msg_typing_stop()` as the messaging interface — but these are **plain functions**, not an abstract class or protocol
- `TelegramSender` doesn't exist as a class — the Telegram functions are imported directly
- `dispatch.py` imports from `telegram/commands.py` directly — no backend abstraction in dispatch
- Feature flags gate features by backend (e.g., vision requires Telegram for photo delivery)

### Design

#### Phase 1: Formalize the interface

Create `src/adjutant/messaging/backend.py`:
```python
from typing import Protocol

class MessagingBackend(Protocol):
    async def send_text(self, chat_id: str, text: str, *, message_id: int | None = None, parse_mode: str | None = None) -> None: ...
    async def send_photo(self, chat_id: str, photo_path: str, *, caption: str = "") -> None: ...
    def typing_start(self, chat_id: str, message_id: int) -> None: ...
    def typing_stop(self, suffix: str) -> None: ...
```

#### Phase 2: Wrap Telegram as a backend

Wrap existing `send.py`/`notify.py` functions into a `TelegramBackend` class implementing `MessagingBackend`.

#### Phase 3: CLI backend (simplest second backend)

```python
class CLIBackend:
    async def send_text(self, chat_id, text, **kw):
        print(text)
    async def send_photo(self, chat_id, photo_path, **kw):
        print(f"[Photo: {photo_path}]")
    def typing_start(self, *a, **kw): pass
    def typing_stop(self, *a, **kw): pass
```

#### Phase 4: Backend selection

`adjutant.yaml`:
```yaml
messaging:
  backend: "telegram"  # or "cli", "slack", "discord"
```

`dispatch.py` resolves the backend at startup and passes it to command handlers.

### Files to create/change
- `src/adjutant/messaging/backend.py` — Protocol definition
- `src/adjutant/messaging/telegram/backend.py` — TelegramBackend class
- `src/adjutant/messaging/cli/backend.py` — CLIBackend class
- `src/adjutant/messaging/dispatch.py` — backend resolution
- `src/adjutant/core/config.py` — backend config validation
- Tests for each backend

---

## Issue #13: Plugin/Capability Discovery (Low Priority)

### Current State

Adding a capability requires **6 manual touchpoints**:
1. `src/adjutant/capabilities/<name>/<name>.py` — implementation
2. `src/adjutant/messaging/telegram/commands.py` — `cmd_<name>` handler
3. `src/adjutant/messaging/dispatch.py` — import + elif routing branch
4. `src/adjutant/cli.py` — Click command registration
5. `src/adjutant/core/config.py` — `FeaturesConfig` Pydantic model field
6. `src/adjutant/setup/steps/features.py` — wizard step

**Critical finding**: Feature flags (`features.<name>.enabled`) are NOT checked at runtime by command handlers. A user can invoke `/screenshot` even with `features.screenshot.enabled: false` in config.

### Design

#### Phase 1: Runtime feature gating (quick win, no plugin system needed)

Add a `_require_feature()` guard to `dispatch.py`:
```python
def _is_feature_enabled(adj_dir: Path, feature: str) -> bool:
    config = load_typed_config(adj_dir / "adjutant.yaml")
    return config.is_feature_enabled(feature)
```

Apply before dispatching feature-gated commands:
```python
elif text.startswith("/screenshot"):
    if not _is_feature_enabled(adj_dir, "screenshot"):
        await msg_send_text("Screenshot is not enabled. Run adjutant setup to enable.", ...)
        return
    await cmd_screenshot(...)
```

#### Phase 2: Command registry (replace if/elif chain)

Create a registry in `dispatch.py`:
```python
_COMMANDS: dict[str, CommandSpec] = {}

@dataclass
class CommandSpec:
    name: str               # "/screenshot"
    handler: str            # "cmd_screenshot"
    module: str             # "adjutant.messaging.telegram.commands"
    feature: str | None     # "screenshot" or None for always-on
    takes_arg: bool         # True for prefix match, False for exact
    description: str        # For /help
```

Populate from a list instead of the if/elif chain. The dispatch loop becomes:
```python
for spec in _COMMANDS.values():
    if spec.takes_arg and text.startswith(f"/{spec.name} "):
        if spec.feature and not _is_feature_enabled(adj_dir, spec.feature):
            ...
        handler = _import_handler(spec)
        await handler(arg, ...)
        return
```

#### Phase 3: capability.yaml discovery (optional, only if third-party plugins become a goal)

Each capability directory gets a `capability.yaml`:
```yaml
name: screenshot
display_name: "Website Screenshots"
description: "Take full-page website screenshots"
commands:
  - name: "screenshot"
    takes_arg: true
    usage: "/screenshot <url>"
feature: "screenshot"
requires_messaging: true
dependencies:
  - npx playwright
```

Discovery scans `capabilities/*/capability.yaml` at startup and populates the command registry.

### Files to change
- Phase 1: `src/adjutant/messaging/dispatch.py` only
- Phase 2: `src/adjutant/messaging/dispatch.py` — registry + loop
- Phase 3: `src/adjutant/capabilities/*/capability.yaml` — one per capability

---

## Implementation Order

| Order | Issue | Effort | Dependency |
|-------|-------|--------|------------|
| 1 | #9 LaunchAgent plist | Small | None |
| 2 | #13 Phase 1 — runtime feature gating | Small | None |
| 3 | #10 Integration tests | Medium | #9 (plist changes affect service tests) |
| 4 | #13 Phase 2 — command registry | Medium | None |
| 5 | #12 Phase 1-2 — formalize interface + wrap Telegram | Medium | None |
| 6 | #11 Multi-instance | Medium | #9 (plist label scoping) |
| 7 | #12 Phase 3-4 — CLI backend + backend selection | Small | #12 Phase 1-2 |
| 8 | #13 Phase 3 — capability.yaml discovery | Small | #13 Phase 2 |

### What to implement now (this session)

1. **#9** — Fix the plist template (small, critical)
2. **#13 Phase 1** — Add runtime feature gating to dispatch.py (small, important)
3. **#10** — At least the test infrastructure + listener lifecycle tests (medium)
4. **Docs** — Update/write adjutant documentation to reflect all changes

### What to defer

- #11 (multi-instance) — no demand, large surface area
- #12 (messaging backends) — no demand, needs interface design
- #13 Phases 2-3 (command registry, capability.yaml) — nice to have

---

## Documentation Updates

All docs under `docs/` must be reviewed and updated to reflect the current state after all implementation work. Specific items:

### Update existing docs
- `docs/guides/getting-started.md` — fix plist example to match wizard-generated plist
- `docs/guides/commands.md` — verify all slash commands listed, add feature-gate notes
- `docs/guides/configuration.md` — document new config fields (`chat_timeout_seconds`, `rate_limit.window_seconds`)
- `docs/guides/lifecycle.md` — verify start/stop/restart docs match current control.py
- `docs/development/testing.md` — add integration test section
- `docs/development/plugin-guide.md` — update "adding a capability" steps to include feature gating
- `AGENTS.md` — update test count, verify repo map accuracy

### Verify accuracy
- `docs/architecture/overview.md` — confirm architecture diagram matches current module layout
- `docs/guides/knowledge-bases.md` — confirm KB guide matches current kb/ module
- `docs/guides/autonomy.md` — confirm heartbeat/pulse/review docs are current
