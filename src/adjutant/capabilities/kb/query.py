"""Query and write to a knowledge base sub-agent via LLM backend.

Replaces: scripts/capabilities/kb/query.sh

When durable operations are disabled, queries use the legacy 80-second backend
timeout and writes use detached execution. When durable operations are enabled,
standalone work enters the daemon queue and attached children execute inline
under the parent's persisted deadline.

Usage:
    result = await kb_query("my-kb", "What is the current portfolio value?", adj_dir)
    result = await kb_query_by_path("/path/to/kb", "question", adj_dir)
    msg = kb_write("my-kb", "Update issue #12: mark complete", adj_dir)
    msg = kb_write_by_path("/path/to/kb", "Update issue #12", adj_dir)
"""

from __future__ import annotations

import contextlib
import os
import time
from pathlib import Path
from typing import TYPE_CHECKING

from adjutant.core.backend import BackendNotFoundError, get_backend
from adjutant.core.logging import adj_log
from adjutant.core.model import resolve_kb_model, resolve_model_spec

if TYPE_CHECKING:
    from collections.abc import Callable

    from adjutant.core.backend import ResolvedModel
    from adjutant.operations.models import Operation

# Legacy non-durable timeout. Durable attached calls use the remaining parent deadline.
KB_QUERY_TIMEOUT = 80.0  # seconds


class KBQueryError(Exception):
    """Raised when the KB query fails fatally."""


def _durable_operations_enabled(adj_dir: Path) -> bool:
    from adjutant.core.config import load_typed_config

    return load_typed_config(adj_dir / "adjutant.yaml").operations.enabled


def _parent_operation_id() -> str | None:
    return os.environ.get("ADJUTANT_PARENT_OPERATION_ID", "").strip() or None


def _submit_kb_operation_by_path(
    kb_path: Path,
    prompt: str,
    adj_dir: Path,
    *,
    kind: str,
    parent_id: str | None = None,
    telegram_chat_id: str | None = None,
    telegram_message_id: int | None = None,
) -> Operation:
    """Create a frozen KB child operation without reading KB content."""
    from adjutant.core.config import load_typed_config
    from adjutant.operations.models import SideEffectClass
    from adjutant.operations.store import OperationStore

    if not kb_path.is_dir():
        raise KBQueryError(f"KB directory does not exist: {kb_path}")
    if not prompt.strip():
        raise KBQueryError("KB operation prompt is empty.")
    resolved = _resolve_model_with_variant(kb_path, adj_dir)
    config = load_typed_config(adj_dir / "adjutant.yaml")
    store = OperationStore(adj_dir)
    payload = {
        "prompt": prompt,
        "kb_name": kb_path.name,
        "reply_to_message_id": telegram_message_id,
    }
    side_effect_class = (
        SideEffectClass.READ_ONLY if kind == "kb_query" else SideEffectClass.MUTATING
    )
    if parent_id:
        if config.llm.backend == "claude-cli":
            raise KBQueryError(
                "Attached durable KB children require the OpenCode ownership hook; "
                "Claude CLI support remains disabled until its caller-death fixture passes."
            )
        parent = store.get_operation(parent_id)
        if parent is None or parent.current_attempt_id is None or parent.deadline_at is None:
            raise KBQueryError(
                f"Parent operation {parent_id} has no active owned attempt or deadline."
            )
        reserve = config.operations.timeouts.cancellation_grace_seconds + 5.0
        deadline_at = min(
            time.time() + config.operations.timeouts.runtime_seconds,
            parent.deadline_at - reserve,
        )
        if deadline_at <= time.time():
            raise KBQueryError(
                f"Parent operation {parent_id} has no remaining budget for a KB child."
            )
        operation, _attempt = store.create_inline_operation(
            kind=kind,
            source="kb",
            payload=payload,
            worker_id=f"inline-kb-{os.getpid()}",
            lease_seconds=config.operations.timeouts.lease_seconds,
            parent_id=parent_id,
            parent_attempt_id=parent.current_attempt_id,
            deadline_at=deadline_at,
            backend=config.llm.backend,
            model=resolved.model,
            variant=resolved.variant,
            agent="kb",
            workdir=str(kb_path),
            side_effect_class=side_effect_class,
            origin_session_id=os.environ.get("ADJUTANT_ORIGIN_SESSION_ID") or None,
            origin_tool_call_id=os.environ.get("ADJUTANT_ORIGIN_TOOL_CALL_ID") or None,
        )
        return operation
    return store.create_operation(
        kind=kind,
        source="kb",
        payload=payload,
        parent_id=None,
        telegram_chat_id=telegram_chat_id,
        telegram_message_id=telegram_message_id,
        backend=config.llm.backend,
        model=resolved.model,
        variant=resolved.variant,
        agent="kb",
        workdir=str(kb_path),
        side_effect_class=side_effect_class,
    )


