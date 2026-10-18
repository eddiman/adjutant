# Nested KB Timeout and Recovery Plan

**Date:** 2026-09-24
**Status:** Implemented and verified
**Branch:** `feature/durable-operations`
**Source:** Repository review, live operation evidence, and GPT-6 Astra planning session
**Parent plan:** [Durable Operations and Persistent Backend](durable-operations.md)

---

## Objective

Allow a KB child operation to use the remaining durable-operation budget without widening every shell timeout. If the calling model tool, CLI process, backend, or worker disappears, Adjutant must close or recover the execution attempt promptly. A mutating child with uncertain effects must enter reconciliation and must never be replayed automatically.

The fix must preserve these existing behaviors:

- Inline KB execution does not consume another top-level worker slot, so a full worker pool cannot deadlock while every parent waits for a child.
- `operations.debug: false` suppresses automatic Telegram operation IDs and status edits.
- Telegram typing belongs to the parent operation and stops on every terminal parent path.
- Persistent OpenCode remains disabled for KB execution until the separate isolation gate passes.
- Adjutant accesses KB contents through the KB API only.

---

## Incident Evidence

The live request created parent `op-f01c9e65b5a547aeb33126a77717bfc0` at 19:20. The parent completed successfully after 234.5 seconds, below its 1,800-second durable runtime ceiling.

Child query `op-79b3f5e685cc48e39c18f34daf67f33b` succeeded after 71.5 seconds. The following inline write created child `op-29e1f7dcd59f4c5898fc08d208831832`, but OpenCode's `bash` tool terminated the CLI after exactly 120,000 milliseconds. The child remained `running` after its process disappeared. Its mutating lease expired at 19:25:07, but online maintenance did not recover it because expired-lease recovery currently runs only when the worker starts.

The agent did not receive the child ID before the shell command ended. It therefore queried the parent ID with `kb status`, received “not found,” and could not verify the write.

---

## Confirmed Root Causes

1. `OperationWorker` permits 1,800 seconds, while OpenCode's shell tool independently defaults to 120 seconds.
2. `_add_runtime_context()` propagates the parent ID but cannot enforce the shell tool's timeout argument.
3. Nested durable writes run inline in the calling CLI process. Tool termination stops lease renewal and ordinary Python cleanup.
4. Child creation and inline claim use separate transactions. The daemon can claim the queued child before the inline CLI does.
5. The CLI prints the child ID only after inline execution returns, so interrupted commands expose no accepted child ID.
6. Online maintenance does not sweep expired operation leases.
7. Lease recovery changes the operation row without closing its execution attempt.
8. State transitions and terminal completion do not fence a stale worker by attempt generation and current lease ownership.
9. Attempt PID, process-group, server-instance, and session evidence is often persisted only after execution completes.
10. `parent_id` also represents conversational follow-ups. Execution cancellation and deadline propagation cannot use every parent-child link indiscriminately.

---

## Design Decisions

### Retain inline KB execution

Keep attached KB children outside the bounded top-level worker pool. Moving them into the same queue while parents wait would restore the pool-exhaustion deadlock that inline execution solved.

Add an explicit execution relationship instead of inferring ownership from `parent_id`:

- execution mode: inline child or daemon queued;
- owning parent attempt ID;
- persisted absolute deadline;
- CLI owner PID and process birth time;
- optional originating backend session and tool-call IDs.

Conversational follow-ups may retain `parent_id`, but they are not execution children and do not receive cancellation or deadline propagation.

### Enforce a scoped OpenCode shell timeout

