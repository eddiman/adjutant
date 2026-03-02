# Adjutant Phase 7: Autonomy & Self-Agency — Implementation Plan

**Status**: Planned  
**Version target**: v0.1.0  
**Prerequisite**: Phase 5 complete (v0.0.2), 3 failing unit tests resolved  
**Readiness assessment**: `docs/reference/2026-03-02-phase7-readiness.md`

---

## Goal

Give Adjutant the ability to act on the user's behalf without real-time oversight. Scheduled pulse checks query all registered knowledge bases, surface signals, and send Telegram notifications when warranted. A daily review synthesizes findings into recommendations. All autonomous actions are logged to a machine-readable ledger. The user retains full control via a single PAUSED kill switch and a hard notification budget at the script layer.

---

## Architectural Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Orchestrator | Adjutant only | One PAUSED kill switch, one budget, one ledger |
| KBs | Passive (never self-schedule, never notify) | Fragments oversight if KBs can push independently |
| Audit trail | `state/actions.jsonl` + journal prose | Machine-readable for tooling, human-readable for review |
| Notification budget | Script-level hard counter in `notify.sh` | LLM-only enforcement is not a safety boundary |
| Dry-run | Checked in all three prompts after PAUSED | Zero-side-effect testing without touching kill switch |
| Pulse cadence | Configurable via `adjutant.yaml autonomy.pulse_schedule` | Defaults to 2×/day; users can tighten or loosen |

---

## Pre-Phase-7 Task: Fix 3 Failing Unit Tests

These must pass before Phase 7 work begins. Shipping new tests on a broken suite creates false confidence.

| Test | File | Description |
|------|------|-------------|
| `not ok 68` | `tests/unit/kb.bats` | `kb_scaffold creates directory structure` |
| `not ok 190` | `tests/unit/wizard.bats` (prerequisites section) | `WIZARD_DEPS_OK array is populated with found deps` |
| `not ok 210` | `tests/unit/repair.bats` | `reports all checks passed when everything is healthy` |

Run after fixing: `bats tests/unit/`

---

## Implementation Steps

Steps are sequenced by dependency. Complete P0 items (1–8) before P1 items (9–18).

### P0 — Required before autonomous cycles are safe

#### Step 1: Define `state/actions.jsonl` schema and gitignore entry

**File to edit**: `.gitignore`  
**Action**: Add `state/actions.jsonl` to `.gitignore` (runtime data, not tracked).

**Schema** (each line is one JSON object):
```json
{"ts":"2026-03-02T14:30:00Z","type":"pulse","kbs_checked":["ml-papers","work"],"issues_found":[],"escalated":false}
{"ts":"2026-03-02T14:30:01Z","type":"notify","detail":"[work] Sprint deadline approaching in 3 days."}
{"ts":"2026-03-02T20:00:00Z","type":"review","kbs_checked":["ml-papers","work"],"insights_sent":1,"recommendations":["Review sprint scope"]}
{"ts":"2026-03-02T20:00:05Z","type":"escalation","trigger":"2026-03-02-1430.md","action":"notified","project":"work"}
```

**Fields**:
- `ts` — ISO-8601 timestamp
- `type` — `pulse` | `review` | `escalation` | `notify`
- `kbs_checked` — array of KB names queried (pulse/review only)
- `issues_found` — short descriptions, or empty array
- `escalated` — boolean (pulse only)
- `insights_sent` — integer (review only)
- `recommendations` — array of strings (review only)
- `trigger` — insight filename (escalation only)
- `action` — `notified` | `logged` | `flagged-for-reflect` (escalation only)
- `project` — project name (escalation only)
- `detail` — notification text (notify only)

---

#### Step 2: Wire action ledger into `prompts/pulse.md`

**File to edit**: `prompts/pulse.md`  
**Action**: Add two new steps:

After existing Step 1 (read context), add a dry-run check:

```
### 1b. Check dry-run mode

Read `adjutant.yaml`. If `debug.dry_run` is `true`:
- Proceed through all steps normally EXCEPT:
  - Do NOT write to `insights/pending/`
  - Do NOT write `state/last_heartbeat.json`
  - Prefix every journal entry with `[DRY RUN]`
  - Append to `state/actions.jsonl`: `{"ts":"...","type":"pulse","dry_run":true,...}`
- Continue to the end of the prompt, then stop.
```

After existing Step 6 (update state), add:

```
### 6b. Append to action ledger

Append one line to `state/actions.jsonl` (create if it doesn't exist):
```json
{"ts":"<ISO-8601>","type":"pulse","kbs_checked":["<names>"],"issues_found":["<descriptions or empty>"],"escalated":<true/false>}
```
```

---

#### Step 3: Wire action ledger into `prompts/review.md`

**File to edit**: `prompts/review.md`  
**Action**: Same pattern as Step 2.

