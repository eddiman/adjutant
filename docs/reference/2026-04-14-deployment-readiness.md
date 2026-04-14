# Deployment Readiness Assessment — 2026-04-14

Adjutant v2.0.0 monorepo. Assessed against the on-disk codebase in this repository.

Generated using the evaluation prompt in `docs/reference/deployment-readiness.md`.

---

## 1. Deployment Readiness Verdict

**Verdict: Not Ready**

The single biggest blocker is that the public release contract is inconsistent at
the user boundary: installation and command documentation materially disagree with
shipped behavior, shell-based scheduled command execution still needs hardening,
and this assessment does not yet have a recorded clean full-suite release gate.

**Deployment** here means: a public GitHub Release that ships the Adjutant tarball
and checksum, supports the documented installation flow, and gets a new user to a
working local install via the published setup or installer path.

---

## 2. Completeness Audit (MECE — 7 branches)

### A. Core runtime is implemented, but release confidence is reduced by drift

- **Status:** Partial
- **Evidence:** CLI and runtime entrypoints exist in `src/adjutant/cli.py`.
  Dispatcher/auth/rate-limit/feature gating are centralized in
  `src/adjutant/messaging/dispatch.py`. Lifecycle control exists in
  `src/adjutant/lifecycle/control.py` and `src/adjutant/lifecycle/cron.py`.
  Lockfile state is handled in `src/adjutant/core/lockfiles.py`. Process
  management exists in `src/adjutant/core/process.py`.
- **Evidence:** The security-critical dispatch path is explicit and centralized:
  auth check in `dispatch.py`, rate limiting in `_check_rate_limit()`, and
  feature-gate rejection in the `_FEATURE_GATES` block.
- **Gap:** The runtime surface is real, but release confidence is reduced by
  command/docs drift and the absence of a clearly demonstrated clean release gate.

### B. Setup and onboarding exist, but installer distribution is only partially integrated

- **Status:** Partial
- **Evidence:** Interactive setup exists in `src/adjutant/setup/wizard.py`.
  Repair and uninstall flows exist in `src/adjutant/setup/repair.py` and
  `src/adjutant/setup/uninstall.py`. Service installation support exists in
  `src/adjutant/setup/steps/service.py`. A curl-style installer exists in
  `src/adjutant/setup/install.py`.
- **Evidence:** Public release packaging exists in `.github/workflows/release.yml`.
- **Gap:** The installer exists as a standalone Python entrypoint, but the public
  release flow still tells users to clone or unpack the tarball, create a venv,
  `pip install -e .`, and run `adjutant setup`.
  `.github/workflows/release.yml:92-111` does not present the installer as the
  canonical path, so the distribution story is only partially integrated.

### C. Security posture is strong in design, but subprocess shell usage is a release risk

- **Status:** Partial
- **Evidence:** Single-operator authentication is enforced in
  `src/adjutant/messaging/dispatch.py` by comparing `from_id` to `chat_id`.
  Feature-gated commands fail closed on config parse failure in the same module.
  `.env` parsing is hand-rolled and non-exec-based in `src/adjutant/core/env.py`.
  KB sandboxing is documented in `docs/guides/knowledge-bases.md` and scaffolded
  in the KB management path.
- **Evidence:** Source-wide subprocess counts gathered during this audit:
  `subprocess.run(...)` = **44**, `subprocess.Popen(...)` = **6**,
  `shell=True` = **3**, `os.system(...)` = **0**.
- **Evidence:** The `shell=True` call sites are:
  - `src/adjutant/cli.py:1097`
  - `src/adjutant/capabilities/schedule/notify_wrap.py:78-84`
  - `src/adjutant/capabilities/schedule/install.py:237-240`
- **Gap:** Scheduled-command execution still relies on shell-string execution in
  public-release code paths. Even if these inputs are operator-authored, they
  should be tightened before public release.

### D. Test coverage is large, but release cleanliness is not yet demonstrated

- **Status:** Partial
- **Evidence:** Test tree count gathered during this audit found
  **61 unit test files / 1422 unit test functions** and
  **2 integration test files / 19 integration test functions**, for a total of
  **1441** discovered test functions.
- **Evidence:** Security-relevant coverage exists in
  `tests/unit/test_messaging_dispatch.py`, `tests/integration/test_feature_gating.py`,
  `tests/unit/test_env.py`, `tests/unit/test_kb_manage.py`,
  `tests/unit/test_schedule_install.py`, and related backend/config tests.
- **Gap:** Release readiness requires a clearly recorded clean full-suite pass.
  At the time of this assessment, that release gate was not documented here as a
  final clean result. Repo docs and builder guidance also still contain stale,
  lower approximate test-count figures.

### E. Public distribution infrastructure exists, but is not yet coherent end-to-end

