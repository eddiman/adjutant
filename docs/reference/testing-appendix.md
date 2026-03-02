# Testing Appendix

Per-test-case detail for all 529 bats tests. For an overview of the test suite, isolation model, and how to run tests, see [Testing](../development/testing.md).

---

## Tier 1 — Unit Tests

### `paths.bats` — 7 tests

**Script:** `scripts/common/paths.sh`

| Test | What it verifies |
|------|-----------------|
| ADJUTANT_HOME override resolves to that directory | Priority 1: explicit env var is used directly |
| ADJ_DIR is exported | Variable is visible to child processes |
| ADJUTANT_DIR is exported as alias of ADJ_DIR | Backward-compat alias for news scripts |
| Resolves via adjutant.yaml walk-up when ADJUTANT_HOME unset | Priority 2: walks up from calling script's directory looking for the root marker file |
| Falls back to HOME/.adjutant when no marker found | Priority 3: legacy fallback when no `adjutant.yaml` exists in any parent |
| Exits 1 when resolved directory does not exist | Error path: resolved path points to a nonexistent directory |
| ADJUTANT_HOME works with spaces in path | Edge case: paths containing spaces are handled correctly |

---

### `env.bats` — 17 tests

**Script:** `scripts/common/env.sh`

| Function | Tests | What they verify |
|----------|------:|-----------------|
| `load_env` | 2 | Succeeds when `.env` exists; fails with error when missing |
| `get_credential` | 5 | Returns correct value for existing keys; returns empty for missing keys; strips single and double quotes; fails when `.env` is missing |
| `has_credential` | 3 | Returns 0 for present keys; returns 1 for missing keys; returns 1 for keys with empty values |
| `require_telegram_credentials` | 5 | Succeeds and exports both variables when both present; fails when token missing; fails when chat_id missing; fails when `.env` missing |
| Guard clause | 2 | Sourcing without `ADJ_DIR` set exits with descriptive error |

---

### `lockfiles.bats` — 24 tests

**Script:** `scripts/common/lockfiles.sh`

| Function group | Tests | What they verify |
|----------------|------:|-----------------|
| `set_paused` / `clear_paused` | 3 | Creates `PAUSED` file; removes it; `clear_paused` is idempotent |
| `set_killed` / `clear_killed` | 3 | Creates `KILLED` file; removes it; `clear_killed` is idempotent |
| `is_paused` | 2 | Returns 0 when paused, 1 when not |
| `is_killed` | 2 | Returns 0 when killed, 1 when not |
| `is_operational` | 4 | Returns 0 when clean; returns 1 when paused, killed, or both |
| `check_killed` | 2 | Returns 0 silently when not killed; returns 1 with stderr message when killed |
| `check_paused` | 2 | Returns 0 silently when not paused; returns 1 with stderr message when paused |
| `check_operational` | 4 | Composite: returns 0 when clean; returns 1 for killed, paused, or both (killed checked first) |
| State transitions | 1 | Full cycle: clean -> paused -> killed -> clear killed (still paused) -> clear paused -> operational |
| Guard clause | 1 | Sourcing without `ADJ_DIR` set exits with descriptive error |

---

### `logging.bats` — 17 tests

**Script:** `scripts/common/logging.sh`

| Function | Tests | What they verify |
|----------|------:|-----------------|
| `adj_log` | 5 | Creates log file and writes entry; timestamp matches `[HH:MM DD.MM.YYYY]` format; appends multiple entries; defaults context to "general"; sanitizes control characters (tabs, carriage returns) |
| `fmt_ts` | 5 | Formats ISO-8601 with Z suffix; formats ISO-8601 without Z; formats date-only input; returns empty for empty input; returns original string for unparseable input |
| `log_error` | 2 | Writes to log file with ERROR prefix; also writes to stderr |
| `log_warn` | 1 | Writes to log file with WARNING prefix; produces no stdout/stderr |
| `log_debug` | 3 | Does nothing when `ADJUTANT_DEBUG` is unset; writes when `ADJUTANT_DEBUG` is set; writes when `DEBUG` is set |
| Guard clause | 1 | Sourcing without `ADJ_DIR` set exits with descriptive error |

---

### `platform.bats` — 18 tests

**Script:** `scripts/common/platform.sh`