After existing Step 1 (read context), add:

```
### 1b. Check dry-run mode

Read `adjutant.yaml`. If `debug.dry_run` is `true`:
- Proceed through all steps normally EXCEPT:
  - Do NOT call `notify.sh`
  - Do NOT move files from `insights/pending/` to `insights/sent/`
  - Prefix every journal entry with `[DRY RUN]`
  - Append to `state/actions.jsonl`: `{"ts":"...","type":"review","dry_run":true,...}`
- Continue to the end of the prompt, then stop.
```

After existing Step 7 (update state), add:

```
### 7b. Append to action ledger

Append one line to `state/actions.jsonl`:
```json
{"ts":"<ISO-8601>","type":"review","kbs_checked":["<names>"],"insights_sent":<n>,"recommendations":["<list>"]}
```
```

---

#### Step 4: Wire action ledger into `prompts/escalation.md`

**File to edit**: `prompts/escalation.md`  
**Action**: Same pattern. After existing Step 5 (update state), add:

```
### 5b. Append to action ledger

Append one line to `state/actions.jsonl`:
```json
{"ts":"<ISO-8601>","type":"escalation","trigger":"<insight filename>","action":"<notified|logged|flagged-for-reflect>","project":"<project name>"}
```

If a notification was sent, also append:
```json
{"ts":"<ISO-8601>","type":"notify","detail":"<notification text>"}
```
```

---

#### Step 5: Hard notification budget guard in `notify.sh`

**File to edit**: `scripts/messaging/telegram/notify.sh`  
**Action**: Add budget enforcement before the curl send.

Logic to insert after message sanitisation (after line 23):

```bash
# --- Notification budget guard ---
local today
today="$(date +%Y-%m-%d)"
local count_file="${ADJ_DIR}/state/notify_count_${today}.txt"
local count=0
[ -f "${count_file}" ] && count="$(cat "${count_file}")"

# Read max_per_day from adjutant.yaml (default: 3)
local max_per_day=3
if [ -f "${ADJ_DIR}/adjutant.yaml" ]; then
  local yaml_val
  yaml_val="$(grep -E '^\s*max_per_day:' "${ADJ_DIR}/adjutant.yaml" | head -1 | grep -oE '[0-9]+')"
  [ -n "${yaml_val}" ] && max_per_day="${yaml_val}"
fi

if [ "${count}" -ge "${max_per_day}" ]; then
  echo "ERROR:budget_exceeded (${count}/${max_per_day} sent today)"
  exit 1
fi
```

And after the successful send check (replace the `echo "Sent."` block):

```bash
if echo "$RESPONSE" | grep -q '"ok":true'; then
  # Increment counter
  echo $(( count + 1 )) > "${count_file}"
  echo "Sent. ($(( count + 1 ))/${max_per_day} today)"
else
  ...
fi
```

---

#### Steps 6–8: Dry-run check in all three prompts

Covered by Steps 2–4 above (each prompt edit includes both the dry-run check and the action ledger step).

---

### P1 — Quality improvements

#### Step 9: Add `autonomy:` section to `adjutant.yaml.example`

**File to edit**: `adjutant.yaml.example`  
**Action**: Add after the `features:` block:

```yaml
autonomy:
  enabled: false                     # set to true to enable scheduled pulses and reviews
  pulse_schedule: "0 9,17 * * 1-5"  # cron: weekdays at 9am and 5pm
  review_schedule: "0 20 * * 1-5"   # cron: weekdays at 8pm
```

---

#### Step 10: Wizard Step 7 — Autonomy configuration

**File to create**: `scripts/setup/steps/autonomy.sh`  
**File to edit**: `scripts/setup/wizard.sh` — add Step 7 source + call after Step 6

`autonomy.sh` flow:
1. `wiz_step 7 7 "Autonomy Configuration"`
2. Ask: "Enable autonomous pulse checks? (Adjutant will query your KBs on a schedule)" [y/N]
3. If yes: show default schedule (`0 9,17 * * 1-5`), offer to customise
4. Ask: "Enable daily review?" [Y/n] (requires pulses enabled)
5. Ask: "Maximum notifications per day?" [3]
6. Ask: "Enable quiet hours?" [y/N] — if yes, ask start/end times
7. Write choices to `adjutant.yaml` under `autonomy:` and `notifications:`
8. If enabled: install cron jobs for pulse and review schedules

**`wizard.sh` change**: Add after Step 6:
```bash
# ── Step 7: Autonomy ───────────────────────────────────────────────────
source "${SETUP_DIR}/steps/autonomy.sh"
step_autonomy || {
  wiz_warn "Autonomy setup incomplete — configure later in adjutant.yaml"
}
```

Update `wiz_step` calls throughout from `N 6` to `N 7`.

---

#### Step 11: Wire autonomy config into `service.sh` cron install

