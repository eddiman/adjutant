# Design Decisions

Why Adjutant is built the way it is.

---

## Python over bash

The original Adjutant codebase was written in bash. It was fully rewritten in Python because:

- **Testability** — pytest gives first-class unit testing with proper mocking, fixtures, and assertions. The bash suite relied on `bats-core` which is hard to mock correctly and slow to run in parallel.
- **Type safety** — Python type annotations catch whole classes of bugs that bash silently ignores (e.g. empty variable expansion, wrong argument order).
- **Maintainability** — Python modules, imports, and dataclasses are far easier to reason about than sourced bash scripts with global variable mutation.
- **Async I/O** — The Telegram listener uses `asyncio` for non-blocking message handling and in-flight task cancellation. This is trivial in Python and extremely hard to do correctly in bash.

The tradeoff: Python requires a `.venv` setup step that bash didn't. This is acceptable for a project that already requires `opencode` as a dependency.

---

## Directory mutex over PID files

`state/listener.lock/` is a directory, not a file. `mkdir` is atomic on POSIX filesystems — only one process can successfully create the directory. A PID file inside the lock directory enables stale-lock detection without races.

The alternative — checking if a PID file exists and then creating one — has a TOCTOU window where two processes can both check, both see "no lock", and both try to start. The directory approach eliminates this entirely.

---

## Adaptor abstraction before multiple backends exist

The `adaptor.py` interface contract was written before any second backend was built. The reason: forcing all shared logic into `dispatch.py` early prevents it from bleeding into `telegram/listener.py` where it would be hard to extract later.

The rule: anything that should work regardless of which messaging platform is in use belongs in `dispatch.py`. The Telegram adaptor only handles Telegram-specific concerns (API format, photo downloads, bot token auth).

---

## Rate limiting in the dispatcher, not the adaptor

Rate limiting applies regardless of backend. Putting it in `dispatch.py` means a Slack or Discord adaptor gets rate limiting for free, without reimplementing it. The adaptor only needs to call `dispatch_message` — all safety checks are centralized.

---

## Line-by-line `.env` parsing, never `exec`

`core/env.py` extracts credentials from `.env` using line-by-line parsing. It never `exec`s or `import`s the file.

Executing a `.env` file runs its contents as Python code. A malformed or tampered `.env` could run arbitrary commands. Line-by-line extraction treats the file as data, not code — it can only extract values for known keys.

---

## Personal files are never committed

`adjutant.yaml`, `.env`, `identity/*.md`, `knowledge_bases/`, and `journal/` are gitignored. Example templates are tracked. This is enforced by `.gitignore` — you can `git pull` updates without worrying about your configuration being overwritten, and you can push your adjutant fork to a public repo without leaking credentials or personal data.

---

## CI is intentionally absent

The pytest suite runs in ~75 seconds locally with 1081 tests. GitHub Actions runners would consume disproportionate minutes for what is a single-maintainer personal tool.

The pre-release gate is a clean local run:

```bash
.venv/bin/pytest tests/unit/ -q
```

All tests must pass before tagging a release. This is enforced by discipline, not automation. The tradeoff — no per-commit CI — is acceptable given the project's scale and audience.

---

## Identity split into three files

`soul.md`, `heart.md`, and `registry.md` are separate files rather than one combined persona file because they change at very different rates:

- `soul.md` changes rarely — maybe a few times a year
- `heart.md` changes occasionally — communication style, tone preferences
- `registry.md` changes frequently — active projects, current priorities, schedule

Loading all three every request is correct: the agent needs full context. But splitting them makes updates surgical — you edit only the file that changed, and git history is meaningful.

---

## KB operations: Python CLI preferred over bash shims

`kb_run()` supports two invocation modes:

1. **Python CLI** (preferred): If `kb.yaml` declares `cli_module: "src.cli"`, `kb_run` invokes `.venv/bin/python -m src.cli --real <operation>` directly — no bash involved.
2. **Bash script** (legacy fallback): If `cli_module` is absent, `kb_run` resolves `scripts/<operation>.sh` and runs it via `bash`.

This dual-path design means KBs with a Python CLI (like `portfolio-kb`) need zero bash shims. Older KBs that only have shell scripts continue to work unchanged.

---

## Timeout on all claude_run calls

`claude` can hang indefinitely if the underlying process is in a degraded state. Without a timeout, a single hung call silently kills a briefing or leaves a chat session showing "typing…" forever — with no log evidence.

The fix: `core/claude.py` wraps subprocess calls with a configurable timeout. Callers set it explicitly based on expected response time. Exit code 124 (standard `timeout` exit code) is checked and logged with a clear message.

---

## KB sub-agents are sandboxed

Every KB has an `opencode.json` that sets `external_directory: deny`. This means a KB sub-agent cannot read or write files outside its own workspace. A compromised or misbehaving KB cannot:

- Read your identity files or other KBs
- Write to `state/` or `journal/`
- Send Telegram notifications

Adjutant is the sole orchestrator. Only Adjutant's prompts call `notify.py`. Only Adjutant's prompts write to `insights/` and `state/actions.jsonl`.
