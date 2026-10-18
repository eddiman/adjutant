# Durable Operations

Adjutant uses a backend-independent operation layer for work that may outlive a Telegram polling cycle or listener process. The operation layer persists acceptance, execution state, results, and outbound delivery in `state/operations.sqlite3`.

## Acceptance

When durable operations are enabled, the Telegram listener handles a natural-language message in this order:

1. It verifies the configured chat identity and applies the existing rate limit.
2. It inserts a Telegram inbox record and a queued operation.
3. It advances that bot's Telegram offset in the same SQLite transaction.
4. When `operations.debug` is enabled, it sends an acknowledgement containing the operation ID.

The `(bot_id, update_id)` primary key makes acceptance idempotent. If Telegram repeats an update, Adjutant returns the existing operation instead of creating another execution.

Photos use the same atomic inbox and offset transaction. The worker downloads the Telegram asset, persists its local path in the operation payload, and runs vision extraction inside the tracked attempt. The bounded conversation context carries that path and Telegram media-group identifier into a later confirmation turn. Pulse and review requests from Telegram, cron, and Adjutant Web create ordinary operations and return without holding the caller open.

The worker sends Telegram's `typing` action while a Telegram operation is running and stops it in a `finally` block after success, failure, timeout, or cancellation. This activity indicator does not depend on the debug acknowledgement. With `operations.debug: false`, Telegram receives the typing indicator followed by the final reply, without operation IDs or lifecycle status edits. The `/operations` and `/operation <id>` commands remain available for explicit inspection.

## Records

The SQLite database contains these record types:

- `operations` stores origin, frozen backend settings, dependencies, state, leases, result text, errors, recovery status, execution mode, absolute deadline, parent attempt, and current attempt.
- `telegram_inbox` links one accepted Telegram update to one operation.
- `telegram_offsets` stores the next update offset for each bot identity.
- `operation_events` stores ordered public lifecycle and progress events.
- `execution_attempts` stores worker ownership and backend evidence for each attempt.
- `deliveries` stores outbound chunks independently from execution state.

The result and its delivery records commit in one transaction. A process failure after that commit can delay delivery, but it does not cause the model operation to run again.

## Worker and leases

`adjutant.operations.daemon` runs as a separate managed process. Startup launches the worker before the Telegram listener accepts new durable work. The worker claims queued records with `BEGIN IMMEDIATE`, respects successful dependencies, and limits active tasks with `operations.worker_concurrency`.

Each claim has a renewable lease. The first attempt fixes an absolute deadline, and later recovery never extends it. Lease renewal, state transitions, attempt evidence, and terminal completion are fenced by the current attempt ID and lease owner. A late worker therefore cannot overwrite a state that recovery or a newer attempt has claimed.

Attached KB children use `execution_mode=inline`. Adjutant creates the child, claims it, creates its attempt, records CLI process evidence, and appends the accepted event in one transaction. The daemon queue ignores inline children, so the daemon and submitting CLI cannot execute the same child. The child deadline is the lower of its configured runtime ceiling and the parent's remaining budget after cancellation and persistence reserves. Conversational follow-ups can still use `parent_id`, but only inline execution children inherit deadlines and cancellation.

A cancellation request changes the operation to `cancel_requested`; the owning worker then cancels the backend task, which invokes the backend's owned-process cleanup. Parent cancellation reaches attached inline children and leaves conversational follow-ups unchanged.

## Recovery

Worker startup and the daemon maintenance loop examine expired execution and delivery leases:

- Read-only and idempotent operations return to `queued`.
- Operations with unknown or mutating external effects enter `reconciling`. Adjutant does not replay them automatically.
- A cancellation request with an expired owner becomes `cancelled`.
- An expired `sending` delivery enters `retry_wait` and is marked uncertain.

Recovery closes the matching execution attempt and revokes its ownership before changing the operation. A mutating inline child with an unknown outcome remains in `reconciling`; Adjutant does not replay the write. Catchable CLI termination uses the same fencing path. A successful parent response cannot hide a non-terminal execution child; the parent ends as interrupted and reports the child IDs for inspection.

Telegram cannot provide an idempotency key for a new message. A lost HTTP response can therefore leave a delivery ambiguous. Adjutant records that ambiguity and retries according to the configured limit. A known Telegram message ID proves that Telegram accepted the send.

## Result delivery

The delivery worker claims pending and due retry records separately from execution. It splits results at paragraph, line, or word boundaries and keeps every chunk at or below 4,000 characters. The complete result remains on the operation record even if one chunk is blocked after exhausting retries.

## Compatibility snapshot and retention

The operation store writes `state/active_operations.json` for local clients that cannot read SQLite. The file contains every queued or running operation, including action, source, state, timestamps, and parent ID. Adjutant Web reads this list and falls back to the legacy `active_operation.json` marker only when durable state is unavailable.

Hourly retention removes old event rows, terminal result records, and completed delivery evidence according to separate age settings. Before deleting a terminal operation that owns an OpenCode session, Adjutant calls the server's session delete endpoint. Only session IDs recorded in `execution_attempts` qualify. If the server cannot confirm deletion, the operation and its attempt evidence remain for the next retention pass.

## Rollout boundary

Set `operations.enabled: true` to route supported entry points through this layer. Set `operations.debug: true` only when Telegram should show operation IDs and lifecycle status edits, then restart Adjutant so the listener and worker load the changed configuration. The persistent OpenCode transport has its own flag, so durable acceptance and delivery continue to work with the one-process-per-call transport during rollback.