def kb_submit_query_by_path(
    kb_path: Path,
    query: str,
    adj_dir: Path,
    *,
    parent_id: str | None = None,
    telegram_chat_id: str | None = None,
    telegram_message_id: int | None = None,
) -> Operation:
    """Submit a tracked read-only KB query."""
    return _submit_kb_operation_by_path(
        kb_path,
        query,
        adj_dir,
        kind="kb_query",
        parent_id=parent_id,
        telegram_chat_id=telegram_chat_id,
        telegram_message_id=telegram_message_id,
    )


def kb_submit_write_by_path(
    kb_path: Path,
    instruction: str,
    adj_dir: Path,
    *,
    parent_id: str | None = None,
    telegram_chat_id: str | None = None,
    telegram_message_id: int | None = None,
) -> Operation:
    """Submit a tracked KB mutation with an explicit verification request."""
    verified_prompt = (
        f"{instruction.strip()}\n\n"
        "After applying the requested change, read the authoritative target again. "
        "Report what changed and the concrete evidence that verifies the final state."
    )
    return _submit_kb_operation_by_path(
        kb_path,
        verified_prompt,
        adj_dir,
        kind="kb_write",
        parent_id=parent_id,
        telegram_chat_id=telegram_chat_id,
        telegram_message_id=telegram_message_id,
    )


async def _execute_tracked_inline(operation: Operation, adj_dir: Path) -> str:
    """Run a child in the submitting CLI process to avoid worker-pool deadlock."""
    from adjutant.core.config import load_typed_config
    from adjutant.operations.models import OperationState
    from adjutant.operations.store import OperationStore
    from adjutant.operations.worker import OperationWorker

    config = load_typed_config(adj_dir / "adjutant.yaml")
    store = OperationStore(adj_dir)
    worker_id = f"inline-kb-{os.getpid()}"
    claimed = store.get_operation(operation.id)
    if (
        claimed is None
        or claimed.lease_owner != worker_id
        or claimed.current_attempt_id is None
        or claimed.execution_mode != "inline"
    ):
        raise KBQueryError(f"KB operation {operation.id} no longer has inline ownership.")
    attempt = store.get_attempt(claimed.current_attempt_id)
    if attempt is None:
        raise KBQueryError(f"KB operation {operation.id} has no execution attempt.")
    remaining = (claimed.deadline_at or time.time()) - time.time()
    if remaining <= 0:
        raise KBQueryError(f"KB operation {operation.id} deadline expired before execution.")
    worker = OperationWorker(
        adj_dir,
        store=store,
        worker_id=worker_id,
        concurrency=1,
        lease_seconds=config.operations.timeouts.lease_seconds,
        startup_seconds=config.operations.timeouts.startup_seconds,
        connection_seconds=config.operations.timeouts.connection_seconds,
        runtime_seconds=min(config.operations.timeouts.runtime_seconds, remaining),
        progress_warning_seconds=config.operations.timeouts.progress_warning_seconds,
        cancellation_grace_seconds=config.operations.timeouts.cancellation_grace_seconds,
    )
    try:
        completed = await worker.run_claimed(claimed, attempt=attempt)
    except BaseException:
        with contextlib.suppress(Exception):
            store.abandon_attempt(
                claimed.id,
                attempt.id,
                worker_id,
                reason="inline CLI execution was interrupted",
            )
            store.sync_active_snapshot()
        raise
    if completed.state is not OperationState.SUCCEEDED:
        raise KBQueryError(
            f"KB operation {completed.id} ended as {completed.state.value}: "
            f"{completed.error_message or completed.error_type or 'unknown error'}"
        )
    return completed.result_text or ""


