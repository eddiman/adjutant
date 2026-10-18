# Configuration

Adjutant is configured through three types of files: `adjutant.yaml` for non-secret settings, `.env` for credentials, and the identity files (`soul.md`, `heart.md`, `registry.md`) for who Adjutant is and what it pays attention to.

All of these files are user-specific and **gitignored** — they live on your machine only and are never committed to version control. Example templates (`*.example`) are provided for each.

---

## `adjutant.yaml`

The main configuration file. Copy the example to get started:

```bash
cp adjutant.yaml.example adjutant.yaml
```

This file contains every non-secret setting for your instance. A full annotated example:

```yaml
instance:
  name: "adjutant"

identity:
  soul: "identity/soul.md"
  heart: "identity/heart.md"
  registry: "identity/registry.md"

messaging:
  backend: "telegram"           # "telegram" or "none" (CLI-only)
  telegram:
    session_timeout_seconds: 7200       # 2h window for conversational context
    default_model: "cheap"             # tier name or explicit model ID
    chat_timeout_seconds: 240           # LLM response timeout per message
    rate_limit:
      messages_per_minute: 10
      window_seconds: 60               # rolling window for rate limiting
      backoff_exponential: true

llm:
  backend: "opencode"                       # "opencode" or "claude-cli"
  permission_mode: "skip"                   # Claude CLI only: "skip" or "allowlist"
  # allowed_tools: "Read,Glob,Grep,Edit,Write,Bash(*)"  # only used with permission_mode: "allowlist"
  models:
    cheap: "anthropic/claude-haiku-4-5"     # routine chat and triage
    medium: "anthropic/claude-sonnet-4-6"   # escalations
    expensive: "anthropic/claude-opus-4-6"  # /confirm only
  reasoning_effort:
    cheap: null                              # OpenCode only: passed as --variant
    medium: null
    expensive: null
  caps:
    session_tokens: 44000             # per-session token budget
    session_window_hours: 5           # rolling window for session tracking
    weekly_tokens: 350000             # weekly budget alert threshold

features:
  news:
    enabled: false                    # set to true and configure news_config.json
    config_path: "news_config.json"
  screenshot:
    enabled: false
  vision:
    enabled: false
    model: "cheap"                    # must be cheap|medium|expensive
  search:
    enabled: false                    # requires BRAVE_API_KEY in .env
  usage_tracking:
    enabled: false

# Scheduled jobs — managed by `adjutant schedule` commands
# Add new jobs with: adjutant schedule add
# Full docs: docs/guides/schedules.md
schedules:
  - name: "news_briefing"
    description: "Daily AI news digest"
    schedule: "0 8 * * 1-5"
    script: ".venv/bin/python -m adjutant news"
    log: "state/news_briefing.log"
    enabled: false

  - name: "autonomous_pulse"
    description: "Scheduled autonomous pulse check"
    schedule: "0 9,17 * * 1-5"
    script: ".venv/bin/python -m adjutant pulse"
    log: "state/pulse.log"
    enabled: false

  - name: "autonomous_review"
    description: "End-of-day review"
    schedule: "0 20 * * 1-5"
    script: ".venv/bin/python -m adjutant review"
    log: "state/review.log"
    enabled: false

platform:
  service_manager: "launchd"          # launchd (macOS) | systemd (Linux) | manual

notifications:
  max_per_day: 3
  quiet_hours:
    enabled: false
    start: "22:00"
    end: "07:00"

security:
  prompt_injection_guard: true
  rate_limiting: true

journal:
  retention_days: 30                  # archive journal entries older than this
  news_retention_days: 14
  log_max_size_kb: 5120               # rotate adjutant.log above 5MB

operations:
  enabled: false                      # route natural-language Telegram work durably
  debug: false                        # show operation IDs and status edits in Telegram
  worker_concurrency: 2               # maximum active operations
  poll_interval_seconds: 0.5
  delivery_max_attempts: 8
  delivery_retry_base_seconds: 2.0
  timeouts:
    acknowledgement_target_seconds: 2.0
    startup_seconds: 60
    connection_seconds: 30
    progress_warning_seconds: 90
    runtime_seconds: 1800             # operation ceiling, separate from legacy chat timeout
    cancellation_grace_seconds: 10
    lease_seconds: 90
  retention:
    completed_days: 30
    events_days: 14
    deliveries_days: 30
    backend_sessions_days: 30
  persistent_opencode:
    enabled: false                    # independent experiment flag
    idle_timeout_seconds: 1200
    startup_timeout_seconds: 30
    health_interval_seconds: 10
    restart_backoff_seconds: 5
    username: opencode
    soft_memory_mb: null
    hard_memory_mb: null

debug:
  dry_run: false
  verbose_logging: false
```