| Function | Tests | What they verify |
|----------|------:|-----------------|
| OS detection | 2 | `ADJUTANT_OS` is "macos" or "linux"; variable is exported |
| `date_subtract` | 5 | Returns ISO-8601 format for hours, days, minutes; fails with error for unknown units; result is within expected range of current time |
| `date_subtract_epoch` | 3 | Returns a numeric epoch; result is less than current time; fails for unknown units |
| `file_mtime` | 2 | Returns a recent epoch for existing files; returns "0" and exit 1 for missing files |
| `file_size` | 3 | Returns correct byte count; returns "0" and exit 1 for missing files; returns "0" for empty files |
| `ensure_path` | 3 | Preserves existing PATH entries; is idempotent (calling twice produces same PATH); adds `/usr/local/bin` when absent |

---

### `adaptor.bats` — 9 tests

**Script:** `scripts/messaging/adaptor.sh`

| Function type | Tests | What they verify |
|---------------|------:|-----------------|
| Required (4 functions) | 4 | `msg_send_text`, `msg_send_photo`, `msg_start_listener`, `msg_stop_listener` all return 1 with "not implemented" on stderr |
| Optional (3 functions) | 3 | `msg_react`, `msg_typing`, `msg_authorize` all return 0 with no output |
| `msg_get_user_id` | 1 | Returns 0 and outputs "unknown" |
| All functions defined | 1 | Verifies all 8 interface functions exist via `declare -f` |

---

### `lifecycle.bats` — 8 tests

**Scripts:** `scripts/lifecycle/pause.sh`, `scripts/lifecycle/resume.sh`

| Script | Tests | What they verify |
|--------|------:|-----------------|
| `pause.sh` | 3 | Creates `PAUSED` file; outputs "Adjutant paused" confirmation; is idempotent |
| `resume.sh` | 3 | Removes `PAUSED` file; outputs "Adjutant resumed" confirmation; is idempotent (no error when not paused) |
| Round-trip | 1 | Pause then resume leaves a clean state (no `PAUSED` file) |
| Isolation | 1 | `pause.sh` creates `PAUSED` in `$TEST_ADJ_DIR`, not in the real project root |

---

### `wizard.bats` (unit) — 50 tests

**Scripts:** `scripts/setup/steps/step_*.sh`, `scripts/setup/helpers.sh`

| Area | Tests | What they verify |
|------|------:|-----------------|
| Step 1: Find/init repo | 5 | Detects existing install; creates fresh directory; validates paths; handles spaces in paths |
| Step 2: Identity files | 5 | Creates soul.md, heart.md, registry.md; preserves existing files; validates content |
| Step 3: Environment | 6 | Creates .env; validates bot token format; validates chat ID format; preserves existing .env |
| Step 4: OpenCode config | 5 | Creates opencode.json; sets correct permissions; handles existing config; validates JSON |
| Step 5: Scripts | 5 | Makes scripts executable; validates permissions; handles missing scripts dir |
| Step 6: Verification | 4 | Validates complete installation; reports missing components; reports placeholder credentials |
| Helpers | 12 | Prompt display functions; input validation; default values; banner formatting |
| Repair mode | 8 | Detects issues; reports counts; handles healthy state; detects non-executable scripts; detects placeholder credentials; detects missing adjutant.yaml |

---

### `journal_rotate.bats` (unit) — 22 tests

**Script:** `scripts/observability/journal_rotate.sh`

| Area | Tests | What they verify |
|------|------:|-----------------|
| Archive eligibility | 4 | Identifies entries older than threshold; skips recent entries; handles empty journal; respects custom retention days |
| Archive creation | 4 | Creates monthly archive directories; moves entries to correct archive; preserves file content; handles year boundaries |
| News cleanup | 4 | Removes old raw/analyzed files; preserves today's files; handles missing directories; respects retention period |
| Log rotation | 4 | Rotates oversized logs; preserves small logs; applies correct size threshold; renames with .old suffix |
| Dry-run mode | 3 | Reports what would happen without modifying files; lists eligible entries; shows size savings |
| Edge cases | 3 | Empty state directory; missing subdirectories; idempotent execution |

---

### `kb.bats` (unit) — 38 tests

**Script:** `scripts/capabilities/kb/manage.sh`