def _read_kb_model_from_yaml(kb_path: Path) -> str:
    """Read the model field from <kb_path>/kb.yaml, default 'inherit'."""
    kb_yaml = kb_path / "kb.yaml"
    if not kb_yaml.is_file():
        return "inherit"
    for line in kb_yaml.read_text().splitlines():
        if line.startswith("model:"):
            val = line[len("model:") :].strip().strip("\"'")
            return val or "inherit"
    return "inherit"


def _resolve_model(kb_path: Path, adj_dir: Path) -> str:
    """Resolve the model for a KB, shared by query and write paths."""
    kb_model_raw = _read_kb_model_from_yaml(kb_path)
    state_dir = adj_dir / "state"

    from adjutant.core.config import load_config

    config = load_config(adj_dir / "adjutant.yaml")
    return resolve_kb_model(kb_model_raw, state_dir, config)


def _resolve_model_with_variant(kb_path: Path, adj_dir: Path) -> ResolvedModel:
    """Resolve the model and reasoning-effort variant for a KB."""
    kb_model_raw = _read_kb_model_from_yaml(kb_path)
    state_dir = adj_dir / "state"

    from adjutant.core.config import load_config

    config = load_config(adj_dir / "adjutant.yaml")
    return resolve_model_spec(kb_model_raw, state_dir, config)


async def kb_query_by_path(
    kb_path: Path,
    query: str,
    adj_dir: Path,
    *,
    timeout: float = KB_QUERY_TIMEOUT,
    receipt_callback: Callable[[Operation], None] | None = None,
) -> str:
    """Query a KB by its directory path.

    Args:
        kb_path: Absolute path to the KB workspace.
        query: The question to ask.
        adj_dir: Adjutant root directory (for model resolution).
        timeout: Opencode timeout in seconds.

    Returns:
        Plain-text answer, or a fallback message if empty.

    Raises:
        KBQueryError: If the KB directory is missing or query is empty.
        BackendNotFoundError: If the backend binary is not on PATH.
    """
    if not kb_path.is_dir():
        raise KBQueryError(f"KB directory does not exist: {kb_path}")
    if not query.strip():
        raise KBQueryError("Query is empty.")

    if _durable_operations_enabled(adj_dir):
        operation = kb_submit_query_by_path(
            kb_path,
            query,
            adj_dir,
            parent_id=_parent_operation_id(),
        )
        if receipt_callback is not None:
            receipt_callback(operation)
        if operation.parent_id:
            return await _execute_tracked_inline(operation, adj_dir)
        from adjutant.operations.process import worker_start

        worker_status = worker_start(adj_dir)
        return f"Query accepted as `{operation.id}`. {worker_status}."

    resolved = _resolve_model_with_variant(kb_path, adj_dir)

    kb_name = kb_path.name
    adj_log(
        "kb",
        f"Query start: kb='{kb_name}' model='{resolved.model}' "
        f"variant='{resolved.variant}' timeout={timeout}s",
    )

    backend = get_backend()
    result = await backend.run(
        query,
        agent="kb",
        workdir=kb_path,
        model=resolved.model,
        variant=resolved.variant,
        timeout=timeout,
    )

    if result.returncode != 0 or result.timed_out:
        adj_log(
            "kb",
            f"Query exited non-zero rc={result.returncode} "
            f"(kb='{kb_name}', timed_out={result.timed_out})",
        )

    reply = result.text

    if not reply:
        adj_log(
            "kb",
            f"Query returned empty reply (kb='{kb_name}', rc={result.returncode})",
        )
        return (
            "The knowledge base did not return an answer. "
            "It may not contain relevant information for this query."
        )

    adj_log("kb", f"Query complete: kb='{kb_name}' reply_len={len(reply)}")
    return reply


