# Durable Operations and Persistent Backend: Implementation Plan

**Date:** 2026-09-23
**Status:** Complete through Stage 8
**Branch:** `feature/durable-operations`
**Source:** Repository review and GPT-6 Astra architecture planning session

---

## Objective

Adjutant must accept Telegram work durably, keep control commands responsive, report observable progress, allow cancellation, and deliver the eventual result even when an LLM operation lasts longer than 240 seconds or the listener restarts. The implementation must preserve the backend abstraction and KB isolation while reducing avoidable process-startup latency.

The work separates two concerns:

1. A backend-independent operation runner provides durable acceptance, execution state, restart recovery, cancellation, and result delivery.
2. Backend transports provide execution. The first transport streams subprocess events. A managed persistent OpenCode server can follow after measurements and isolation tests support it.

Native OpenCode sub-agents may divide work inside an operation. They do not replace the operation runner or the KB security boundary.

---

## Verified Baseline

- `opencode_run()` buffers stdout and stderr through `proc.communicate()`.
- Timeout handling terminates the process and replaces captured output with empty bytes.
- KB writes use `run_detached()` and return no durable operation identifier.
- The Telegram listener persists the batch offset before dispatching its updates.
- Conversational turns and their ordering exist only in the process-local `_INFLIGHT` map.
- Long slash commands can run inside the polling loop.
- `msg_send_text()` suppresses delivery errors, while callers may log successful delivery.
- Telegram text is clamped to 4,000 characters instead of being delivered in chunks.
- `active_operation.json` represents one operation and cannot safely describe concurrent work.
- OpenCode cleanup compares global language-server PID snapshots, which is unsafe under concurrent or persistent execution.
- `llm.caps.session_tokens` feeds usage estimation but does not rotate or summarize chat sessions.
- Telegram currently resolves to `openai/gpt-5.6-terra` with `high` reasoning. Recent logged operations range from seconds to 82 seconds, with one 240-second timeout. Existing timings do not isolate startup, provider, reasoning, retrieval, or composition latency.

---

## Target Architecture

```text
Telegram update
    |
    v
Durable inbox transaction
    |-- accepted update record
    |-- operation record
    `-- Telegram offset advancement
    |
    v
Supervised operation worker
    |-- OpenCode streaming subprocess
    |-- Claude CLI subprocess
    `-- optional managed OpenCode server
    |
    |-- normalized progress events
    |-- persisted result or structured failure
    `-- cancellation and reconciliation evidence
    |
    v
Durable outbound delivery
    |-- status message updates
    |-- final reply chunks
    `-- retry and ambiguous-delivery handling
```

SQLite under `state/` will provide atomic transitions without adding an external service. Model and network work must occur outside database transactions.

### Operation states

```text
queued -> starting -> running -> succeeded | failed | timed_out
                         |-> waiting_children -> running
                         |-> waiting_input -> running
                         `-> cancel_requested -> cancelled

starting/running + lost ownership -> reconciling
reconciling -> running | succeeded | failed | interrupted
```

Delivery state is independent:

```text
pending -> sending -> delivered
             `-> retry_wait -> sending
             `-> blocked