### Key settings explained

**`messaging.backend`** — Set to `"telegram"` to use the Telegram adaptor. Set to `"none"` for CLI-only mode (no listener, you call scripts directly).

**`messaging.telegram.session_timeout_seconds`** — Adjutant maintains conversational context within a session window. After this much inactivity, the next message starts a fresh context. Default is 2 hours (7200s).

**`llm.backend`** — Which LLM backend to use. `"opencode"` uses the OpenCode CLI with an Anthropic API key. `"claude-cli"` uses the Claude Code CLI with a Claude subscription. See [Backends](backends.md) for the full guide.

**`llm.permission_mode`** — Claude CLI only. `"skip"` (default) uses `--dangerously-skip-permissions` for non-interactive mode. `"allowlist"` uses `--allowedTools` with an explicit whitelist. Ignored when backend is `"opencode"`.

**`llm.models`** — Three tiers. Adjutant uses `cheap` by default for chat and triage, escalates to `medium` for reasoning, analysis, and `/reflect`, and only uses `expensive` for `/confirm`. Default tiers: `cheap` = claude-haiku-4-5, `medium` = claude-sonnet-4-6, `expensive` = claude-opus-4-6. You can change these to any model supported by your backend.

**`llm.reasoning_effort`** — Optional per-tier reasoning effort. On the OpenCode backend this is passed through as `opencode run --variant ...`. This is provider-specific, so only set values your selected model supports.

**`llm.caps`** — Token budget guardrails. These generate usage warnings but do not hard-block requests.

**`schedules:`** — Registry of all scheduled jobs. Each entry maps to one crontab line. `enabled: true` installs the entry; `enabled: false` tracks it in the registry but removes it from crontab. Manage with `adjutant schedule` commands or edit this file and run `adjutant schedule sync`. See [Schedules](schedules.md) for the full guide.

**`heartbeat.enabled`** — Legacy configuration retained for compatibility. It no longer controls scheduled work; use each schedule entry's `enabled` flag instead.

**`notifications.max_per_day`** — Adjutant respects this limit when sending proactive notifications. It will batch and suppress rather than spam.

**`journal.log_max_size_kb`** — When `adjutant.log` exceeds this size, `adjutant rotate` will compress and rotate it. Default is 5MB.

**`operations.enabled`** — Starts the supervised operation worker and routes natural-language messages, photos, pulse, review, tracked KB work, and the web dashboard's pulse/review actions through durable acceptance. The listener commits natural-language and photo operations together with the Telegram offset.

**`operations.debug`** — Shows automatic operation-ID acknowledgements and lifecycle status edits in Telegram. It defaults to `false`. The worker still sends `typing` while it runs and delivers the final reply when debug output is disabled. Explicit `/operations` and `/operation <id>` inspection remains available. Restart Adjutant after changing this flag.

**`operations.worker_concurrency`** — Limits active operations in the separate worker process. Conversation-session serialization and explicit dependencies can reduce actual parallelism below this ceiling.

**`operations.timeouts.runtime_seconds`** — Sets the maximum duration for a durable operation. This is separate from the legacy `messaging.telegram.chat_timeout_seconds` used when durable operations are disabled.

