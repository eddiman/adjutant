"""Interactive knowledge-base creation wizard.

Replaces: scripts/setup/steps/kb_wizard.sh

Supports two modes:
  Interactive (default): full multi-step wizard
  Quick (--quick):       non-interactive one-liner scaffold
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from adjutant.setup.wizard import (
    expand_path,
    wiz_confirm,
    wiz_header,
    wiz_info,
    wiz_input,
    wiz_ok,
    wiz_warn,
)

_VALID_KB_NAME = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")


# ---------------------------------------------------------------------------
# Registry helpers (mirror capabilities/kb/run.py registry parser)
# ---------------------------------------------------------------------------


def _kb_exists(adj_dir: Path, name: str) -> bool:
    """Return True if a KB with this name is in the registry."""
    registry = adj_dir / "knowledge_bases" / "registry.yaml"
    if not registry.is_file():
        return False
    for line in registry.read_text().splitlines():
        m = re.match(r'\s*-\s+name:\s+"?([^"]+)"?', line)
        if m and m.group(1) == name:
            return True
    return False


def _detect_content(kb_path: Path) -> str:
    """Return a comma-separated list of what's in kb_path."""
    if not kb_path.is_dir():
        return "empty"
    items = [p.name for p in kb_path.iterdir()]
    if not items:
        return "empty"
    return ", ".join(sorted(items)[:6])


def _kb_create(
    adj_dir: Path, name: str, kb_path: Path, description: str, model: str, access: str
) -> None:
    """Scaffold a new KB directory and register it."""
    from adjutant.capabilities.kb.manage import kb_create

    kb_create(adj_dir, name, kb_path, description, model, access)


def _kb_create_simple(
    adj_dir: Path, name: str, kb_path: Path, description: str, model: str, access: str
) -> None:
    """Scaffold KB directory and register without calling bash manage.sh.

    This is the pure-Python path used when the kb manage module is not yet
    migrated. Writes the registry entry directly.
    """
    # Create directory structure
    for subdir in ["data", "knowledge", "history", "templates", "scripts"]:
        (kb_path / subdir).mkdir(parents=True, exist_ok=True)

    # Write kb.yaml
    from datetime import date

    kb_yaml = kb_path / "kb.yaml"
    kb_yaml.write_text(
        f'name: "{name}"\n'
        f'description: "{description}"\n'
        f'model: "{model}"\n'
        f'access: "{access}"\n'
        f'created: "{date.today().isoformat()}"\n'
    )

    # Write minimal current.md
    current_md = kb_path / "data" / "current.md"
    if not current_md.exists():
        current_md.write_text(f"# {name} — Current Status\n\n*No data yet.*\n")

    # Register in registry.yaml
    registry = adj_dir / "knowledge_bases" / "registry.yaml"
    registry.parent.mkdir(parents=True, exist_ok=True)

    from datetime import date as _date

    entry = (
        f'\n  - name: "{name}"\n'
        f'    path: "{kb_path}"\n'
        f'    description: "{description}"\n'
        f'    model: "{model}"\n'
        f'    access: "{access}"\n'
        f'    created: "{_date.today().isoformat()}"\n'
    )

    if registry.is_file():
        text = registry.read_text()
        if "knowledge_bases:" in text:
            registry.write_text(text + entry)
        else:
            registry.write_text("knowledge_bases:" + entry)
    else:
        registry.write_text("knowledge_bases:" + entry)


# ---------------------------------------------------------------------------
# Quick mode
# ---------------------------------------------------------------------------


def kb_quick_create(
    adj_dir: Path,
    name: str,
    kb_path: str,
    description: str = "",
    model: str = "inherit",
    access: str = "read-only",
) -> None:
    """Non-interactive KB creation.

    Args:
        adj_dir: Adjutant root directory.
        name: KB name.
        kb_path: Path to KB workspace (expanded).
        description: Optional description.
        model: Model tier or explicit ID.
        access: 'read-only' or 'read-write'.

    Raises:
        ValueError: If name or path are invalid.
        RuntimeError: If creation fails.
    """
    if not name or not kb_path:
        raise ValueError("--name and --path are required")

    expanded = Path(expand_path(kb_path))
    desc = description or f"Knowledge base: {name}"

    _kb_create_simple(adj_dir, name, expanded, desc, model, access)
    print(f"OK: Created knowledge base '{name}' at {expanded}")


# ---------------------------------------------------------------------------
# Interactive mode
# ---------------------------------------------------------------------------