| Function | Tests | What they verify |
|----------|------:|-----------------|
| `kb_count` | 3 | Returns 0 for empty registry; correct count after registering; returns 0 when registry file missing |
| `kb_exists` | 2 | Returns false for non-existent KB; returns true for registered KB |
| `kb_register` | 4 | Adds entry to empty registry; appends to non-empty; fails on duplicate name; writes all fields correctly |
| `kb_unregister` | 4 | Removes entry from registry; fails for non-existent KB; preserves other entries; restores empty list when last entry removed |
| `kb_list` | 3 | Outputs nothing for empty registry; outputs tab-separated fields; outputs multiple entries |
| `kb_info` | 2 | Returns key=value pairs; fails for non-existent KB |
| `kb_get_field` | 1 | Returns correct field value |
| `kb_scaffold` | 6 | Creates directory structure; renders kb.yaml with correct name; renders agent definition; sets write=false for read-only; sets write=true for read-write; does not overwrite existing docs |
| `kb_create` | 6 | Scaffolds and registers in one call; rejects uppercase names; rejects names with spaces; rejects relative paths; rejects duplicate names; accepts single-character name |
| `kb_remove` | 1 | Unregisters but does not delete files |
| `kb_detect_content` | 6 | Finds markdown files; finds code files; finds data files; returns empty for empty dir; returns multiple types; fails for non-existent dir |

---

## Tier 2 — Integration Tests

### Mock Infrastructure

Mock creators (write scripts to `$MOCK_BIN/`):

| Function | What it mocks |
|----------|--------------|
| `create_mock_curl` | `curl` — returns canned JSON |
| `create_mock_curl_telegram_ok` | `curl` — returns Telegram success response |
| `create_mock_curl_telegram_error` | `curl` — returns Telegram error response |
| `create_mock_opencode` | `opencode` — returns canned NDJSON output |
| `create_mock_opencode_reply` | `opencode` — returns a simple text reply |
| `create_mock_opencode_model_error` | `opencode` — returns a model-not-found error |
| `create_mock_npx` | `npx` — creates a fake PNG for Playwright screenshots |
| `create_mock_python3` | `python3` — returns a canned domain string |
| `create_mock_crontab` | `crontab` — returns canned crontab output |
| `create_mock_timeout` | `timeout` — skips the duration arg and execs the command |
| `_create_mock_custom` | Generic — writes a custom script body for complex mocks |

Assertion helpers:

| Function | What it checks |
|----------|---------------|
| `assert_mock_called` | Mock was called at least once |
| `assert_mock_not_called` | Mock was never called |
| `assert_mock_call_count` | Mock was called exactly N times |
| `assert_mock_args_contain` | Last call's args contained a specific string |
| `mock_last_args` | Returns the last call's args |
| `mock_call_args` | Returns the Nth call's args (1-indexed) |
| `mock_call_count` | Returns the number of calls |

State seeders:

| Function | What it seeds |
|----------|--------------|
| `seed_telegram_session` | `state/telegram_session.json` |
| `seed_model_file` | `state/telegram_model.txt` |
| `seed_heartbeat` | `state/last_heartbeat.json` |
| `seed_usage_log` | `state/usage_log.jsonl` |
| `seed_news_config` | `news_config.json` |
| `seed_raw_news` | `state/news_raw/<today>.json` |
| `seed_analyzed_news` | `state/news_analyzed/<today>.json` |
| `seed_news_dedup` | `state/news_seen_urls.json` |
| `seed_prompt` | `prompts/<name>` |
| `seed_pending_reflect` | `state/pending_reflect` |

---

### `notify.bats` — 16 tests

**Script:** `scripts/messaging/telegram/notify.sh`

| Area | Tests | What they verify |
|------|------:|-----------------|
| Happy path | 6 | Sends message successfully; calls sendMessage endpoint; includes bot token; sends text and chat_id as url-encoded params; does NOT set parse_mode |
| Input validation | 2 | Exits with usage error when no argument; exits with error for empty string |
| Input sanitization | 2 | Truncates messages >4096 chars; strips control characters |
| Error handling | 2 | Reports Telegram API errors; handles non-JSON curl output |
| Credentials | 3 | Fails when token missing; fails when chat_id missing; fails when .env missing |
| Invocation count | 1 | Calls curl exactly once per send |

---

### `reply.bats` — 16 tests

**Script:** `scripts/messaging/telegram/reply.sh`