```

An operation may complete while delivery remains pending. An interrupted mutation may have uncertain external effects and must not be replayed automatically.

---

## Data Model

An operation records its stable ID, schema version, type, origin, Telegram update/chat/message identity, parent and dependency IDs, backend, model, variant, agent, resolved workspace reference, permission fingerprint, state, attempt number, lease, cancellation request, timestamps, result reference, normalized error, side-effect classification, and recovery status.

An execution attempt records the owned PID and process birth time, process group or server instance, backend session and message IDs, exit status, timeout reason, and resource measurements.

Events use a monotonically increasing sequence per operation. Deliveries record their destination, payload or result reference, chunk number, Telegram message ID, retry time, and last error.

Telegram ingestion uses a unique key based on bot identity and update ID. Acceptance and offset advancement occur in one transaction so repeated ingestion returns the existing operation.

---

## Backend Interface

Keep `get_backend()` and the existing `run()` interface during migration. Add a typed execution interface that emits normalized events:

- `started` and `session_started`
- `tool_started` and `tool_finished`
- `text_delta` and `usage`
- `waiting_input`
- `completed` and `failed`

`run()` can collect the event stream into `LLMResult` for compatibility. Execution handles provide cancellation and reconciliation. Backend capabilities will distinguish event streaming, persistent sessions, reconnection, and native abort support.

OpenCode must drain stdout and stderr concurrently, parse NDJSON incrementally, retain bounded diagnostics, preserve partial output, and clean up only its owned process tree on timeout or cancellation. Claude CLI can initially emit lifecycle and elapsed-time events while retaining its JSON response format.

---

## Telegram Experience

- Persist accepted work before acknowledging it.
- Send a short acknowledgement containing an operation ID.
- Edit one status message with observable progress and elapsed-time updates.
- Do not expose hidden reasoning or sensitive tool arguments.
- Add `/operations`, `/operation <id>`, and `/cancel <id>`.
- Extend `/status` with queued and active work.
- Keep control commands outside model execution and responsive during long work.
- Persist the complete result before delivery and split it at paragraph boundaries.
- Record Telegram API receipts and retry failed delivery.

Conversation sessions retain one writer. Long work moves to its own operation session. Dependent follow-ups wait for the referenced operation; unrelated work may use another session.

---

## Persistent OpenCode Trial

The installed OpenCode version supports `run --attach`, `--dir`, `--session`, and JSON output. The first trial will keep the CLI adapter and attach it to a supervised server. Direct HTTP and SSE integration can follow if the trial establishes a benefit.

Each instance will bind to loopback with authentication, record its ownership and configuration, start on demand, pass a health check, stop after an initial 15–30 minute idle interval, and drain under configuration changes or sustained memory pressure. Resource accounting includes owned MCP and LSP descendants.

Soft and hard memory limits will be selected after soak measurements. The soft limit stops new assignments and drains the instance. The hard limit may terminate an unhealthy instance, after which affected operations enter reconciliation.

---

## KB Isolation Gate

Persistent KB workers remain disabled until fixture tests cover outside-directory access, read-only mutation denial, shell restrictions, symlink escapes, root and KB configuration precedence, cross-KB session contamination, permission changes, and child-agent permission inheritance.

Keep actual KB access behind the KB APIs. A separate process and working directory alone do not constitute an operating-system sandbox.

---

## Documentation Deliverables

- [x] Update `docs/architecture/backends.md` with execution events, persistent transport capabilities, and process ownership.
- [x] Add `docs/architecture/operations.md` covering the operation, attempt, event, delivery, and recovery models.
- [x] Update `docs/architecture/identity.md` where conversational and operation sessions interact.
- [x] Update `docs/development/backend-guide.md` with the streaming interface and compatibility adapter.
- [x] Update `docs/development/testing.md` with crash, cancellation, delivery, and memory soak tests.
- [x] Update `docs/development/plugin-guide.md` if capability invocation changes.
- [x] Update `docs/guides/commands.md` with operation status and cancellation commands.
- [x] Update `docs/guides/configuration.md` with operation, worker, timeout, retention, and persistent-server settings.
- [x] Update `docs/guides/knowledge-bases.md` with tracked KB operations and verified isolation limits.
- [x] Update `docs/web/` when the dashboard moves from the single active-operation marker to the operation list.
- [x] Update `.opencode/agents/adjutant.md` with delegation, operation IDs, and verified-completion rules.
- [x] Update `adjutant.yaml.example` alongside every new configuration field.

Documentation changes ship in the same increment as the behavior they describe.

---

## Implementation Stages

### Stage 1: Measurement and immediate correctness

- [x] Add correlation IDs and stage timing.
- [x] Return structured Telegram delivery receipts and stop logging unverified success.
- [x] Report configured timeout values instead of a hard-coded 240 seconds.
- [x] Preserve bounded partial output on timeout.
- [x] Replace global PID-difference cleanup with operation ownership.
- [x] Add tests for delivery failure, timeout output, cancellation cleanup, and concurrent process ownership.

Acceptance: delivery failures cannot be recorded as delivered; timeouts retain bounded partial evidence; concurrent calls cannot kill unrelated processes.

### Stage 2: Durable acceptance and worker

- [x] Add the operations SQLite schema and migrations.
- [x] Commit Telegram acceptance and offset advancement atomically.
- [x] Add a supervised worker with leases and bounded concurrency.
- [x] Add durable outbound delivery and retry.
- [x] Recover queued and completed-but-undelivered operations after restart.

Acceptance: fault injection between receipt, execution, result persistence, and delivery loses no accepted request and does not rerun a persisted result.

### Stage 3: Streaming and controls

- [x] Add incremental OpenCode NDJSON parsing.
- [x] Add normalized execution events and progress updates.
- [x] Add operation status and cancellation commands.
- [x] Split acknowledgement, startup, progress-warning, connection, cancellation, and runtime timeouts.

Acceptance: a fixture operation exceeding 240 seconds completes; status and cancellation remain responsive; blocked stdout or stderr cannot deadlock execution.

### Stage 4: Tracked KB operations

- [x] Replace KB `run_detached()` writes with durable submission.
- [x] Track parent and child operation IDs.
- [x] Add KB query, status, result, and write-verification flows.
- [x] Prevent bounded-worker parent/child deadlocks.

Acceptance: every KB submission has an inspectable terminal or reconciliation state and a known delivery destination when applicable.

### Stage 5: Conversation delegation

- [x] Give long operations separate sessions.
- [x] Track follow-up dependencies and serialize continuation into the main conversation.
- [x] Allow unrelated work without overlapping writers on one session.

Acceptance: unrelated work proceeds during a long operation, dependent follow-ups retain context, and session writers never overlap.

### Stage 6: Persistent OpenCode experiment

- [x] Add managed server ownership, health, drain, and restart behavior.
- [x] Trial the existing CLI adapter with `--attach`.
- [x] Add session reconciliation and native abort where verified.
- [x] Run latency, memory, reconnect, and KB isolation experiments.

Acceptance: the trial demonstrates measured latency improvement, bounded processes and memory, passing isolation fixtures, and no automatic replay after uncertain execution.

### Stage 7: Broader adoption and retention

- [x] Move pulse, review, photo, and web operations onto the operation layer.
- [x] Replace the single active-operation marker with operation-list compatibility.
- [x] Add retention for operation events, result artifacts, deliveries, and Adjutant-owned backend sessions.

Acceptance: every entry point reports status and delivery consistently, and retention never deletes unrelated OpenCode sessions.

### Stage 8: Nested KB deadline and recovery hardening

Detailed plan: [Nested KB Timeout and Recovery Plan](nested-kb-timeout-recovery.md)

- [x] Atomically create, claim, and start inline KB child attempts.
- [x] Fence state changes and completion by current attempt ownership.
- [x] Propagate persisted parent deadlines into child runtime budgets.
- [x] Add a scoped OpenCode hook that extends only recognized nested KB shell calls.
- [x] Emit the child operation ID before backend execution.
- [x] Recover expired inline leases during normal daemon operation.
- [x] Close attempts and preserve mutation uncertainty during recovery.
- [x] Verify caller death, timeout, cancellation, concurrency, and Telegram behavior with process-level fixtures.

Acceptance: nested KB work can exceed OpenCode's 120-second shell default without exceeding its parent deadline; an interrupted mutation becomes inspectable reconciliation work promptly and is never replayed automatically; stale attempts cannot overwrite recovered state.

---

## Rollout and Rollback

The durable runner and persistent transport use separate feature flags. Accepted operations freeze their backend, model, and variant. Rollback stops new runner submissions, drains or reconciles active work, keeps result delivery running, and then routes new requests through the legacy path. The operation database and result artifacts remain available after rollback.

The complete Python test suite must pass before release. Dispatch authorization, rate limiting, and feature gates must remain intact.

---

## Progress Record

This section is updated when an item is completed. Each entry records what changed, how it works, verification, and any follow-up created by the implementation.

### 2026-09-23: Plan established

**Completed:** Saved the repository-backed Astra planning result, created branch `feature/durable-operations`, expanded documentation work into explicit deliverables, and established the progress-record convention.

**How:** The plan separates durable orchestration from backend transport so reliability work applies to OpenCode and Claude CLI. Persistent OpenCode remains an independently controlled experiment.

**Verification:** Confirmed the branch with Git and preserved the pre-existing untracked `.codex/` directory and `.opencode/package-lock.json` without modification.

### 2026-09-23: Telegram delivery receipts

**Completed:** Added the first Stage 1 correctness item. `msg_send_text()` now returns a `TelegramDeliveryReceipt` containing confirmed delivery state, Telegram message ID, Markdown-fallback use, uncertainty, and an error description. Natural-chat dispatch records delivery only when Telegram returned `ok: true`.

**How:** The send path validates Telegram's response instead of treating a completed HTTP call as proof of delivery. It records explicit rejections separately from network-ambiguous failures. The existing Markdown parse-error retry now returns the result of its plain-text attempt. Dispatch logs confirmed, failed, and uncertain outcomes with different messages.

**Verification:** Added tests for confirmed delivery, rejected delivery, network ambiguity, plain-text fallback, empty messages, and dispatch logging. `tests/unit/test_telegram_send.py` and `tests/unit/test_messaging_dispatch.py` pass with 54 tests.

**Follow-up:** Other command and lifecycle senders can ignore the receipt safely during migration. The durable outbound queue in Stage 2 will consume the same receipt type and persist retry decisions.

### 2026-09-23: Accurate chat timeout reporting

**Completed:** Removed the hard-coded 240-second value from Telegram chat timeout logs and user-facing timeout responses.

**How:** `run_chat()` now uses the resolved `messaging.telegram.chat_timeout_seconds` value both when invoking the backend and when explaining a timeout. Anthropic-specific guidance remains conditional on the resolved model.

**Verification:** Added a configuration-driven test using a 615-second timeout and verified that both the backend call and response use 615 seconds. The Telegram chat, send, and dispatch test selection passes with 78 tests.

### 2026-09-23: Partial output and owned process cleanup

**Completed:** OpenCode timeouts now preserve partial stdout and stderr, and timeout or Python-task cancellation terminates the invocation's owned process group. The invocation path no longer snapshots all system language-server PIDs and kills every process that appeared while it ran.

**How:** `opencode_run()` starts OpenCode in a new process session, shields output collection from the timeout wrapper, signals the owned process group on timeout or cancellation, reaps the parent, and then collects the closed pipes. Timeout evidence retains the beginning and end of each stream within a 256 KiB limit. `OpenCodeBackend.run()` therefore returns partial parsed text together with `timed_out=True` and `error_type="timeout"`.

**Verification:** Added process-level tests showing that timeout preserves an emitted NDJSON text event, cancellation completes within two seconds, terminating an OpenCode fixture leaves an unrelated process alive, and one timed-out invocation cannot terminate a concurrent invocation. Added a backend test showing that partial text survives parsing. The OpenCode core and backend selection passes with 24 tests after removing the obsolete PID-snapshot helper and its test.

**Follow-up:** The periodic orphan and RSS reaper remains available for processes left by older failures. Stage 3 will replace buffered `communicate()` collection with incremental event parsing, which also bounds memory during execution rather than only bounding retained timeout evidence.

### 2026-09-23: First-slice regression verification

**Completed:** Ran the complete Python unit suite after the first Stage 1 implementation slice.

**Verification:** The final first-slice state passes with `1457 passed, 74 skipped` in 5.92 seconds. The test count dropped by one because the obsolete global PID-snapshot helper and its dedicated test were removed with the implementation they covered.

### 2026-09-23: Correlation IDs and execution phase timing

**Completed:** Finished the remaining Stage 1 implementation item. Backend calls accept an optional correlation ID, generate one when absent, propagate it through the subprocess environment, return it on `LLMResult`, and include it in backend logs. Results also expose spawn, execution, cleanup, parsing, and total durations.

**How:** Added the shared `ExecutionTimings` contract, measured subprocess phases inside both backend adapters, and connected Telegram text, screenshot, and photo work to stable message-derived identifiers. Updated the backend architecture and developer documentation with the new contract and process-ownership rules.

**Verification:** Backend, contract, OpenCode process, Telegram chat, photo, and dispatch selections pass with `155 passed, 27 skipped`.

**Follow-up:** Durable operations will pass their operation ID as the correlation ID. Timing fields provide the baseline for the persistent-server trial and distinguish process spawn cost from provider and tool execution.

### 2026-09-23: Durable operation store

**Completed:** Added the Stage 2 SQLite foundation under `state/operations.sqlite3`. The schema stores operations, Telegram inbox records and offsets, ordered events, execution attempts, and independent outbound deliveries. It records parent and dependency relationships, frozen backend settings, leases, cancellation requests, results, errors, recovery state, and side-effect classification.

**How:** `OperationStore` uses WAL mode, foreign keys, a bounded busy timeout, and short `BEGIN IMMEDIATE` transactions for claims and sequence allocation. It validates operation state transitions, claims each queued item once, waits for dependencies to succeed, advances Telegram offsets inside the same transaction as inbox acceptance, and keeps delivery state independent from execution state. Schema initialization is idempotent and records version 1 in the metadata table.

**Verification:** Ruff passes for the new operations package and tests. `tests/unit/test_operations_store.py` passes with 13 tests covering initialization, create/read, valid and invalid transitions, dependency ordering, concurrent claims, queued and running cancellation, Telegram deduplication and monotonic offsets, event sequencing, and delivery success and retry.

**Follow-up:** The execution-attempt table is present for worker evidence. Worker and recovery code will add the attempt lifecycle and expired-lease reconciliation behavior.

### 2026-09-23: Durable acceptance, execution, delivery, and recovery

**Completed:** Finished Stage 2 behind `operations.enabled`. Natural-language Telegram messages can now commit their inbox record, frozen execution settings, queued operation, and next Telegram offset in one transaction. Startup manages a separate bounded worker process before it starts the listener. The worker records attempts and events, renews leases, observes cancellation, stores the complete terminal result, and creates every outbound delivery chunk in the same transaction. A separate delivery loop records confirmed Telegram message IDs and retries rejected or ambiguous sends with a bounded exponential schedule.

**How:** Added operation service, worker, delivery, recovery, daemon, and process-lifecycle modules. Worker startup requeues expired read-only or idempotent work, sends unknown or mutating work to reconciliation, and returns expired sending records to retry wait with the ambiguity flag set. Results split at paragraph, line, or word boundaries instead of losing text at Telegram's length limit. Configuration now separates worker concurrency, runtime, lease, cancellation, delivery, retention, and persistent-OpenCode experiment settings.

**Verification:** A focused regression run passes with `135 passed, 5 skipped`. New tests cover atomic and duplicate acceptance, frozen backend selection, concurrent claims, attempt evidence, dependencies, cancellation, timeout, lease recovery by side-effect class, atomic result and delivery creation, complete multi-chunk output, confirmed receipts, ambiguous retry, and restart delivery of a persisted result without another backend attempt. Added the operation architecture guide and updated configuration, backend, testing, example configuration, and documentation navigation.

**Follow-up:** The durable feature remains opt-in during migration. Stage 3 adds incremental backend events, progress delivery, responsive operation commands, and the remaining timeout classes before broadening entry-point coverage.

### 2026-09-23: Streaming events, progress, controls, and timeout policies

**Completed:** Finished Stage 3. OpenCode now drains stdout and stderr concurrently, publishes complete NDJSON records before process exit, maps backend records to the shared execution-event contract, and retains bounded raw diagnostics and recent raw events. Claude CLI exposes the same started and terminal lifecycle interface around its collected JSON response. Durable workers persist safe public events, omit text deltas from the event database, edit the acknowledgement through the outbound queue, and record a quiet-progress warning without treating silence as failure.

**How:** Added `ExecutionRequest`, `ExecutionEvent`, and the normalized event types while retaining `run()` as the compatibility result interface. Backend startup and operation runtime use separate deadlines. Configuration also separates acknowledgement target, connection attempt, quiet-progress warning, lease, and cancellation-grace limits. Added `/operations`, `/operation <id>`, and `/cancel <id>` as direct control paths, and extended `/status` with active and queued counts. The final reply still comes from the persisted result and is independent of status-message edits.

**Verification:** The Stage 3 regression selection passes with `232 passed, 28 skipped`. Process fixtures prove that an stdout event arrives while the process is still running, a one-megabyte stderr stream cannot deadlock execution, retained stderr stays bounded, startup timeout is distinct from runtime timeout, and the normalized OpenCode stream hides tool arguments. Worker and Telegram tests cover quiet-progress warnings, durable status edits, final reply delivery, command inspection, and cancellation.

**Follow-up:** The runtime ceiling defaults to 1,800 seconds, so durable operations are no longer governed by the legacy 240-second chat deadline. A production soak lasting more than 240 seconds remains part of the persistent-transport experiment and release validation.

### 2026-09-23: Tracked KB operations

**Completed:** Finished Stage 4 for the durable path. Single-KB reads and writes create operations with frozen backend, model, reasoning variant, KB workspace, agent, parent ID, and side-effect class. Telegram returns the operation ID and the worker delivers the persisted result. CLI callers can inspect work with `adjutant kb status <id>` and retrieve the terminal result with `adjutant kb result <id>`.

**How:** Read operations are replay-safe. Writes are mutating and include a required post-mutation read of the authoritative target plus concrete verification evidence in the prompt. Read-only registries reject tracked writes before execution. A KB CLI invoked inside a parent operation inherits the parent ID, records a child, and executes the child inline through the same worker lifecycle. This preserves tracking while avoiding the pool deadlock where every parent waits for a queued child.

**Verification:** KB, CLI, operation, session, command, and dispatch selections pass with `162 passed`. Tests cover frozen KB boundaries, read and mutation classification, parent linkage, verification prompts, persisted status and result access, and inline child completion while the parent remains outside the child claim path.

**Follow-up:** The legacy detached write remains available only when durable operations are disabled for rollback. Persistent KB server reuse remains gated on the isolation experiment.

### 2026-09-23: Operation-owned conversation sessions

**Completed:** Finished Stage 5. Each durable chat turn owns its backend execution instead of sharing a writable backend session. The worker builds bounded context from completed earlier turns. A message that names an operation ID or replies to its Telegram acknowledgement links to that operation; an unfinished target becomes a dependency.

**How:** Successful dependency results and recent completed turns are serialized into the new operation's prompt. Failed dependencies terminate queued follow-ups with `dependency_failed` instead of leaving them queued forever. Messages without an explicit target have no dependency and may use the configured worker concurrency. Separate operation-owned executions prevent overlapping writers on one backend session.

**Verification:** Session tests cover explicit ID and Telegram-reply resolution, dependency creation, bounded completed-turn context, and unrelated acceptance. A worker concurrency test holds two unrelated handlers active simultaneously and verifies that both finish as independent operations.

**Follow-up:** Explicit operation IDs and Telegram replies are the supported targeting mechanisms. Adjutant does not infer that every adjacent message depends on unfinished work.

### 2026-09-24: Managed persistent OpenCode transport

**Completed:** Finished Stage 6 behind `operations.persistent_opencode.enabled`. Adjutant can start one authenticated loopback `opencode serve` instance, attach the existing JSON CLI adapter, reuse a healthy instance, drain it on idle or soft memory pressure, stop it at the hard limit, and replace dead or unhealthy ownership. Server state records instance ID, PID, process creation time, version, status, last use, and restart count. The generated password is stored separately with mode 0600.

**How:** `ManagedOpenCodeServer` verifies PID creation time and the `serve` command before signalling a process group. Health uses `/global/health`. Attached cancellation and timeout use `/session/:id/abort` after the stream reveals a session ID. A CLI disconnect queries `/session/status`, returns `reconciliation_required`, and does not submit the prompt again. Startup, connection, runtime, cancellation, idle, soft-memory, and hard-memory limits remain distinct. A backend result records its server instance and timeout phase on the execution attempt.

**Verification:** The installed OpenCode 1.18.0 trial became healthy in 0.577 seconds and reused the same instance in 0.012 seconds. Three identical cold prompts took 4.595, 7.150, and 4.859 seconds; three attached prompts took 2.747, 3.092, and 5.812 seconds. Median latency fell from 4.859 to 3.092 seconds, or 36.4 percent, and all results matched. After five more attached calls, RSS rose from 381 MB before model work to 693 MB and remained below the 900 MB trial soft limit. A separate 600 MB policy trial stopped a 666 MB idle server. Forced process death produced a new healthy instance with one root process and 379 MB RSS. Native abort, connection timeout, uncertain-disconnect reconciliation, restart backoff, ownership, secret handling, and memory policy have deterministic tests.

**Follow-up:** Persistent reuse stays disabled for `kb_query` and `kb_write`. The dual-workdir fixture confirms that two KB calls use distinct sessions and never receive `--attach`; the existing KB permission fixtures confirm external-directory denial and read-only edit/write/bash denial. This keeps the stronger persistent KB isolation gate closed while allowing persistent transport for Adjutant-owned non-KB operations.

### 2026-09-24: Broader operation adoption and retention

**Completed:** Finished Stage 7. Telegram photo updates commit an operation and bot offset before download. Telegram, cron, and Adjutant Web pulse/review requests submit tracked operations. The web API returns the accepted operation ID when durable mode is active. Local clients read `state/active_operations.json`, which lists concurrent queued and running work, and fall back to the legacy single marker only while the rollback path is active.

**How:** Photo download and vision extraction now run inside the tracked worker attempt before the main-agent prompt. Terminal results and Telegram deliveries still commit together. Hourly maintenance applies server policy and independent retention ages for events, completed operation results, delivery evidence, and backend sessions. Session deletion only considers IDs recorded with both an Adjutant operation attempt and a managed server instance. A failed deletion protects the operation record so maintenance can retry later.

**Verification:** Tests cover durable photo acceptance, tracked vision preparation, Telegram prompt destinations, cron and web source attribution, operation-list snapshots, active dependency protection, owned-session deletion, and preservation after a failed session cleanup. The Web API suite passes with 99 tests, the frontend TypeScript check passes, the KB isolation selection passes with 103 tests, the Stage 7 focused Python selection passes with 78 tests, the full Python unit suite passes with `1520 passed, 75 skipped`, and the integration suite passes with 19 tests.

**Follow-up:** The release audit also corrected the existing API TypeScript annotations in `sessions.ts` and `folderService.ts`. The API now passes its standalone strict TypeScript check as well as the production build.

### 2026-09-24: Release audit and long-operation soak

**Completed:** Closed the final verification gap. A durable fixture operation ran inside `OperationWorker` for 241.019 seconds, crossed the former 240-second Telegram boundary, and finished as `succeeded`. The store retained `soak-complete` as its result and recorded exactly one execution attempt with state `succeeded`.

**How:** The soak used the production operation store and worker lifecycle with a 300-second runtime ceiling. The handler intentionally remained silent for 241 seconds. The worker kept the lease and operation state active, then persisted the terminal result after the handler returned. No backend or network service was involved, so the result isolates the durable runner's long-operation behavior.

**Verification:** The managed-server restart-backoff policy has a direct regression test. The active-operation compatibility snapshot has a 24-writer concurrency test and serializes generation through SQLite. The latest Python suite passes with `1545 passed, 75 skipped`; the Web API suite passes with `99 passed`; the API and frontend strict TypeScript checks pass; and the API, frontend, and documentation production builds pass. Ruff passes for every changed Python source file and every new operation test. `git diff --check` passes, and no implementation or documentation checkbox remains open. The repository-wide Ruff baseline still reports older findings in files outside this plan's changes.

### 2026-09-24: Live Telegram reconciliation and nested-KB correction

**Completed:** Corrected defects exposed by the first live IxDA query. A persistent-session disconnect returned `reconciliation_required`, but the worker attempted the invalid direct transition from `running` to `interrupted`; it now records `reconciling` first and then commits the terminal interrupted result. Raw OpenCode error records remain internal until the adapter knows the terminal outcome, so Telegram no longer receives a premature backend-error status.

**How:** Persistent server tools do not inherit environment variables from the attached CLI process. The worker now places the current operation ID in an internal runtime-context block and tells nested Adjutant KB commands to pass it as `ADJUTANT_PARENT_OPERATION_ID`. The resulting KB operation is linked to its Telegram parent and executes inline without consuming another worker slot. Soft-memory drain now protects active clients, routes new assignments through isolated CLI execution, and stops the server only after the active count reaches zero. The live hard limit remains unset until nested workloads establish a safe threshold; the 900 MB soft limit remains enabled.

**Verification:** The failed operation `op-098c760721fc4b4d97adda16fd26aebd` was repaired to `interrupted`. Linked retry `op-4e2fe727473f46e9b991e7ba57a07739` created child KB operation `op-4a300cc1dbdd4a92bbdf8bf149581da6`; both finished as `succeeded`, and Telegram confirmed final delivery as message 4779. Regression tests cover reconciliation transitions, internal parent-ID propagation, suppression of premature error status, draining-server fallback, and stop-after-drain behavior.

### 2026-09-24: Telegram debug output, typing, and portfolio schedule repair

**Completed:** Put automatic operation acknowledgements and lifecycle status edits behind `operations.debug`, defaulted the flag to `false`, and restored Telegram's `typing` action for durable operations. Repaired the missing isolated Python environment for the registered portfolio KB.

**How:** Telegram only stores a status-message ID when debug output is enabled, so the existing delivery worker naturally skips operation-ID status edits when the flag is off. The listener loads the flag at startup; changing it requires an Adjutant restart and does not add runtime configuration polling. The operation worker starts a per-operation typing loop for Telegram work and stops it in a `finally` block after every terminal path. The portfolio KB lives in iCloud Drive, where the standard-library virtualenv symlink failed, so its environment was rebuilt with `uv` and copy-mode dependency installation.

**Verification:** Configuration, Telegram command, and operation worker tests pass with `80 passed`; the complete Python suite passes with `1548 passed, 75 skipped`; the documentation production build and `git diff --check` pass. A direct run of the configured `portfolio_fetch` schedule completed successfully and updated a snapshot containing nine positions, cash, position value, and total portfolio value. Adjutant restarted with operation worker PID 94403 and listener PID 94415, and the loaded configuration reports `operations.debug=False`. Documentation now describes the debug flag, typing lifecycle, and the iCloud-compatible KB environment command.

### 2026-09-24: Nested KB timeout and recovery planning

**Completed:** Reopened the plan with Stage 8 and saved a focused Astra architecture plan for the nested KB timeout and stranded-attempt defect.

**How:** The planning session traced the live parent, query child, write child, OpenCode tool transcript, lease expiry, and recovery path. It retained inline execution to avoid worker-pool deadlock, selected OpenCode's supported `tool.execute.before` hook for a narrowly scoped KB shell timeout, and coupled that change with atomic child claim, persisted deadlines, attempt fencing, early child receipts, and continuous expired-lease recovery.

**Verification:** Confirmed that the parent completed in 234.5 seconds under its 1,800-second ceiling, the query child succeeded in 71.5 seconds, and the write command was killed by the shell tool at exactly 120,000 milliseconds. Confirmed that the mutating child remained `running` after its lease expired because recovery only runs at worker startup. Repository and installed-package inspection confirmed the hook surface and the OpenCode 1.18.0 shell timeout behavior. No runtime code, service, or live operation was changed during planning.

### 2026-09-25: Nested KB ownership, deadlines, and receipts

**Completed:** Finished Stage 8 ownership and deadline work. Attached KB children now commit acceptance, lease, execution attempt, CLI ownership, deadline, and accepted event atomically. Every worker mutation is fenced by the current attempt. Standalone KB work remains on the daemon queue, while attached work stays inline and cannot consume or race a top-level worker slot.

**How:** A top-level deadline freezes when its first attempt starts. Child submission validates the active parent attempt and reserves cancellation plus persistence time. The backend receives the remaining deadline. The OpenCode plugin changes only a recognized standalone KB bash call after `operation-context` validates its parent and attempt. The CLI flushes the child ID before starting the backend, and parent status lists attached KB children.

**Verification:** Store, worker, KB, CLI, backend, and JavaScript tests cover atomic ownership, frozen deadlines, stale fencing, quoted and compound shell forms, and receipt ordering. Installed OpenCode 1.18.0 loaded the plugin, preserved a receipt across a forced tool timeout, and completed a 121-second fixture with a 150,000 ms tool timeout.

### 2026-09-25: Continuous recovery and incident closure

**Completed:** Finished Stage 8 recovery, rollout, and live reconciliation. Daemon maintenance continuously recovers expired leases, closes the matching attempt, refreshes the compatibility snapshot, and cleans only the recorded process or persistent session after ownership is revoked. Parent cancellation applies only to execution children. Parent success cannot conceal unsettled child work. Claude attached children remain gated until their early-evidence fixture passes.

**How:** PID cleanup verifies creation time and command identity before signalling the recorded process group. Persistent cleanup verifies the managed server instance and aborts only the recorded session. Mutating uncertainty enters `reconciling` without replay. Catchable inline termination unwinds through a scoped SIGTERM handler, and SIGKILL or backend death is handled by lease recovery.

**Verification:** The stranded IxDA write `op-29e1f7dcd59f4c5898fc08d208831832` was recovered and verified through read-only operation `op-252f57f3509647d090259bfdd388c8e8`; the original write now records that evidence and is `succeeded`. Separate temporary write `op-9d079f23b4124c2b8e466338806184c3` and query `op-19310036163b4004bcda0a94366ea1a9` proved one-time mutation plus authoritative readback. The temporary KB was removed. Adjutant restarted on the new code with worker PID 14073 and listener PID 14078. The complete Python suite passes with `1568 passed, 75 skipped`; focused Ruff and mypy checks pass; `git diff --check` passes; and the Docusaurus production site builds successfully from the updated documentation source.