def kb_wizard_interactive(adj_dir: Path) -> None:
    """Run the full interactive KB creation wizard.

    Args:
        adj_dir: Adjutant root directory.
    """
    wiz_header("Create a Knowledge Base")
    print("", file=sys.stderr)
    wiz_info("A KB is a scoped directory that Adjutant can query as a sub-agent.")
    wiz_info("Place docs, notes, or references in it and ask Adjutant questions.")
    print("", file=sys.stderr)

    # Step 1: Name
    name = ""
    while True:
        name = wiz_input("KB name (lowercase, hyphens ok)", "")
        if not name:
            wiz_warn("Name cannot be empty.")
            continue
        if not _VALID_KB_NAME.match(name):
            wiz_warn("Must be lowercase alphanumeric with hyphens (e.g., 'ml-papers').")
            continue
        if _kb_exists(adj_dir, name):
            wiz_warn(f"A KB named '{name}' already exists.")
            continue
        break

    # Step 2: Path
    default_path = str(Path.home() / "knowledge-bases" / name)
    kb_path_str = ""
    while True:
        kb_path_str = wiz_input("Directory path", default_path)
        kb_path_str = expand_path(kb_path_str)
        p = Path(kb_path_str)

        if not p.is_absolute():
            wiz_warn("Path must be absolute.")
            continue

        if p.is_dir() and any(p.iterdir()):
            content = _detect_content(p)
            wiz_info(f"Directory exists with content: {content}")
            if not wiz_confirm("Use this existing directory?", "Y"):
                continue
        break

    kb_path = Path(kb_path_str)

    # Step 3: Description
    description = wiz_input("Description (drives auto-detection)", "") or f"Knowledge base: {name}"

    # Step 4: Access level
    choice = 0
    from adjutant.setup.wizard import wiz_choose

    choice = wiz_choose(
        "Access level for the sub-agent?",
        "Read-only (recommended — agent can read but not modify)",
        "Read-write (agent can also create and edit files)",
    )
    access = "read-write" if choice == 2 else "read-only"

    # Step 5: Model
    model = "inherit"
    if not wiz_confirm("Use Adjutant's current model?", "Y"):
        model = wiz_input("Model name (e.g., anthropic/claude-haiku-4-5)", "inherit")

    # Summary
    print("", file=sys.stderr)
    wiz_header("Summary")
    wiz_info(f"Name:        {name}")
    wiz_info(f"Path:        {kb_path}")
    wiz_info(f"Description: {description}")
    wiz_info(f"Access:      {access}")
    wiz_info(f"Model:       {model}")
    print("", file=sys.stderr)

    if not wiz_confirm("Create this knowledge base?", "Y"):
        print("Cancelled.", file=sys.stderr)
        return

    _kb_create_simple(adj_dir, name, kb_path, description, model, access)

    print("", file=sys.stderr)
    wiz_ok(f"Knowledge base '{name}' created!")
    wiz_info(f"Path:     {kb_path}")
    wiz_info(f"Registry: {adj_dir}/knowledge_bases/registry.yaml")
    print("", file=sys.stderr)
    wiz_info("Next steps:")
    wiz_info(f"  1. Fill in {kb_path}/data/current.md — live status snapshot")
    wiz_info(f"  2. Add reference docs to {kb_path}/knowledge/")
    wiz_info("  3. Update README.md with what questions this KB can answer")
    wiz_info("  4. Ask Adjutant a question — it will auto-detect this KB by description.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """CLI entry point.

    Usage:
        kb_wizard.py                          # interactive
        kb_wizard.py --quick --name n --path p [--desc "..."] [--model m] [--access a]
    """
    import os

    args = argv if argv is not None else sys.argv[1:]

    adj_dir_str = os.environ.get("ADJ_DIR", "").strip()
    if not adj_dir_str:
        sys.stderr.write("ERROR: ADJ_DIR not set\n")
        return 1
    adj_dir = Path(adj_dir_str)

    if args and args[0] == "--quick":
        rest = args[1:]
        kw: dict[str, str] = {}
        i = 0
        while i < len(rest):
            if rest[i] in ("--name",) and i + 1 < len(rest):
                kw["name"] = rest[i + 1]
                i += 2
            elif rest[i] in ("--path",) and i + 1 < len(rest):
                kw["kb_path"] = rest[i + 1]
                i += 2
            elif rest[i] in ("--desc",) and i + 1 < len(rest):
                kw["description"] = rest[i + 1]
                i += 2
            elif rest[i] in ("--model",) and i + 1 < len(rest):
                kw["model"] = rest[i + 1]
                i += 2
            elif rest[i] in ("--access",) and i + 1 < len(rest):
                kw["access"] = rest[i + 1]
                i += 2
            else:
                i += 1
        try:
            kb_quick_create(adj_dir, **kw)
            return 0
        except (ValueError, RuntimeError, TypeError) as exc:
            sys.stderr.write(f"ERROR: {exc}\n")
            return 1

    try:
        kb_wizard_interactive(adj_dir)
        return 0
    except (KeyboardInterrupt, SystemExit):
        print("\nCancelled.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