| Area | Tests | What they verify |
|------|------:|-----------------|
| Happy path | 6 | Sends message; calls sendMessage; includes token; sends chat_id; sets parse_mode=Markdown; sends text |
| Behavior | 2 | Does not check response (prints "Replied." even on errors or garbage) |
| Input validation | 2 | Exits with error when no argument; error for empty string |
| Input sanitization | 2 | Truncates at 4000 chars (not 4096 like notify); strips control chars |
| Credentials | 3 | Fails for missing token, chat_id, or .env |
| Invocation count | 1 | Calls curl exactly once |

---

### `send.bats` — 26 tests

**Script:** `scripts/messaging/telegram/send.sh`

| Function | Tests | What they verify |
|----------|------:|-----------------|
| `msg_send_text` | 8 | Endpoint, token, chat_id, text, parse_mode, truncation, reply_to_message_id (with and without) |
| `msg_send_photo` | 5 | Endpoint, file path, caption (with and without), fails for missing file, no curl call for missing file |
| `msg_react` | 3 | Default eyes emoji, custom emoji, silent success for empty message_id |
| `msg_typing` | 4 | Start spawns background process with pidfile; stop removes pidfile and kills process; error for unknown action; stop is safe when no indicator active |
| `msg_authorize` | 3 | Returns 0 for matching from_id; returns 1 for non-matching; returns 1 for empty |
| `msg_get_user_id` | 1 | Returns the TELEGRAM_CHAT_ID value |

---

### `chat.bats` — 18 tests

**Script:** `scripts/messaging/telegram/chat.sh`

| Area | Tests | What they verify |
|------|------:|-----------------|
| Core behavior | 4 | Returns assembled text from NDJSON; uses `--format json`, `--agent adjutant`, `--dir` flags |
| Input validation | 2 | Exits with error for no argument; exits for empty string |
| Session management | 5 | Creates session file; saves session_id; reuses within timeout; starts fresh after 7200s expiry; updates timestamp on reuse |
| Model selection | 2 | Uses default model when no file; reads from state/telegram_model.txt |
| Error handling | 3 | Reports model-not-found gracefully; returns fallback for no text output; handles zero-byte response |
| Invocation count | 1 | Calls opencode exactly once |

---

### `commands.bats` — 32 tests

**Script:** `scripts/messaging/telegram/commands.sh`

| Command | Tests | What they verify |
|---------|------:|-----------------|
| `/status` | 4 | Calls status.sh; includes heartbeat timestamp; shows "not recorded yet" without heartbeat; fallback on failure |
| `/pause` | 3 | Creates PAUSED lockfile; sends confirmation; writes journal entry |
| `/resume` | 3 | Removes PAUSED lockfile; sends confirmation; writes journal entry |
| `/kill` | 2 | Sends shutdown message; invokes emergency_kill.sh in background |
| `/pulse` | 3 | Sends acknowledgment; shows heartbeat data when available; fallback without heartbeat |
| `/restart` | 1 | Sends restarting message |
| `/reflect` | 5 | Request creates pending file and sends cost warning; confirm removes file and starts reflection; error when opencode missing; error when prompt missing |
| `/help` | 3 | Lists all commands; mentions natural language; mentions photo support |
| `/model` | 5 | Shows current model with no arg; reads from state file; switches to valid model; confirms switch; rejects unrecognized model |
| `/screenshot` | 2 | Sends react emoji; prompts for URL when empty |

---

### `dispatch.bats` — 25 tests

**Script:** `scripts/messaging/dispatch.sh`

| Area | Tests | What they verify |
|------|------:|-----------------|
| Authorization | 2 | Rejects unauthorized senders; accepts authorized senders |
| Command routing | 12 | Routes /status, /pause, /resume, /help, /start, /kill, /screenshot (with and without URL), /model, /reflect to correct handlers |
| Reflect state | 3 | Confirms when /confirm sent while pending; cancels on other text; blocks other commands while pending |
| Chat routing | 4 | Spawns background chat job; calls msg_react; registers PID in job file; sends reply via msg_send_text |
| Photo routing | 3 | Rejects unauthorized photos; sends "not available" without handler; calls handler when available |
| Job management | 3 | Removes job file after killing; no-op without job file; creates job file with pid and msg_id |

---

### `photos.bats` — 13 tests

**Script:** `scripts/messaging/telegram/photos.sh`

