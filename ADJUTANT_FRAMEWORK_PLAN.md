# Adjutant Framework — Generalization Plan

**Status**: Phase 5 complete (Generalization & Public Distribution)  
**Last Updated**: 2026-03-01  
**Objective**: Transform Adjutant from a personal agent into a generalizable framework for building persistent autonomous agents with pluggable interfaces, multiple LLM backends, and flexible deployment.

---

## Table of Contents

1. [Part 1: Honest Diagnosis](#part-1-honest-diagnosis--whats-wrong-today)
2. [Part 2: Proposed Directory Structure](#part-2-proposed-directory-structure)
3. [Part 3: The Shared Utilities](#part-3-the-shared-utilities--scriptscommon)
4. [Part 4: Unified Configuration](#part-4-unified-configuration--adjutantyaml)
5. [Part 5: The Setup Wizard](#part-5-the-setup-wizard)
6. [Part 6: Messaging Adaptor Interface](#part-6-messaging-adaptor-interface)
7. [Part 7: Breaking Up the Listener](#part-7-breaking-up-the-660-line-listener)
8. [Part 8: Additional Proposals](#part-8-additional-proposals)
9. [Part 9: Migration Path](#part-9-migration-path-full-backward-compatibility)
10. [Part 10: What NOT to Change](#part-10-what-not-to-change)
11. [Summary: Priority Order](#summary-priority-order)

---

## Design Constraints

Based on your answers to the planning questions:

- **Target Platforms**: macOS + Linux initially, Docker support planned for later
- **Messaging**: Telegram (existing), with adaptors provided for others
- **LLM Backend**: OpenCode only
- **Setup**: Interactive wizard with token cost estimates
- **Backward Compatibility**: Full — existing `~/.adjutant/` setup must work unchanged

---

## Part 1: Honest Diagnosis — What's Wrong Today

### 1.1 The 660-Line God Script

`telegram_listener.sh` is the nervous system of Adjutant. It handles:

- Telegram API polling (long-poll loop)
- Authentication / chat ID validation
- Command parsing and dispatch (`/status`, `/pause`, `/pulse`, `/reflect`, `/screenshot`, `/model`, `/kill`, etc.)
- Photo downloading and vision routing
- Typing indicator management
- In-flight job killing and registration
- Python-embedded JSON parsing (via heredocs)
- Session management
- Base64 encoding/decoding of message payloads
- Timestamp formatting via inline Python
- Direct `curl` calls to Telegram API

**Problem**: If you want anyone else to set up Adjutant, or if you want to swap Telegram for anything else, this script IS Adjutant. Everything is welded together.

### 1.2 Hardcoded Path Assumptions

Every script resolves `ADJ_DIR` independently. Most use `$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)` (the relative approach — good), but several hardcode `${HOME}/.adjutant`:

| Script | Path Strategy |
|--------|--------------|
| `telegram.sh` | `$HOME/.adjutant` hardcoded |
| `startup.sh` | `$HOME/.adjutant` hardcoded |
| `emergency_kill.sh` | `$HOME/.adjutant` hardcoded |
| `restart.sh` | `$HOME/.adjutant` hardcoded |
| `news_briefing.sh` | `$HOME/.adjutant` hardcoded |
| `fetch_news.sh` | `$HOME/.adjutant` hardcoded |
| `analyze_news.sh` | `$HOME/.adjutant` hardcoded |
| `fetch_agentic_news.sh` | `$HOME/.adjutant` hardcoded |
| Others | Relative resolution ✓ |

**Impact**: 8 of 18 shell scripts would break if you installed Adjutant anywhere other than `~/.adjutant/`.

### 1.3 Credential Loading is Copy-Pasted

The same 4-line block appears in **5 separate scripts**:

```bash
TELEGRAM_BOT_TOKEN="$(grep -E '^TELEGRAM_BOT_TOKEN=' "${ENV_FILE}" | head -1 | cut -d '=' -f2- | tr -d "'\"")"
TELEGRAM_CHAT_ID="$(grep -E '^TELEGRAM_CHAT_ID=' "${ENV_FILE}" | head -1 | cut -d '=' -f2- | tr -d "'\"")"
```

Found in: `telegram_listener.sh`, `notify_telegram.sh`, `screenshot.sh`, `telegram_reply.sh`, and implicitly expected by `telegram_chat.sh`.

**Problem**: A single change to credential format requires touching all five scripts.

### 1.4 Python-in-Bash Anti-Pattern

You embed Python inside bash heredocs for JSON parsing, timestamp formatting, session management, base64 decoding, and URL parsing. This is ~15 separate Python snippets embedded across the scripts.

**Issues**:
- Fragile (escaping issues)
- Hard to test independently
- Hard to read
- **Security risk**: Your own security assessment (SECURITY_ASSESSMENT.md, lines 43-49) flags the `fmt_ts()` function as HIGH severity — it has Python code injection vulnerability

### 1.5 Flat `scripts/` Directory — No Semantic Grouping

All 19 scripts sit in one directory, but they serve different purposes:

| Concern | Scripts |
|---------|---------|
| **Messaging/Telegram** | `telegram_listener.sh`, `telegram_chat.sh`, `telegram_reply.sh`, `telegram.sh`, `notify_telegram.sh` |
| **Lifecycle/System** | `startup.sh`, `restart.sh`, `emergency_kill.sh`, `kill.sh`, `resume.sh`, `status.sh` |
| **Capabilities** | `screenshot.sh`, `vision.sh` |
| **News subsystem** | `news_briefing.sh`, `fetch_news.sh`, `fetch_agentic_news.sh`, `analyze_news.sh` |
| **Observability** | `usage_estimate.sh` |
| **Browser support** | `playwright-stealth.js` |

**Problem**: Six different concerns, one flat folder. Makes it hard to understand scope, swap implementations, or remove features.

### 1.6 No Configuration Layer

Configuration is scattered across:

- `.env` — secrets
- `news_config.json` — news feature config
- `opencode.json` — OpenCode workspace permissions
- `soul.md` — behavioral config disguised as identity
- `heart.md` — runtime priorities
- `registry.md` — project registration
- `state/telegram_model.txt` — a single text file for one setting
- Hardcoded values in scripts (`SESSION_TIMEOUT_SECONDS=7200`, `SESSION_CAP=44000`, `WEEK_CAP=350000`)

**Problem**: No single source of truth for "how is this Adjutant instance configured?"

### 1.7 macOS-Only Assumptions

- Launch Agent plist for service management
- `stat -f "%m %N"` (macOS-specific; Linux uses `stat -c`)
- `date -v-5H` (macOS-specific; Linux uses `date -d "5 hours ago"`)
- `crontab` for scheduling (the news briefing)
- `launchctl` for process management

**Note**: The `news_briefing.sh` and `usage_estimate.sh` actually have some Linux fallbacks (`date -d`), but most scripts don't.

### 1.8 Duplicate/Dead Code

- `fetch_agentic_news.sh` (37 lines) appears to be a **prototype** of `fetch_news.sh` (163 lines). It fetches from HN and Reddit with hardcoded queries, writes to `news_cache.json` (a different cache file than the production `news_raw/` system). It's never referenced by `news_briefing.sh`. **Dead code**.
- `kill.sh` (8 lines) and `resume.sh` (7 lines) are labeled "legacy" in the architecture doc but still exist.

---

## Part 2: Proposed Directory Structure

Here's the reorganized structure. **Key principle**: group by concern, not by file type.

```
~/.adjutant/                          # or any install path
├── adjutant.yaml                     # ← NEW: single unified config file
├── .env                              # Secrets only (unchanged)
├── .env.example
│
├── identity/                         # ← WAS: loose files in root
│   ├── soul.md                       # Identity, personality, values
│   ├── heart.md                      # Current priorities
│   └── registry.md                   # Project manifests
│
├── prompts/                          # Unchanged
│   ├── pulse.md
│   ├── review.md
│   └── escalation.md
│
├── scripts/
│   ├── common/                       # ← NEW: shared utilities
│   │   ├── env.sh                    # load_env(), get_credential()
│   │   ├── paths.sh                  # ADJ_DIR resolution, path helpers
│   │   ├── logging.sh                # log(), fmt_ts() (fixed, no Python injection)
│   │   ├── platform.sh               # OS detection, date/stat abstraction
│   │   ├── lockfiles.sh              # check_killed(), check_paused()
│   │   └── opencode.sh               # opencode_run() wrapper, opencode_reap() orphan cleanup
│   │
│   ├── messaging/                    # ← WAS: telegram_*.sh scattered in scripts/
│   │   ├── adaptor.sh                # ← NEW: messaging interface contract
│   │   ├── telegram/
│   │   │   ├── listener.sh           # Polling loop only — thin dispatcher
│   │   │   ├── commands.sh           # Command handlers (status, pause, pulse, etc.)
│   │   │   ├── chat.sh               # Natural language routing
│   │   │   ├── send.sh               # Outbound: reply(), react(), typing, sendPhoto
│   │   │   ├── photos.sh             # Photo download + vision routing
│   │   │   └── service.sh            # start/stop/restart/status
│   │   └── dispatch.sh               # ← NEW: command dispatch (backend-agnostic)
│   │
│   ├── capabilities/                 # ← NEW grouping
│   │   ├── _registry.sh              # ← NEW: discover & load capabilities
│   │   ├── screenshot/
│   │   │   ├── capability.yaml
│   │   │   └── screenshot.sh
│   │   └── vision/
│   │       ├── capability.yaml
│   │       └── vision.sh
│   │
│   ├── news/                         # ← WAS: news_*.sh / fetch_*.sh / analyze_*.sh
│   │   ├── capability.yaml           # ← NEW: make news a capability
│   │   ├── briefing.sh               # Orchestrator
│   │   ├── fetch.sh                  # Multi-source fetcher
│   │   └── analyze.sh                # Haiku ranking
│   │
│   ├── lifecycle/                    # ← WAS: all mixed together
│   │   ├── startup.sh
│   │   ├── restart.sh
│   │   ├── emergency_kill.sh
│   │   ├── pause.sh                  # replaces kill.sh (better name)
│   │   └── resume.sh
│   │
│   └── observability/
│       ├── status.sh
│       ├── usage_estimate.sh
│       ├── journal_rotate.sh         # ← NEW: archive old entries
│       ├── healthcheck.sh            # ← NEW: status JSON for external tools
│       └── doctor.sh                 # ← NEW: health check + dependency verification
│
├── .opencode/                        # Unchanged
│   ├── agents/
│   │   └── adjutant.md
│   └── package.json
│
├── opencode.json                     # Workspace config
│
├── journal/                          # Runtime data (gitignored)
├── insights/
│   ├── pending/
│   └── sent/
├── state/
├── photos/
├── screenshots/
│
├── docs/
│   ├── emergency_kill.md
│   ├── news_briefing.md
│   ├── news_briefing_setup.md
│   ├── adaptor_guide.md              # ← NEW: how to build Slack/Discord/CLI adaptors
│   └── plugin_guide.md               # ← NEW: how to build capabilities
│
├── ARCHITECTURE.md
├── SECURITY_ASSESSMENT.md
├── ADJUTANT_FRAMEWORK_PLAN.md        # ← This file
└── README.md
```

### What Changed and Why

| Change | Rationale |
|--------|-----------|
| `scripts/common/` with shared utilities | Eliminates 5× credential loading duplication, inline Python injection vectors, per-script platform workarounds |
| `scripts/messaging/telegram/` | Isolates ALL Telegram concerns. Swapping to Slack means building `scripts/messaging/slack/` without touching anything else |
| `scripts/messaging/adaptor.sh` | Documents the interface contract: what functions a messaging backend must implement |
| `scripts/capabilities/` | Screenshot, vision, and news are *optional capabilities*, not core features. Grouping makes them removable |
| `scripts/news/` as a capability | News subsystem is self-contained and optional. Can be disabled or replaced |
| `scripts/lifecycle/` | startup/restart/kill/pause/resume are system lifecycle — separate from features |
| `identity/` directory | soul.md, heart.md, registry.md are the agent's identity layer. Dedicated folder reinforces architecture |
| `adjutant.yaml` | Single source of truth for operational settings |
| New CLI entrypoint | `adjutant setup`, `adjutant start`, `adjutant logs`, etc. |
| Delete `fetch_agentic_news.sh` | Dead prototype code |
| Rename `kill.sh` → `pause.sh` | `kill.sh` doesn't kill — it creates PAUSED. Name is misleading |

---

## Part 3: The Shared Utilities — `scripts/common/`

This is the **highest-value refactor**. It eliminates duplication, fixes security bugs, and enables portability.

### 3.1 `env.sh` — Credential Loading (replaces 5× copy-paste)

```bash
#!/bin/bash
# scripts/common/env.sh
# Load credentials from .env without sourcing

_adj_env_file="${ADJ_DIR}/.env"

load_env() {
  if [ ! -f "${_adj_env_file}" ]; then
    echo "Error: ${_adj_env_file} not found." >&2
    return 1
  fi
}

get_credential() {
  local key="$1"
  grep -E "^${key}=" "${_adj_env_file}" | head -1 | cut -d '=' -f2- | tr -d "'\""
}

# Usage in any script:
# TELEGRAM_BOT_TOKEN="$(get_credential TELEGRAM_BOT_TOKEN)"
# TELEGRAM_CHAT_ID="$(get_credential TELEGRAM_CHAT_ID)"
```

### 3.2 `paths.sh` — Consistent Path Resolution

```bash
#!/bin/bash
# scripts/common/paths.sh
# Resolve ADJ_DIR from any script location

resolve_adj_dir() {
  # If ADJ_DIR is set explicitly (by config/wizard), use it
  if [ -n "${ADJUTANT_HOME:-}" ]; then
    echo "${ADJUTANT_HOME}"
    return
  fi
  # Otherwise, resolve relative to the calling script
  local script_dir
  script_dir="$(cd "$(dirname "${BASH_SOURCE[1]}")" && pwd)"
  # Walk up until we find adjutant.yaml (the root marker)
  local dir="$script_dir"
  while [ "$dir" != "/" ]; do
    if [ -f "$dir/adjutant.yaml" ]; then
      echo "$dir"
      return
    fi
    dir="$(dirname "$dir")"
  done
  # Fallback to legacy location
  echo "${HOME}/.adjutant"
}

ADJ_DIR="$(resolve_adj_dir)"
export ADJ_DIR
```

### 3.3 `platform.sh` — OS Abstraction

```bash
#!/bin/bash
# scripts/common/platform.sh
# Detect OS and provide portable wrappers

ADJUTANT_OS="unknown"
case "$(uname -s)" in
  Darwin) ADJUTANT_OS="macos" ;;
  Linux)  ADJUTANT_OS="linux" ;;
esac
export ADJUTANT_OS

# Portable date math
date_subtract() {
  local amount="$1" unit="$2"
  if [ "$ADJUTANT_OS" = "macos" ]; then
    date -u -v-"${amount}${unit}" +"%Y-%m-%dT%H:%M:%SZ"
  else
    date -u -d "${amount} ${unit} ago" +"%Y-%m-%dT%H:%M:%SZ"
  fi
}

# Portable file mod time (epoch seconds)
file_mtime() {
  local filepath="$1"
  if [ "$ADJUTANT_OS" = "macos" ]; then
    stat -f "%m" "$filepath"
  else
    stat -c "%Y" "$filepath"
  fi
}

# Portable file stat
file_stat() {
  local filepath="$1"
  if [ "$ADJUTANT_OS" = "macos" ]; then
    stat -f "%m" "$filepath"
  else
    stat -c "%Y" "$filepath"
  fi
}
```

### 3.4 `lockfiles.sh` — Killed/Paused Checks (replaces 18× scattered checks)

```bash
#!/bin/bash
# scripts/common/lockfiles.sh
# Centralized lockfile checks (replaces 18+ scattered checks)

check_killed() {
  if [ -f "${ADJ_DIR}/KILLED" ]; then
    echo "KILLED lockfile exists. Run startup.sh to restore." >&2
    exit 1
  fi
}

check_paused() {
  if [ -f "${ADJ_DIR}/PAUSED" ]; then
    echo "Adjutant is paused." >&2
    return 1
  fi
}

check_operational() {
  check_killed
  check_paused
}
```

### 3.5 `logging.sh` — Safe Logging (fixes the Python injection vulnerability)

```bash
#!/bin/bash
# scripts/common/logging.sh
# Safe, platform-agnostic logging (replaces Python-in-heredoc pattern)

adj_log() {
  local context="${1:-general}"
  shift
  local msg="$*"
  # Sanitize: strip control chars and newlines from log content
  msg="$(printf '%s' "$msg" | tr -d '\000-\011\013-\037\177' | tr '\n' ' ')"
  echo "[$(date '+%H:%M %d.%m.%Y')] [${context}] ${msg}" >> "${ADJ_DIR}/state/adjutant.log"
}

# Portable timestamp formatting — no Python, no injection vulnerabilities
fmt_ts() {
  local raw="$1"
  # Try ISO-8601 → human-readable conversion, pure bash/date
  if [ "$ADJUTANT_OS" = "macos" ]; then
    date -jf "%Y-%m-%dT%H:%M:%SZ" "$raw" "+%H:%M %d.%m.%Y" 2>/dev/null || echo "$raw"
  else
    date -d "$raw" "+%H:%M %d.%m.%Y" 2>/dev/null || echo "$raw"
  fi
}
```

### 3.6 `opencode.sh` — Safe OpenCode Wrapper (prevents orphaned child processes)

**Problem**: `opencode run` spawns a `bash-language-server` child process for bash file
intelligence. When `opencode run` exits, the child survives — reparented to PID 1, each
holding ~400 MB RSS. Over days, these accumulate silently, consuming gigabytes of RAM.

**Solution**: Two-layer defense:

1. **`opencode_run`** — Drop-in replacement for `opencode` that snapshots child PIDs
   before and after, then kills any new orphans the opencode process left behind.
2. **`opencode_reap`** — Periodic sweeper (called from the listener main loop) that finds
   all `bash-language-server` processes whose parent is PID 1 (orphaned) and kills them.

```bash
#!/bin/bash
# scripts/common/opencode.sh
# Safe opencode wrapper with child-process cleanup

_OPENCODE_BIN="${_OPENCODE_BIN:-$(command -v opencode 2>/dev/null || echo "")}"

# Drop-in replacement for `opencode` — cleans up leaked children after exit
opencode_run() {
  local _before_pids _after_pids _new_pids
  _before_pids="$(pgrep -f 'bash-language-server' 2>/dev/null | sort || true)"

  "${_OPENCODE_BIN}" "$@"
  local _rc=$?

  _after_pids="$(pgrep -f 'bash-language-server' 2>/dev/null | sort || true)"
  _new_pids="$(comm -13 <(echo "${_before_pids}") <(echo "${_after_pids}") || true)"

  for _pid in ${_new_pids}; do
    kill -TERM "${_pid}" 2>/dev/null || true
  done

  return ${_rc}
}

# Periodic safety net — kill orphaned bash-language-servers (parent = PID 1)
opencode_reap() {
  local _pids _pid _ppid
  _pids="$(pgrep -f 'bash-language-server' 2>/dev/null || true)"
  for _pid in ${_pids}; do
    _ppid="$(ps -o ppid= -p "${_pid}" 2>/dev/null | tr -d ' ')" || continue
    if [ "${_ppid}" = "1" ] || ! kill -0 "${_ppid}" 2>/dev/null; then
      kill -TERM "${_pid}" 2>/dev/null || true
    fi
  done
}
```

**Invocation sites using `opencode_run`**:

| Script | Invocation |
|--------|------------|
| `messaging/telegram/chat.sh` | `opencode_run run --agent adjutant --dir ... --format json` |
| `news/analyze.sh` | `opencode_run run "$PROMPT" --model ... --format json` |
| `capabilities/vision/vision.sh` | `opencode_run run --model ... --format json -f <image>` |
| `capabilities/kb/query.sh` | `opencode_run run --agent kb --dir <kb-path> --format json` |

**Invocation sites using inline PID snapshot** (because `timeout` can't call bash functions):

| Script | Command |
|--------|---------|
| `messaging/telegram/commands.sh` (`cmd_pulse`) | `timeout 120 opencode run --print ...` |
| `messaging/telegram/commands.sh` (`cmd_reflect_confirm`) | `timeout 300 opencode run --model opus --print ...` |

**Periodic reaper**: The listener main loop calls `opencode_reap` every ~50 poll cycles
(~8 minutes) as a safety net for any orphans that slip through the wrapper (e.g., when
opencode is killed by `timeout` or `_kill_inflight_job` before the wrapper's cleanup runs).

### Usage Pattern

Every script in the new structure starts with:

```bash
#!/bin/bash
set -euo pipefail

# Load common utilities
source "$(dirname "${BASH_SOURCE[0]}")/../common/paths.sh"
source "${ADJ_DIR}/scripts/common/env.sh"
source "${ADJ_DIR}/scripts/common/logging.sh"
source "${ADJ_DIR}/scripts/common/lockfiles.sh"
source "${ADJ_DIR}/scripts/common/platform.sh"

# Now the script can use:
# - $ADJ_DIR (correctly resolved)
# - get_credential "TELEGRAM_BOT_TOKEN"
# - check_operational (handles KILLED/PAUSED)
# - adj_log "context" "message"
# - date_subtract 5 "hours"
# - file_mtime "/path/to/file"
# - $ADJUTANT_OS (macos | linux)
```

---

## Part 4: Unified Configuration — `adjutant.yaml`

Replace the scattered config with one file as the single source of truth:

```yaml
# adjutant.yaml — Single source of truth for this Adjutant instance

instance:
  name: "adjutant"                    # Instance name (for multi-agent setups)
  install_path: "~/.adjutant"         # Where this instance lives
  
identity:
  soul: "identity/soul.md"            # Agent personality & values
  heart: "identity/heart.md"          # Current priorities
  registry: "identity/registry.md"    # Registered projects

messaging:
  backend: "telegram"                 # Which adaptor to use (telegram | slack | discord | cli)
  telegram:
    session_timeout_seconds: 7200     # 2 hours
    default_model: "anthropic/claude-haiku-4-5"
    rate_limit:
      messages_per_minute: 10
      backoff_exponential: true

llm:
  backend: "opencode"                 # Currently only supported backend
  models:
    cheap: "anthropic/claude-haiku-4-5"
    medium: "anthropic/claude-sonnet-4-5"
    expensive: "claude-opus-4-5"      # Manual only
  caps:
    session_tokens: 44000
    session_window_hours: 5
    weekly_tokens: 350000

features:
  news:
    enabled: true
    config_path: "news_config.json"   # Keep existing config file
    schedule: "0 8 * * 1-5"           # Cron expression: weekdays 8am
  screenshot:
    enabled: true
  vision:
    enabled: true
  usage_tracking:
    enabled: true

platform:
  service_manager: "launchd"          # launchd | systemd | manual
  process_manager: "pidfile"          # pidfile | supervisor

notifications:
  max_per_day: 3
  quiet_hours:
    enabled: false
    start: "22:00"
    end: "07:00"

security:
  prompt_injection_guard: true
  env_file: ".env"
  log_unknown_senders: true
  rate_limiting: true

debug:
  dry_run: false                      # Process but don't send/call LLM
  verbose_logging: false
  mock_llm: false                     # Return canned responses instead of calling API
```

This doesn't replace `soul.md`/`heart.md`/`registry.md` (those are *identity*, not config). It replaces the 7+ places where operational settings are hardcoded.

---

## Part 5: The Setup Wizard

An interactive LLM-driven setup that walks a new user through getting Adjutant running.

### 5.1 Wizard Flow

```
$ adjutant setup

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Adjutant — Setup Wizard
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Step 1 of 6: Prerequisites Check
  ✓ opencode CLI found (v1.2.10)
  ✓ python3 found (3.12.1)
  ✓ curl found
  ✓ jq found
  ✗ playwright not found
    → Optional: needed for /screenshot. Install with: npx playwright install chromium

Step 2 of 6: Installation Path
  Default: ~/.adjutant
  Custom path? [Enter to accept default]: _

Step 3 of 6: Identity Setup
  What should your agent be called? [adjutant]: _
  
  I'll now generate your soul.md (personality/values) and heart.md (priorities).
  This uses an LLM to tailor the agent to your needs.
  
  Describe what you want your agent to monitor and help with:
  > I need help tracking tasks, deadlines, and priorities across my projects.
  
  Token estimate: ~2,000 input + ~800 output (Haiku) ≈ $0.01
  Proceed? [Y/n]: _
  
  Generating soul.md... ✓
  Generating heart.md... ✓
  Review and edit these files anytime.

Step 4 of 6: Messaging — Telegram Setup
  Do you have a Telegram bot token? [y/N]: _
  
  Let me walk you through it:
  1. Open Telegram and search for @BotFather
  2. Send /newbot and follow the prompts
  3. Paste the bot token here: _
  
  Now I need your chat ID:
  1. Send any message to your new bot
  2. I'll check for it automatically...
  ✓ Found chat ID: <YOUR_CHAT_ID>
  
  Saved to .env ✓

Step 5 of 6: Features
  Enable news briefing? (fetches AI news daily) [y/N]: _
  Enable screenshot capability? (requires Playwright) [y/N]: _
  Enable usage tracking? [Y/n]: _

Step 6 of 6: Service Installation
  Platform detected: macOS
  
  Install Launch Agent for auto-start? [Y/n]: _
  ✓ Created ~/Library/LaunchAgents/adjutant.telegram.plist
  ✓ Loaded launch agent
  
  Install news briefing cron job (weekdays 8am)? [Y/n]: _
  ✓ Cron job installed

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ✅ Adjutant is online!
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Send /help to your Telegram bot to get started.
  
  Estimated monthly cost at typical usage:
  ┌──────────────────────────┬───────────┬──────────┐
  │ Operation                │ Frequency │ Cost/mo  │
  ├──────────────────────────┼───────────┼──────────┤
  │ Casual chat (Haiku)      │ 5/day     │ ~$3.00   │
  │ Pulse checks             │ 2/day     │ ~$0.60   │
  │ News briefing (Haiku)    │ 1/day     │ ~$1.50   │
  │ Deep reflect (Opus)      │ 1/week    │ ~$1.20   │
  ├──────────────────────────┼───────────┼──────────┤
  │ Total estimate           │           │ ~$6.30   │
  └──────────────────────────┴───────────┴──────────┘

  Config:  ~/.adjutant/adjutant.yaml
  Docs:    ~/.adjutant/README.md
```

### 5.2 The LLM-Driven Identity Generation

The wizard's Step 3 is the novel part. Instead of users writing `soul.md` and `heart.md` from scratch:

1. Ask the user what they want to monitor (free text)
2. Send that to Haiku with a meta-prompt
3. **Show a pre-calculated token estimate before calling the API**
4. Write the files, tell the user to review/edit

### 5.3 Token Pre-Calculation

The wizard should estimate tokens before every LLM call:

```bash
estimate_tokens() {
  local text="$1"
  # Rough approximation: 1 token ≈ 4 chars for English text
  local chars=${#text}
  echo $(( chars / 4 ))
}

estimate_cost() {
  local input_tokens="$1"
  local output_tokens="$2"
  local model="$3"
  
  case "$model" in
    *haiku*)  echo "scale=4; ($input_tokens * 0.25 + $output_tokens * 1.25) / 1000000" | bc ;;
    *sonnet*) echo "scale=4; ($input_tokens * 3 + $output_tokens * 15) / 1000000" | bc ;;
    *opus*)   echo "scale=4; ($input_tokens * 15 + $output_tokens * 75) / 1000000" | bc ;;
  esac
}
```

Show this estimate before every call:

```
Estimated: ~2,100 input tokens + ~800 output tokens
Model: Haiku → ~$0.001
Proceed? [Y/n]:
```

### 5.4 Re-Runnable Setup (Post-Install Repair)

The wizard must be safe to run on an existing installation. Running `adjutant setup` after install should detect what's already configured, skip those steps, and fix anything that's broken. This covers common issues that surface after git operations, OS updates, or manual tinkering:

- **File permissions** — ensure `adjutant` CLI is executable (`chmod +x`), `scripts/` has correct permissions (`chmod -R 700`)
- **PATH / shell alias** — check if `adjutant` is reachable from `$PATH`; if not, offer to add an alias to `~/.zshrc` or `~/.bashrc`
- **Missing directories** — recreate `state/`, `journal/`, `insights/`, `photos/`, `screenshots/` if absent
- **Credential check** — verify `.env` exists and contains non-empty `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` (don't re-prompt if already valid)
- **Dependency check** — re-run the prerequisites check (Step 1) and report anything newly missing
- **Service state** — report whether the listener is running, offer to start it if not
- **Crontab** — verify news briefing cron is installed if enabled in config

```
$ adjutant setup

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Adjutant — Setup Wizard
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Existing installation detected at ~/.adjutant

  Checking installation health...
    ✓ adjutant.yaml present
    ✓ .env present with valid credentials
    ✗ adjutant CLI not executable → fixed (chmod +x)
    ✗ adjutant not on PATH → added alias to ~/.zshrc
    ✓ scripts/ permissions OK
    ✓ All dependencies found
    ✓ state/ directory exists
    ✗ journal/ directory missing → created
    ✓ Listener running (PID 12345)
    ✓ News briefing cron installed

  All issues fixed. Adjutant is ready.
```

The key principle: **`adjutant setup` should always be the answer to "something isn't working."** It's the single command a user runs when things break, not just on first install.

---

## Part 6: Messaging Adaptor Interface

The key to making Adjutant backend-agnostic. Define a contract that any messaging backend must satisfy.

### 6.1 Adaptor Interface Contract

**File**: `scripts/messaging/adaptor.sh`

```bash
#!/bin/bash
# Messaging Adaptor Interface Contract
# Any backend (Telegram, Slack, Discord, CLI) must implement these functions.
#
# To create a new adaptor:
# 1. Create scripts/messaging/<backend>/
# 2. Implement all REQUIRED functions below
# 3. Implement optional functions if supported
# 4. Set messaging.backend in adjutant.yaml
# 5. See docs/adaptor_guide.md for complete documentation

# ===== REQUIRED FUNCTIONS =====

# Send a text message to the user
# Args: $1 = message text, $2 = optional reply-to message ID
# Returns: 0 on success, 1 on failure
msg_send_text() {
  echo "ERROR: msg_send_text() not implemented by adaptor" >&2
  return 1
}

# Send a photo/image to the user
# Args: $1 = file path to image, $2 = optional caption
# Returns: 0 on success, 1 on failure
msg_send_photo() {
  echo "ERROR: msg_send_photo() not implemented by adaptor" >&2
  return 1
}

# Start the message polling/listening loop
# This should run indefinitely, calling msg_dispatch() for each received message
# The loop should respect the KILLED and PAUSED lockfiles (checked by dispatcher)
msg_start_listener() {
  echo "ERROR: msg_start_listener() not implemented by adaptor" >&2
  return 1
}

# Stop the listener gracefully
# Returns: 0 on success, 1 on failure
msg_stop_listener() {
  echo "ERROR: msg_stop_listener() not implemented by adaptor" >&2
  return 1
}

# ===== OPTIONAL FUNCTIONS =====

# Add a reaction (emoji) to a message
# Args: $1 = message ID, $2 = emoji
# Default: no-op (returns 0)
msg_react() {
  return 0
}

# Show/hide typing indicator
# Args: $1 = start|stop
# Default: no-op (returns 0)
msg_typing() {
  return 0
}

# Validate sender identity
# Args: $1 = sender ID (adaptor-specific)
# Returns: 0 if authorized, 1 if not
# Default: allow all (returns 0)
msg_authorize() {
  return 0
}

# Get the authenticated user ID
# Returns: user ID string on stdout
msg_get_user_id() {
  echo "unknown"
}
```

### 6.2 Dispatcher Interface

**File**: `scripts/messaging/dispatch.sh` (NEW — backend-agnostic)

The command dispatch logic moves here, independent of Telegram:

```bash
#!/bin/bash
# scripts/messaging/dispatch.sh
# Backend-agnostic command dispatcher
# Called by msg_start_listener() when a new message arrives

dispatch_message() {
  local text="$1"
  local message_id="$2"
  local from_id="$3"
  
  # Check authorization
  if ! msg_authorize "$from_id"; then
    adj_log messaging "Rejected unauthorized sender: $from_id"
    return
  fi
  
  # Reflect confirmation flow
  if [ -f "${ADJ_DIR}/state/pending_reflect" ]; then
    if [ "$text" = "/confirm" ]; then
      cmd_reflect_confirm "$message_id"
    else
      rm -f "${ADJ_DIR}/state/pending_reflect"
      msg_send_text "No problem — I've cancelled the reflection." "$message_id"
      adj_log messaging "Reflect cancelled"
    fi
    return
  fi
  
  # Command dispatch
  case "$text" in
    /status)        cmd_status "$message_id" ;;
    /pause)         cmd_pause "$message_id" ;;
    /resume)        cmd_resume "$message_id" ;;
    /kill)          cmd_kill "$message_id" ;;
    /pulse)         cmd_pulse "$message_id" ;;
    /restart)       cmd_restart "$message_id" ;;
    /reflect)       cmd_reflect_request "$message_id" ;;
    /help)          cmd_help "$message_id" ;;
    /start)         cmd_help "$message_id" ;;
    /model)         cmd_model "" "$message_id" ;;
    /model\ *)      cmd_model "${text#/model }" "$message_id" ;;
    /screenshot\ *) cmd_screenshot "${text#/screenshot }" "$message_id" ;;
    /screenshot)    msg_send_text "Please provide a URL. Example: /screenshot https://example.com" "$message_id" ;;
    *)
      # Natural language conversation
      adj_log messaging "Chat message from $from_id: ${text:0:50}..."
      msg_typing start
      local reply
      reply="$(bash "${ADJ_DIR}/scripts/messaging/telegram/chat.sh" "$text" 2>>"${ADJ_DIR}/state/adjutant.log")" || true
      msg_typing stop
      if [ -n "$reply" ]; then
        msg_send_text "$reply" "$message_id"
      else
        msg_send_text "I ran into a problem getting a response. Try again in a moment." "$message_id"
      fi
      ;;
  esac
}

dispatch_photo() {
  local from_id="$1"
  local message_id="$2"
  local file_path="$3"
  local caption="$4"
  
  # Check authorization
  if ! msg_authorize "$from_id"; then
    adj_log messaging "Rejected photo from unauthorized sender: $from_id"
    return
  fi
  
  adj_log messaging "Processing photo: $file_path"
  msg_react "$message_id"
  msg_typing start
  
  local vision_reply
  vision_reply="$(bash "${ADJ_DIR}/scripts/capabilities/vision/vision.sh" "$file_path" "$caption" 2>>"${ADJ_DIR}/state/adjutant.log")"
  
  msg_typing stop
  
  if [ -n "$vision_reply" ]; then
    msg_send_text "$vision_reply" "$message_id"
  else
    msg_send_text "Photo saved but vision analysis failed. Try again." "$message_id"
  fi
}
```

The Telegram adaptor sources this and calls `dispatch_message` / `dispatch_photo`.

---

## Part 7: Breaking Up the 660-Line Listener

The current `telegram_listener.sh` becomes 5 focused files under `scripts/messaging/telegram/`:

| New File | Lines (est.) | Responsibility |
|----------|-------------|----------------|
| `listener.sh` | ~80 | Poll loop, update parsing, dispatch to `commands.sh` or `chat.sh` |
| `commands.sh` | ~200 | All `/command` handlers: status, pause, pulse, reflect, model, etc. |
| `chat.sh` | ~100 | Natural language routing through OpenCode |
| `send.sh` | ~80 | `msg_send_text()`, `msg_send_photo()`, `msg_react()`, typing indicators |
| `photos.sh` | ~80 | Photo download, storage, vision routing |

### 7.1 The Thin Listener

**File**: `scripts/messaging/telegram/listener.sh`

```bash
#!/bin/bash
# Telegram adaptor — polling loop only (thin dispatcher)

set -euo pipefail

source "${ADJ_DIR}/scripts/common/paths.sh"
source "${ADJ_DIR}/scripts/common/env.sh"
source "${ADJ_DIR}/scripts/common/logging.sh"
source "${ADJ_DIR}/scripts/common/lockfiles.sh"

source "${ADJ_DIR}/scripts/messaging/adaptor.sh"
source "${ADJ_DIR}/scripts/messaging/telegram/send.sh"
source "${ADJ_DIR}/scripts/messaging/telegram/photos.sh"
source "${ADJ_DIR}/scripts/messaging/dispatch.sh"

check_killed

TELEGRAM_BOT_TOKEN="$(get_credential TELEGRAM_BOT_TOKEN)"
TELEGRAM_CHAT_ID="$(get_credential TELEGRAM_CHAT_ID)"

OFFSET_FILE="${ADJ_DIR}/state/telegram_offset"
OFFSET=0
[ -f "${OFFSET_FILE}" ] && OFFSET="$(cat "${OFFSET_FILE}")"

adj_log telegram "Listener started (offset=$OFFSET)"
msg_send_text "I'm online and ready. Send /help if you'd like to see what I can do."

while true; do
  if [ -f "${ADJ_DIR}/KILLED" ]; then
    adj_log telegram "KILLED lockfile detected. Stopping listener."
    break
  fi
  
  # Poll Telegram
  resp="$(curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getUpdates?offset=${OFFSET}&timeout=2&allowed_updates=%5B%22message%22%5D")"
  
  # Parse updates and dispatch
  python3 << PYEOF
import json
resp = json.loads('''${resp}''')
if not resp.get('ok'):
  exit(0)
for update in resp.get('result', []):
  msg = update.get('message', {})
  chat_id = msg.get('chat', {}).get('id')
  msg_id = msg.get('message_id')
  
  # Text message
  if msg.get('text'):
    print(f"TEXT|{update['update_id']}|{chat_id}|{msg_id}|{msg['text']}")
  
  # Photo message
  if msg.get('photo'):
    photos = msg['photo']
    if photos:
      print(f"PHOTO|{update['update_id']}|{chat_id}|{msg_id}|{photos[-1]['file_id']}|{msg.get('caption', '')}")
PYEOF
  
  # Dispatch (to be implemented)
  # ... process each line and call dispatch_message/dispatch_photo
  
  sleep 1
done

adj_log telegram "Listener stopped"
```

This is **much thinner** than the original 660-line monolith. It delegates to backend-agnostic dispatchers.

---

## Part 8: Additional Proposals

### 8.1 Journal Rotation & Search

The security assessment notes journals grow unbounded. Add:

**File**: `scripts/observability/journal_rotate.sh`

```bash
#!/bin/bash
# Archive/compress journal entries older than threshold

ADJ_JOURNAL_DIR="${ADJ_DIR}/journal"
ARCHIVE_DIR="${ADJ_DIR}/journal/.archive"
DAYS_TO_KEEP=30

mkdir -p "${ARCHIVE_DIR}"

# Find files older than 30 days
find "${ADJ_JOURNAL_DIR}" -maxdepth 1 -name "*.md" -type f -mtime +${DAYS_TO_KEEP} | while read file; do
  gzip "$file" -c > "${ARCHIVE_DIR}/$(basename "$file").gz"
  rm "$file"
  adj_log observability "Archived: $(basename "$file")"
done
```

And simple search:

```bash
adjutant search "speaker confirmation"
```

### 8.2 Health Check Endpoint

**File**: `scripts/observability/healthcheck.sh`

Written every 60s by the listener:

```bash
#!/bin/bash
# Generate status JSON for external monitoring

{
  "status": "running",
  "uptime_seconds": 3600,
  "last_message_at": "2026-02-26T10:30:00Z",
  "listener_pid": 12345,
  "paused": $([ -f "${ADJ_DIR}/PAUSED" ] && echo "true" || echo "false"),
  "killed": $([ -f "${ADJ_DIR}/KILLED" ] && echo "true" || echo "false"),
  "version": "1.0.0"
} > "${ADJ_DIR}/state/healthcheck.json"
```

This enables future monitoring (Prometheus scraping, uptime checks, a web dashboard).

### 8.3 Plugin System for Capabilities

Screenshot, vision, and news are all **optional capabilities**. Formalize this:

```
scripts/capabilities/
├── _registry.sh          # Discovers and loads installed capabilities
├── screenshot/
│   ├── capability.yaml
│   └── screenshot.sh
├── vision/
│   ├── capability.yaml
│   └── vision.sh
└── news/
    ├── capability.yaml
    ├── briefing.sh
    ├── fetch.sh
    └── analyze.sh
```

**File**: `scripts/capabilities/screenshot/capability.yaml`

```yaml
name: screenshot
display_name: "Website Screenshots"
description: "Take full-page website screenshots and send them to messaging"
version: "1.0"
commands:
  - name: "/screenshot"
    usage: "/screenshot <url>"
    description: "Take a full-page screenshot and send it"
dependencies:
  - npx playwright
requires_messaging: true
```

The wizard's Step 5 becomes: "Which capabilities do you want to enable?" and it reads from `capabilities/*/capability.yaml`.

### 8.4 Dry-Run / Simulation Mode

For development and debugging:

```yaml
# adjutant.yaml
debug:
  dry_run: false        # Process but don't send/call
  verbose_logging: false
  mock_llm: false       # Return canned responses instead of calling API
```

### 8.5 Multi-Instance Support

The `adjutant.yaml` `instance.name` field enables running multiple agents:

```
~/.adjutant/           # Work instance
~/.adjutant-personal/  # Personal instance
```

Each has its own soul, heart, registry, and messaging config. The wizard supports:

```bash
adjutant setup --instance personal --path ~/.adjutant-personal
```

### 8.6 `adjutant` CLI Entrypoint

Instead of remembering script paths:

```bash
$ adjutant setup          # Run wizard
$ adjutant start          # Start all services
$ adjutant stop           # Stop all services
$ adjutant restart        # Restart
$ adjutant status         # System status
$ adjutant kill           # Emergency shutdown
$ adjutant logs           # Tail the log
$ adjutant search "term"  # Search journals
$ adjutant config         # Edit adjutant.yaml
$ adjutant doctor         # Check health, dependencies, permissions
```

This is a thin bash script that dispatches to the appropriate script in the new directory structure.

### 8.7 Security Fixes as Part of the Refactor

Since you're touching every script, fix the known vulnerabilities:

- **Python injection in `fmt_ts()`** → replaced by pure bash/date in `common/logging.sh`
- **Log injection** → sanitized in `common/logging.sh` (strip newlines)
- **Rate limiting** → add to the listener: max 10 messages/minute, exponential backoff
- **Prompt injection guard in agent prompt** → add to `adjutant.md` (security assessment flagged as missing)
- **Directory permissions** → ensure `chmod 700 ~/.adjutant/scripts`

---

## Part 9: Migration Path (Full Backward Compatibility)

Since you need full backward compatibility:

### Phase 0: Preparation (no behavior change)

1. Add `adjutant.yaml` that reads existing config locations (`.env`, `news_config.json`, hardcoded values)
2. Add `scripts/common/` and have new utilities coexist with old scripts
3. Add `adjutant` CLI entrypoint that wraps existing scripts
4. ✅ Existing `~/.adjutant/` works exactly as before

### Phase 1: Restructure (move files, update paths)

1. Move `soul.md`, `heart.md`, `registry.md` → `identity/` (with symlinks at old locations)
2. Create new directory structure under `scripts/`
3. Old scripts become thin wrappers that source new locations
4. All existing paths still work via symlinks
5. ✅ Existing workflows unaffected

### Phase 2: Refactor (rewrite internals)

1. Break up `telegram_listener.sh` into 5 files
2. Extract shared utilities to `scripts/common/`
3. Eliminate all hardcoded `~/.adjutant` paths
4. Eliminate all embedded Python snippets (replace with pure bash + common utilities)
5. Implement messaging adaptor interface
6. ✅ Behavior unchanged, code is cleaner

### Phase 3: Enhance (new features)

1. ✅ Build setup wizard (`scripts/setup/` — wizard, repair, 6 step scripts, helpers)
2. ✅ Add `adjutant` CLI (setup subcommand added)
3. Add plugin/capability system
4. ✅ Add journal rotation (`scripts/observability/journal_rotate.sh` — archives journal, news, rotates logs)
5. ✅ Add health check (repair mode with prompt-before-fix)
6. Write adaptor guide documentation
7. ✅ New capabilities available

### Phase 4: Knowledge Base System (sub-agent architecture)

Build a knowledge base (KB) system where each KB is an isolated workspace with its own
OpenCode sub-agent. Adjutant acts as a router — auto-detecting which KB is relevant to a
user's question, spawning a scoped `opencode run` session against that KB, and synthesizing
the sub-agent's answer with its own personality before replying.

#### Architecture

```
User → Telegram → Adjutant agent (--dir ADJ_DIR)
                        ↓
              Reads KB registry from knowledge_bases/registry.yaml
              Decides: "this question is about ml-papers"
                        ↓
              Runs: opencode run --agent kb --dir <kb-path> --format json "query"
                        ↓
              KB sub-agent answers (scoped to its own dir, can't see ADJ_DIR)
                        ↓
              Adjutant reads KB answer, synthesizes with soul.md personality, replies
```

**Isolation model**: Each KB is a separate OpenCode workspace. The KB agent runs with
`--dir <kb-path>`, scoping it to that directory only. The KB has its own `opencode.json`
(permissions) and `.opencode/agents/kb.md` (agent definition). Adjutant's agent never
directly reads KB files — it communicates exclusively via OpenCode process invocation.

#### KB Registry (`knowledge_bases/registry.yaml`)

```yaml
knowledge_bases:
  - name: ml-papers
    description: "Machine learning research papers and notes on transformer architectures"
    path: /Users/edvard/research/ml-papers
    model: inherit                    # inherit | anthropic/claude-haiku-4-5 | etc.
    access: read-only                 # read-only | read-write
    created: 2026-02-27
```

The `description` field drives auto-detection — Adjutant's agent reads the registry and
uses name + description to decide which KB is relevant to a given question.

#### KB Scaffold (generated per KB)

```
<kb-path>/
├── opencode.json              # Permissions (deny .env-like patterns)
├── .opencode/
│   └── agents/
│       └── kb.md              # Sub-agent definition
├── kb.yaml                    # KB metadata (name, description, model, access)
└── docs/                      # User's content goes here
    └── README.md              # Placeholder explaining how to use the KB
```

#### Design Decisions

| Decision | Choice |
|----------|--------|
| KB location | Anywhere on filesystem — registry stores absolute paths |
| KB scope | Domain knowledge (docs, notes, references) |
| Agent communication | Direct OpenCode invocation (`opencode run --agent kb --dir <kb-path>`) |
| Auto-detection | Registry metadata matching with fallback ("which KB did you mean?") |
| Folder structure | Minimal (kb.yaml, opencode.json, .opencode/agents/kb.md, docs/) |
| Write access | Configurable per KB (default: read-only) |
| Existing directories | Supported — auto-detect content types and tailor agent definition |
| Model | Configurable per KB, default inherits from Adjutant's current model |
| Telegram | Both /kb commands and natural language auto-detection |
| Creation UX | Interactive wizard (default), `--quick` flag for one-liner scaffold |

#### Implementation Steps

**Phase A — Foundation (scaffolding + registry)**

1. ✅ Create `knowledge_bases/` directory and empty `registry.yaml`
2. ✅ Create `templates/kb/` — scaffold templates (opencode.json, kb.md agent, kb.yaml, docs/README.md)
3. ✅ Create `scripts/capabilities/kb/manage.sh` — core operations: create scaffold, register/unregister, list, info; includes auto-detect for existing directories
4. ✅ Create `scripts/setup/steps/kb_wizard.sh` — interactive wizard using `helpers.sh` prompts, optional LLM-enhanced agent definition generation

**Phase B — Query pipeline**

5. ✅ Create `scripts/capabilities/kb/query.sh` — spawns `opencode run --agent kb --dir <kb-path>`, parses NDJSON, returns text; handles model resolution (inherit vs explicit)
6. ✅ Update `.opencode/agents/adjutant.md` — add KB routing instructions: read registry, detect relevance, call query.sh, synthesize answer
7. ✅ Update `identity/soul.md` — add `knowledge_bases/` to architecture section

**Phase C — CLI + Telegram integration**

8. ✅ Update `adjutant` CLI — add `kb` subcommand dispatching to manage.sh (create, list, remove, info, query)
9. ✅ Update `scripts/messaging/telegram/commands.sh` — add `/kb` command handler for list/query from Telegram

**Phase D — Tests**

10. ✅ Create `tests/unit/kb.bats` — scaffold generation, registry CRUD, template rendering, auto-detect (38 tests)
11. ✅ Create `tests/integration/kb.bats` — end-to-end: create KB, query (mocked opencode), CLI routing, /kb command (18 tests)
12. ✅ Run full test suite — 529/529 pass, no regressions

#### Files to Create

| File | Description |
|------|-------------|
| `knowledge_bases/registry.yaml` | KB registry (starts empty) |
| `templates/kb/opencode.json` | Template for KB permissions |
| `templates/kb/agents/kb.md` | Template for KB agent definition |
| `templates/kb/kb.yaml` | Template for KB metadata |
| `templates/kb/docs/README.md` | Placeholder docs |
| `scripts/capabilities/kb/manage.sh` | KB CRUD operations |
| `scripts/capabilities/kb/query.sh` | Query a KB sub-agent |
| `scripts/setup/steps/kb_wizard.sh` | Interactive KB creation wizard |
| `tests/unit/kb.bats` | Unit tests |
| `tests/integration/kb.bats` | Integration tests |

#### Files to Modify

| File | Change |
|------|--------|
| `.opencode/agents/adjutant.md` | Add KB routing instructions |
| `identity/soul.md` | Add knowledge_bases/ to architecture section |
| `adjutant` | Add `kb` subcommand |
| `scripts/messaging/telegram/commands.sh` | Add `/kb` command handler |

---

## Part 10: What NOT to Change

Some things are working well and should be preserved exactly:

1. **The soul/heart/registry conceptual model** — elegant. The three-layer identity architecture is the best part of Adjutant.
2. **Append-only journal** — correct pattern for an observability system.
3. **Cheap-then-expensive escalation flow** — Haiku triages, Sonnet escalates, Opus reflects. Smart cost management.
4. **Human-in-the-loop for Opus** — the `/confirm` pattern before expensive operations.
5. **The security posture** — env parsing via grep, chat ID validation, no shell execution of message content. Good practices.
6. **OpenCode as the LLM backend** — it handles auth, rate limiting, session management. Don't reimplement.

---

## Summary: Priority Order

If implementing this plan, here's the recommended order:

| Priority | Task | Impact | Effort | Dependencies |
|----------|------|--------|--------|--------------|
| **1** | Create `scripts/common/` shared utilities | Fixes security bugs, eliminates duplication | Medium | None |
| **2** | Unify paths (eliminate hardcoded `~/.adjutant`) | Required for install-anywhere support | Low | Phase 1 |
| **3** | Add `adjutant.yaml` unified config | Single source of truth | Medium | Phase 1 |
| **4** | Break up `telegram_listener.sh` | Codebase maintainability & testability | High | Phase 1 |
| **5** | Implement messaging adaptor interface | Enables other backends | Medium | Phase 2 |
| **6** | Build the `adjutant` CLI entrypoint | User experience | Low | Phase 1 |
| **7** | Build the setup wizard | First-run experience for new users | High | ✅ Done |
| **8** | Restructure directories | Organizational clarity | Low | Phase 1 |
| **9** | Plugin/capability system | Extensibility | Medium | Phase 2 |
| **10** | Knowledge base system (sub-agent architecture) | Domain expertise + isolation | High | ✅ Done |
| **11** | Multi-instance support | Power user feature | Low | Phase 2 |

**Phases 1–3 get you from "monolith" to "modular."**  
**Phase 4 adds the knowledge base sub-agent architecture.**  
**Phase 5+ adds remaining "framework" features.**

---

## Phase 5: Generalization & Public Distribution (Completed)

### Goal

Make Adjutant usable by anyone — not just the original author. Separate user-specific
files from project files, add a curl installer, a setup wizard with conditional flow
(Telegram optional), and a self-update mechanism.

### 5.1 Root Marker & Config Separation

**Problem**: `adjutant.yaml` served double duty as both the root marker and user config.
Since config contains user-specific values, it can't be tracked in git for a public repo.

**Solution**:
- Created `.adjutant-root` as the new root marker (empty file, tracked in git)
- Updated `scripts/common/paths.sh` to check for `.adjutant-root` first, then fall back
  to `adjutant.yaml` for backward compatibility
- `adjutant.yaml` is now fully generated by the wizard, gitignored
- `adjutant.yaml.example` tracked as a reference template
- `scripts/setup/steps/install_path.sh` detects both markers and creates `.adjutant-root`
  on fresh installs

**Files created**: `.adjutant-root`, `adjutant.yaml.example`
**Files modified**: `scripts/common/paths.sh`, `scripts/setup/steps/install_path.sh`

### 5.2 Gitignore User-Specific Files

**Problem**: Identity files (`soul.md`, `heart.md`, `registry.md`), `adjutant.yaml`, and
`news_config.json` contain user-specific content that shouldn't be in a public repo.

**Solution**:
- Added all 5 files to `.gitignore`
- Ran `git rm --cached` to untrack them (files remain on disk)
- Created `.example` templates for each:
  - `identity/soul.md.example` — generic personality template
  - `identity/heart.md.example` — generic priorities template
  - `identity/registry.md.example` — empty registry scaffold
  - `news_config.json.example` — default news config
- Also gitignored `KILLED` lockfile and `knowledge_bases/` data directories

**Files created**: `identity/soul.md.example`, `identity/heart.md.example`,
`identity/registry.md.example`, `news_config.json.example`
**Files modified**: `.gitignore`

### 5.3 Wizard Conditional Flow (Telegram Optional)

**Problem**: The wizard assumed Telegram was mandatory. Users who just want CLI + OpenCode
web interface had no valid path.

**Solution**: CLI-only mode is now a first-class configuration:

- **messaging.sh** rewritten: asks "Enable Telegram?" first. If no, exports
  `WIZARD_MESSAGING_ENABLED=false` and `WIZARD_MESSAGING_BACKEND=none`, skips token/chat
  ID setup entirely.
- **features.sh** rewritten: gates vision capability on messaging (requires photo
  delivery). Screenshot and news still work in CLI-only mode — screenshots save to disk,
  news writes to journal instead of sending via Telegram. Sets `delivery.telegram: false`
  in `news_config.json` when no messaging.
- **service.sh** rewritten: skips Telegram listener service when no messaging. Offers
  OpenCode web server as a standalone service (launchd on macOS, systemd on Linux).
  Service installation functions are now parameterized by type.
- **wizard.sh** completion display: shows CLI-only cost estimates (lower — no chat costs)
  and appropriate next-step instructions.

**Design decision**: `messaging.backend: "none"` is the default in the generated
`adjutant.yaml`. Step 4 updates it to `"telegram"` only if the user opts in.

**Files modified**: `scripts/setup/steps/messaging.sh`, `scripts/setup/steps/features.sh`,
`scripts/setup/steps/service.sh`, `scripts/setup/wizard.sh`

### 5.4 Curl Installer & GitHub Release Workflow

**Problem**: Installing Adjutant required `git clone`, which assumes git knowledge and
makes updates manual.

**Solution — Remote installer** (`scripts/setup/install.sh`):
- Format: `curl -fsSL https://raw.githubusercontent.com/anomalyco/adjutant/main/scripts/setup/install.sh | bash`
- Checks prerequisites (bash 4+, curl, jq, opencode)
- Prompts for install directory (default: `~/.adjutant`)
- Downloads tarball from GitHub releases API (latest release)
- Extracts to install path
- Runs the setup wizard automatically
- No git required for end users

**Solution — GitHub Actions workflow** (`.github/workflows/release.yml`):
- Triggered on tag push (`v*`)
- Builds tarball excluding user-specific files (adjutant.yaml, identity files,
  news_config.json, journal/, state/, etc.)
- Attaches tarball + standalone `install.sh` to GitHub release

**Files created**: `scripts/setup/install.sh`, `.github/workflows/release.yml`

### 5.5 Self-Update Mechanism

**Problem**: No way to update Adjutant after install without manual file replacement.

**Solution** (`scripts/lifecycle/update.sh`):
- `adjutant update` checks GitHub releases API for latest version
- Compares with local `VERSION` file (semver comparison in pure bash)
- Downloads tarball, backs up current `scripts/` and `templates/` directories
- Extracts new files, preserving all user-specific files (identity, config, journal,
  state, knowledge bases)
- Runs `adjutant doctor` after update to verify health
- `adjutant update --check` for dry-run version check

**Files created**: `VERSION` (set to `5.0.0`), `scripts/lifecycle/update.sh`
**Files modified**: `adjutant` (added `update` subcommand)

### Architecture Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Root marker | `.adjutant-root` (empty file) | Separates marker from config; trivial to create |
| Config generation | Wizard generates `adjutant.yaml` | User-specific values can't be in git |
| Telegram optional | `messaging.backend: "none"` | CLI + OpenCode web is a valid standalone mode |
| Install method | Tarball from GitHub releases | No git required; clean separation of release artifacts |
| Update strategy | Download + backup + extract | Preserves user files; rollback via backup |
| Version file | `VERSION` in repo root | Simple; read by update.sh and release workflow |
| Default repo | `anomalyco/adjutant` | Hardcoded in install.sh/update.sh with env var override |

---

## Next Steps

Phases 1–4 and Phase 5 are complete. The remaining items are:

1. **Phase 6 — Documentation** — comprehensive `docs/` directory (adaptor guide, plugin guide, architecture deep-dive, troubleshooting)
2. **Multi-instance support** — allows running multiple Adjutant instances with separate configs
3. **Tier 3 system tests** — process isolation tests for lifecycle scripts (see `docs/testing.md`)
4. **Additional messaging backends** — Slack, Discord, etc. via the adaptor interface
5. **Setup wizard revamp — LaunchAgent plist hardening** — the wizard's Step 6 currently generates a basic plist with `KeepAlive: true`. The key things to ensure:
   - `KeepAlive: true` (unconditional) is correct — the listener must always be restarted since it is a long-running service. `SuccessfulExit: false` must NOT be used; the listener can exit cleanly (exit 0) in certain states and must be restarted in those cases too.
   - `ThrottleInterval` should be at least 30 seconds to limit blast radius during any crash loops
   - The listener must never send a startup notification itself — only `startup.sh` sends "I'm online". This prevents notification spam when launchd restarts the listener after a crash.

The framework is now publicly distributable with a curl installer, optional Telegram,
setup wizard, self-update mechanism, and knowledge base sub-agent architecture.

---

**End of ADJUTANT_FRAMEWORK_PLAN.md**