- **Status:** Partial
- **Evidence:** `.github/workflows/release.yml` verifies tag vs `VERSION`, builds
  a tarball, generates a `.sha256`, and publishes a GitHub Release. Versioning is
  driven from `VERSION` through packaging metadata. Self-update logic exists in
  `src/adjutant/lifecycle/update.py`.
- **Gap:** Artifact production is implemented, but the install story is split
  between release assets, manual editable installation, and a separate installer.
  Public distribution exists mechanically, not yet as one coherent user flow.

### F. Documentation is extensive, but materially out of sync with shipped behavior

- **Status:** Partial
- **Evidence:** Public docs exist across `README.md`, `docs/guides/`,
  `docs/architecture/`, and `site/`.
- **Evidence:** `README.md:71-79` advertises Telegram commands `/models`,
  `/memory`, and `/news`, but targeted search found no corresponding command
  handlers in `src/adjutant/messaging/telegram/*.py`.
- **Evidence:** `README.md:122` links to `docs/getting-started/installation.md`,
  while the current tracked guide structure includes `docs/guides/getting-started.md`.
- **Evidence:** `docs/guides/commands.md` still references backend-native web
  server concepts such as `cloudcli`, while current backend capability objects in
  `src/adjutant/core/backend_opencode.py` and
  `src/adjutant/core/backend_claude_cli.py` explicitly set `web_server=False`.
- **Gap:** A public release cannot rely on docs that advertise commands, links,
  or backend behavior the shipped code does not provide.

### G. Cross-platform support is implemented for macOS and Linux, with operational caveats

- **Status:** Implemented
- **Evidence:** Platform/service support exists in the setup and platform layers,
  including macOS launchd, Linux systemd-user, and cron-backed scheduled jobs.
  These paths are represented in `src/adjutant/setup/steps/service.py`,
  `src/adjutant/core/platform.py`, and schedule modules under
  `src/adjutant/capabilities/schedule/`.
- **Gap:** The remaining issue is not missing platform support. It is the safety
  and robustness of shell-based scheduled-command execution across those supported
  platforms.

---

## 3. Code Quality Deep Dive

### Unused or weakly integrated code still exists

- **Declared-but-unused dependency:** `rich` appears to be unused as a runtime
  import. Search in `src/` found no actual `rich` import usage; only incidental
  text matches.
- **Standalone-but-unwired installer:** `src/adjutant/setup/install.py` is a real
  installer, but the public release workflow still routes users through manual
  clone or tarball extraction plus editable install.
- **Decorative or stale docs abstractions:** docs still describe retired
  backend-native web-server behavior while backend capability objects explicitly
  declare `web_server=False`.

### Broad exception handling is frequent

- **Count:** `except Exception` in `src/` = **100**
- **Approximate categories gathered during this audit:**
  - `catch_and_log`: **41**
  - `fallback_default`: **28**
  - `silent_swallow`: **20**
  - `user_visible_fallback`: **3**
  - `reraises_or_raises`: **5**
  - `other`: **3**
- **Observation:** `src/adjutant/core/config.py` returns defaults on parse/load
  errors. That is acceptable in some branches, but security-sensitive paths must
  explicitly fail closed. `src/adjutant/messaging/dispatch.py` does this correctly
  for feature-gated commands.

### Subprocess safety is the sharpest code-quality and security intersection

- **Counts:** `subprocess.run` = **44**, `subprocess.Popen` = **6**,
  `shell=True` = **3**, `os.system` = **0**.
- **High-risk or high-scrutiny call sites:**
  - `src/adjutant/cli.py:1095-1097` — scheduled job execution via shell
  - `src/adjutant/capabilities/schedule/notify_wrap.py:78-84` — wrapper runs a
    command string via shell
  - `src/adjutant/capabilities/schedule/install.py:237-240` — KB-backed
    scheduled jobs via shell
- **Assessment:** These do not appear to be directly fed from arbitrary Telegram
  input, but they are still the main hardening target before a public installer
  release.

### Naming and boundary violations are small but real

- **Private helper imports discovered during this audit:**
  - `src/adjutant/capabilities/schedule/install.py` imports `_resolve_command`
  - `src/adjutant/capabilities/kb/query.py` imports `_get_kb`
- **Assessment:** This weakens module boundaries and violates the project's own
  naming conventions for underscore-prefixed internals.

### Dependency hygiene is imperfect

- Runtime dependencies are small and mostly justified.
- `rich` appears unused.
- Public docs still describe old backend or web-server concepts that are no
  longer reflected by code.
- This is not a release blocker on its own, but it is visible polish debt.

---

## 4. Critical Path: P0 / P1 / P2

### P0 — blocks release