**File to edit**: `scripts/setup/steps/service.sh`  
**Action**: In `_service_install_news_cron()`, read cron schedule from `adjutant.yaml` `features.news.schedule` instead of hardcoding `"0 8 * * 1-5"`. Pulse/review cron installation moves to `autonomy.sh` (Step 10).

```bash
# Read schedule from adjutant.yaml
local schedule="0 8 * * 1-5"
if [ -f "${ADJ_DIR}/adjutant.yaml" ]; then
  local yaml_schedule
  yaml_schedule="$(grep -A2 'news:' "${ADJ_DIR}/adjutant.yaml" | grep 'schedule:' | head -1 | sed "s/.*schedule:[[:space:]]*//" | tr -d '"')"
  [ -n "${yaml_schedule}" ] && schedule="${yaml_schedule}"
fi
local cron_line="${schedule} ${ADJ_DIR}/scripts/news/briefing.sh >> ${ADJ_DIR}/state/adjutant.log 2>&1"
```

---

#### Step 12: KB creation offer at wizard completion

**File to edit**: `scripts/setup/wizard.sh` `_show_completion()`  
**Action**: After the cost estimate table, add:

```bash
echo ""
if wiz_confirm "Would you like to create a knowledge base now?" "N"; then
  bash "${ADJ_DIR}/scripts/setup/steps/kb_wizard.sh"
fi
```

---

#### Step 13: Extend `/status` with autonomous activity

**File to edit**: `scripts/observability/status.sh`  
**Action**: After the existing cron jobs section, add:

```bash
echo ""
echo "Autonomous activity:"

# Last heartbeat
local heartbeat_file="${ADJ_DIR}/state/last_heartbeat.json"
if [ -f "${heartbeat_file}" ]; then
  local hb_type hb_ts
  hb_type="$(grep -o '"type":"[^"]*"' "${heartbeat_file}" | cut -d'"' -f4)"
  hb_ts="$(grep -o '"timestamp":"[^"]*"' "${heartbeat_file}" | cut -d'"' -f4)"
  echo "  Last cycle: ${hb_type} at ${hb_ts}"
else
  echo "  No autonomous cycles recorded yet."
fi

# Today's notification count
local today count_file count max_per_day
today="$(date +%Y-%m-%d)"
count_file="${ADJ_DIR}/state/notify_count_${today}.txt"
count=0
[ -f "${count_file}" ] && count="$(cat "${count_file}")"
max_per_day="$(grep -E '^\s*max_per_day:' "${ADJ_DIR}/adjutant.yaml" 2>/dev/null | head -1 | grep -oE '[0-9]+' || echo 3)"
echo "  Notifications today: ${count}/${max_per_day}"

# Last 5 actions
local actions_file="${ADJ_DIR}/state/actions.jsonl"
if [ -f "${actions_file}" ] && [ -s "${actions_file}" ]; then
  echo "  Recent actions:"
  tail -5 "${actions_file}" | while IFS= read -r line; do
    local ts type
    ts="$(echo "${line}" | grep -o '"ts":"[^"]*"' | cut -d'"' -f4)"
    type="$(echo "${line}" | grep -o '"type":"[^"]*"' | cut -d'"' -f4)"
    echo "    ${ts}  ${type}"
  done
fi
```

---

#### Step 14: Unit tests for notification budget guard

**File to create**: `tests/unit/autonomy.bats`

Tests to include:
- `notify.sh: rejects send when budget is exceeded`
- `notify.sh: increments counter after successful send`
- `notify.sh: reads max_per_day from adjutant.yaml`
- `notify.sh: uses default budget of 3 when adjutant.yaml absent`
- `notify.sh: counter file is date-scoped (YYYY-MM-DD)`
- `actions.jsonl: pulse appends correct JSONL schema`
- `actions.jsonl: review appends correct JSONL schema`
- `actions.jsonl: escalation appends correct JSONL schema`

Follow existing unit test patterns: `ADJUTANT_HOME` isolation per test, mock curl via PATH injection.

---

#### Step 15: Integration tests for autonomous cycle

**File to create**: `tests/integration/autonomy.bats`

Tests to include:
- `pulse: writes journal entry when not paused`
- `pulse: skips when PAUSED exists`
- `pulse: logs DRY RUN when dry_run: true`
- `review: sends notification via notify.sh for pending insight`
- `review: moves insight to sent/ after notifying`
- `review: skips notification when PAUSED`
- `escalation: notifies and moves insight when notification-worthy`
- `escalation: flags for reflect when too complex`
- `notify.sh: budget guard blocks send at limit`
- `status.sh: surfaces last heartbeat and notification count`

Mock `opencode` and `curl` via PATH injection (existing pattern in `tests/test_helper/mocks.bash`).

---

#### Step 16: User guide for autonomous operation

