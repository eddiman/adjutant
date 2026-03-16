"""Step 3: LLM-Driven Identity Generation.

Replaces: scripts/setup/steps/identity.sh

Generates soul.md and heart.md using OpenCode + Haiku based on user input.
Shows a token estimate before each LLM call and asks for confirmation.
If soul.md/heart.md already exist, offers to keep or regenerate.
Falls back to template files if opencode is unavailable or the user declines.
"""

from __future__ import annotations

import asyncio
import json
import shutil
import sys
from datetime import datetime
from typing import TYPE_CHECKING

from adjutant.setup.wizard import (
    BOLD,
    RESET,
    wiz_confirm,
    wiz_fail,
    wiz_info,
    wiz_input,
    wiz_ok,
    wiz_step,
    wiz_warn,
)

if TYPE_CHECKING:
    from pathlib import Path

# ---------------------------------------------------------------------------
# Meta-prompts (match identity.sh exactly)
# ---------------------------------------------------------------------------

_SOUL_META_PROMPT = """\
You are generating a soul.md file for an autonomous agent called Adjutant.

The soul.md defines the agent's identity, personality, values, \
escalation rules, and behavioral constraints.

Based on the user's description of what they need, generate a soul.md that follows this structure:

# Adjutant — Soul

**Identity**: [One sentence: what this agent IS]

**Personality**: [Adjective list: communication style]

**Values** (in order):
1. [Most important value]
2. [Second value]
3. [Third value]
4. [Fourth value]

**Escalate when**: [conditions that warrant proactive notification]
**Notify when**: [conditions for informational notifications]
**Stay silent when**: [when NOT to bother the user]
**Max notifications**: 2-3/day, batch minor items

**Telegram format**: `[Project] One sentence.` No greetings, no emoji, no sign-offs.

**Never**: [list of things the agent must never do — always include: \
edit project files autonomously, message anyone but the commander, \
notify > 3x/day without emergency, auto-restart after KILLED lockfile]

Keep it concise. The soul.md should be under 40 lines. Match the user's domain and concerns."""

_HEART_META_PROMPT = """\
You are generating a heart.md file for an autonomous agent called Adjutant.

The heart.md defines the agent's current priorities and active \
concerns. It changes frequently — the user edits it whenever \
their focus shifts.

Based on the user's description, generate a heart.md that follows this structure:

# Adjutant — Heart

What matters right now. Edit this file whenever your focus shifts.
Adjutant reads this on every heartbeat to know what to pay attention to.

**Last updated**: [today's date]

---

## Current Priorities

1. **[Priority name]** — [Brief description with any known dates/deadlines]
2. **[Priority name]** — [Brief description]

---

## Active Concerns

- [Things that need monitoring]
- [Potential issues to watch]

---

## Quiet Zones

Nothing muted right now.

---

## Notes

- [Planning horizon, cadence, constraints]
- Keep it to 1-3 priorities. If this list grows beyond 3, something needs to be deferred.

Keep it concise. Heart.md should be under 30 lines of content. \
Extract priorities from the user's description."""

# ---------------------------------------------------------------------------
# Token estimation (rough: 1 token ≈ 4 chars)
# ---------------------------------------------------------------------------

_HAIKU_IN_PER_1K = 0.00025
_HAIKU_OUT_PER_1K = 0.00125


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _show_estimate(input_tokens: int, output_tokens: int) -> None:
    cost = (input_tokens / 1000 * _HAIKU_IN_PER_1K) + (output_tokens / 1000 * _HAIKU_OUT_PER_1K)
    print(
        f"  {BOLD}Estimated cost:{RESET} ~{input_tokens} in / {output_tokens} out tokens"
        f" (≈ ${cost:.4f} with claude-haiku-4-5)",
        file=sys.stderr,
    )


# ---------------------------------------------------------------------------
# LLM call (opencode)
# ---------------------------------------------------------------------------


def _extract_opencode_text(ndjson: str) -> str:
    """Extract assembled text from opencode NDJSON output."""
    assembled: list[str] = []
    for line in ndjson.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            text = (obj.get("part") or {}).get("text") or ""
            if text:
                assembled.append(text)
        except (json.JSONDecodeError, AttributeError):
            pass
    return "".join(assembled)


def _run_opencode(prompt: str, adj_dir: Path) -> str | None:
    """Call opencode with the given prompt. Returns extracted text or None on failure."""
    try:
        from adjutant.core.opencode import opencode_run

        result = asyncio.run(
            opencode_run(
                ["--model", "anthropic/claude-haiku-4-5", "--format", "json", prompt],
            )
        )
        if result.returncode != 0 or result.timed_out:
            return None
        text = _extract_opencode_text(result.stdout)
        return text if text.strip() else None
    except Exception:  # noqa: BLE001 — fallback to template on LLM error
        return None


# ---------------------------------------------------------------------------
# Template fallbacks
# ---------------------------------------------------------------------------

