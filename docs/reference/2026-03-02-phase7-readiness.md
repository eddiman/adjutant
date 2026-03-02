# Adjutant Phase 7 Readiness Assessment
**Date**: 2026-03-02  
**Evaluator role**: Principal Technical Evaluator  
**Subject**: Adjutant framework — readiness for Phase 7: Autonomy & Self-Agency  
**Scope**: Autonomous operation (pulse/review/escalation) that acts on the user's behalf without real-time oversight  
**Branch evaluated**: `main` (current HEAD, post-v0.0.2)  
**Ground truth method**: Direct script inspection, `bats tests/unit/` run, review of prompts/, scripts/, adjutant.yaml.example

---

## 1. Deployment Readiness Verdict

**VERDICT: CONDITIONALLY READY**

**Critical factor**: The autonomous action loop is architecturally sound — PAUSED kill switch, pulse/review/escalation separation, and KB sub-agent isolation are all in place — but three P0 gaps make unsupervised operation unsafe: (1) `notify.sh` has no hard notification budget counter, relying solely on the LLM's soul.md instructions to self-limit; (2) there is no machine-readable autonomous action log (`state/actions.jsonl` does not exist), meaning oversight requires parsing journal prose; (3) the `debug.dry_run` flag in `adjutant.yaml` is never checked by `pulse.md`, `review.md`, or `escalation.md`, so dry-run mode silently has no effect on autonomous cycles.

**Phase 7 definition**: Adjutant runs scheduled pulse checks and daily reviews without any user input, proactively sends Telegram notifications based on its own judgment, and maintains an auditable ledger of all autonomous actions — all while remaining interruptible at any time via a single PAUSED kill switch.

---

## 2. Completeness Audit (MECE — 7 Branches)

### A. Core Autonomous Loop — Implemented (with kill-switch gap in prompts)

**Status**: Implemented  
**Evidence**:
- `prompts/pulse.md` — 74-line lightweight pulse: checks PAUSED (line 7), reads soul.md + heart.md, queries all KBs, evaluates against heart.md concerns, writes journal entry, updates `state/last_heartbeat.json`, writes to `insights/pending/` if escalation warranted
- `prompts/review.md` — 79-line deep review: checks PAUSED (line 7), reads journal entries, queries all KBs in depth, processes pending insights, sends Telegram notifications via `notify.sh`, writes daily journal summary, updates `state/last_heartbeat.json`
- `prompts/escalation.md` — 55-line escalation: prompt injection guard (lines 3–5), checks PAUSED (line 9), reads insight files, deep-reads project files, determines notification vs. log vs. flag-for-reflect
- `scripts/messaging/telegram/commands.sh` — `cmd_pulse()` invokes `prompts/pulse.md` via `opencode run --print`; `cmd_reflect()` invokes reflection flow
- `state/last_heartbeat.json` — machine-readable state written by every autonomous cycle

**Gap**: `pulse.md` and `review.md` check PAUSED but do not check `debug.dry_run` from `adjutant.yaml`. If `dry_run: true` is set, autonomous cycles still query KBs and send live notifications — the flag is documented in the schema but never enforced in prompts.

---

### B. Notification Budget — LLM-enforced only (no hard guard)

**Status**: Partial  
**Evidence (present)**:
- `adjutant.yaml.example` lines 54–59: `notifications.max_per_day: 3`, `quiet_hours.enabled/start/end` — schema exists
- `identity/soul.md` (gitignored, personal) — understood to contain behavioral rules referencing `max_per_day`
- `review.md` step 5 — instructs the agent to evaluate whether each insight "needs a Telegram notification" before sending

**Evidence (absent)**:
- `scripts/messaging/telegram/notify.sh` — 36-line script. Sends directly via curl with no counter check. No read/write of a daily notification count. No quiet-hours gate. The notification budget is enforced entirely by the LLM's judgment, with no script-level hard stop.
- `state/notify_count_YYYY-MM-DD.txt` (or equivalent) — does not exist on disk
- Quiet-hours enforcement logic — not present in `notify.sh` or anywhere in `scripts/`

**Gap**: An LLM that misreads soul.md, encounters a malformed insight file, or enters an error-recovery loop can send unlimited notifications. The budget cap has no enforcement layer below the LLM.

---

### C. Autonomous Action Audit Trail — Missing

**Status**: Missing  
**Evidence (present)**:
- `journal/YYYY-MM-DD.md` — append-only human-readable log. All pulse/review/escalation cycles write structured entries with timestamps.
- `scripts/observability/journal_rotate.sh` — archives journal entries older than `retention_days` to `.archive/`

