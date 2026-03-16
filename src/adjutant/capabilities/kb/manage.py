"""Knowledge base CRUD operations.

Replaces: scripts/capabilities/kb/manage.sh

Provides functions for creating, registering, unregistering, listing,
and inspecting knowledge bases. Used by the CLI (adjutant kb) and the
interactive wizard (kb_wizard.py).

The registry file is knowledge_bases/registry.yaml — a simple hand-written
YAML file parsed line-by-line (no yq dependency, matching bash behaviour).

Scaffold template variables replaced by kb_scaffold():
  {{KB_NAME}}, {{KB_DESCRIPTION}}, {{KB_MODEL}}, {{KB_ACCESS}},
  {{KB_WRITE_ENABLED}}, {{KB_CREATED}}
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class KBEntry:
    name: str
    path: str = ""
    description: str = ""
    model: str = "inherit"
    access: str = "read-only"
    created: str = ""

    def as_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "path": self.path,
            "description": self.description,
            "model": self.model,
            "access": self.access,
            "created": self.created,
        }


# ---------------------------------------------------------------------------
# Registry helpers
# ---------------------------------------------------------------------------

_ENTRY_START = re.compile(r'^\s*-\s+name:\s+"?([^"]+)"?\s*$')
_FIELD = re.compile(r'^\s+([\w]+):\s+"?([^"]*)"?\s*$')


def _load_registry(registry_path: Path) -> list[KBEntry]:
    """Parse registry.yaml into a list of KBEntry objects."""
    if not registry_path.is_file():
        return []

    entries: list[KBEntry] = []
    current: KBEntry | None = None

    for line in registry_path.read_text().splitlines():
        m = _ENTRY_START.match(line)
        if m:
            if current is not None:
                entries.append(current)
            current = KBEntry(name=m.group(1))
            continue
        if current is not None:
            fm = _FIELD.match(line)
            if fm:
                fname, fval = fm.group(1), fm.group(2)
                if fname == "path":
                    current.path = fval
                elif fname == "description":
                    current.description = fval
                elif fname == "model":
                    current.model = fval
                elif fname == "access":
                    current.access = fval
                elif fname == "created":
                    current.created = fval

    if current is not None:
        entries.append(current)

    return entries


def _write_registry(registry_path: Path, entries: list[KBEntry]) -> None:
    """Write the full entries list back to registry.yaml."""
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    if not entries:
        registry_path.write_text("knowledge_bases: []\n")
        return

    lines = ["knowledge_bases:"]
    for e in entries:
        lines.append(f'  - name: "{e.name}"')
        lines.append(f'    description: "{e.description}"')
        lines.append(f'    path: "{e.path}"')
        lines.append(f'    model: "{e.model}"')
        lines.append(f'    access: "{e.access}"')
        lines.append(f'    created: "{e.created}"')
    registry_path.write_text("\n".join(lines) + "\n")


def _registry_path(adj_dir: Path) -> Path:
    return adj_dir / "knowledge_bases" / "registry.yaml"


def _templates_path(adj_dir: Path) -> Path:
    return adj_dir / "templates" / "kb"


# ---------------------------------------------------------------------------
# Public query API
# ---------------------------------------------------------------------------


def kb_count(adj_dir: Path) -> int:
    """Return the number of registered KBs."""
    return len(_load_registry(_registry_path(adj_dir)))


def kb_exists(adj_dir: Path, name: str) -> bool:
    """Return True if a KB with the given name is registered."""
    return any(e.name == name for e in _load_registry(_registry_path(adj_dir)))


def kb_list(adj_dir: Path) -> list[KBEntry]:
    """Return all registered KB entries."""
    return _load_registry(_registry_path(adj_dir))


def kb_info(adj_dir: Path, name: str) -> KBEntry:
    """Return the KBEntry for a given name.

    Raises:
        ValueError: If the KB is not registered.
    """
    for entry in _load_registry(_registry_path(adj_dir)):
        if entry.name == name:
            return entry
    raise ValueError(f"Knowledge base '{name}' not found in registry.")


def kb_get_field(adj_dir: Path, name: str, field_name: str) -> str:
    """Get a single field from a KB entry. Returns empty string if not found."""
    try:
        entry = kb_info(adj_dir, name)
        return getattr(entry, field_name, "") or ""
    except ValueError:
        return ""


def kb_get_operation_script(adj_dir: Path, name: str, operation: str) -> Path:
    """Resolve the path to a KB-local operation script.

    Convention: <kb-path>/scripts/<operation>.sh

    Args:
        adj_dir: Adjutant root directory.
        name: KB name.
        operation: Operation name (lowercase letters, digits, hyphens, underscores).

    Returns:
        Absolute Path to the script.

    Raises:
        ValueError: If name or operation is invalid, KB not found, or script missing.
    """
    if not re.match(r"^[a-z][a-z0-9_-]*$", operation):
        raise ValueError(
            f"Invalid KB operation '{operation}'. "
            "Use lowercase letters, digits, hyphens, or underscores."
        )

    entry = kb_info(adj_dir, name)  # raises ValueError if missing

    kb_path = Path(entry.path)
    if not kb_path.is_dir():
        raise ValueError(f"KB directory does not exist: {kb_path}")

    script_path = kb_path / "scripts" / f"{operation}.sh"
    if not script_path.is_file():
        raise ValueError(
            f"KB '{name}' does not implement operation '{operation}' (expected {script_path})."
        )

    return script_path


# ---------------------------------------------------------------------------
# Registry mutations
# ---------------------------------------------------------------------------


def kb_register(
    adj_dir: Path,
    name: str,
    path: str,
    description: str,
    model: str = "inherit",
    access: str = "read-only",
    created: str | None = None,
) -> None:
    """Register a KB in the registry.

    Raises:
        ValueError: If a KB with the same name is already registered.
    """
    reg = _registry_path(adj_dir)
    entries = _load_registry(reg)

    if any(e.name == name for e in entries):
        raise ValueError(f"Knowledge base '{name}' already registered.")

    new_entry = KBEntry(
        name=name,
        path=path,
        description=description,
        model=model,
        access=access,
        created=created or date.today().isoformat(),
    )
    entries.append(new_entry)
    _write_registry(reg, entries)


def kb_unregister(adj_dir: Path, name: str) -> None:
    """Remove a KB from the registry. Does NOT delete files on disk.

    Raises:
        ValueError: If the KB is not registered.
    """
    reg = _registry_path(adj_dir)
    entries = _load_registry(reg)

    new_entries = [e for e in entries if e.name != name]
    if len(new_entries) == len(entries):
        raise ValueError(f"Knowledge base '{name}' not found in registry.")

    _write_registry(reg, new_entries)


# ---------------------------------------------------------------------------
# Scaffold
# ---------------------------------------------------------------------------


def _render_template(template_path: Path, variables: dict[str, str]) -> str:
    """Render a template file by replacing {{VAR}} placeholders."""
    text = template_path.read_text()
    for key, value in variables.items():
        text = text.replace("{{" + key + "}}", value)
    return text


def _write_kb_opencode_json(kb_path: Path, access: str) -> None:
    """Generate opencode.json for a KB, tailored to its access level.

    All KBs get:
      - external_directory: deny  (sandbox)
      - read/glob deny for .env and secrets
      - bash: deny  (no shell execution)

    Read-write KBs additionally get edit/write allowed (implicit by
    omitting deny rules for those tools). Read-only KBs get edit denied.
    """
    permission: dict[str, Any] = {
        "external_directory": "deny",
        "read": {
            "*": "allow",
            "**/.env": "deny",
            ".env": "deny",
            "**/.env.*": "deny",
            "**/*secret*": "deny",
            "**/*credential*": "deny",
        },
        "glob": {
            "*": "allow",
            "**/.env": "deny",
            ".env": "deny",
        },
        "bash": {
            "*": "deny",
        },
    }

    if access != "read-write":
        permission["edit"] = {"*": "deny"}
        permission["write"] = {"*": "deny"}

    config = {
        "$schema": "https://opencode.ai/config.json",
        "permission": permission,
    }

    (kb_path / "opencode.json").write_text(json.dumps(config, indent=2) + "\n")


def kb_scaffold(
    adj_dir: Path,
    name: str,
    kb_path: Path,
    description: str,
    model: str = "inherit",
    access: str = "read-only",
) -> None:
    """Create the scaffold files for a new KB at kb_path.

    Directory structure created:
      kb.yaml                  — Adjutant metadata
      .opencode/agents/kb.md  — sub-agent definition
      opencode.json            — workspace permissions
      docs/README.md           — orientation doc (if no .md files exist)
      data/current.md          — live status stub
      data/.gitkeep
      knowledge/.gitkeep
      history/.gitkeep
      state/.gitkeep
      templates/.gitkeep
      docs/reference/.gitkeep

    Template variables substituted: KB_NAME, KB_DESCRIPTION, KB_MODEL,
    KB_ACCESS, KB_WRITE_ENABLED, KB_CREATED.
    """
    templates = _templates_path(adj_dir)
    created = date.today().isoformat()
    write_enabled = "true" if access == "read-write" else "false"

    variables = {
        "KB_NAME": name,
        "KB_DESCRIPTION": description,
        "KB_MODEL": model,
        "KB_ACCESS": access,
        "KB_WRITE_ENABLED": write_enabled,
        "KB_CREATED": created,
    }

    # Create standard directory structure
    for subdir in [
        ".opencode/agents",
        "data",
        "docs",
        "docs/reference",
        "knowledge",
        "history",
        "state",
        "templates",
    ]:
        (kb_path / subdir).mkdir(parents=True, exist_ok=True)

    # kb.yaml from template
    kb_yaml_tmpl = templates / "kb.yaml"
    if kb_yaml_tmpl.is_file():
        (kb_path / "kb.yaml").write_text(_render_template(kb_yaml_tmpl, variables))

    # opencode.json — generated dynamically based on access level
    _write_kb_opencode_json(kb_path, access)

    # Agent definition
    agent_tmpl = templates / "agents" / "kb.md"
    if agent_tmpl.is_file():
        (kb_path / ".opencode" / "agents" / "kb.md").write_text(
            _render_template(agent_tmpl, variables)
        )

    # docs/README.md — only if no existing .md files in docs/
    readme_tmpl = templates / "docs" / "README.md"
    docs_dir = kb_path / "docs"
    existing_docs = list(docs_dir.glob("*.md"))
    if (
        readme_tmpl.is_file()
        and not (kb_path / "docs" / "README.md").exists()
        and not existing_docs
    ):
        (kb_path / "docs" / "README.md").write_text(_render_template(readme_tmpl, variables))

    # data/current.md stub
    current_md = kb_path / "data" / "current.md"
    if not current_md.exists():
        current_md.write_text(
            f"# Current Status — {name}\n"
            f"Last updated: {created}\n\n"
            "---\n\n"
            "## Active priorities\n\n"
            "- (fill in)\n\n"
            "## Open items / blockers\n\n"
            "- (fill in)\n\n"
            "## What's coming up\n\n"
            "- (fill in)\n\n"
            "## Key references\n\n"
            "- (add links to key files as the KB grows)\n"
        )

    # .gitkeep placeholders
    for gitkeep_dir in ["knowledge", "history", "state", "docs/reference", "templates"]:
        (kb_path / gitkeep_dir / ".gitkeep").touch()


# ---------------------------------------------------------------------------
# Content detection
# ---------------------------------------------------------------------------

_CONTENT_PATTERNS: list[tuple[str, str]] = [
    ("markdown", "*.md"),
    ("code", "*.py"),
    ("code", "*.js"),
    ("code", "*.ts"),
    ("code", "*.sh"),
    ("code", "*.go"),
    ("code", "*.rs"),
    ("code", "*.rb"),
    ("code", "*.java"),
    ("data", "*.json"),
    ("data", "*.yaml"),
    ("data", "*.yml"),
    ("text", "*.txt"),
    ("text", "*.rst"),
    ("text", "*.org"),
    ("pdf", "*.pdf"),
]


def kb_detect_content(kb_path: Path) -> str:
    """Detect content types present in an existing KB directory.

    Returns:
        Comma-separated list of detected types (e.g. "markdown,code,json"),
        or "empty" if no recognised files are found.
    """
    if not kb_path.is_dir():
        return "empty"

    found: list[str] = []
    seen: set[str] = set()

    for content_type, pattern in _CONTENT_PATTERNS:
        if content_type in seen:
            continue
        # Search up to depth 3
        for depth in ["*", "*/*", "*/*/*"]:
            matches = list(kb_path.glob(f"{depth}/{pattern}"))
            if not matches:
                matches = list(kb_path.glob(pattern))
            if matches:
                found.append(content_type)
                seen.add(content_type)
                break

    return ",".join(found) if found else "empty"


# ---------------------------------------------------------------------------
# Combined create / remove
# ---------------------------------------------------------------------------

_VALID_KB_NAME = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")


def kb_create(
    adj_dir: Path,
    name: str,
    kb_path: Path,
    description: str,
    model: str = "inherit",
    access: str = "read-only",
) -> None:
    """Scaffold + register a new KB.

    Args:
        adj_dir: Adjutant root directory.
        name: KB name (lowercase alphanumeric + hyphens).
        kb_path: Absolute path where the KB will be created.
        description: Human-readable description.
        model: LLM model string or 'inherit'.
        access: 'read-only' or 'read-write'.

    Raises:
        ValueError: If name invalid, path relative, or name already registered.
    """
    # Validate name
    if not _VALID_KB_NAME.match(name):
        raise ValueError(
            f"KB name must be lowercase alphanumeric with hyphens (e.g. 'ml-papers'), got '{name}'."
        )

    # Validate path is absolute
    if not kb_path.is_absolute():
        raise ValueError(f"KB path must be absolute (got '{kb_path}').")

    # Check duplicate
    if kb_exists(adj_dir, name):
        raise ValueError(f"Knowledge base '{name}' already registered.")

    kb_scaffold(adj_dir, name, kb_path, description, model, access)
    kb_register(adj_dir, name, str(kb_path), description, model, access)


def kb_remove(adj_dir: Path, name: str) -> None:
    """Unregister a KB (does NOT delete files on disk).

    Raises:
        ValueError: If the KB is not registered.
    """
    kb_unregister(adj_dir, name)