OpenCode provides a `tool.execute.before` plugin hook whose arguments are mutable. The official [plugin documentation](https://opencode.ai/docs/plugins/) describes tool argument modification. In OpenCode 1.18.0, the [tool execution path](https://raw.githubusercontent.com/anomalyco/opencode/v1.18.0/packages/opencode/src/session/tools.ts) invokes the hook immediately before execution, and the [shell tool](https://raw.githubusercontent.com/anomalyco/opencode/v1.18.0/packages/opencode/src/tool/shell.ts) uses `params.timeout` or its two-minute default.

Add `.opencode/plugins/adjutant-kb-timeout.js` with narrow matching:

- act only on the `bash` tool;
- accept only one standalone Adjutant KB query, write, query-all, or cross-query command;
- support the required `ADJUTANT_PARENT_OPERATION_ID=<id>` prefix and an optional direct `bash` launcher;
- reject pipelines, compound commands, background execution, and command substitutions for this privileged timeout path;
- ask a small Python operation-context helper for the validated remaining budget;
- set only that call's `output.args.timeout`;
- leave every unrelated shell call at OpenCode's normal timeout.

Prompt instructions document the supported form, but the hook and CLI enforce it. Prompt compliance alone is insufficient.

The repository's plugin type package and installed OpenCode binary have different version numbers. Use plain JavaScript for the hook and require an installed-version smoke test before rollout.

### Use one persisted deadline hierarchy

Set an absolute deadline when a top-level operation starts its first attempt. Freeze that deadline so restart or later configuration changes cannot extend accepted work.

For an attached child:

1. Read the active parent attempt and its remaining time.
2. Reserve the configured cancellation grace plus a five-second persistence and return margin.
3. Reject a new child when the remaining budget cannot cover cleanup.
4. Set the child deadline to the lower of its configured ceiling and the parent's usable remainder.
5. Pass that remaining budget to the backend.
6. Set the scoped shell timeout high enough for child cancellation and persistence, but below the parent's absolute deadline.

The CLI validates the deadline independently. A missing hook cannot grant a child more time than its parent.

### Fence attempts and recovery

Use the attempt ID or attempt number as an ownership generation. Lease renewal, event writes that imply execution ownership, attempt updates, state transitions, and terminal completion must include the expected attempt and worker owner.

A stale attempt cannot overwrite a recovered state or enqueue duplicate delivery. Terminal completion closes the current attempt and persists the operation outcome atomically.

Recovery uses two phases:

1. In a short transaction, compare the observed lease and attempt, revoke execution ownership, and claim recovery responsibility.
2. Outside the transaction, inspect or stop only the recorded process or backend session. Then persist the attempt and operation outcome with the recovery generation.

A concurrent heartbeat or completion either wins before recovery claims ownership or is rejected afterward.

---

## Implementation Stages

### Stage 1: Atomic inline acceptance and ownership

Likely files:

- `src/adjutant/operations/models.py`
- `src/adjutant/operations/store.py`
- `src/adjutant/capabilities/kb/query.py`
- `src/adjutant/cli.py`

Work:

- [x] Add additive schema fields for deadline, execution mode, parent attempt, CLI PID/birth time, and originating session/tool call where available.
- [x] Add one store transaction that creates, claims, starts the attempt, and appends the accepted event for an inline child.
- [x] Keep standalone KB work on the daemon queue.
- [x] Add attempt-generation and lease-owner preconditions to renewals, transitions, attempt updates, and terminal completion.
- [x] Persist PID and backend identity evidence as soon as it becomes known.
- [x] Ensure model or network work never occurs inside a database transaction.

Acceptance:

- The daemon and inline CLI cannot execute the same child.
- A crash between acceptance and backend startup leaves an inspectable attempt.
- A prior attempt cannot overwrite a recovered state.

### Stage 2: Deadline propagation and scoped hook

Likely files:

- `src/adjutant/operations/worker.py`
- `src/adjutant/operations/store.py`
- `src/adjutant/capabilities/kb/query.py`
- `src/adjutant/core/backend.py`
- `.opencode/plugins/adjutant-kb-timeout.js`
- a small operation-context helper and unit tests

Work:

- [x] Persist a top-level absolute deadline on first execution.
- [x] Derive child runtime from the parent's remaining budget and cleanup reserve.
- [x] Reject child submission after the usable parent budget is exhausted.
- [x] Enforce the same bound inside the CLI and backend request.
- [x] Add the scoped OpenCode hook for recognized KB shell calls only.
- [x] Bound `asyncio.wait_for()` cleanup when a backend ignores cancellation or abort stalls.
- [x] Cover isolated OpenCode, persistent-parent plus isolated-child, draining fallback, and supported Claude paths. Attached Claude children are explicitly gated until equivalent evidence exists.

Acceptance:

- A nested KB call may run beyond 120 seconds when the parent has time remaining.
- No nested child can extend the parent's persisted deadline.
- Unrelated shell commands retain the two-minute OpenCode default.

### Stage 3: Early child receipt and inspection

Likely files:

- `src/adjutant/cli.py`
- `src/adjutant/capabilities/kb/query.py`
- `src/adjutant/operations/service.py`
- `src/adjutant/operations/store.py`
- `.opencode/agents/adjutant.md`

Work:

- [x] Emit and flush a structured child acceptance receipt immediately after the atomic transaction and before backend startup.
- [x] Keep capability functions free of stdout. Let the CLI own the receipt format.
- [x] Verify that OpenCode preserves partial receipt output when it terminates a tool call.
- [x] Extend KB status with parent, attempt, activity, deadline, and reconciliation reason.
- [x] Let inspection of a non-KB parent identify attached KB children instead of returning only “not found.”
- [x] Tell the agent to inspect an accepted child after interruption and never replay the original write merely because its shell response timed out.
- [x] Correct stale docstrings that describe all durable writes as fire-and-forget or all KB reads as 80-second calls.

Acceptance:

- The child ID is available before backend execution.
- Parent inspection finds its execution children even if shell output disappears.

### Stage 4: Continuous recovery and bounded cleanup

Likely files:

- `src/adjutant/operations/recovery.py`
- `src/adjutant/operations/store.py`
- `src/adjutant/operations/worker.py`
- `src/adjutant/operations/daemon.py`
- `src/adjutant/core/opencode.py`
- `src/adjutant/core/backend_opencode.py`
- `src/adjutant/core/backend_claude_cli.py`

Work:

- [x] Run bounded expired-lease recovery from the existing daemon maintenance loop.
- [x] Close or supersede the matching attempt whenever recovery changes an operation.
- [x] Refresh `active_operations.json` after recovery.
- [x] Add scoped SIGTERM and SIGINT handling around inline CLI execution.
- [x] Abort only the affected persistent OpenCode session; never stop the shared server for one child.
- [x] Stop isolated backend processes through recorded PID, birth time, and process-group ownership.
- [x] Propagate parent cancellation and deadline expiry only to attached execution children.
- [x] Settle any active execution child before allowing a parent to hide it behind a successful final reply.
- [x] Gate equivalent guarantees on Claude until its owned-process cancellation fixtures pass.

Acceptance:

- An expired inline mutating child moves promptly to `reconciling` without restart.
- A read-only child is replayed only after its old execution is settled and its parent/deadline policy allows it.
- Catchable termination persists cleanup evidence; SIGKILL is handled by lease recovery.
- Unrelated processes and persistent sessions survive cleanup.

### Stage 5: Verification and documentation

Tests:

- [x] Scoped hook changes timeout for recognized KB commands and leaves other shell calls unchanged.
- [x] Quoted arguments work; compound or invalid commands fail before child execution.
- [x] Child budget derives from the parent's persisted remaining time.
- [x] A restart does not extend the deadline.
- [x] Forced create/claim races produce one attempt.
- [x] Heartbeat-versus-recovery races have one winner.
- [x] Late stale results cannot alter state or create duplicate delivery.
- [x] Early receipt survives forced caller termination.
- [x] SIGTERM, SIGKILL, backend death, cancellation, and daemon restart close or reconcile attempts.
- [x] A mutating fixture writes once, loses its caller before verification, and is never replayed automatically.
- [x] Parent cancellation reaches execution children but not conversational follow-ups.
- [x] Inline children finish with worker concurrency one and with all top-level slots occupied.
- [x] Debug-off Telegram typing and final delivery remain correct for success, timeout, cancellation, and reconciliation.
- [x] An installed OpenCode fixture runs a nested KB operation beyond 120 seconds through the actual hook.

Documentation:

- [x] Update `docs/architecture/operations.md` for deadlines, ownership fencing, continuous recovery, and child uncertainty.
- [x] Update `docs/architecture/backends.md` and `docs/development/backend-guide.md` for early process/session evidence and scoped timeout handling.
- [x] Update `docs/development/testing.md` for nested shell timeout and caller-death fixtures.
- [x] Update `docs/guides/knowledge-bases.md` and `docs/guides/commands.md` for early receipts and child inspection.
- [x] Update `docs/guides/configuration.md` if deadline semantics add configuration. No configuration field changed, so no edit was required.
- [x] Update `.opencode/agents/adjutant.md` with supported standalone command forms and interrupted-write recovery.
- [x] Update `docs/plans/durable-operations.md` after each completed stage with what changed, how it works, and verification evidence.

Release verification:

- [x] Full Python suite.
- [x] New JavaScript hook checks.
- [x] Documentation production build.
- [x] `git diff --check`.
- [x] Installed OpenCode compatibility smoke test.
- [x] Disposable live mutation with authoritative readback. The IxDA write was reconciled separately and was not used as the fixture.

---

## Implementation Record

### 2026-09-25: Atomic ownership and deadline hierarchy

**Completed:** Added schema version 3 fields for execution mode, absolute deadline, parent and current attempts, origin session and tool IDs, plus separate CLI-owner and backend-process evidence. Attached children now commit the operation, lease, attempt, owner identity, and accepted event in one transaction. Standalone KB operations remain daemon queued.

**How:** The first top-level attempt freezes its deadline. An inline child's deadline is the lower of its configured ceiling and the parent remainder after cancellation plus persistence reserves. Renewals, state transitions, attempt updates, and terminal result delivery carry the current attempt and worker fence. Terminal completion closes the attempt in the same transaction as the operation result and deliveries.

**Verification:** Store tests cover atomic inline acceptance, daemon exclusion, fixed deadlines across recovery, one-winner heartbeat recovery, stale completion rejection, atomic attempt closure, and cancellation limited to execution children.

### 2026-09-25: Scoped OpenCode timeout and early receipt

**Completed:** Added `.opencode/plugins/adjutant-kb-timeout.js`, the hidden `operation-context` helper, structured CLI acceptance receipts, parent-to-child inspection, and the interrupted-write instructions in the runtime agent prompt.

**How:** The hook accepts one standalone KB command with a validated parent ID, asks the operation store for the remaining deadline, changes only that bash call's timeout, and injects the originating session and tool-call IDs. It rejects shell composition outside quoted arguments. The CLI writes and flushes `{"accepted_operation_id":"op-..."}` to stderr before backend startup.

**Verification:** JavaScript checks cover recognized, unrelated, quoted, and compound commands. Installed OpenCode 1.18.0 loaded the local plugin and ran a disposable 121-second command with `timeout: 150000`, returning `HOOK_LONG_OK`. A forced 3,000 ms tool timeout preserved `op-child-smoke` in partial output, and OpenCode reported that child ID in its final answer.

### 2026-09-25: Continuous recovery and bounded cleanup

**Completed:** Added expired-lease recovery to the online maintenance loop, attempt closure and ownership revocation, active-snapshot refresh, inline SIGTERM unwinding, owned process-group termination, persistent-session abort, parent cancellation scoping, and parent completion checks for unsettled children. Attached Claude children are rejected until Claude emits equivalent early process evidence.

**How:** Recovery records candidates, revokes ownership in a short transaction, then performs cleanup outside the transaction. It validates PID birth time and command identity before signalling a backend process. For persistent OpenCode, it verifies the server instance and aborts only the recorded session. A mutating uncertain operation enters `reconciling` and is never queued for replay; an attached read whose caller vanished closes as interrupted.

**Verification:** Tests cover process identity refusal, matching process-group termination, inline caller loss, stale fencing, runtime timeout typing cleanup, and SIGTERM handler restoration. The complete Python suite passes with `1568 passed, 75 skipped`, and Adjutant restarted with worker PID 14073 and listener PID 14078.

### 2026-09-25: Live reconciliation and disposable mutation

**Completed:** Recovered the incident write without replay and completed a separate disposable mutation trial.

**How:** Expired write `op-29e1f7dcd59f4c5898fc08d208831832` moved to `reconciling`. Read-only operation `op-252f57f3509647d090259bfdd388c8e8` confirmed the complete Eva Ebbesen Munkvik board update, open onboarding task, missing fields, and independent Elleve relationship through the KB interface. The write then moved to `succeeded` with that readback ID as reconciliation evidence. Disposable write `op-9d079f23b4124c2b8e466338806184c3` created one temporary record; independent query `op-19310036163b4004bcda0a94366ea1a9` verified the identifier, status, and one-record cardinality. The temporary KB was unregistered and deleted.

**Verification:** The documentation site production build, focused Ruff and mypy checks, and `git diff --check` passed. The installed plugin and live worker trials passed. Final suite and diff evidence are recorded in the parent plan.

---

## State and Replay Rules

| Event | Required result |
|---|---|
| Verified child completion | `running -> succeeded`; close the attempt atomically |
| Cancellation before backend start | `cancelled`; no mutation uncertainty |
| Caller disappears after mutation may start | `running -> reconciling`; never replay automatically |
| Mutating child reaches deadline without verification | `reconciling` with timeout evidence |
| Read-only attached child loses its caller | Settle the old execution before any replay; respect parent state and deadline |
| Standalone replay-safe work loses ownership | Requeue only after the prior execution is settled and time remains |
| Backend stop cannot be confirmed | `reconciling`, not `cancelled` |
| Authoritative evidence proves recovered mutation complete | `reconciling -> succeeded` |
| External effects remain unknown | Preserve reconciliation evidence; optionally close as `interrupted` |
| Old worker returns after recovery | Reject its update and delivery |

---

## Rollout and Rollback

Ship ownership fencing, atomic inline claim, and continuous recovery before enabling the timeout hook. Apply the schema migration additively. Drain existing work, reconcile expired mutations, restart Adjutant and its managed OpenCode server, and then run the installed-version hook smoke test.

Rollback preserves operations, attempts, and reconciliation evidence. Drain or reconcile active work first, disable the hook if required, and restart. Disabling persistent transport does not remove OpenCode's shell timeout. Do not use the legacy detached write path to recover an uncertain durable mutation.

---

## Existing Stale Child Repair

Do not replay `op-29e1f7dcd59f4c5898fc08d208831832` automatically.

1. Recheck that its lease is expired and no owned process or backend execution remains.
2. Move only that child to `reconciling`, close its abandoned attempt as interrupted, and append the observed 120-second shell termination evidence.
3. Query the IxDA KB through `adjutant kb query` for the intended authoritative records. Do not read KB files directly.
4. Mark the child succeeded only if the complete intended change is verified.
5. If the change is absent or partial, record the differences and prepare a targeted correction for explicit approval.
6. Preserve the parent's completed response and Telegram delivery.

A restart or general expired-lease recovery could affect unrelated work. Enumerate active operations before any live repair and use a targeted reconciliation action.

---

## Open Risks

- Installed OpenCode hook behavior must match the pinned 1.18.0 execution path despite the older local plugin type package.
- Backend session IDs may arrive after process start, so PID/process-group evidence must cover that interval.
- A nominally read-only KB agent may still have write-capable workspace permissions. Replay decisions use the operation's accepted side-effect class and verified backend cleanup, not the KB's general access mode alone.
- Parent completion policy must preserve a useful generated reply while clearly reporting any unresolved mutating child.
- `query-all` and `cross-query` need fan-out tests so timeout enforcement does not introduce another held-resource deadlock.