_SOUL_TEMPLATE = """\
# Adjutant — Soul

**Identity**: Trusted aide. Never the decision-maker. Makes sure nothing slips.

**Personality**: Concise. Direct. Calm. Honest. Quiet by default. One line if one line is enough.

**Values** (in order):
1. Protect focus time — every notification is an interruption, earn it
2. No surprises — surface things before they become emergencies
3. Sustainable pace — 1-3 priorities, not 10
4. Accuracy over speed — don't guess, cite sources

**Escalate when**: watched file changed + relates to active concern, \
or deadline < 2 weeks with TBD items
**Notify when**: action needed within 48h, or material status change on a priority
**Stay silent when**: routine changes, low-priority projects, weekends (unless urgent)
**Max notifications**: 2-3/day, batch minor items

**Telegram format**: `[Project] One sentence.` No greetings, no emoji, no sign-offs.

**Never**: edit project files autonomously, message anyone but \
the commander, notify > 3x/day without emergency, \
auto-restart after KILLED lockfile
"""

_REGISTRY_TEMPLATE = """\
# Adjutant — Project Registry

Register projects here for Adjutant to monitor.
Each project has a path, key files to watch, and concerns.

---

## Projects

_No projects registered yet. Add your first project below._

<!--
### Example Project

- **Path**: ~/Projects/my-project
- **Watch**: README.md, package.json, CHANGELOG.md
- **Agent**: Tracks releases and dependency updates
- **Concerns**: Breaking changes, overdue PRs, stale branches
-->
"""


def _heart_template(today: str) -> str:
    return f"""\
# Adjutant — Heart

What matters right now. Edit this file whenever your focus shifts.
Adjutant reads this on every heartbeat to know what to pay attention to.

**Last updated**: {today}

---

## Current Priorities

1. **Get Adjutant running** — Complete setup wizard, verify Telegram connection works

---

## Active Concerns

- Initial configuration and testing

---

## Quiet Zones

Nothing muted right now.

---

## Notes

- Keep it to 1-3 priorities. If this list grows beyond 3, something needs to be deferred.
"""


def _write_templates(adj_dir: Path, *, dry_run: bool = False) -> None:
    today = datetime.now().strftime("%Y-%m-%d")
    identity_dir = adj_dir / "identity"
    if dry_run:
        wiz_ok("[DRY RUN] Would write template soul.md, heart.md, registry.md")
        return
    identity_dir.mkdir(parents=True, exist_ok=True)
    (identity_dir / "soul.md").write_text(_SOUL_TEMPLATE)
    (identity_dir / "heart.md").write_text(_heart_template(today))
    if not (identity_dir / "registry.md").is_file():
        (identity_dir / "registry.md").write_text(_REGISTRY_TEMPLATE)
    wiz_ok("Template identity files written")
    wiz_info("Edit these files to customize your agent:")
    wiz_info(f"  {adj_dir}/identity/soul.md")
    wiz_info(f"  {adj_dir}/identity/heart.md")
    wiz_info(f"  {adj_dir}/identity/registry.md")


# ---------------------------------------------------------------------------
# Multiline input helper
# ---------------------------------------------------------------------------


def _wiz_multiline(prompt: str) -> str:
    """Collect multi-line input until the user enters a blank line."""
    print(f"  {prompt}", file=sys.stderr)
    print("  (Press Enter twice when done)", file=sys.stderr)
    lines: list[str] = []
    try:
        while True:
            line = input()
            if not line and lines and not lines[-1]:
                break
            lines.append(line)
    except (EOFError, KeyboardInterrupt):
        print("", file=sys.stderr)
    # Strip the trailing blank line sentinel
    if lines and not lines[-1]:
        lines = lines[:-1]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Generation helpers
# ---------------------------------------------------------------------------


def _generate_soul(
    agent_name: str, user_description: str, adj_dir: Path, *, dry_run: bool = False
) -> bool:
    full_prompt = (
        f"{_SOUL_META_PROMPT}\n\n"
        f"The agent is called: {agent_name}\n\n"
        f"User's description of their needs:\n{user_description}\n\n"
        "Generate the soul.md content now. Output ONLY the markdown content, no code fences."
    )
    input_tokens = _estimate_tokens(full_prompt)
    output_tokens = 600  # soul.md ~ 40 lines

    print("", file=sys.stderr)
    print(f"  {BOLD}Generating soul.md...{RESET}", file=sys.stderr)
    _show_estimate(input_tokens, output_tokens)

    if not wiz_confirm("Proceed?", "Y"):
        return False

    if dry_run:
        wiz_ok(
            f"[DRY RUN] Would call opencode haiku (~{input_tokens} in / {output_tokens} out tokens)"
        )
        wiz_ok("[DRY RUN] Would write soul.md")
        return True

    result = _run_opencode(full_prompt, adj_dir)
    if not result:
        wiz_fail("Failed to generate soul.md via LLM")
        return False

    identity_dir = adj_dir / "identity"
    identity_dir.mkdir(parents=True, exist_ok=True)
    (identity_dir / "soul.md").write_text(result)
    wiz_ok("soul.md generated")
    return True