async def kb_query(
    kb_name: str,
    query: str,
    adj_dir: Path,
    *,
    timeout: float = KB_QUERY_TIMEOUT,
    receipt_callback: Callable[[Operation], None] | None = None,
) -> str:
    """Query a KB by its registered name.

    Looks up the KB path in knowledge_bases/registry.yaml via the same
    registry parser as kb/run.py.

    Args:
        kb_name: Registered KB name.
        query: The question to ask.
        adj_dir: Adjutant root directory.
        timeout: Opencode timeout in seconds.

    Returns:
        Plain-text answer.

    Raises:
        KBQueryError: If KB not found or query fails.
    """
    from adjutant.capabilities.kb.run import KBNotFoundError, get_kb

    try:
        entry = get_kb(adj_dir, kb_name)
    except KBNotFoundError as exc:
        raise KBQueryError(str(exc)) from exc

    kb_path_str = entry.get("path", "")
    if not kb_path_str:
        raise KBQueryError(f"KB '{kb_name}' has no path in registry.")

    return await kb_query_by_path(
        Path(kb_path_str),
        query,
        adj_dir,
        timeout=timeout,
        receipt_callback=receipt_callback,
    )


def kb_write_by_path(
    kb_path: Path,
    instruction: str,
    adj_dir: Path,
    *,
    receipt_callback: Callable[[Operation], None] | None = None,
) -> str:
    """Submit or execute a write operation through the selected lifecycle.

    Durable standalone writes enter the daemon queue. Durable attached writes
    execute inline under their parent's deadline. The rollback path dispatches
    a detached backend only when durable operations are disabled.

    This is synchronous and safe to call from ``asyncio.run()`` (CLI) or
    from an async context via ``await asyncio.to_thread(kb_write_by_path, ...)``.

    Args:
        kb_path: Absolute path to the KB workspace.
        instruction: The write instruction for the sub-agent.
        adj_dir: Adjutant root directory (for model resolution).

    Returns:
        Acceptance text for standalone work or a verified result for an attached child.

    Raises:
        KBQueryError: If the KB directory is missing or instruction is empty.
        BackendNotFoundError: If the backend binary is not on PATH.
    """
    if not kb_path.is_dir():
        raise KBQueryError(f"KB directory does not exist: {kb_path}")
    if not instruction.strip():
        raise KBQueryError("Write instruction is empty.")

    if _durable_operations_enabled(adj_dir):
        operation = kb_submit_write_by_path(
            kb_path,
            instruction,
            adj_dir,
            parent_id=_parent_operation_id(),
        )
        if receipt_callback is not None:
            receipt_callback(operation)
        if operation.parent_id:
            import asyncio

            result = asyncio.run(_execute_tracked_inline(operation, adj_dir))
            return f"Write `{operation.id}` completed and verified: {result}"
        from adjutant.operations.process import worker_start

        worker_status = worker_start(adj_dir)
        return f"Write accepted as `{operation.id}`. {worker_status}."

    resolved = _resolve_model_with_variant(kb_path, adj_dir)
    kb_name = kb_path.name

    adj_log(
        "kb",
        f"Write dispatched: kb='{kb_name}' model='{resolved.model}' variant='{resolved.variant}'",
    )

    log_path = adj_dir / "state" / "adjutant.log"
    backend = get_backend()
    backend.run_detached(
        instruction,
        agent="kb",
        workdir=kb_path,
        model=resolved.model,
        variant=resolved.variant,
        log_path=log_path,
    )

    preview = instruction[:120]
    if len(instruction) > 120:
        preview += "..."
    return f"Write dispatched to '{kb_name}' (pending; completion not verified): {preview}"