**File to create**: `docs/guides/autonomy.md`

Sections:
1. What autonomy mode does (pulse → escalation → review)
2. Enabling autonomy (wizard Step 7 or manual `adjutant.yaml` edit)
3. Configuring pulse cadence and review schedule
4. Notification budget and quiet hours
5. Understanding the action ledger (`state/actions.jsonl`)
6. Pausing and resuming (`/pause`, `/resume`, `touch PAUSED`)
7. Dry-run mode (testing without side effects)
8. Reading the `/status` output

---

#### Step 17: Architecture doc for autonomous loop

**File to create**: `docs/architecture/autonomy.md`

Sections:
1. Control flow diagram (cron → opencode run --print pulse.md → insights/pending/ → escalation.md → notify.sh)
2. Kill-switch hierarchy (PAUSED > dry_run > budget > quiet_hours)
3. Data flow (what each prompt reads and writes)
4. Isolation guarantees (why KBs are passive, why Adjutant is sole orchestrator)
5. Budget enforcement architecture (script-layer vs. LLM-layer)
6. Action ledger schema and retention policy

---

#### Step 18: CHANGELOG.md Phase 7 entry

**File to edit**: `CHANGELOG.md`  
**Action**: Add entry under a new `## [Unreleased]` or `## [0.1.0]` heading:

```markdown
## [0.1.0] — Autonomy & Self-Agency

### Added
- Scheduled autonomous pulse checks query all registered KBs on a configurable cron schedule
- Daily review synthesizes pulse findings and sends Telegram notifications for significant insights
- Machine-readable action ledger (`state/actions.jsonl`) for programmatic oversight
- Hard notification budget counter in `notify.sh` — script-layer enforcement independent of LLM
- Dry-run mode enforced in all three autonomous prompts (`pulse.md`, `review.md`, `escalation.md`)
- Wizard Step 7: guided autonomy configuration (cadence, budget, quiet hours)
- `/status` now surfaces last heartbeat timestamp and today's notification count
- `autonomy:` section added to `adjutant.yaml.example`
- `docs/guides/autonomy.md` and `docs/architecture/autonomy.md`

### Fixed
- 3 failing unit tests: `kb_scaffold` (#68), `WIZARD_DEPS_OK` (#190), `repair health check` (#210)
```

---

## File Inventory

### Files to create

| File | Purpose |
|------|---------|
| `scripts/setup/steps/autonomy.sh` | Wizard Step 7 |
| `tests/unit/autonomy.bats` | Unit tests for budget guard and ledger |
| `tests/integration/autonomy.bats` | Integration tests for full autonomous cycle |
| `docs/guides/autonomy.md` | User guide |
| `docs/architecture/autonomy.md` | Architecture reference |

### Files to edit

| File | Change |
|------|--------|
| `prompts/pulse.md` | Add dry-run check + action ledger step |
| `prompts/review.md` | Add dry-run check + action ledger step |
| `prompts/escalation.md` | Add action ledger step |
| `scripts/messaging/telegram/notify.sh` | Add hard budget guard |
| `scripts/setup/wizard.sh` | Add Step 7 call + KB offer at completion |
| `scripts/setup/steps/service.sh` | Read cron schedule from adjutant.yaml |
| `scripts/observability/status.sh` | Surface autonomous activity |
| `adjutant.yaml.example` | Add `autonomy:` section |
| `.gitignore` | Add `state/actions.jsonl` |
| `CHANGELOG.md` | Add Phase 7 entry |

### Files to fix (pre-Phase-7)

| File | Failing test |
|------|-------------|
| `tests/unit/kb.bats` (or source under test) | `not ok 68` — kb_scaffold directory structure |
| `tests/unit/wizard.bats` (or source under test) | `not ok 190` — WIZARD_DEPS_OK array |
| `tests/unit/repair.bats` (or source under test) | `not ok 210` — repair health check |

---

## Completion Gate

Phase 7 is complete when:

1. `bats tests/unit/ tests/integration/` — 0 failures (including new autonomy tests)
2. `notify.sh` rejects sends when `state/notify_count_YYYY-MM-DD.txt` count >= `max_per_day`
3. `touch PAUSED && opencode run --print prompts/pulse.md` outputs "Adjutant is paused. Skipping pulse." and writes nothing to `insights/` or `state/actions.jsonl`
4. `adjutant.yaml` with `debug.dry_run: true` — pulse/review run end-to-end, journal entries prefixed `[DRY RUN]`, no notifications sent, `state/actions.jsonl` records `"dry_run":true`
5. `adjutant status` shows last heartbeat type/timestamp and `N/M` notification count
6. `adjutant setup` reaches Step 7 and writes `autonomy:` block to `adjutant.yaml`
7. `docs/guides/autonomy.md` and `docs/architecture/autonomy.md` exist and are accurate