def _generate_heart(
    agent_name: str, user_description: str, adj_dir: Path, *, dry_run: bool = False
) -> bool:
    today = datetime.now().strftime("%Y-%m-%d")
    full_prompt = (
        f"{_HEART_META_PROMPT}\n\n"
        f"The agent is called: {agent_name}\n"
        f"Today's date: {today}\n\n"
        f"User's description of their needs:\n{user_description}\n\n"
        "Generate the heart.md content now. Output ONLY the markdown content, no code fences."
    )
    input_tokens = _estimate_tokens(full_prompt)
    output_tokens = 400  # heart.md ~ 25 lines

    print("", file=sys.stderr)
    print(f"  {BOLD}Generating heart.md...{RESET}", file=sys.stderr)
    _show_estimate(input_tokens, output_tokens)

    if not wiz_confirm("Proceed?", "Y"):
        return False

    if dry_run:
        wiz_ok(
            f"[DRY RUN] Would call opencode haiku (~{input_tokens} in / {output_tokens} out tokens)"
        )
        wiz_ok("[DRY RUN] Would write heart.md")
        return True

    result = _run_opencode(full_prompt, adj_dir)
    if not result:
        wiz_fail("Failed to generate heart.md via LLM")
        return False

    identity_dir = adj_dir / "identity"
    identity_dir.mkdir(parents=True, exist_ok=True)
    (identity_dir / "heart.md").write_text(result)
    wiz_ok("heart.md generated")
    return True


# ---------------------------------------------------------------------------
# Public step entry point
# ---------------------------------------------------------------------------


def step_identity(adj_dir: Path, *, dry_run: bool = False) -> bool:
    """Run Step 3: Identity Setup.

    Returns:
        True always (identity is optional; falls back to templates on any failure).
    """
    wiz_step(3, 7, "Identity Setup")
    print("", file=sys.stderr)

    identity_dir = adj_dir / "identity"
    soul_exists = (identity_dir / "soul.md").is_file()
    heart_exists = (identity_dir / "heart.md").is_file()

    if soul_exists and heart_exists:
        wiz_ok("soul.md exists")
        wiz_ok("heart.md exists")
        print("", file=sys.stderr)
        if not wiz_confirm("Regenerate identity files? (current ones will be backed up)", "N"):
            wiz_info("Keeping existing identity files")
            return True

        # Backup existing files
        if dry_run:
            wiz_ok("[DRY RUN] Would back up existing identity files")
        else:
            import time

            ts = int(time.time())
            (identity_dir / "soul.md").rename(identity_dir / f"soul.md.backup.{ts}")
            (identity_dir / "heart.md").rename(identity_dir / f"heart.md.backup.{ts}")
            wiz_ok("Backed up existing files")
        print("", file=sys.stderr)

    # Check if opencode is available
    if shutil.which("opencode") is None:
        wiz_warn("opencode not found — cannot generate identity with LLM")
        _write_templates(adj_dir, dry_run=dry_run)
        return True

    # Get user input
    agent_name = wiz_input("What should your agent be called?", "adjutant")
    print("", file=sys.stderr)
    print(
        "  I'll generate your soul.md (personality/values) and heart.md (priorities)",
        file=sys.stderr,
    )
    print("  using an LLM tailored to your needs.", file=sys.stderr)
    print("", file=sys.stderr)

    user_description = _wiz_multiline("Describe what you want your agent to monitor and help with")
    print("", file=sys.stderr)

    if not user_description.strip():
        wiz_warn("No description provided — writing template files instead")
        _write_templates(adj_dir, dry_run=dry_run)
        return True

    # Generate soul.md
    if not _generate_soul(agent_name, user_description, adj_dir, dry_run=dry_run):
        wiz_warn("LLM generation failed — writing template files instead")
        _write_templates(adj_dir, dry_run=dry_run)
        return True

    # Generate heart.md
    if not _generate_heart(agent_name, user_description, adj_dir, dry_run=dry_run):
        wiz_warn("heart.md generation failed — writing template instead")
        today = datetime.now().strftime("%Y-%m-%d")
        if not dry_run:
            identity_dir.mkdir(parents=True, exist_ok=True)
            (identity_dir / "heart.md").write_text(_heart_template(today))

    print("", file=sys.stderr)
    wiz_ok("Identity files generated")
    wiz_info("Review and edit these files anytime:")
    wiz_info(f"  {adj_dir}/identity/soul.md")
    wiz_info(f"  {adj_dir}/identity/heart.md")

    # Also create registry.md if it doesn't exist
    if not (identity_dir / "registry.md").is_file():
        if dry_run:
            wiz_ok("[DRY RUN] Would write registry.md (template)")
        else:
            identity_dir.mkdir(parents=True, exist_ok=True)
            (identity_dir / "registry.md").write_text(_REGISTRY_TEMPLATE)

    return True
