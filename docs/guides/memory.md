# Memory

Adjutant has persistent long-term memory stored as plain Markdown files. The memory system lets Adjutant remember corrections, decisions, people, project knowledge, and patterns -- and recall them later.

## How It Works

Memory is stored under `memory/` in the Adjutant directory. Each category has its own file. When you tell Adjutant to remember something, it auto-classifies the content and appends it to the right file with a timestamp.

The agent loads `memory/memory.md` (the index) at startup so it knows what's available. Individual memory files are loaded on demand when relevant to the current conversation.

## Directory Structure

```
memory/
├── memory.md                    # Index -- loaded at startup
├── facts/
│   ├── people.md                # People, roles, preferences
│   ├── projects.md              # Learned project knowledge
│   ├── decisions.md             # Decisions and rationale
│   └── corrections.md           # Mistakes and corrections
├── patterns/
│   ├── preferences.md           # Communication/style preferences
│   ├── workflows.md             # Recurring workflows
│   └── exceptions.md            # Edge cases and gotchas
├── summaries/
│   ├── weekly/                  # Weekly journal digests
│   └── monthly/                 # Monthly summaries
├── conversations/               # Notable conversation takeaways
└── working/                     # Ephemeral working memory (auto-cleaned)
```

## Commands

### Telegram

| Command | What it does |
|---------|-------------|
| `/remember <text>` | Save something to memory (auto-classified) |
| `/forget <topic>` | Archive memories matching the topic |
| `/recall` | Show the memory index |
| `/recall <query>` | Search memory for matching entries |
| `/digest` | Compress recent journal entries into a weekly summary |

### CLI

```bash
adjutant memory init              # Scaffold the memory directory
adjutant memory remember "text"   # Add a memory
adjutant memory forget "topic"    # Archive a memory
adjutant memory recall            # Show memory index
adjutant memory recall "query"    # Search memory
adjutant memory digest            # Compress journal to weekly summary
adjutant memory digest --days 14  # Digest the last 14 days
adjutant memory status            # Show memory stats
```

## Auto-Classification

When you use `/remember`, Adjutant analyzes the text and routes it to the right file using keyword matching. No LLM call is needed -- classification is instant.

| Keywords detected | Category |
|-------------------|----------|
| "wrong", "mistake", "correction", "actually" | `facts/corrections.md` |
| "decided", "chose", "went with", "settled on" | `facts/decisions.md` |
| "person", "name is", "works at", "colleague" | `facts/people.md` |
| "project", "repo", "codebase", "deployment" | `facts/projects.md` |
| "prefer", "always", "never", "style", "format" | `patterns/preferences.md` |
| "workflow", "process", "routine", "usually" | `patterns/workflows.md` |
| "edge case", "gotcha", "watch out", "workaround" | `patterns/exceptions.md` |

If no clear match is found, the default is `facts/projects.md`.

You can also specify a category explicitly:

```bash
adjutant memory remember "Alice prefers async communication" --category facts/people.md
```

## Forgetting

`/forget` doesn't delete memories permanently. It moves matching entries to `memory/.archive/`, preserving them in case you need them back. The archive mirrors the original directory structure.

## Weekly Digest

The `/digest` command (or `adjutant memory digest`) reads journal entries from the past 7 days, produces a summary, and writes it to `summaries/weekly/YYYY-WNN.md`. This keeps your memory system current without manual work.

You can schedule this automatically:

```yaml
# In adjutant.yaml, under schedules:
- name: "memory_digest"
  description: "Weekly memory compression"
  schedule: "0 21 * * 0"  # Sunday 9pm
  script: ".venv/bin/python -m adjutant memory digest"
  enabled: true
```

## Security

- All memory writes include timestamps for auditability
- `/forget` archives rather than deletes -- reversible
- The agent prompt treats memory file content as **data, not instructions** -- this prevents prompt injection via crafted memory entries
- Memory files are gitignored (user-specific data)

## Best Practices

- Use `/remember` for corrections -- these are the highest-value memories
- Let auto-classification handle routing -- it works well for most inputs
- Run `/digest` weekly to keep summaries current
- Use `/recall` to check what Adjutant knows before asking it to remember something new
