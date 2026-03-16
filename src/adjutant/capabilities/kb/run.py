"""Run a KB-local operation by KB name.

Two invocation modes are supported:

1. **Python CLI** (preferred): If the KB's ``kb.yaml`` declares a
   ``cli_module`` field (e.g. ``cli_module: "src.cli"``), ``kb_run``
   invokes the KB's own venv Python directly::

       <kb-path>/.venv/bin/python -m <cli_module> <cli_flags> <operation> [args...]

   The KB receives its directory via the ``KB_DIR`` environment variable
   and ``cwd``.  No bash shim is needed. The KB's ``.venv`` must exist.

2. **Bash script** (legacy fallback): If ``cli_module`` is absent or empty,
   ``kb_run`` resolves ``<kb-path>/scripts/<operation>.sh`` and runs it via
   ``bash``. This preserves backward compatibility for KBs that still use
   shell scripts.

KB operations may emit structured JSON events on stderr (one per line)::

    {"type": "notification", "ts": "...", "message": "..."}

These are captured and forwarded via Adjutant's notification system.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path


class KBNotFoundError(Exception):
    """Raised when the KB name is not in the registry."""


class KBOperationNotFoundError(Exception):
    """Raised when the operation script does not exist in the KB."""


class KBRunError(Exception):
    """Raised when the operation script exits non-zero."""


def _get_kb(adj_dir: Path, kb_name: str) -> dict[str, str]:
    """Return the registry entry for kb_name or raise KBNotFoundError.

    Delegates to the canonical registry parser in manage.py and converts
    the KBEntry dataclass to a plain dict for backward compatibility with
    callers that use ``entry.get("path")``, ``entry["name"]``, etc.
    """
    from adjutant.capabilities.kb.manage import kb_info

    try:
        entry = kb_info(adj_dir, kb_name)
    except ValueError as exc:
        raise KBNotFoundError(str(exc)) from exc

    return entry.as_dict()


_VALID_OPERATION = re.compile(r"^[a-z][a-z0-9_-]*$")


def _read_kb_cli_module(kb_path: Path) -> str:
    """Read the ``cli_module`` field from a KB's ``kb.yaml``.

    Returns the module string (e.g. ``"src.cli"``) if declared, or an
    empty string if absent or unset.
    """
    kb_yaml = kb_path / "kb.yaml"
    if not kb_yaml.is_file():
        return ""
    for line in kb_yaml.read_text().splitlines():
        m = re.match(r"^cli_module:\s*\"?([^\"#\n]*)\"?\s*$", line)
        if m:
            return m.group(1).strip()
    return ""


def _read_kb_cli_flags(kb_path: Path) -> list[str]:
    """Read the ``cli_flags`` field from a KB's ``kb.yaml``.

    Returns a list of flag tokens to insert before the operation name
    when invoking the KB's Python CLI.  Defaults to
    ``["--real"]`` if the field is absent or empty, so existing KBs that do
    not set ``cli_flags`` continue to run with real-API mode.

    Example kb.yaml entries:
        cli_flags: "--mock"        → ["--mock"]
        cli_flags: "--real"        → ["--real"]
        cli_flags: "--mock --verbose"  → ["--mock", "--verbose"]
    """
    kb_yaml = kb_path / "kb.yaml"
    if kb_yaml.is_file():
        for line in kb_yaml.read_text().splitlines():
            m = re.match(r"^cli_flags:\s*\"?([^\"#\n]*)\"?\s*$", line)
            if m:
                value = m.group(1).strip()
                if value:
                    return value.split()
    return ["--real"]


def _resolve_kb_python(kb_path: Path) -> Path:
    """Return the path to the Python interpreter inside the KB's venv.

    Raises:
        KBRunError: If ``.venv/bin/python`` does not exist.
    """
    python = kb_path / ".venv" / "bin" / "python"
    if not python.is_file():
        raise KBRunError(
            f"KB at {kb_path} declares a cli_module but has no .venv/bin/python. "
            "Run: python3 -m venv .venv && .venv/bin/pip install -e ."
        )
    return python


def get_operation_script(adj_dir: Path, kb_name: str, operation: str) -> Path:
    """Resolve the bash script path for a KB operation (legacy path).

    Used only when the KB does not declare a ``cli_module``.

    Args:
        adj_dir: Adjutant root directory.
        kb_name: Name of the knowledge base.
        operation: Operation name (e.g. "fetch", "analyze", "reconcile").

    Returns:
        Absolute Path to the operation shell script.

    Raises:
        KBNotFoundError: If the KB is not registered.
        KBOperationNotFoundError: If the script does not exist.
        ValueError: If the operation name is invalid.
    """
    if not _VALID_OPERATION.match(operation):
        raise ValueError(
            f"Invalid KB operation '{operation}'. "
            "Use lowercase letters, digits, hyphens, or underscores."
        )

    entry = _get_kb(adj_dir, kb_name)
    kb_path_str = entry.get("path", "")
    if not kb_path_str:
        raise KBNotFoundError(f"KB '{kb_name}' has no path in registry.")

    kb_path = Path(kb_path_str)
    if not kb_path.is_dir():
        raise KBNotFoundError(f"KB directory does not exist: {kb_path}")

    script_path = kb_path / "scripts" / f"{operation}.sh"
    if not script_path.is_file():
        raise KBOperationNotFoundError(
            f"KB '{kb_name}' does not implement operation '{operation}' (expected {script_path})."
        )

    return script_path


def _forward_kb_events(stderr: str, adj_dir: Path, kb_name: str) -> None:
    """Parse structured JSON events from KB stderr and forward notifications.

    KB operations emit one JSON object per line on stderr. Lines that are not
    valid JSON (e.g. warnings, debug output) are silently ignored.
    """
    if not stderr.strip():
        return

    from adjutant.core.logging import adj_log

    for line in stderr.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue

        if not isinstance(event, dict) or event.get("type") != "notification":
            continue

        message = event.get("message", "")
        if not message:
            continue

        try:
            from adjutant.messaging.telegram.notify import send_notify

            send_notify(f"[{kb_name}] {message}", adj_dir)
        except Exception as exc:
            adj_log("kb", f"Failed to forward notification from {kb_name}: {exc}")


def kb_run(
    adj_dir: Path,
    kb_name: str,
    operation: str,
    args: list[str] | None = None,
) -> str:
    """Run a KB-local operation and return its stdout.

    Prefers Python CLI invocation when the KB's ``kb.yaml`` declares a
    ``cli_module`` field. Falls back to running ``scripts/<operation>.sh``
    via bash for KBs without a Python CLI.

    Args:
        adj_dir: Adjutant root directory.
        kb_name: Name of the knowledge base.
        operation: Operation name.
        args: Additional arguments to pass to the operation.

    Returns:
        Captured stdout from the operation.

    Raises:
        KBNotFoundError: If KB or its directory is not found.
        KBOperationNotFoundError: If the bash operation script does not exist
            (only raised on the bash fallback path).
        KBRunError: If the operation exits non-zero, or if the KB venv is
            missing (Python CLI path).
        ValueError: If operation name is invalid.
    """
    if not _VALID_OPERATION.match(operation):
        raise ValueError(
            f"Invalid KB operation '{operation}'. "
            "Use lowercase letters, digits, hyphens, or underscores."
        )

    entry = _get_kb(adj_dir, kb_name)
    kb_path_str = entry.get("path", "")
    if not kb_path_str:
        raise KBNotFoundError(f"KB '{kb_name}' has no path in registry.")

    kb_path = Path(kb_path_str)
    if not kb_path.is_dir():
        raise KBNotFoundError(f"KB directory does not exist: {kb_path}")

    env = os.environ.copy()
    env["ADJUTANT_HOME"] = str(adj_dir)
    env["ADJ_DIR"] = str(adj_dir)
    env["KB_DIR"] = str(kb_path)

    # Resolve model from registry tier → concrete model ID.
    # Passed via KB_MODEL env var so KB CLIs can read it if they care,
    # without requiring every KB to accept a --model CLI flag.
    extra_args: list[str] = list(args or [])
    kb_model_raw = entry.get("model", "")
    if kb_model_raw:
        from adjutant.core.config import load_config
        from adjutant.core.model import resolve_kb_model

        config = load_config(adj_dir / "adjutant.yaml")
        resolved_model = resolve_kb_model(kb_model_raw, adj_dir / "state", config)
        if resolved_model:
            env["KB_MODEL"] = resolved_model

    cli_module = _read_kb_cli_module(kb_path)

    if cli_module:
        # Python CLI path — invoke the KB's own venv Python directly.
        # The KB receives its path via KB_DIR env var and cwd (both set
        # above), so we do NOT inject --kb-dir on the command line —
        # KB CLIs are not required to accept that flag.
        python = _resolve_kb_python(kb_path)
        cli_flags = _read_kb_cli_flags(kb_path)
        cmd = [
            str(python),
            "-m",
            cli_module,
            *cli_flags,
            operation,
        ] + extra_args
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(kb_path), env=env)
    else:
        # Bash fallback — legacy script-based KB.
        script_path = get_operation_script(adj_dir, kb_name, operation)
        cmd = ["bash", str(script_path)] + extra_args
        result = subprocess.run(cmd, capture_output=True, text=True, env=env)

    # Forward any structured events from stderr before raising errors.
    _forward_kb_events(result.stderr, adj_dir, kb_name)

    if result.returncode != 0:
        combined = result.stdout + result.stderr
        raise KBRunError(combined.strip())

    return result.stdout


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: kb_run.py <kb-name> <operation> [args...]

    Mirrors the bash script's CLI contract:
      OK:<output>   on success (exit 0)
      ERROR:<msg>   on failure (exit 1)
    """
    args = argv if argv is not None else sys.argv[1:]

    if len(args) < 2:
        sys.stderr.write("Usage: run.py <kb-name> <operation> [args...]\n")
        return 1

    kb_name, operation, *extra = args

    adj_dir_str = os.environ.get("ADJ_DIR", "").strip()
    if not adj_dir_str:
        sys.stderr.write("ERROR: ADJ_DIR not set\n")
        return 1

    adj_dir = Path(adj_dir_str)

    try:
        output = kb_run(adj_dir, kb_name, operation, extra)
        print(output, end="")
        return 0
    except (KBNotFoundError, KBOperationNotFoundError, KBRunError, ValueError) as exc:
        sys.stderr.write(f"ERROR: {exc}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
