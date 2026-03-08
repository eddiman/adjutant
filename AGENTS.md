# AGENTS.md — Builder Guide

For AI coding agents working on Adjutant. Not read at runtime — zero token cost to the Adjutant agent itself.

---

## What This Is

Adjutant is a bash-only persistent agent framework. An OpenCode-powered LLM agent receives messages via Telegram, queries sandboxed knowledge base sub-agents, and orchestrates lifecycle/heartbeat logic. No compiled code, no long-running server — only shell scripts and OpenCode process invocations.

---

## Repo Map

```
adjutant/
├── adjutant                        # CLI entrypoint — case dispatcher
├── adjutant.yaml.example           # Config template (adjutant.yaml is gitignored)
├── .env.example                    # Secrets template (.env is gitignored)
├── .opencode/agents/adjutant.md    # Main agent definition (tracked)
├── identity/                       # Soul/heart/registry — gitignored, personal
├── knowledge_bases/                # registry.yaml (gitignored) + nothing else tracked
├── templates/kb/                   # KB scaffold templates — tracked
├── prompts/                        # pulse.md, review.md, escalation.md — tracked
├── scripts/
│   ├── common/                     # Shared library — source these, don't modify lightly
│   ├── messaging/                  # Adaptor contract + Telegram backend
│   ├── capabilities/               # screenshot/, vision/, kb/ — add new ones here
│   ├── lifecycle/                  # start/stop/pause/kill/restart/update
│   ├── news/                       # fetch → analyze → briefing pipeline
│   ├── observability/              # status, usage, log rotation
│   └── setup/                      # installer, wizard, repair, steps/
├── tests/
│   ├── test_helper/                # setup.bash + mocks.bash
│   ├── unit/                       # Tier 1 — pure logic, no external calls
│   └── integration/                # Tier 2 — mock curl/opencode via PATH
└── docs/
    ├── development/                # plugin-guide, adaptor-guide, testing, setup-wizard
    ├── architecture/               # overview, messaging, identity, state, design-decisions
    └── guides/                     # getting-started, commands, knowledge-bases, configuration
```

---

## Never Commit

These are gitignored and contain personal or runtime data:

- `identity/` — soul.md, heart.md, registry.md (personal; `.example` files are tracked)
- `state/` — all runtime mutable state
- `journal/`, `insights/`, `photos/`, `screenshots/`
- `.env` — secrets only (`.env.example` is tracked)
- `adjutant.yaml` — live config (`adjutant.yaml.example` is tracked)
- `knowledge_bases/registry.yaml` — live KB routing table

---

## Shell Conventions

1. Shebang: `#!/bin/bash` — not `#!/usr/bin/env bash`
2. Safety flags: `set -euo pipefail` in executable scripts only — **not** in sourced library files (propagates to callers)
3. Variables: `UPPER_CASE` for globals/exports; `local lower_case` with explicit `local` declaration
4. Source order: always `paths.sh` first (resolves `ADJ_DIR`), then `env.sh`, `logging.sh`, `platform.sh`, `opencode.sh`
5. Credentials: never `source .env` — use `get_credential KEY` from `env.sh`
6. Temp files: always `TMP="$(mktemp)"; trap 'rm -f "${TMP}"' EXIT`
7. Stdout is for return values only — all logging goes to `adj_log "component" "message"`
8. `paths.sh` must be **sourced**, not run in a subshell — it uses `BASH_SOURCE[1]` to locate itself

---

## Entry Script Contract

Every capability script outputs to stdout:
- `OK:<result>` on success, exit 0
- `ERROR:<reason>` on failure, exit non-zero

Callers always check both the exit code and the prefix. See `docs/development/plugin-guide.md` for the full template, credentials pattern, and the screenshot capability as the reference implementation.

---

## Function Naming

| Prefix | Location | Purpose |
|--------|----------|---------|
| `cmd_*` | `messaging/telegram/commands.sh` | Slash command handlers |
| `msg_*` | `messaging/adaptor.sh` + backend | Messaging interface (send, react, typing) |
| `adj_log` | `common/logging.sh` | Structured log appender |
| `kb_*` | `capabilities/kb/manage.sh` | Knowledge base CRUD |
| `wiz_*` | `setup/helpers.sh` | Wizard UI (write to `/dev/tty`, safe in `$()`) |
| `step_*` | `setup/steps/*.sh` | Wizard setup steps |
| `_*` | anywhere | Private/internal — not part of public API |

---

## Adding a Capability

