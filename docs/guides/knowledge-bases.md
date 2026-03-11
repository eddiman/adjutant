# Knowledge Bases

How to create, structure, register, and query knowledge bases in Adjutant.

---

## How Adjutant queries a KB

When you ask Adjutant something domain-specific, it:
1. Reads `knowledge_bases/registry.yaml` to find a matching KB
2. Spawns `opencode run --agent kb --dir <kb-path>`
3. The sub-agent uses **glob** and **grep** to find relevant files, then **reads** them
4. Returns a synthesized answer

The sub-agent has no memory between sessions. Every query starts cold. This means **file layout and naming are the primary navigation tools** — the sub-agent finds answers by pattern-matching filenames and scanning content. Good structure = fast, accurate answers. Poor structure = missed or hallucinated answers.

---

## Pulse and reflect integration

KBs are the primary data source for `/pulse` and `/reflect`. Adjutant has no direct access to external project directories — all project knowledge enters through KB sub-agents.

**`/pulse`** queries every registered KB with a brief prompt:
> "Quick pulse: what is the current status? List any active blockers, open items, or upcoming deadlines in the next 2 weeks."

Adjutant collects the responses, evaluates them against `heart.md` priorities, and writes a journal entry. Anything significant is written to `insights/pending/` for follow-up.

**`/reflect`** queries every registered KB in depth:
> "Full reflection: give me a thorough status report. What's on track, what's at risk, what's stale? Any deadlines in the next 2–4 weeks? If any of your data files look outdated, update them now."

For read-write KBs, the sub-agent has write and bash access — it can update `data/current.md`, run data-refresh scripts, rebuild rendered views, and fix stale state directly during a reflect call. This means `/reflect` isn't just a read — it's an opportunity to bring KB data current.

For safety-sensitive or operational KBs, read-write access does not imply blanket permission to perform sensitive external actions. Refresh, repair, and reconciliation are acceptable. Real-world side effects still require explicit user intent.

**Practical implication:** `data/current.md` is the first file the KB agent reads during any pulse or reflect. Keeping it fresh makes both commands more useful. For structured-state KBs, `current.md` should be a rendered summary of canonical state, not the state authority itself.

---

## Required files (root of every KB)

```
kb.yaml              — metadata (name, description, model, access)
docs/README.md       — what this KB is about, what questions it can answer
```

`kb.yaml` is what Adjutant reads to register and query the KB. `docs/README.md` is what the sub-agent reads first to orient itself — it is placed under `docs/` in the scaffold so the KB root stays clean.

For automation-heavy KBs, `docs/README.md` and `data/current.md` should point clearly at any canonical structured state files. Adjutant does not need to understand those files directly, but the KB agent should be able to use them for precision.

---

## Recommended directory layout

```
<kb-root>/
├── kb.yaml
├── README.md
│
├── data/                    # Live, frequently-updated operational data
│   ├── current.md           # Single "right now" snapshot — the most important file
│   ├── <topic>/             # Subdirectory per domain (events, people, finances, etc.)
│   │   ├── index.md         # Summary + links/refs for the topic
│   │   └── <records>.md     # Individual records, named by date or subject
│   └── ...
│
├── knowledge/               # Stable, slow-changing reference material
│   ├── <topic>.md           # One file per concept or domain area
│   └── ...
│
├── history/                 # Archived records — past events, old decisions
│   └── <year>/
│       └── <record>.md
│
├── templates/               # Reusable formats for creating new records
│   └── <template-name>.md
│
├── state/                   # Runtime state for advanced operational KBs (optional)
└── docs/reference/          # Architectural notes and implementation plans (optional)
```

---

## The three content layers

### 1. `data/` — operational, changes often
Everything that reflects current state. Agents read this to answer "what's happening now" questions.

- `data/current.md` — **the single most important file**. A concise snapshot of active status: open items, next actions, current priorities. The sub-agent will almost always read this first.
- Topic subdirectories for anything with multiple records (events, people, finances, etc.)
- Files named by date (`2026-03-17-event.md`) or subject (`volunteers.md`) — whichever is more stable

### 2. `knowledge/` — reference, changes rarely
Stable facts, rules, playbooks, role descriptions, formats. Things that don't change week to week.

- One file per concept (`event-formats.md`, `roles.md`, `communication-playbook.md`)
- No dates in filenames unless it's a versioned policy
- Write these as reference documents, not logs

### 3. `history/` — archive
Completed events, past decisions, closed records. Moved here so `data/` stays lean. Organized by year for easy glob.

---

## Naming conventions

| Pattern | Use for |
|---|---|
| `YYYY-MM-DD-subject.md` | Meeting notes, events, dated entries |
| `subject.md` | Reference docs, role descriptions, playbooks |
| `current.md` | The live snapshot (always this exact name) |
| `index.md` | Summary + navigation within a subdirectory |

- Lowercase, hyphens, no spaces
- Descriptive over short — the sub-agent uses filenames to decide what to read
- Avoid generic names like `notes.md` or `misc.md` — they tell the agent nothing

---

## What goes in `current.md`

This file is the sub-agent's landing pad. It should always contain:

```markdown
# Current Status — <KB name>
Last updated: YYYY-MM-DD

## Active priorities
- ...

## Open items / blockers
- ...

## What's coming up
- ...

## Quick references
- Key people: ...
- Key files: data/<topic>/index.md
```