**Evidence (absent)**:
- `state/actions.jsonl` — not on disk. No machine-readable ledger of autonomous actions.
- No JSONL schema defined anywhere in docs or scripts
- `scripts/observability/status.sh` (53 lines) — reports RUNNING/PAUSED/KILLED + cron jobs, does not surface recent autonomous activity, last heartbeat, or notification count

**Gap**: Oversight of autonomous behavior requires opening journal files and reading prose. There is no programmatic way to query "how many notifications were sent today" or "what did the last pulse do" without parsing the journal. The `/status` command surfaces nothing about autonomous cycles.

---

### D. Dry-Run & Interruptibility — Partial

**Status**: Partial  
**Evidence (present)**:
- `PAUSED` lockfile — checked at top of all three prompts. A single `touch PAUSED` stops all autonomous activity immediately. This is correct and working.
- `adjutant.yaml` schema — `debug.dry_run: false` exists
- `scripts/setup/wizard.sh` — `--dry-run` flag fully implemented for the wizard
- `scripts/messaging/telegram/commands.sh` — `/pause` and `/resume` handlers present

**Evidence (absent)**:
- No dry-run enforcement in `prompts/pulse.md`, `prompts/review.md`, `prompts/escalation.md` — none of these read `adjutant.yaml` to check `debug.dry_run`
- No `/dryrun` Telegram command to toggle dry-run mode
- `scripts/messaging/dispatch.sh` — no `dry_run` case in the command dispatch block

**Gap**: Dry-run mode is in the config schema but has zero enforcement in the autonomous path. The kill switch (PAUSED) works; the softer dry-run mode does not.

---

### E. Autonomy Configuration — Schema present, no wizard step

**Status**: Partial  
**Evidence (present)**:
- `adjutant.yaml.example` — `notifications:` and `debug:` sections present with correct keys
- `scripts/setup/steps/service.sh` — installs cron schedule hardcoded as `"0 8 * * 1-5"` (line 281), does not read from `adjutant.yaml`
- 6-step wizard covers prerequisites, install path, identity, messaging, features, service

**Evidence (absent)**:
- `scripts/setup/steps/autonomy.sh` — does not exist. No wizard step for pulse cadence, quiet hours, notification cap, or dry-run preference.
- No `autonomy:` section in `adjutant.yaml.example` (pulse/review schedules are not exposed as config keys)
- The cron schedule for pulse is hardcoded in `service.sh`; changing it requires editing the script manually

**Gap**: A new user installing Adjutant has no guided path for autonomy configuration. Pulse cadence, notification limits, and quiet hours are either hardcoded or require manual `adjutant.yaml` editing after setup.

---

### F. Test Coverage for Autonomous Paths — Not started

**Status**: Planned-only  
**Evidence (present)**:
- `tests/unit/` — 210 declared tests across 10 files (none cover autonomous paths)
- `tests/integration/` — 319 declared tests across 17 files (none cover autonomous paths)
- `tests/integration/notify.bats` — tests `notify.sh` in isolation (mock curl); does not test budget enforcement
- 3 unit tests currently failing: `not ok 68` (kb_scaffold), `not ok 190` (prerequisites), `not ok 210` (repair)

**Evidence (absent)**:
- `tests/unit/autonomy.bats` — does not exist
- `tests/integration/autonomy.bats` — does not exist
- No test for notification budget counter
- No test for quiet-hours enforcement
- No test for dry-run mode in prompts

**Gap**: The entire autonomous action surface has no automated test coverage. The 3 existing failures must be resolved before Phase 7 — shipping new tests on top of a broken suite creates false confidence.

---

### G. Documentation for Autonomous Operation — Not started

**Status**: Planned-only  
**Evidence (present)**:
- `docs/guides/knowledge-bases.md` — comprehensive KB guide
- `docs/development/testing.md` — test strategy documented
- `AGENTS.md` — builder guide for AI coding agents

**Evidence (absent)**:
- `docs/guides/autonomy.md` — does not exist. No user guide for pulse cadence, notification triggers, action ledger, or pause/resume/dry-run.
- `docs/architecture/autonomy.md` — does not exist. No architecture document for the autonomous action loop.

**Gap**: A user enabling autonomous mode has no documentation explaining how it works, what it will do, or how to control it.

---

## 3. Critical Path: What Blocks Phase 7 vs. What Degrades It