| Function | Tests | What they verify |
|----------|------:|-----------------|
| `tg_download_photo` | 7 | Calls getFile API; returns local file path; saves with correct extension; handles png; fails without file_path; fails for empty download; includes token in URL |
| `tg_handle_photo` | 6 | Rejects unauthorized; reacts with emoji; sends vision reply; passes caption as prompt; error on download failure; fallback for empty vision result |

---

### `fetch.bats` — 18 tests

**Script:** `scripts/news/fetch.sh`

| Area | Tests | What they verify |
|------|------:|-----------------|
| Preconditions | 2 | Fails without config; exits when KILLED |
| Hacker News | 6 | Calls HN API; includes keywords in URL; writes raw file; valid JSON output; extracts title/url; sets source field; objectID fallback; maps points to score |
| Disabled sources | 2 | No reddit call when disabled; no blog calls when disabled |
| Reddit | 2 | Calls reddit API when enabled; includes User-Agent header |
| Multiple sources | 1 | Combines items from all enabled sources |
| Empty results | 1 | Writes empty array for no results |
| Logging | 2 | Logs total item count; logs start message |

---

### `analyze.bats` — 23 tests

**Script:** `scripts/news/analyze.sh`

| Area | Tests | What they verify |
|------|------:|-----------------|
| Preconditions | 3 | Exits when KILLED; fails without raw file; creates dedup file if missing |
| Deduplication | 4 | Filters seen URLs; empty output when all deduped; no opencode call when all deduped; logs unseen count |
| Keyword filter | 4 | Keeps matching titles (case-insensitive); empty when no matches; no opencode call; logs filtered count |
| Sorting/limit | 2 | Sorts by score descending; respects prefilter_limit |
| Opencode call | 4 | Uses config model; sends --format json; includes titles/URLs in prompt; fails on invalid JSON response |
| Output | 3 | Writes output file; valid JSON array; contains ranked items |
| Logging | 3 | Logs start date; logs final count; logs raw item count |

---

### `briefing.bats` — 36 tests

**Script:** `scripts/news/briefing.sh`

| Area | Tests | What they verify |
|------|------:|-----------------|
| Preconditions | 3 | Exits when KILLED; exits when PAUSED; succeeds when clean |
| Subprocess invocation | 4 | Calls fetch.sh; calls analyze.sh; aborts when fetch fails; aborts when analyze fails |
| No results handling | 4 | Exits gracefully without analyzed file; exits for empty array; no journal; no notify call |
| Briefing formatting | 4 | Logs item count; includes date in header; includes titles; includes URLs and summaries |
| Journal delivery | 2 | Writes journal when enabled; skips when disabled |
| Telegram delivery | 3 | Calls notify.sh when enabled; passes briefing text; skips when disabled |
| Dedup cache | 4 | Adds URLs to cache; cache contains analyzed URLs; entries have first_seen; preserves existing entries |
| Dedup pruning | 3 | Prunes old entries; keeps recent entries; logs cache size |
| File cleanup | 3 | Preserves today's raw file; preserves today's analyzed file; logs cleanup step |
| Logging | 5 | Logs start banner with date; logs "Briefing complete!"; logs fetch/analyze/format steps |

---

### `vision.bats` — 12 tests

**Script:** `scripts/capabilities/vision/vision.sh`

| Area | Tests | What they verify |
|------|------:|-----------------|
| Core behavior | 5 | Returns text from NDJSON; uses --format json; uses -f for image; default prompt; custom prompt |
| Model selection | 2 | Uses default model without file; reads from state/telegram_model.txt |
| Input validation | 2 | Exits without image path; exits for missing file |
| Error handling | 3 | Reports model-not-found; error for no text output; calls opencode once |

---

### `screenshot.bats` — 14 tests

**Script:** `scripts/capabilities/screenshot/screenshot.sh`

| Area | Tests | What they verify |
|------|------:|-----------------|
| Happy path | 5 | Returns OK with file path; calls npx playwright; creates file; sends via sendPhoto; includes token |
| URL handling | 2 | Prepends https:// when missing; preserves http:// |
| Caption | 2 | Uses URL as default caption; uses custom caption |
| Error handling | 4 | Fails without URL; reports playwright failures; falls back to sendDocument on sendPhoto error; fails without credentials |
| Viewport | 1 | Uses 1280x900 dimensions |

---

### `status.bats` — 11 tests

**Script:** `scripts/observability/status.sh`