def kb_write(
    kb_name: str,
    instruction: str,
    adj_dir: Path,
    *,
    receipt_callback: Callable[[Operation], None] | None = None,
) -> str:
    """Submit a write operation to a KB by its registered name.

    Looks up the KB path in knowledge_bases/registry.yaml, then delegates
    to ``kb_write_by_path()``.

    Args:
        kb_name: Registered KB name.
        instruction: The write instruction for the sub-agent.
        adj_dir: Adjutant root directory.

    Returns:
        Acceptance text for standalone work or a verified result for an attached child.

    Raises:
        KBQueryError: If KB not found or instruction fails validation.
    """
    from adjutant.capabilities.kb.run import KBNotFoundError, get_kb

    try:
        entry = get_kb(adj_dir, kb_name)
    except KBNotFoundError as exc:
        raise KBQueryError(str(exc)) from exc

    kb_path_str = entry.get("path", "")
    if not kb_path_str:
        raise KBQueryError(f"KB '{kb_name}' has no path in registry.")
    if entry.get("access", "read-only") != "read-write":
        raise KBQueryError(f"KB '{kb_name}' is read-only.")

    return kb_write_by_path(
        Path(kb_path_str),
        instruction,
        adj_dir,
        receipt_callback=receipt_callback,
    )


def kb_submit_query(
    kb_name: str,
    query: str,
    adj_dir: Path,
    parent_id: str | None = None,
    telegram_chat_id: str | None = None,
    telegram_message_id: int | None = None,
) -> Operation:
    """Resolve a registered KB and submit a tracked query."""
    from adjutant.capabilities.kb.run import KBNotFoundError, get_kb

    try:
        entry = get_kb(adj_dir, kb_name)
    except KBNotFoundError as exc:
        raise KBQueryError(str(exc)) from exc
    kb_path = entry.get("path", "")
    if not kb_path:
        raise KBQueryError(f"KB '{kb_name}' has no path in registry.")
    return kb_submit_query_by_path(
        Path(kb_path),
        query,
        adj_dir,
        parent_id=parent_id,
        telegram_chat_id=telegram_chat_id,
        telegram_message_id=telegram_message_id,
    )


def kb_submit_write(
    kb_name: str,
    instruction: str,
    adj_dir: Path,
    parent_id: str | None = None,
    telegram_chat_id: str | None = None,
    telegram_message_id: int | None = None,
) -> Operation:
    """Resolve a writable registered KB and submit a tracked mutation."""
    from adjutant.capabilities.kb.run import KBNotFoundError, get_kb

    try:
        entry = get_kb(adj_dir, kb_name)
    except KBNotFoundError as exc:
        raise KBQueryError(str(exc)) from exc
    kb_path = entry.get("path", "")
    if not kb_path:
        raise KBQueryError(f"KB '{kb_name}' has no path in registry.")
    if entry.get("access", "read-only") != "read-write":
        raise KBQueryError(f"KB '{kb_name}' is read-only.")
    return kb_submit_write_by_path(
        Path(kb_path),
        instruction,
        adj_dir,
        parent_id=parent_id,
        telegram_chat_id=telegram_chat_id,
        telegram_message_id=telegram_message_id,
    )