### P0 — Must fix before Phase 7 is safe to enable

**P0-1: No hard notification budget guard in `notify.sh`**  
- File to edit: `scripts/messaging/telegram/notify.sh`  
- Action: Before sending, read `state/notify_count_YYYY-MM-DD.txt`. If count >= `notifications.max_per_day` from `adjutant.yaml`, exit 1 with `ERROR:budget_exceeded`. Increment counter after successful send.  
- Dependency: Requires bash YAML parsing to read `max_per_day` (pattern already used in other scripts).

**P0-2: No machine-readable action log (`state/actions.jsonl`)**  
- Files to edit: `prompts/pulse.md`, `prompts/review.md`, `prompts/escalation.md` — add a step to append a JSONL record after every action taken  
- Schema: `{"ts":"ISO-8601","type":"pulse|review|escalation|notify","kbs_checked":[],"action":"","detail":""}`  
- Also: add `state/actions.jsonl` to `.gitignore`

**P0-3: Dry-run flag never enforced in autonomous prompts**  
- Files to edit: `prompts/pulse.md`, `prompts/review.md`, `prompts/escalation.md`  
- Action: After PAUSED check, read `adjutant.yaml`. If `debug.dry_run: true`, log `[DRY RUN]` to journal and `state/actions.jsonl` for every action that would have been taken, but do not call `notify.sh` and do not write to `insights/`.

---

### P1 — Degrades quality, does not block

**P1-1: No `autonomy:` section in `adjutant.yaml.example`**  
- File to edit: `adjutant.yaml.example`  
- Action: Add `autonomy:` block with `pulse_schedule`, `review_schedule`, `enabled: false` default.

**P1-2: No wizard Step 7 for autonomy configuration**  
- File to create: `scripts/setup/steps/autonomy.sh`  
- File to edit: `scripts/setup/wizard.sh` — add Step 7 call after Step 6  
- Action: Ask: enable autonomous pulses? Set cadence. Set notification cap. Set quiet hours. Write to `adjutant.yaml` and install cron.

**P1-3: Cron schedule hardcoded in `service.sh`**  
- File to edit: `scripts/setup/steps/service.sh` line 281  
- Action: Read schedule from `adjutant.yaml` `autonomy.pulse_schedule`. Fall back to hardcoded default if not set.

**P1-4: KB wizard not surfaced at wizard completion**  
- File to edit: `scripts/setup/wizard.sh` `_show_completion()`  
- Action: After cost estimate, offer: "Would you like to create a knowledge base now?"

**P1-5: `/status` does not surface autonomous activity**  
- File to edit: `scripts/observability/status.sh`  
- Action: Read `state/last_heartbeat.json` and last 5 entries from `state/actions.jsonl`. Display last pulse time, last review time, notifications sent today vs. budget.

---

### P2 — Deferred by design, acceptable to ship Phase 7 without

- **Quiet-hours enforcement in `notify.sh`**: Schema exists; script-level enforcement can follow after budget counter lands.
- **`/dryrun` Telegram command**: Config file edit is functional; command is a convenience.
- **`actions.jsonl` archival in `journal_rotate.sh`**: JSONL files are small; low urgency.
- **Tier 3 system tests** for lifecycle scripts: Explicitly deferred per `docs/development/testing.md`.

---

## 4. Structural Strengths Worth Protecting

**1. PAUSED as the universal kill switch**  
All three autonomous prompts check the `PAUSED` file before doing anything. This is a filesystem-level interruption requiring no LLM cooperation. It can be set via Telegram (`/pause`), CLI, or emergency script. Do not replace with a config flag or database entry.

**2. The pulse → escalation → review three-tier model**  
Pulses are cheap and frequent (Haiku, lightweight). Escalations are triggered only when a pulse flags something (Sonnet, targeted). Reviews are deep and periodic (Sonnet, thorough). This tiering controls LLM cost while ensuring signals are caught. Collapsing to a single "autonomous cycle" would either miss signals or run expensive calls too often.

**3. KB sub-agent isolation as the autonomous data boundary**  
Adjutant never reads KB files directly during autonomous cycles — it always invokes `query.sh`, which runs `opencode run --agent kb --dir <kb-path>`. This means an autonomous pulse cannot accidentally read `.env`, `identity/soul.md`, or any file outside the KB workspace. Do not add direct file reads to pulse/review prompts as an "optimization."

