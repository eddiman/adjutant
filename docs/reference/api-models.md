# API Model Suite Reference

Multi-provider model configuration for Adjutant. Goal: spread cost across providers instead of running 100% Anthropic.

---

## Architecture

Adjutant uses three model tiers defined in `adjutant.yaml` under `llm.models`:

| Tier | Purpose | Volume |
|------|---------|--------|
| `cheap` | Retrieval, formatting, notifications, triage, Telegram default | Highest |
| `medium` | Reasoning, analysis, signal generation, escalations | Medium |
| `expensive` | `/reflect` + `/confirm` only | Lowest |

### How tiers resolve

- **KB sub-agents** (`scripts/capabilities/kb/query.sh`) — `_resolve_model()` maps tier names from each KB's `kb.yaml` to the `adjutant.yaml` model strings. This is the only place tier names are resolved.
- **Telegram chat** — uses `state/telegram_model.txt` (set by `/model` command), falling back to `messaging.telegram.default_model`.
- **Health check** (`opencode.sh`) — hardcoded to `anthropic/claude-haiku-4-5`.
- **OpenCode TUI** — `.opencode/agents/adjutant.md` frontmatter `model:` field is the default, but always overridden at runtime by `--model` flag.

Any `provider/model-id` string works in all positions — passed verbatim to `opencode run --model`.

---

## Available Providers

Via OpenCode 1.2.24:

| Provider prefix | Description |
|----------------|-------------|
| `anthropic/` | Direct Anthropic API — full Claude lineup |
| `opencode/` | Zen (pay-as-you-go) — multi-vendor models at competitive rates |

### OpenCode Zen Model Catalogue

| Model | Input/1M | Output/1M | Cached/1M | Notes |
|-------|----------|-----------|-----------|-------|
| MiniMax M2.5 Free | Free | Free | Free | Free tier, rate-limited |
| Big Pickle | Free | Free | Free | Free tier |
| MiniMax M2.5 | $0.30 | $1.20 | $0.06 | |
| Qwen3 Coder 480B | $0.45 | $1.50 | — | Code-specialized |
| Gemini 3 Flash | $0.50 | $3.00 | $0.05 | |
| Kimi K2.5 | $0.60 | $3.00 | $0.10 | Strong reasoning |
| GPT-5 Nano | Free | Free | Free | Free tier |
| GPT-5 Mini | $0.25 | $2.00 | — | |
| GPT-5 | $1.25 | $10.00 | — | |
| GLM 5 | $1.00 | $3.20 | $0.20 | |
| Gemini 3 Pro | $2.00 | $12.00 | $0.20 | Strong reasoning |
| Claude Haiku 4.5 | $1.00 | $5.00 | $0.10 | Same as direct Anthropic |
| Claude Sonnet 4.6 | $3.00 | $15.00 | $0.30 | Same as direct Anthropic |
| Claude Opus 4.5/4.6 | $5.00 | $25.00 | $0.50 | Same as direct Anthropic |

### OpenAI (via Zen)

| Model | Input/1M | Output/1M |
|-------|----------|-----------|
| GPT-5 Nano | $0.05 | $0.40 |
| GPT-5 Mini | $0.25 | $2.00 |
| GPT-5 | $1.25 | $10.00 |
| GPT-5.1 | $1.25 | $10.00 |
| GPT-5.2 | $1.75 | $14.00 |
| GPT-5.4 | $2.50 | $15.00 |

---

## Chosen Model Suite

### Tier assignments

| Tier | Model | Provider | Input/1M | Output/1M | Rationale |
|------|-------|----------|----------|-----------|-----------|
| `cheap` | Kimi K2.5 | `opencode/kimi-k2.5` | $0.60 | $3.00 | 40% cheaper than Haiku; strong reasoning; highest-volume tier = biggest savings |
| `medium` | Gemini 3 Pro | `opencode/gemini-3-pro` | $2.00 | $12.00 | 33% cheaper input than Sonnet; competitive analysis quality |
| `expensive` | Claude Opus 4.5 | `anthropic/claude-opus-4-5` | $5.00 | $25.00 | Low volume; reliability anchor for /reflect + /confirm |

### Other model assignments

| Use case | Model | Rationale |
|----------|-------|-----------|
| Telegram default | `opencode/kimi-k2.5` | Same as cheap tier — most chat is lightweight |
| OpenCode TUI default | `anthropic/claude-sonnet-4-6` | Best balance of speed/quality/cost for interactive dev work |
| Health check probe | `anthropic/claude-haiku-4-5` | Hardcoded in `opencode.sh` — not configurable via YAML |

### Cost comparison vs all-Anthropic

| Tier | Before (Anthropic) | After (Multi-provider) | Savings |
|------|-------------------|----------------------|---------|
| cheap (input) | $1.00/1M | $0.60/1M | 40% |
| cheap (output) | $5.00/1M | $3.00/1M | 40% |
| medium (input) | $3.00/1M | $2.00/1M | 33% |
| medium (output) | $15.00/1M | $12.00/1M | 20% |
| expensive | unchanged | unchanged | 0% |

The cheap tier dominates token volume, so the 40% reduction there drives most of the overall savings.

---

## Alternatives Considered

| Option | Why not chosen |
|--------|---------------|
| MiniMax M2.5 Free for cheap | Free but unproven reliability for production triage workloads |
| GPT-5 Mini for cheap | $0.25/$2.00 — cheaper, but less proven with Adjutant's prompt patterns |
| Qwen3 Coder 480B for medium | Code-specialized; may underperform on general analysis/reasoning |
| OpenCode Go ($10/mo flat) | Good value if volume is high enough; revisit if monthly Zen spend exceeds $10 |

---

## Config Locations

| File | Tracked | Fields |
|------|---------|--------|
| `adjutant.yaml` | No (gitignored) | `llm.models.cheap`, `llm.models.medium`, `llm.models.expensive`, `messaging.telegram.default_model` |
| `adjutant.yaml.example` | Yes | Same fields — template with comments |
| `.opencode/agents/adjutant.md` | Yes | `model:` frontmatter — TUI default only |
| `scripts/common/opencode.sh` | Yes | Health check model — hardcoded |

---

## Changing Models

To swap a tier model:

1. Edit `adjutant.yaml` — change the tier value (e.g., `cheap: "opencode/kimi-k2.5"`)
2. Restart Adjutant (`adjutant restart`) — scripts re-read YAML on each invocation, but Telegram long-poll needs restart
3. All KBs using that tier name automatically pick up the new model — no per-KB edits needed

To test a model before committing:
```bash
opencode run --model "opencode/kimi-k2.5" --prompt "Hello, confirm you are working"
```