def kb_operation_status(operation_id: str, adj_dir: Path) -> str:
    """Return an inspectable status for one tracked KB operation."""
    from adjutant.operations.store import OperationStore

    store = OperationStore(adj_dir)
    operation = store.get_operation(operation_id)
    if operation is None:
        raise KBQueryError(f"Tracked KB operation '{operation_id}' was not found.")
    if operation.kind not in {"kb_query", "kb_write"}:
        children = store.list_execution_children(operation.id)
        if not children:
            raise KBQueryError(f"Tracked KB operation '{operation_id}' was not found.")
        lines = [f"{operation.id}: {operation.state.value}; attached KB children:"]
        lines.extend(f"- {child.id}: {child.kind}, {child.state.value}" for child in children)
        return "\n".join(lines)
    detail = f"{operation.id}: {operation.state.value}, attempts={operation.attempt_count}"
    if operation.parent_id:
        detail += f", parent={operation.parent_id}"
    if operation.current_attempt_id:
        detail += f", attempt={operation.current_attempt_id}"
    if operation.deadline_at is not None:
        detail += f", deadline={operation.deadline_at:.3f}"
    if operation.last_activity_at is not None:
        detail += f", last_activity={operation.last_activity_at:.3f}"
    if operation.recovery_status:
        detail += f", recovery={operation.recovery_status}"
    if operation.error_type:
        detail += f", error={operation.error_type}"
    return detail


def kb_operation_result(operation_id: str, adj_dir: Path) -> str:
    """Return the persisted result after a tracked KB operation completes."""
    from adjutant.operations.store import OperationStore

    operation = OperationStore(adj_dir).get_operation(operation_id)
    if operation is None or operation.kind not in {"kb_query", "kb_write"}:
        raise KBQueryError(f"Tracked KB operation '{operation_id}' was not found.")
    if not operation.state.terminal:
        raise KBQueryError(
            f"KB operation {operation.id} is still {operation.state.value}; no final result yet."
        )
    if operation.state.value != "succeeded":
        raise KBQueryError(
            f"KB operation {operation.id} ended as {operation.state.value}: "
            f"{operation.error_message or operation.error_type or 'unknown error'}"
        )
    return operation.result_text or ""


async def kb_query_all(
    adj_dir: Path,
    *,
    query: str | None = None,
    timeout: float = KB_QUERY_TIMEOUT,
) -> str:
    """Query ALL registered KBs in parallel and return combined results.

    For each KB, uses ``query_hint`` from the registry to build a targeted
    question (falls back to a generic status query).  All queries run
    concurrently via ``asyncio.gather``, giving a ~Nx speedup over
    sequential execution.

    Args:
        adj_dir: Adjutant root directory.
        query: Override query text for all KBs (ignores query_hint).
        timeout: Per-KB timeout in seconds.

    Returns:
        Formatted multi-KB result string with one section per KB.
    """
    import asyncio

    from adjutant.capabilities.kb.manage import kb_list

    entries = kb_list(adj_dir)
    if not entries:
        return "No knowledge bases registered."

    default_query = (
        "Quick pulse: current status? Active blockers or deadlines "
        "in the next 2 weeks? Brief bullets only."
    )

    async def _query_one(name: str, path: str, hint: str) -> tuple[str, str]:
        q = query or (hint if hint else default_query)
        try:
            result = await kb_query_by_path(
                Path(path),
                q,
                adj_dir,
                timeout=timeout,
            )
        except (KBQueryError, BackendNotFoundError) as exc:
            result = f"[error: {exc}]"
        return name, result

    tasks = [_query_one(e.name, e.path, e.query_hint) for e in entries if e.path]
    results = await asyncio.gather(*tasks)

    parts: list[str] = []
    for name, response in results:
        parts.append(f"### {name}\n{response}")

    return "\n\n".join(parts)


_CROSS_QUERY_KB_TIMEOUT = 60.0  # tighter than single-query — budget shared with synthesis
_CROSS_QUERY_SYNTH_TIMEOUT = 45.0  # synthesis is lightweight, just combining responses