1. **Public docs advertise commands the Telegram dispatcher does not implement**
   - **Files:** `README.md`, `docs/guides/commands.md`,
     `src/adjutant/messaging/dispatch.py`,
     `src/adjutant/messaging/telegram/commands.py`
   - **Action:** Align public command docs to actual shipped handlers, or
     implement the missing commands before release.

2. **Release and install story is not coherent end-to-end**
   - **Files:** `.github/workflows/release.yml`, `src/adjutant/setup/install.py`,
     `README.md`
   - **Action:** Pick one supported public install path and document it
     consistently. If the Python installer is the intended story, wire and
     publish it as such. If not, stop presenting it as part of release readiness.

3. **Shell-based scheduled command execution needs hardening before public ship**
   - **Files:** `src/adjutant/cli.py`,
     `src/adjutant/capabilities/schedule/notify_wrap.py`,
     `src/adjutant/capabilities/schedule/install.py`
   - **Action:** Replace shell-string execution with argument-list execution where
     possible, or constrain and validate command generation so no user- or
     config-derived string reaches `shell=True` unsafely.

4. **Release gate requires a clearly recorded clean full test run**
   - **Files:** `tests/`, release/testing docs, backend and schedule test paths
   - **Action:** Run the full suite, resolve any failures, and make a clean full
     pass the explicit release gate before tagging.

### P1 — degrades quality

1. **Documentation still references retired backend-native web server behavior**
   - **Files:** `docs/guides/commands.md`, `docs/guides/backends.md`,
     `docs/guides/configuration.md`, `README.md`
   - **Action:** Remove CloudCLI or opencode-web-era references and align docs to
     the current `web/` architecture.

2. **Unused runtime dependency likely remains**
   - **Files:** `pyproject.toml`
   - **Action:** Remove `rich` if it is truly unused, or add the missing usage
     intentionally.

3. **Private helper imports weaken code boundaries**
   - **Files:** `src/adjutant/capabilities/schedule/install.py`,
     `src/adjutant/capabilities/kb/query.py`
   - **Action:** Promote these helpers to public APIs or stop importing
     underscore-prefixed functions across modules.

4. **Exception swallowing remains high**
   - **Files:** distributed across `src/`
   - **Action:** Review silent-swallow and fallback-default cases, especially
     around config, filesystem, and subprocess branches.

### P2 — acceptable to defer

- Fuzz or property-style testing for hand-rolled parsers (`.env`, registry,
  NDJSON, Claude JSON)
- Further reduction of broad exception usage in non-critical paths
- Cleanup of stale historical doc references and outdated test-count statements

---

## 5. Structural Strengths Worth Protecting

1. **Centralized dispatch security envelope**
   - `src/adjutant/messaging/dispatch.py` keeps auth, rate limiting, feature
     gating, and routing in one place.
   - This is worth protecting because fail-closed behavior remains reviewable and
     testable.

2. **Backend abstraction with explicit capability flags**
   - `src/adjutant/core/backend.py` plus backend-specific capability objects form
     a good boundary.
   - This is worth protecting because optional features can degrade via declared
     capabilities instead of backend-specific conditionals scattered everywhere.

3. **Lockfile-based lifecycle model**
   - `KILLED` and `PAUSED` precedence is simple and operationally legible.
   - This is worth protecting because it reduces hidden state and keeps recovery
     logic understandable.

4. **Hand-rolled, non-exec parsing for environment and config-adjacent inputs**
   - The `.env` parser and related small parsers avoid dangerous shell sourcing
     behavior.
   - This is worth protecting because it removes an entire class of injection and
     config-evaluation surprises.

5. **KB sandbox model**
   - KB queries and KB-local operations are scoped through controlled boundaries.
   - This is worth protecting because it prevents the main runtime from casually
     traversing external project trees.

---

## 6. Implementation Roadmap (Immediate / Short-term / Long-term)

### Immediate (before any public release)

- **Make the full test suite green and record the result** — **Small**
- **Align README and docs with actual Telegram and CLI commands** — **Medium**
- **Decide and unify the public installation path** — **Medium**
- **Harden all `shell=True` schedule execution paths** — **Medium**
- **Remove retired backend web-server references from docs** — **Small**

**Sequencing dependencies:**

- Docs alignment should follow the installation-path decision.
- Release should wait on shell hardening and a confirmed clean full-suite pass.

### Short-term (next minor)

- **Remove unused dependency or dependency drift (`rich`)** — **Small**
- **Clean private-helper cross-imports** — **Small**
- **Audit and reduce silent `except Exception` cases in non-critical paths** —
  **Medium**
- **Refresh stale test-count and architecture statements in docs** — **Small**

### Long-term (next major)

- **Add stronger parser fuzz or property tests** — **Medium**
- **Refactor schedule command resolution toward structured argv throughout** —
  **Medium**
- **Continue tightening backend/docs/feature-contract discipline** — **Medium**
