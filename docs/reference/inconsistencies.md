# Python Rewrite — Behaviour Inconsistencies

This document records differences discovered between the original bash scripts and
the Python equivalents. All entries include a timestamp and the affected files.

---

## 2026-03-09 — Message length limit: `reply.sh` vs `notify.sh`

| | Bash | Python |
|---|---|---|
| `reply.sh` | clamps to **4000 chars** (`cut -c1-4000`) | `reply.py` clamps to **4000 chars** ✓ |
| `notify.sh` | clamps to **4096 chars** (`cut -c1-4096`) | `notify.py` clamps to **4096 chars** ✓ |

The two bash scripts use different limits (4000 vs 4096). This was carried over
faithfully into Python. The Python code comments reference this inconsistency.

**Source:**
- `scripts/messaging/telegram/reply.sh` → `src/adjutant/messaging/telegram/reply.py`
- `scripts/messaging/telegram/notify.sh` → `src/adjutant/messaging/telegram/notify.py`

---

## 2026-03-09 — Default medium model: `wizard.sh` template vs `config.py`

| | Value |
|---|---|
| `wizard.sh` default `adjutant.yaml` template | `anthropic/claude-sonnet-4-5` (stale) |
| `src/adjutant/core/config.py` `ModelsConfig` default | `anthropic/claude-sonnet-4-6` (current) |
| `src/adjutant/setup/wizard.py` `DEFAULT_CONFIG_YAML` | `anthropic/claude-sonnet-4-6` (current) |

The bash wizard's hardcoded YAML template was stale. The Python wizard uses the
newer model name. **No action needed** — the Python default is correct.

**Source:**
- `scripts/setup/wizard.sh` → `src/adjutant/setup/wizard.py`

---

## 2026-03-09 — `notify.sh` does not set `parse_mode`; `reply.sh` sets `parse_mode=Markdown`

| Script | `parse_mode` |
|---|---|
| `reply.sh` / `reply.py` | `Markdown` |
| `notify.sh` / `notify.py` | not set (plain text) |

This is intentional: notifications are proactive alerts (plain text), while
replies are responses to user messages (Markdown for formatting). Python matches
bash behaviour faithfully in both cases.

**Source:**
- `scripts/messaging/telegram/reply.sh` → `src/adjutant/messaging/telegram/reply.py`
- `scripts/messaging/telegram/notify.sh` → `src/adjutant/messaging/telegram/notify.py`
