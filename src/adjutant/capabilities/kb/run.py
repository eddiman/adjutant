"""Run a KB-local operation by KB name.

Replaces: scripts/capabilities/kb/run.sh

The bash script:
  1. Sources paths.sh + kb/manage.sh
  2. Looks up the KB in the registry via kb_get_operation_script()
  3. Resolves the operation script path: <kb-path>/scripts/<operation>.sh
  4. Runs it via bash, capturing stdout+stderr
  5. Returns OK:<output> or ERROR:<reason>

This module reproduces that logic in Python, reading the KB registry YAML
directly (no bash subprocess needed).
"""

from __future__ import annotations

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


def _load_registry(adj_dir: Path) -> list[dict[str, str]]:
    """Parse knowledge_bases/registry.yaml into a list of dicts.

    The registry is a hand-written YAML file in the format:

        knowledge_bases:
          - name: "my-notes"
            path: "/path/to/kb"
            description: "..."
            model: "inherit"
            access: "read-only"
            created: "2026-01-01"

    We parse it without an external YAML library to match the pure-bash
    line-by-line approach in manage.sh (which also avoids yq).  The
    registry structure is simple enough that this is safe.
    """
    registry_path = adj_dir / "knowledge_bases" / "registry.yaml"
    if not registry_path.is_file():
        return []

    entries: list[dict[str, str]] = []
    current: dict[str, str] = {}

    for line in registry_path.read_text().splitlines():
        # New entry
        m = re.match(r'\s*-\s+name:\s+"?([^"]+)"?', line)
        if m:
            if current:
                entries.append(current)
            current = {"name": m.group(1)}
            continue
        # Field: value pairs inside an entry block
        for field in ("path", "description", "model", "access", "created"):
            m = re.match(rf'\s+{field}:\s+"?([^"]*)"?', line)
            if m:
                current[field] = m.group(1)
                break

    if current:
        entries.append(current)

    return entries


def _get_kb(adj_dir: Path, kb_name: str) -> dict[str, str]:
    """Return the registry entry for kb_name or raise KBNotFoundError."""
    entries = _load_registry(adj_dir)
    for entry in entries:
        if entry.get("name") == kb_name:
            return entry
    raise KBNotFoundError(f"Knowledge base '{kb_name}' not found in registry.")


_VALID_OPERATION = re.compile(r"^[a-z][a-z0-9_-]*$")


def get_operation_script(adj_dir: Path, kb_name: str, operation: str) -> Path:
    """Resolve the script path for a KB operation.

    Matches bash kb_get_operation_script():
        <kb-path>/scripts/<operation>.sh

    Args:
        adj_dir: Adjutant root directory.
        kb_name: Name of the knowledge base.
        operation: Operation name (e.g. "fetch", "analyze", "reconcile").

    Returns:
        Absolute Path to the operation script.

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


def kb_run(
    adj_dir: Path,
    kb_name: str,
    operation: str,
    args: list[str] | None = None,
) -> str:
    """Run a KB-local operation and return its stdout.

    Matches bash kb_run() in run.sh:
      - Resolves the operation script
      - Runs it via bash, capturing combined stdout+stderr
      - Returns the output on success

    Args:
        adj_dir: Adjutant root directory.
        kb_name: Name of the knowledge base.
        operation: Operation name.
        args: Additional arguments to pass to the operation script.

    Returns:
        Captured stdout from the operation script.

    Raises:
        KBNotFoundError: If KB or its directory is not found.
        KBOperationNotFoundError: If the operation script does not exist.
        KBRunError: If the script exits non-zero.
        ValueError: If operation name is invalid.
    """
    script_path = get_operation_script(adj_dir, kb_name, operation)
    cmd = ["bash", str(script_path)] + (args or [])

    result = subprocess.run(cmd, capture_output=True, text=True)
    combined = result.stdout + result.stderr

    if result.returncode != 0:
        raise KBRunError(combined.strip())

    return result.stdout


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: kb_run.py <kb-name> <operation> [args...]

    Mirrors the bash script's CLI contract:
      OK:<output>   on success (exit 0)
      ERROR:<msg>   on failure (exit 1)
    """
    import os as _os

    args = argv if argv is not None else sys.argv[1:]

    if len(args) < 2:
        sys.stderr.write("Usage: run.py <kb-name> <operation> [args...]\n")
        return 1

    kb_name, operation, *extra = args

    adj_dir_str = _os.environ.get("ADJ_DIR", "").strip()
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