| Area | Tests | What they verify |
|------|------:|-----------------|
| State reporting | 4 | RUNNING when clean; PAUSED when paused; KILLED when killed; KILLED takes precedence over PAUSED |
| Cron parsing | 4 | Shows "(none)" without jobs; detects briefing job; recognizes old path; formats weekday 08:00 schedule |
| Edge cases | 3 | Labels unrecognized jobs; exits 0 on crontab error; always exits 0 |

---

### `usage_estimate.bats` — 14 tests

**Script:** `scripts/observability/usage_estimate.sh`

| Area | Tests | What they verify |
|------|------:|-----------------|
| Input validation | 2 | Usage help when input_tokens=0; usage help with no arguments |
| Logging | 4 | Appends JSONL line; entry contains operation name; correct token count; input/output counts |
| Model selection | 2 | Defaults to sonnet; uses opus when specified |
| Display | 4 | Shows "Logged:" confirmation; session usage %; weekly usage %; total tokens |
| Rolling window | 1 | Session total only includes last 5 hours |
| Health | 1 | Shows "healthy" below 50% |

---

### `wizard.bats` (integration) — 18 tests

**Scripts:** `scripts/setup/wizard.sh`, `scripts/setup/steps/kb_wizard.sh`

| Area | Tests | What they verify |
|------|------:|-----------------|
| Full wizard flow | 5 | End-to-end: creates all identity files, .env, opencode.json, and verifies; handles existing installation detection; repair mode integration |
| KB wizard interactive | 5 | Prompts for name, path, description, model, access; validates inputs; creates scaffold; registers KB |
| KB wizard --quick | 3 | One-liner scaffold; fails without required args; custom model and access options |
| Error handling | 5 | Graceful exit on Ctrl-C; reports validation errors; handles missing dependencies |

---

### `journal_rotate.bats` (integration) — 9 tests

**Script:** `scripts/observability/journal_rotate.sh`

| Area | Tests | What they verify |
|------|------:|-----------------|
| End-to-end rotation | 3 | Archives old entries, cleans news, rotates logs in one invocation; correct archive directory structure; idempotent re-run |
| News pipeline cleanup | 2 | Removes raw + analyzed files older than retention; preserves today's pipeline files |
| Log rotation | 2 | Rotates large logs; preserves small logs |
| Integration with state | 2 | Works with realistic journal directory; handles concurrent state access |

---

### `kb.bats` (integration) — 18 tests

**Scripts:** `scripts/capabilities/kb/query.sh`, `scripts/messaging/telegram/commands.sh`, `adjutant` CLI

| Area | Tests | What they verify |
|------|------:|-----------------|
| Full lifecycle | 3 | Create/list/info/remove cycle; multiple KBs coexist; scaffold on existing directory with content |
| Query pipeline | 8 | Parses NDJSON and returns text; handles multi-part text responses; returns fallback for empty response; fails for non-existent KB; passes correct model; uses inherited model from telegram state; passes --dir flag; passes --agent kb flag |
| Telegram /kb command | 2 | cmd_kb list shows registered KBs; cmd_kb with no args defaults to list |
| CLI routing | 2 | `adjutant kb help` shows usage; `adjutant kb list` shows empty state |
| Quick create wizard | 3 | Scaffolds and registers; fails without required args; custom model and access |

---

## Tier 3 — System Tests (Planned)

Scripts that require full process isolation to test safely:

| Script | What it does | Why it needs system-level testing |
|--------|-------------|----------------------------------|
| `scripts/lifecycle/emergency_kill.sh` | Nuclear shutdown — kills all Adjutant processes by pattern, removes crontab, creates KILLED lockfile | Terminates multiple process families with `pkill`, runs `crontab -r`. Irreversible side effects that cannot be mocked safely. |
| `scripts/lifecycle/startup.sh` | Normal startup and emergency recovery | Interactive `read -p` prompts, daemon start with `nohup`, crontab manipulation. |
| `scripts/lifecycle/restart.sh` | Stop + start with confirmation prompt | Interactive prompt, process kills via PID files, delegates to startup.sh. |
| `scripts/messaging/telegram/service.sh` | Telegram listener daemon manager | PID-based process manager that starts background daemons, sends signals, handles stale PID cleanup. |
| `scripts/messaging/telegram/listener.sh` | Infinite Telegram polling loop | Long-running daemon with `while true`, signal trap handlers, persistent state across poll cycles. |
