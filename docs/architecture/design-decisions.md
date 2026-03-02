# Design Decisions

Why Adjutant is built the way it is.

---

## No server process

There is no long-running daemon with its own event loop. The listener is a plain shell `while true` loop. This means:

- No custom init system or supervisor required
- Stopping the listener leaves in-flight commands to complete naturally
- Restarts are clean — no shared mutable state between runs
- The entire system is inspectable with `ps`, `ls`, and `cat`

The tradeoff is that the listener must be restarted explicitly after updates. This is acceptable for a single-maintainer personal agent.

---

## Directory mutex over PID files

`state/listener.lock/` is a directory, not a file. `mkdir` is atomic on POSIX filesystems — only one process can successfully create the directory. A PID file inside the lock directory enables stale-lock detection without races.

The alternative — checking if a PID file exists and then creating one — has a TOCTOU window where two processes can both check, both see "no lock", and both try to start. The directory approach eliminates this entirely.

---

## `jq` over Python for JSON parsing

The original listener used embedded Python heredocs for JSON parsing. Phase 2 replaced all JSON parsing with `jq`:

- Simpler: one-liner expressions instead of multi-line Python
- Faster: no interpreter startup cost per call
- Consistent: `jq` is a single dependency with a predictable API
- Testable: `jq` expressions are easy to unit-test in isolation

The one remaining Python dependency is `screenshot.sh`, which uses `python3` for URL domain extraction. This is a known technical debt item.

---

## Adaptor abstraction before multiple backends exist

The `adaptor.sh` interface contract was written before any second backend was built. The reason: forcing all shared logic into `dispatch.sh` early prevents it from bleeding into `telegram/listener.sh` where it would be hard to extract later.

The rule: anything that should work regardless of which messaging platform is in use belongs in `dispatch.sh`. The Telegram adaptor only handles Telegram-specific concerns (API format, photo downloads, bot token auth).

---

## Rate limiting in the dispatcher, not the adaptor

Rate limiting applies regardless of backend. Putting it in `dispatch.sh` means a Slack or Discord adaptor gets rate limiting for free, without reimplementing it. The adaptor only needs to call `dispatch_message` — all safety checks are centralized.

---

## Personal files are never committed

`adjutant.yaml`, `.env`, `identity/*.md`, `knowledge_bases/`, and `journal/` are gitignored. Example templates are tracked. This is enforced in two places:

1. `.gitignore` — prevents accidental staging
2. The release tarball build — strips personal files via `.github/workflows/release.yml`

The consequence: you can `git pull` updates without worrying about your configuration being overwritten, and you can push your adjutant fork to a public repo without leaking credentials or personal data.

---

## grep-based `.env` parsing, never `source`

`scripts/common/env.sh` extracts credentials from `.env` using `grep`/`cut`/`tr`. It never `source`s the file.

Sourcing a `.env` file executes its contents as shell code. A malformed or tampered `.env` could run arbitrary commands. Grep-based extraction treats the file as data, not code — it can only extract values for known keys.

---

## CI is intentionally absent

The 529-test bats suite spawns subprocesses heavily and takes 60–90 seconds locally. GitHub Actions runners would consume disproportionate minutes for what is a single-maintainer personal tool.

The pre-release gate is a clean local run:

```bash
bats tests/unit/ tests/integration/
```

All 529 tests must pass before tagging a release. This is enforced by discipline, not automation. The tradeoff — no per-commit CI — is acceptable given the project's scale and audience.

---

## Identity split into three files

`soul.md`, `heart.md`, and `registry.md` are separate files rather than one combined persona file because they change at very different rates:

- `soul.md` changes rarely — maybe a few times a year
- `heart.md` changes occasionally — communication style, tone preferences
- `registry.md` changes frequently — active projects, current priorities, schedule

Loading all three every request is correct: the agent needs full context. But splitting them makes updates surgical — you edit only the file that changed, and git history is meaningful (a commit to `registry.md` is clearly "updated project state", not "changed core values").

---

## Timeout on all opencode_run calls

`opencode run` can hang indefinitely if the underlying server is in a degraded state (e.g. after a macOS sleep/wake cycle). Without a timeout, a single hung call silently kills the briefing or leaves a chat session showing "typing…" forever — with no log evidence of what happened.

The fix is `OPENCODE_TIMEOUT` — an env var consumed by `opencode_run` in `opencode.sh` that wraps the call with `_adj_timeout`. Callers set it explicitly:

- `analyze.sh`: 90s — enough for a Haiku analysis call, short enough to fail clearly
- `chat.sh`: 120s — slightly longer to accommodate heavier Sonnet calls

Exit code 124 (the standard `timeout` exit code) is checked at each call site and logged with a clear message.

`timeout` is not available on macOS without GNU coreutils. `_adj_timeout` handles this: it prefers `timeout` or `gtimeout` if present, and falls back to a shell-native watchdog (background job + `sleep` + `kill`) otherwise. This means timeouts work correctly on a stock macOS install.

---

## Health check before critical opencode calls

Timing out a hung call is necessary but not sufficient — the next retry will hang again unless the root cause (degraded web server) is fixed first.

`opencode_health_check` probes the server with a `curl --max-time 5` GET to `http://localhost:4096/` before the main API call. If it fails:

1. Kills the existing `opencode web` process (identified via `state/opencode_web.pid`)
2. Restarts it
3. Waits up to 15s for the probe to succeed

This is called in `analyze.sh` before the Haiku analysis step. If the restart fails, the script exits cleanly with a log entry rather than hanging.

`curl` is used rather than `opencode --version` because `--version` does not actually connect to the server — it exits 0 immediately regardless of server state. The HTTP probe is the only reliable way to confirm the server is accepting connections.

---

## Reaper catches language servers stranded under opencode web

`opencode_run` diffs bash/yaml-language-server PIDs before and after each call to kill any it spawned. This works when the call exits normally.

When a call is killed by timeout, the diff still runs — but the language servers may already have been reparented to the `opencode web` process (their grandparent) before cleanup. The old reaper only killed servers whose parent was PID 1 or gone, so these looked legitimate and were never reaped.

The fix: `opencode_reap` now also kills any language server whose direct parent is the `opencode web` PID. A language server that has a *live* `opencode run` as its parent is fine — that run is still working. One directly under the web server means its run has already exited, so it's stranded.
