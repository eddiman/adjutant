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
    default_model: "anthropic/claude-haiku-4-5"
    chat_timeout_seconds: 240           # LLM response timeout per message
    rate_limit:
      messages_per_minute: 10
      window_seconds: 60               # rolling window for rate limiting
      backoff_exponential: true

llm:
  backend: "opencode"
  models:
    cheap: "anthropic/claude-haiku-4-5"     # routine chat and triage
    medium: "anthropic/claude-sonnet-4-6"   # escalations
    expensive: "anthropic/claude-opus-4-5"  # /confirm only
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
  search:
    enabled: false                    # requires BRAVE_API_KEY in .env
  usage_tracking:
    enabled: false

heartbeat:
  enabled: false                    # set to true, then enable autonomous_pulse/review in schedules:

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

debug:
  dry_run: false
  verbose_logging: false
```

### Key settings explained

**`messaging.backend`** — Set to `"telegram"` to use the Telegram adaptor. Set to `"none"` for CLI-only mode (no listener, you call scripts directly).

**`messaging.telegram.session_timeout_seconds`** — Adjutant maintains conversational context within a session window. After this much inactivity, the next message starts a fresh context. Default is 2 hours (7200s).

**`llm.models`** — Three tiers. Adjutant uses `cheap` by default for chat and triage, escalates to `medium` for reasoning, analysis, and `/reflect`, and only uses `expensive` for `/confirm`. Default tiers: `cheap` = claude-haiku-4-5, `medium` = claude-sonnet-4-6, `expensive` = claude-opus-4-5. You can change these to any model supported by your OpenCode setup.

**`llm.caps`** — Token budget guardrails. These generate usage warnings but do not hard-block requests.

**`heartbeat.enabled`** — Master switch for autonomous pulse and review jobs. Set to `true` to enable, then also enable the corresponding `schedules:` entries: `adjutant schedule enable autonomous_pulse`.

**`schedules:`** — Registry of all scheduled jobs. Each entry maps to one crontab line. `enabled: true` installs the entry; `enabled: false` tracks it in the registry but removes it from crontab. Manage with `adjutant schedule` commands or edit this file and run `adjutant schedule sync`. See [Schedules](schedules.md) for the full guide.

**`notifications.max_per_day`** — Adjutant respects this limit when sending proactive notifications. It will batch and suppress rather than spam.

**`journal.log_max_size_kb`** — When `adjutant.log` exceeds this size, `adjutant rotate` will compress and rotate it. Default is 5MB.

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

## `opencode.json`

The OpenCode workspace configuration. This file controls what Adjutant's AI agent is allowed to read, write, and execute. It is generated by the setup wizard and you generally don't need to edit it.

The key section is the `permission` block. By default, external directory access is denied and `.env` is protected from direct reads (Adjutant reads credentials via `get_credential()` instead of sourcing the file):

```json
{
  "$schema": "https://opencode.ai/config.json",
  "permission": {
    "external_directory": "deny",
    "read": {
      "*": "allow",
      "**/.env": "deny",
      ".env": "deny"
    },
    "bash": {
      "*": "allow",
      "*cat .env": "deny",
      "env": "deny",
      "printenv": "deny"
    }
  }
}
```

The `external_directory: deny` prevents the agent from accessing files outside the Adjutant directory. The bash deny rules prevent common `.env` leakage patterns. You generally don't need to edit this file — the setup wizard maintains it.

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