1. Create `scripts/capabilities/<name>/<name>.sh` following the entry script contract
2. Add `cmd_<name>()` handler in `scripts/messaging/telegram/commands.sh`
3. Register in the `case` block in `scripts/messaging/dispatch.sh`
4. Add to `cmd_help()` in `commands.sh`
5. Document in `.opencode/agents/adjutant.md` so the agent knows it exists
6. Add integration test at `tests/integration/<name>.bats`
7. Add to `docs/guides/commands.md`

Full guide: `docs/development/plugin-guide.md`

---

## Adding a Slash Command

Add to the `case` block in `scripts/messaging/dispatch.sh`:

```bash
/mycommand)      cmd_mycommand "${message_id}" ;;
/mycommand\ *)   cmd_mycommand "${message_id}" "${text#/mycommand }" ;;
```

Handler shape in `commands.sh`:

```bash
cmd_mycommand() {
  local message_id="$1"
  local arg="${2:-}"
  local result
  result="$(bash "${ADJ_DIR}/scripts/capabilities/myfeature/myfeature.sh" "${arg}")"
  if [[ "${result}" == OK:* ]]; then
    msg_send_text "${result#OK:}" "${message_id}"
  else
    msg_send_text "Error: ${result#ERROR:}" "${message_id}"
  fi
}
```

For long-running commands, wrap in `( ... ) &; disown $!` and use `msg_typing start/stop`.

---

## Knowledge Bases

A KB is a sandboxed OpenCode workspace in its own directory. The main Adjutant agent never reads KB files directly — it queries them via a sub-agent process.

**Query a KB:**
```bash
bash "${ADJ_DIR}/scripts/capabilities/kb/query.sh" "<name>" "question"
```

**Create a KB** (interactive wizard):
```bash
bash "${ADJ_DIR}/scripts/setup/steps/kb_wizard.sh"
```

**Scaffold structure** (generated from `templates/kb/`):
```
<kb-path>/
├── kb.yaml                       # Metadata
├── .opencode/agents/kb.md        # Sub-agent definition (rendered from template)
├── opencode.json                 # Sandboxed permissions (external_directory: deny)
├── data/current.md               # Live status — sub-agent reads this first
├── knowledge/                    # Stable reference docs
├── history/                      # Archived records
└── templates/                    # Reusable formats
```

**Template variables** replaced by `kb_scaffold()` in `manage.sh`: `{{KB_NAME}}`, `{{KB_DESCRIPTION}}`, `{{KB_MODEL}}`, `{{KB_ACCESS}}`, `{{KB_WRITE_ENABLED}}`, `{{KB_CREATED}}`.

**KB registry** (`knowledge_bases/registry.yaml`) is the routing table. `kb_register()` appends to it; `kb_exists()` / `kb_get_field()` query it without `yq` (pure bash, line-by-line parsing).

**Access levels:** `read-only` KBs have `bash: false` in their workspace. `read-write` KBs can update their own `data/` files during a `/reflect`.

Full guide: `docs/guides/knowledge-bases.md`

---

## Agent Prompt

`.opencode/agents/adjutant.md` is the only agent definition that is tracked. Edit it when:
- A new capability needs to be surfaced to the agent
- Startup/routing behavior changes
- A new tool invocation pattern is added

`identity/soul.md`, `identity/heart.md`, `identity/registry.md` are **personal and gitignored** — never edit them programmatically or stage them.

---

## Testing

bats-core, two tiers:
- **Unit** (`tests/unit/`) — pure logic, no external calls, `ADJUTANT_HOME` isolation per test
- **Integration** (`tests/integration/`) — mock `curl`/`opencode`/`npx` via PATH injection

**Parallelism is required.** The suite has 583 tests and cannot complete within typical timeout limits (~2 min) when run serially. GNU `parallel` must be installed before running `tests/run`.

```bash
brew install parallel              # macOS (required — do this first)
git submodule update --init --recursive
brew install bats-core
tests/run                          # full suite — always use this, not bare bats
```

To run a single file without parallel (safe — it's only the full suite that times out):

```bash
bats tests/unit/lockfiles.bats
bats tests/integration/commands.bats
```

All 583 tests must pass before release. No CI — discipline-enforced.

Full guide: `docs/development/testing.md`

---

## Gotchas

- **`paths.sh` uses `BASH_SOURCE[1]`** — must be sourced, not executed in a subshell, or `ADJ_DIR` resolution breaks
- **Setup globals** — `resolve_version()` and `prompt_install_dir()` in the installer set globals instead of printing to stdout; never capture them with `$()`
- **`wiz_*` write to `/dev/tty`** — intentional, so they're safe inside `$()` capture without polluting return values
- **`set -e` in sourced files** — don't. It propagates to the caller's shell and causes silent failures in unrelated code paths
- **`dispatch.sh` auth + rate-limit block** — security-critical; don't refactor without running the full integration suite first