**`operations.timeouts.acknowledgement_target_seconds`** — Sets the observation target for committing a Telegram operation and, when debug output is enabled, sending its acknowledgement. Exceeding it produces a timing warning; it does not discard accepted work.

**`operations.timeouts.startup_seconds`** — Limits backend process creation before execution begins. A startup timeout is reported separately from the operation runtime ceiling.

**`operations.timeouts.connection_seconds`** — Limits a connect or reconnect attempt for transports that support attachment. The one-process-per-call transport does not open a separate backend connection.

**`operations.timeouts.progress_warning_seconds`** — Controls when a running operation records and delivers a quiet-progress warning. Quiet work continues; silence alone does not terminate it.

**`operations.timeouts.cancellation_grace_seconds`** — Controls how long the worker waits for cooperative backend cancellation before owned-process cleanup finishes.

**`operations.timeouts.lease_seconds`** — Sets how long a worker owns an operation without renewal. On restart, expired read-only work can be queued again. Work with uncertain external effects enters reconciliation instead of being replayed.

**`operations.delivery_max_attempts`** and **`delivery_retry_base_seconds`** — Control exponential retries for failed or ambiguous Telegram sends. Adjutant stores the complete result before it attempts delivery.

**`operations.retention.*`** — Sets independent ages for terminal operation results, event rows, delivery receipts, and Adjutant-owned OpenCode sessions. Session cleanup uses only session IDs recorded on Adjutant execution attempts. A failed session deletion protects its operation evidence for a later retry.

**`operations.persistent_opencode.enabled`** — Attaches OpenCode operation calls to an authenticated loopback `opencode serve` process. Adjutant records PID creation time before signalling the process, checks `/global/health`, uses the documented session abort endpoint on cancellation, and never replays an uncertain attached execution. This flag is independent from `operations.enabled` so the durable worker can run with one CLI process per call.

**`operations.persistent_opencode.idle_timeout_seconds`** — Stops an unused server after the configured interval. The next operation starts a new owned instance.

**`operations.persistent_opencode.soft_memory_mb`** and **`hard_memory_mb`** — Apply to the server and all descendants. The soft limit drains existing work; new assignments use an isolated CLI process until maintenance stops the drained server. The hard limit may stop the owned process group immediately; affected unknown or mutating operations require reconciliation. Leave the hard limit unset until representative nested-tool workloads establish a safe emergency threshold for the host.

---

## `.env`

Credentials only. Never put tokens in `adjutant.yaml`.

Copy the example:

```bash
cp .env.example .env
chmod 600 .env
```

Fill in your values:

```bash
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
TELEGRAM_CHAT_ID=123456789

# Optional — required for /search and the agent's web search tool
BRAVE_API_KEY=BSAxxxxxxxxxxxxxxxxxxxxxxx
```

The `.env` file is never `source`d directly — Adjutant uses grep-based extraction to read individual values by key. This prevents accidentally leaking all credentials into the environment.

