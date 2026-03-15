"""Query and write to a knowledge base sub-agent via opencode.

Replaces: scripts/capabilities/kb/query.sh

Spawns ``opencode run --agent kb --dir <kb-path> --format json --model <model>``
with an 80-second timeout, parses NDJSON output, and returns the plain-text answer.

For writes, spawns the sub-agent as a detached background process and returns
immediately with a confirmation message (fire-and-forget).

Usage:
    result = await kb_query("my-kb", "What is the current portfolio value?", adj_dir)
    result = await kb_query_by_path("/path/to/kb", "question", adj_dir)
    msg = kb_write("my-kb", "Update issue #12: mark complete", adj_dir)
    msg = kb_write_by_path("/path/to/kb", "Update issue #12", adj_dir)
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from adjutant.core.logging import adj_log
from adjutant.core.model import resolve_kb_model
from adjutant.core.opencode import OpenCodeNotFoundError, opencode_run
from adjutant.lib.ndjson import parse_ndjson

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
        OpenCodeNotFoundError: If opencode is not on PATH.
    """
    if not kb_path.is_dir():
        raise KBQueryError(f"KB directory does not exist: {kb_path}")
    if not query.strip():
        raise KBQueryError("Query is empty.")

    model = _resolve_model(kb_path, adj_dir)

    kb_name = kb_path.name
    adj_log("kb", f"Query start: kb='{kb_name}' model='{model}' timeout={timeout}s")

    args = [
        "run",
        "--agent",
        "kb",
        "--dir",
        str(kb_path),
        "--format",
        "json",
        "--model",
        model,
        query,
    ]

    result = await opencode_run(args, timeout=timeout)

    if result.returncode != 0 or result.timed_out:
        adj_log(
            "kb",
            f"Query exited non-zero rc={result.returncode} (kb='{kb_name}', timed_out={result.timed_out})",
        )

    parsed = parse_ndjson(result.stdout)
    reply = parsed.text

    if not reply:
        adj_log("kb", f"Query returned empty reply (kb='{kb_name}', rc={result.returncode})")
        return "The knowledge base did not return an answer. It may not contain relevant information for this query."

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
    from adjutant.capabilities.kb.run import _get_kb, KBNotFoundError

    try:
        entry = _get_kb(adj_dir, kb_name)
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
        OpenCodeNotFoundError: If opencode is not on PATH.
    """
    if not kb_path.is_dir():
        raise KBQueryError(f"KB directory does not exist: {kb_path}")
    if not instruction.strip():
        raise KBQueryError("Write instruction is empty.")

    opencode_bin = shutil.which("opencode")
    if opencode_bin is None:
        raise OpenCodeNotFoundError("opencode not found on PATH")

    model = _resolve_model(kb_path, adj_dir)
    kb_name = kb_path.name

    adj_log("kb", f"Write dispatched: kb='{kb_name}' model='{model}'")

    # Build the wrapper script that runs opencode and logs the result.
    # This runs as a fully detached process that survives parent exit.
    log_path = adj_dir / "state" / "adjutant.log"
    args = [
        opencode_bin,
        "run",
        "--agent",
        "kb",
        "--dir",
        str(kb_path),
        "--format",
        "json",
        "--model",
        model,
        instruction,
    ]

    # Spawn detached subprocess.  stdout/stderr are piped to /dev/null
    # from the parent's perspective — the wrapper script handles logging.
    # We use a small shell wrapper so we can log completion to adjutant.log.
    shell_script = (
        f"{' '.join(_shell_quote(a) for a in args)} > /dev/null 2>&1; "
        f"RC=$?; "
        f'TS=$(date "+%H:%M %d.%m.%Y"); '
        f'if [ "$RC" -eq 0 ]; then '
        f"  echo \"[$TS] [kb] Write complete: kb='{kb_name}'\" >> {_shell_quote(str(log_path))}; "
        f"else "
        f"  echo \"[$TS] [kb] Write failed: kb='{kb_name}' rc=$RC\" >> {_shell_quote(str(log_path))}; "
        f"fi"
    )

    subprocess.Popen(
        ["bash", "-c", shell_script],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        start_new_session=True,  # detach from parent process group
    )

    preview = instruction[:120]
    if len(instruction) > 120:
        preview += "..."
    return f"Write dispatched to '{kb_name}': {preview}"


def _shell_quote(s: str) -> str:
    """Quote a string for safe shell embedding."""
    import shlex

    return shlex.quote(s)


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
    from adjutant.capabilities.kb.run import _get_kb, KBNotFoundError

    try:
        entry = _get_kb(adj_dir, kb_name)
    except KBNotFoundError as exc:
        raise KBQueryError(str(exc)) from exc

    kb_path_str = entry.get("path", "")
    if not kb_path_str:
        raise KBQueryError(f"KB '{kb_name}' has no path in registry.")

    return kb_write_by_path(Path(kb_path_str), instruction, adj_dir)


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
    except (KBQueryError, OpenCodeNotFoundError) as exc:
        _sys.stderr.write(f"ERROR: {exc}\n")
        return 1