Keep it under ~100 lines. Compress, don't accumulate. When something is resolved, move it to `history/` — don't leave it in `current.md` as a completed item.

For structured-state KBs, `current.md` should be regenerated from canonical JSON or other machine-readable state. Treat it as the agent landing page, not as the database.

---

## Rendered views vs canonical state

Some KBs are simple and can keep their primary truth in markdown.

Operational KBs often need stronger contracts. In those KBs:

- `data/current.md` is the human-readable summary
- markdown tables and reports are rendered views
- canonical truth lives in machine-readable state files such as JSON

Recommended pattern:

- `data/current.md` — concise operational summary
- `data/<topic>/*.json` — canonical state for automation-heavy workflows
- `data/<topic>/*.md` — rendered reports derived from canonical state

Adjutant should remain agnostic about the exact schema. The KB agent is responsible for knowing which files are authoritative inside its own workspace.

---

## Access levels

Set in `kb.yaml`:

- `read-only` — Adjutant can query but not write. Use for reference KBs.
- `read-write` — Adjutant can update files and run scripts. Use for operational KBs where you want it to record decisions, update `current.md`, or run data-fetch scripts during `/reflect`.

Default to `read-write` for active project KBs. The sub-agent won't write unless explicitly told to. Read-write KBs have `edit` and `write` tools permitted in their `claude.json` workspace config, while `read-only` KBs have those tools denied — restricting the sub-agent to read operations only.

---

## KB registration

Register every KB in `$ADJ_DIR/knowledge_bases/registry.yaml`:

```yaml
knowledge_bases:
  - name: "my-kb"
    description: "One sentence: what this KB contains and what questions it answers."
    path: "/absolute/path/to/kb-root"
    model: "anthropic/claude-sonnet-4-6"
    access: "read-write"
    created: "YYYY-MM-DD"
```

The `description` field is what Adjutant uses to decide whether to query this KB. Make it specific — it's the routing signal.

You can also register a KB from the command line or via the setup wizard:

```bash
# Interactive wizard
adjutant kb create

# One-liner (quick create)
adjutant kb create --quick --name my-kb --path /path/to/kb --desc "..."

# List registered KBs
adjutant kb list

# Show details for a KB
adjutant kb info my-kb

# Run a KB-local operation by name
adjutant kb run my-kb fetch

# Remove a KB from the registry (does not delete files)
adjutant kb remove my-kb
```

---

## KB-local operations

`adjutant kb run <name> <op>` executes an operation inside the KB. There are two resolution paths:

**1. Python CLI module (preferred for Python KBs)**

If `kb.yaml` declares a `cli_module` field, Adjutant invokes it directly via the Python entry point:

```yaml
# kb.yaml
cli_module: "src.cli"
```

This causes `adjutant kb run <name> <op>` to run:
```
python -m <cli_module> <op>
```

**2. Shell script fallback**

Without `cli_module`, Adjutant looks for a script at:

```
<kb-path>/scripts/<op>.sh
```

`<op>` is the operation name — lowercase letters, digits, hyphens, and underscores. The script must exist and be executable, otherwise the command fails with a clear error.

Running KB operations manually:

```bash
adjutant kb run my-kb fetch
adjutant kb run my-kb analyze
adjutant kb run my-kb reconcile
```

The same mechanism is used when scheduling a KB job without a hardcoded path:

```yaml
schedules:
  - name: "my_kb_fetch"
    schedule: "0 9,12,15 * * 1-5"
    kb_name: "my-kb"
    kb_operation: "fetch"
    log: "/path/to/my-kb/state/fetch.log"
    enabled: true
```

Adjutant resolves `kb_operation: fetch` via the `cli_module` or script convention at install and run time — no absolute paths needed in the config.

**Script contract (shell path):** exit 0 on success, non-zero on failure. Stdout is captured by `/schedule run <name>` and shown in Telegram.

---

## Minimal viable KB (starting point)

If you're creating a new KB and don't have much content yet, start with just this:

```
kb.yaml
README.md
data/
  current.md
knowledge/
  <one file per major concept>
```

Add subdirectories and `history/` as volume grows.

---

## What NOT to do

- **Don't dump everything in root.** Files scattered at root with no subdirectories are hard to navigate by glob.
- **Don't use one giant file.** A single 2000-line document is slow to search and easy to miss things in. Split by topic.
- **Don't leave stale data in `data/`.** Old completed items should move to `history/`. Stale data confuses answers.
- **Don't use vague filenames.** `notes.md`, `stuff.md`, `temp.md` — the agent can't know what's in them without reading them.
- **Don't mix live data with reference.** Events calendar in `data/`, event format guide in `knowledge/`. Keep the layers clean.
- **Don't put operational data inside `.claude/`.** That directory is for agent/command definitions, not content.

---

## Summary

| Layer | Directory | Content type | Update frequency |
|---|---|---|---|
| Operational | `data/` | Live state, current records | Weekly or more |
| Reference | `knowledge/` | Stable facts, playbooks, roles | Monthly or less |
| Archive | `history/` | Completed records | On completion |
| Tooling | `templates/` | Document formats | Rarely |