**`BRAVE_API_KEY`** — Required for the `/search` Telegram command and for the Adjutant agent to look things up on the web. Get a free key (2,000 queries/month) at [api.search.brave.com](https://api.search.brave.com). The setup wizard will prompt for this during feature configuration.

### Backend environment variables

These are optional overrides for backend binary paths. They're set in `.env` or your shell environment, not in `adjutant.yaml`.

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENCODE_BIN` | auto-detected | Explicit path to the `opencode` binary |
| `CLAUDE_CODE_BIN` | auto-detected | Explicit path to the `claude` binary |

Adjutant auto-detects binaries from PATH. Only set these if the binary is installed in a non-standard location.

---

## Identity files

These three files define who Adjutant is and what it pays attention to. They are loaded into the agent's context on every conversation. The setup wizard generates initial versions; you edit them as your situation changes.

Copy the examples to get started:

```bash
cp identity/soul.md.example identity/soul.md
cp identity/heart.md.example identity/heart.md
cp identity/registry.md.example identity/registry.md
```

---

### `identity/soul.md` — Who Adjutant is

The stable core. This file rarely changes. It defines:

- **Identity** — what role Adjutant plays (aide, not decision-maker)
- **Personality** — tone, communication style, defaults
- **Values** — what to protect, what to prioritize, what to never do
- **Hard limits** — actions Adjutant must refuse regardless of instruction

Example:

```markdown
# Adjutant — Soul

**Identity**: Trusted aide. Never the decision-maker. Makes sure nothing slips.

**Personality**: Concise. Direct. Calm. Honest. One line if one line is enough.

**Values**: Protect focus time. No surprises. Accuracy over speed — don't guess, cite sources.

**Never**: edit project files autonomously · message anyone but [YOUR NAME] ·
notify more than 3x/day · auto-restart after KILLED lockfile.
```

**When to edit:** Rarely. Only when the fundamental character of the agent needs to change — not when your priorities shift. For priority changes, edit `heart.md`.

---

### `identity/heart.md` — What matters right now

Your current focus. Adjutant reads this on every heartbeat and chat. It should always be accurate.

```markdown
# Adjutant — Heart

**Last updated**: 2026-03-01

## Current Priorities

1. **Project A** — launch deadline March 15, sponsor confirmation still pending
2. **Project B** — board meeting prep, need draft agenda by Friday

## Active Concerns

- Project A: venue contract not signed
- Project B: three speakers haven't confirmed

## Quiet Zones

- Project C — on hold until April
```

**When to edit:** Whenever your focus shifts. After a deadline passes. When a new project becomes urgent. This is the highest-leverage file — Adjutant can only pay attention to what's in here.

Keep it to 1–3 priorities. If it grows beyond 3, something needs to be deferred.

---

### `identity/registry.md` — What Adjutant monitors

The list of projects Adjutant watches during heartbeats and pulse checks.

```markdown
# Adjutant — Project Registry

## Project Name

- **Path**: /absolute/path/to/your/project
- **Priority**: High
- **Type**: client work / community / research / etc.
- **Watch files**:
  - data/current.md
  - data/status.md
- **Agents**: kb-agent-name
- **Concerns**: deadline approaching, dependency blocked
```

Each entry tells Adjutant:
- Where to find the project on disk
- How important it is relative to others
- Which files to read during a pulse check
- What sub-agents (KB agents) are available
- What specific concerns to look for

**When to edit:** When you start monitoring a new project. When a project ends and should no longer be watched. When a project's priority changes.

---

## Workspace permissions

### OpenCode: `opencode.json`

When using the OpenCode backend, `opencode.json` controls what the AI agent is allowed to read, write, and execute. Key protections:

```json
{
  "permission": {
    "external_directory": "deny",
    "read": { "*": "allow", "**/.env": "deny", ".env": "deny" },
    "bash": { "*": "allow", "*cat .env": "deny", "env": "deny", "printenv": "deny" }
  }
}
```

### Claude CLI: `.claude/settings.json` + hooks

When using the Claude CLI backend, permissions are managed via `.claude/settings.json` and security hooks in `.claude/hooks/`:

- `block-env-access.sh` — blocks Bash commands that read `.env` files
- `block-env-read.sh` — blocks Read tool calls targeting `.env` files

These hooks fire even when `--dangerously-skip-permissions` is active, making them the primary defense for credential protection on the Claude CLI backend.

Both systems prevent the agent from accessing files outside the Adjutant directory and protect `.env` from direct reads. You generally don't need to edit these files — the setup wizard maintains them.

---

## Where things live

```
$ADJ_DIR/
├── adjutant.yaml        ← main config (gitignored)
├── .env                 ← credentials (gitignored)
├── opencode.json        ← workspace permissions
└── identity/
    ├── soul.md          ← stable identity (gitignored)
    ├── heart.md         ← current priorities (gitignored)
    └── registry.md      ← monitored projects (gitignored)
```

All four gitignored files have `*.example` counterparts in the same locations — these are committed and safe to share.