async def kb_cross_query(
    kb_names: list[str],
    question: str,
    adj_dir: Path,
    *,
    timeout: float = _CROSS_QUERY_KB_TIMEOUT,
) -> str:
    """Query multiple KBs in parallel and synthesize a unified answer.

    Queries selected KBs concurrently, then runs a synthesis prompt
    through the backend using the cheap model (synthesis is lightweight).
    Total budget: ~60s (parallel KB queries) + ~45s (synthesis) = ~105s,
    well within the 240s Telegram chat timeout.

    Args:
        kb_names: List of registered KB names to query.
        question: The cross-domain question to answer.
        adj_dir: Adjutant root directory.
        timeout: Per-KB timeout in seconds.

    Returns:
        Synthesized answer combining insights from all queried KBs.

    Raises:
        KBQueryError: If any KB name is not found.
    """
    import asyncio

    if not kb_names:
        raise KBQueryError("No KB names provided.")
    if not question.strip():
        raise KBQueryError("Question is empty.")

    async def _query_one(name: str) -> tuple[str, str]:
        try:
            result = await kb_query(name, question, adj_dir, timeout=timeout)
        except (KBQueryError, BackendNotFoundError) as exc:
            result = f"[error: {exc}]"
        return name, result

    tasks = [_query_one(name) for name in kb_names]
    results = await asyncio.gather(*tasks)

    # Build synthesis prompt
    context_parts: list[str] = []
    for name, response in results:
        context_parts.append(f"### {name}\n{response}")
    combined = "\n\n".join(context_parts)

    synthesis_prompt = (
        "You have received responses from multiple knowledge bases about "
        "the same question. Synthesize these into a single, unified answer "
        "that identifies connections, conflicts, and combined insights.\n\n"
        f"## Question\n{question}\n\n"
        f"## KB Responses\n{combined}\n\n"
        "## Your Task\n"
        "Provide a concise, unified answer. Highlight cross-domain "
        "connections and any conflicts between the sources."
    )

    # Use cheap model for synthesis — it's just combining two responses,
    # not deep reasoning.  Saves tokens and avoids the timeout ceiling.
    from adjutant.core.config import load_typed_config

    resolved = resolve_model_spec(
        "cheap", adj_dir / "state", load_typed_config(adj_dir / "adjutant.yaml").model_dump()
    )

    backend = get_backend()
    result = await backend.run(
        synthesis_prompt,
        workdir=adj_dir,
        model=resolved.model,
        variant=resolved.variant,
        timeout=_CROSS_QUERY_SYNTH_TIMEOUT,
    )

    if result.text:
        return result.text
    return f"Synthesis returned empty. Raw KB responses:\n\n{combined}"


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: kb_query.py <kb-name|--path /path> <query>

    Usage:
        kb_query.py my-kb "What is the current value?"
        kb_query.py --path /absolute/path "What is the current value?"
    """
    import asyncio
    import sys as _sys

    args = argv if argv is not None else _sys.argv[1:]

    if len(args) < 2:
        _sys.stderr.write('Usage: query.py <kb-name> "your question"\n')
        _sys.stderr.write('       query.py --path /path/to/kb "your question"\n')
        return 1

    adj_dir_str = os.environ.get("ADJ_DIR", "").strip()
    if not adj_dir_str:
        _sys.stderr.write("ERROR: ADJ_DIR not set\n")
        return 1

    adj_dir = Path(adj_dir_str)

    async def _run() -> str:
        if args[0] == "--path":
            if len(args) < 3:
                _sys.stderr.write("ERROR: --path requires a path and a query\n")
                raise SystemExit(1)
            return await kb_query_by_path(Path(args[1]), args[2], adj_dir)
        else:
            return await kb_query(args[0], args[1], adj_dir)

    try:
        answer = asyncio.run(_run())
        print(answer, end="")
        return 0
    except (KBQueryError, BackendNotFoundError) as exc:
        _sys.stderr.write(f"ERROR: {exc}\n")
        return 1