**4. Insights pipeline (`insights/pending/` → `insights/sent/`)**  
The two-phase insight lifecycle decouples detection from notification, prevents duplicate sends, and creates a natural audit trail. Extend it (e.g., write a JSONL record on move); do not replace it with a direct pulse-to-notify flow.

**5. Adjutant as sole orchestrator — KBs are passive**  
KBs never self-schedule, never call `notify.sh`, never push. One PAUSED kill switch, one notification budget, one action ledger. A model where KBs trigger notifications independently would fragment oversight across N agents.

---

## 5. Implementation Roadmap

### Immediate — Required Before Phase 7 Is Safe

*Sequenced by dependency:*

| # | Action | File(s) | Effort | Depends on |
|---|--------|---------|--------|------------|
| 0 | Fix 3 failing unit tests | `tests/unit/kb.bats`, `tests/unit/wizard.bats`, `tests/unit/repair.bats` | Small | — |
| 1 | Define `state/actions.jsonl` schema + gitignore entry | `.gitignore` | Small | — |
| 2 | Wire action ledger into pulse prompt | `prompts/pulse.md` | Small | #1 |
| 3 | Wire action ledger into review prompt | `prompts/review.md` | Small | #1 |
| 4 | Wire action ledger into escalation prompt | `prompts/escalation.md` | Small | #1 |
| 5 | Hard notification budget guard in `notify.sh` | `scripts/messaging/telegram/notify.sh` | Small | — |
| 6 | Dry-run check in pulse prompt | `prompts/pulse.md` | Small | — |
| 7 | Dry-run check in review prompt | `prompts/review.md` | Small | — |
| 8 | Dry-run check in escalation prompt | `prompts/escalation.md` | Small | — |

### Short-term — Phase 7 Quality

| # | Action | File(s) | Effort | Depends on |
|---|--------|---------|--------|------------|
| 9 | Add `autonomy:` section to `adjutant.yaml.example` | `adjutant.yaml.example` | Small | — |
| 10 | Wizard Step 7: autonomy configuration | `scripts/setup/steps/autonomy.sh`, `wizard.sh` | Medium | #9 |
| 11 | Wire autonomy config into `service.sh` cron | `scripts/setup/steps/service.sh` | Small | #9 |
| 12 | KB creation offer at wizard completion | `scripts/setup/wizard.sh` | Small | — |
| 13 | Extend `/status` with autonomous activity | `scripts/observability/status.sh` | Small | #1 |
| 14 | Unit tests for notification budget guard | `tests/unit/autonomy.bats` | Small | #5 |
| 15 | Integration tests for autonomous cycle | `tests/integration/autonomy.bats` | Medium | #2–8 |
| 16 | User guide for autonomous operation | `docs/guides/autonomy.md` | Small | — |
| 17 | Architecture doc for autonomous loop | `docs/architecture/autonomy.md` | Small | — |
| 18 | CHANGELOG.md Phase 7 entry | `CHANGELOG.md` | Small | — |

### Long-term — Phase 7 Polish

| # | Action | Effort | Notes |
|---|--------|--------|-------|
| 19 | Quiet-hours enforcement in `notify.sh` | Small | Schema exists; a time comparison in bash |
| 20 | `/dryrun` Telegram command | Small | Convenience; config edit is functional |
| 21 | `actions.jsonl` archival in `journal_rotate.sh` | Small | Files are small; low urgency |
| 22 | Multi-KB pulse parallelization | Medium | Currently sequential; parallel `query.sh` calls would be faster |
| 23 | Adaptive pulse cadence (more pulses when issues detected) | Medium | Needs action ledger as foundation |

---

## Summary Table

| Dimension | Status | P0 Blockers | P1 Degraders |
|-----------|--------|-------------|--------------|
| A. Core autonomous loop | ✅ Implemented | Dry-run not enforced in prompts | — |
| B. Notification budget | ⚠️ Partial | No hard guard in `notify.sh` | Quiet-hours not enforced |
| C. Action audit trail | ❌ Missing | `state/actions.jsonl` absent | `/status` doesn't surface activity |
| D. Dry-run & interruptibility | ⚠️ Partial | Dry-run flag unused in prompts | `/dryrun` command absent |
| E. Autonomy configuration | ⚠️ Partial | — | No wizard step; cron hardcoded |
| F. Test coverage | ❌ Not started | 3 existing failures to fix | No autonomy test files exist |
| G. Documentation | ❌ Not started | — | No autonomy guide or architecture doc |

**P0 count: 3 blockers** — all small effort, resolvable in a single focused session before enabling autonomous cycles.
