"""Query and write to a knowledge base sub-agent via LLM backend.

Replaces: scripts/capabilities/kb/query.sh

Sends queries to the KB sub-agent via the configured LLM backend with an
80-second timeout and returns the plain-text answer.

For writes, dispatches the sub-agent as a detached background process and
returns immediately with a confirmation message (fire-and-forget).

Usage:
    result = await kb_query("my-kb", "What is the current portfolio value?", adj_dir)
    result = await kb_query_by_path("/path/to/kb", "question", adj_dir)
    msg = kb_write("my-kb", "Update issue #12: mark complete", adj_dir)
    msg = kb_write_by_path("/path/to/kb", "Update issue #12", adj_dir)
"""

from __future__ import annotations

import os
from pathlib import Path

from adjutant.core.backend import BackendNotFoundError, get_backend
from adjutant.core.logging import adj_log
from adjutant.core.model import resolve_kb_model, resolve_model_spec

# Keep under the 120 s bash-tool ceiling.
# health check (~5-20 s) + query timeout must not exceed ~110 s total.
KB_QUERY_TIMEOUT = 80.0  # seconds


class KBQueryError(Exception):
    """Raised when the KB query fails fatally."""


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


def _resolve_model_with_variant(kb_path: Path, adj_dir: Path):
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

    return await kb_query_by_path(Path(kb_path_str), query, adj_dir, timeout=timeout)


def kb_write_by_path(
    kb_path: Path,
    instruction: str,
    adj_dir: Path,
) -> str:
    """Dispatch a write operation to a KB sub-agent (fire-and-forget).

    Spawns the sub-agent as a detached background process and returns
    immediately with a confirmation message.  The sub-agent runs without
    a timeout and logs completion/failure to adjutant.log.

    This is synchronous and safe to call from ``asyncio.run()`` (CLI) or
    from an async context via ``await asyncio.to_thread(kb_write_by_path, ...)``.

    Args:
        kb_path: Absolute path to the KB workspace.
        instruction: The write instruction for the sub-agent.
        adj_dir: Adjutant root directory (for model resolution).

    Returns:
        Confirmation message string.

    Raises:
        KBQueryError: If the KB directory is missing or instruction is empty.
        BackendNotFoundError: If the backend binary is not on PATH.
    """
    if not kb_path.is_dir():
        raise KBQueryError(f"KB directory does not exist: {kb_path}")
    if not instruction.strip():
        raise KBQueryError("Write instruction is empty.")

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
    return f"Write dispatched to '{kb_name}': {preview}"


def kb_write(
    kb_name: str,
    instruction: str,
    adj_dir: Path,
) -> str:
    """Dispatch a write operation to a KB by its registered name (fire-and-forget).

    Looks up the KB path in knowledge_bases/registry.yaml, then delegates
    to ``kb_write_by_path()``.

    Args:
        kb_name: Registered KB name.
        instruction: The write instruction for the sub-agent.
        adj_dir: Adjutant root directory.

    Returns:
        Confirmation message string.

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

    return kb_write_by_path(Path(kb_path_str), instruction, adj_dir)


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
