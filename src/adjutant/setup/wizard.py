"""Terminal UI helpers and setup wizard orchestrator.

Replaces:
  - scripts/setup/helpers.sh (wiz_* UI primitives)
  - scripts/setup/wizard.sh  (main setup flow)

The wizard is intentionally thin: it delegates to step modules (prerequisites,
install_path, identity, messaging, features, service, autonomy) that live in
setup/steps/. This module owns only the orchestration and the shared UI layer.

Note: All UI output goes to sys.stderr (matching bash's /dev/tty writes) so
that wizards can be safely invoked inside $() subshells if needed.
"""

from __future__ import annotations

import os
import platform
import shutil
import sys
from pathlib import Path
from typing import Callable

# ---------------------------------------------------------------------------
# Colour helpers (match helpers.sh)
# ---------------------------------------------------------------------------

_IS_TTY = sys.stderr.isatty() and not os.environ.get("NO_COLOR")


def _c(code: str) -> str:
    return f"\033[{code}m" if _IS_TTY else ""


BOLD = _c("1")
DIM = _c("2")
RESET = _c("0")
GREEN = _c("32")
RED = _c("31")
YELLOW = _c("33")
CYAN = _c("36")


def wiz_ok(msg: str) -> None:
    print(f"  {GREEN}✓{RESET} {msg}", file=sys.stderr)


def wiz_fail(msg: str) -> None:
    print(f"  {RED}✗{RESET} {msg}", file=sys.stderr)


def wiz_warn(msg: str) -> None:
    print(f"  {YELLOW}!{RESET} {msg}", file=sys.stderr)


def wiz_info(msg: str) -> None:
    print(f"  {DIM}→{RESET} {msg}", file=sys.stderr)


def wiz_header(title: str) -> None:
    print(f"\n{BOLD}{CYAN}{title}{RESET}", file=sys.stderr)


def wiz_banner() -> None:
    print("", file=sys.stderr)
    print(f"{BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{RESET}", file=sys.stderr)
    print(f"{BOLD}  Adjutant — Setup Wizard{RESET}", file=sys.stderr)
    print(f"{BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{RESET}", file=sys.stderr)
    print("", file=sys.stderr)


def wiz_complete_banner() -> None:
    print("", file=sys.stderr)
    print(f"{BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{RESET}", file=sys.stderr)
    print(f"{BOLD}{GREEN}  Adjutant is online!{RESET}", file=sys.stderr)
    print(f"{BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{RESET}", file=sys.stderr)
    print("", file=sys.stderr)


def wiz_step(current: int, total: int, title: str) -> None:
    print("", file=sys.stderr)
    print(f"{BOLD}Step {current} of {total}: {title}{RESET}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------


def wiz_confirm(prompt: str, default: str = "Y") -> bool:
    """Ask a yes/no question, returns True for yes."""
    hint = "[Y/n]" if default.upper() == "Y" else "[y/N]"
    while True:
        sys.stderr.write(f"  {prompt} {hint}: ")
        sys.stderr.flush()
        try:
            answer = input().strip()
        except (EOFError, KeyboardInterrupt):
            print("", file=sys.stderr)
            return False
        answer = answer or default
        if answer.lower() in ("y", "yes"):
            return True
        if answer.lower() in ("n", "no"):
            return False
        print("  Please answer y or n.", file=sys.stderr)


def wiz_choose(prompt: str, *options: str) -> int:
    """Present a numbered menu; return 1-based choice index."""
    print(f"  {prompt}\n", file=sys.stderr)
    for i, opt in enumerate(options, 1):
        print(f"    {BOLD}{i}){RESET}  {opt}", file=sys.stderr)
    print("", file=sys.stderr)
    while True:
        sys.stderr.write(f"  Choose [1-{len(options)}]: ")
        sys.stderr.flush()
        try:
            answer = input().strip()
        except (EOFError, KeyboardInterrupt):
            print("", file=sys.stderr)
            return 1
        try:
            idx = int(answer)
            if 1 <= idx <= len(options):
                return idx
        except ValueError:
            pass
        print(f"  Please enter a number between 1 and {len(options)}.", file=sys.stderr)


def wiz_input(prompt: str, default: str = "") -> str:
    """Single-line text input with optional default."""
    if default:
        sys.stderr.write(f"  {prompt} [{default}]: ")
    else:
        sys.stderr.write(f"  {prompt}: ")
    sys.stderr.flush()
    try:
        answer = input().strip()
    except (EOFError, KeyboardInterrupt):
        print("", file=sys.stderr)
        return default
    return answer or default


def wiz_secret(prompt: str) -> str:
    """Password-style input (no echo)."""
    import getpass

    try:
        return getpass.getpass(f"  {prompt}: ")
    except (EOFError, KeyboardInterrupt):
        print("", file=sys.stderr)
        return ""


def expand_path(path: str) -> str:
    """Expand ~ to $HOME, return as str."""
    return str(Path(path).expanduser())


# ---------------------------------------------------------------------------
# Default adjutant.yaml content
# ---------------------------------------------------------------------------

DEFAULT_CONFIG_YAML = """\
# adjutant.yaml — Single source of truth for this Adjutant instance
#
# This file serves two purposes:
#   1. Root marker for path resolution (adjutant.core.paths looks for this)
#   2. Unified configuration replacing scattered hardcoded values
#
# Secrets (tokens, chat IDs) stay in .env — this file is safe to commit.

instance:
  name: "adjutant"

identity:
  soul: "identity/soul.md"
  heart: "identity/heart.md"
  registry: "identity/registry.md"

messaging:
  backend: "telegram"
  telegram:
    session_timeout_seconds: 7200
    default_model: "anthropic/claude-haiku-4-5"
    rate_limit:
      messages_per_minute: 10
      backoff_exponential: true

llm:
  backend: "opencode"
  models:
    cheap: "anthropic/claude-haiku-4-5"
    medium: "anthropic/claude-sonnet-4-6"
    expensive: "anthropic/claude-opus-4-5"
  caps:
    session_tokens: 44000
    session_window_hours: 5
    weekly_tokens: 350000

features:
  news:
    enabled: false
    config_path: "news_config.json"
    schedule: "0 8 * * 1-5"
  screenshot:
    enabled: false
  vision:
    enabled: true
  usage_tracking:
    enabled: true

platform:
  service_manager: "launchd"
  process_manager: "pidfile"

notifications:
  max_per_day: 3
  quiet_hours:
    enabled: false
    start: "22:00"
    end: "07:00"

security:
  prompt_injection_guard: true
  env_file: ".env"
  log_unknown_senders: true
  rate_limiting: true

debug:
  dry_run: false
  verbose_logging: false
  mock_llm: false
"""

# ---------------------------------------------------------------------------
# Wizard orchestrator
# ---------------------------------------------------------------------------


def detect_os() -> str:
    """Return 'macos', 'linux', or 'unknown'."""
    s = platform.system()
    if s == "Darwin":
        return "macos"
    if s == "Linux":
        return "linux"
    return "unknown"


def ensure_config(adj_dir: Path, *, dry_run: bool = False) -> None:
    """Write default adjutant.yaml if it doesn't exist."""
    config_file = adj_dir / "adjutant.yaml"
    if config_file.is_file():
        return
    if dry_run:
        wiz_info(f"[DRY RUN] Would write {config_file}")
        wiz_ok("Would create adjutant.yaml")
        return
    config_file.write_text(DEFAULT_CONFIG_YAML)
    wiz_ok("Created adjutant.yaml")


def _show_completion(adj_dir: Path, *, news_enabled: bool = False) -> None:
    """Show the post-setup completion summary."""
    wiz_complete_banner()
    print("  Send /help to your Telegram bot to get started.", file=sys.stderr)
    print("", file=sys.stderr)

    print(f"  {BOLD}Estimated monthly cost at typical usage:{RESET}", file=sys.stderr)
    print("", file=sys.stderr)
    rows = [
        ("Operation", "Frequency", "Cost/mo"),
        ("--------------------------", "-----------", "--------"),
        ("Casual chat (Haiku)", "5/day", "~$3.00"),
        ("Pulse checks", "2/day", "~$0.60"),
    ]
    if news_enabled:
        rows.append(("News briefing (Haiku)", "1/day", "~$1.50"))
    rows += [
        ("Deep reflect (Opus)", "1/week", "~$1.20"),
        ("--------------------------", "-----------", "--------"),
    ]
    total = "~$6.30" if news_enabled else "~$4.80"
    rows.append(("Total estimate", "", total))

    for op, freq, cost in rows:
        print(f"  {op:<26} {freq:<11} {cost}", file=sys.stderr)
    print("", file=sys.stderr)

    print(f"  Config:   {adj_dir}/adjutant.yaml", file=sys.stderr)
    print(f"  Logs:     {adj_dir}/state/adjutant.log", file=sys.stderr)
    print(f"  Identity: {adj_dir}/identity/", file=sys.stderr)
    print("", file=sys.stderr)

    if wiz_confirm("Would you like to create a knowledge base now?", "N"):
        from adjutant.setup.steps.kb_wizard import kb_wizard_interactive

        try:
            kb_wizard_interactive(adj_dir)
        except (KeyboardInterrupt, SystemExit):
            pass


def run_wizard(adj_dir: Path | None = None, *, dry_run: bool = False, repair: bool = False) -> None:
    """Main wizard entry point.

    If adj_dir is None, the wizard will ask the user to choose an install path.
    For an existing install, offers repair vs fresh-setup.
    """
    os.environ["ADJUTANT_OS"] = detect_os()

    wiz_banner()

    if dry_run:
        print(
            f"  {YELLOW}[DRY RUN]{RESET} Simulation mode — prompts are real, no files written.\n",
            file=sys.stderr,
        )

    existing = adj_dir is not None and (adj_dir / "adjutant.yaml").is_file()

    if existing and not repair:
        print(f"  Existing installation detected at {BOLD}{adj_dir}{RESET}\n", file=sys.stderr)
        choice = wiz_choose(
            "What would you like to do?",
            "Repair / health check (recommended)",
            "Run full setup from scratch",
        )
        if choice == 1:
            _run_repair(adj_dir)
            return

    _run_fresh_setup(adj_dir, dry_run=dry_run)


def _run_repair(adj_dir: Path | None) -> None:
    """Delegate to repair module."""
    try:
        from adjutant.setup.repair import run_repair

        run_repair(adj_dir)
    except ImportError:
        wiz_warn("Repair module not yet implemented — running fresh setup instead.")
        _run_fresh_setup(adj_dir)


def _run_fresh_setup(adj_dir: Path | None, *, dry_run: bool = False) -> None:
    """Run the 7-step fresh setup."""

    # Steps are imported lazily so missing stubs don't break the import chain
    def _run_step(name: str, fn: Callable[..., bool], *args: object) -> bool:
        try:
            return fn(*args)
        except (ImportError, NotImplementedError):
            wiz_warn(f"Step '{name}' not yet implemented — skipping")
            return True

    # Step 1: Prerequisites
    try:
        from adjutant.setup.steps.prerequisites import step_prerequisites

        if not _run_step("prerequisites", step_prerequisites):
            wiz_fail("Cannot continue without required dependencies.")
            raise SystemExit(1)
    except ImportError:
        wiz_warn("Prerequisites step not yet implemented — skipping")

    # Step 2: Install path
    if adj_dir is None:
        try:
            from adjutant.setup.steps.install_path import step_install_path

            adj_dir = step_install_path()
            if adj_dir is None:
                wiz_fail("Installation path setup failed.")
                raise SystemExit(1)
        except ImportError:
            wiz_warn("Install path step not yet implemented")
            adj_dir = Path.home() / ".adjutant"

    ensure_config(adj_dir, dry_run=dry_run)

    for step_name, module_path, fn_name in [
        ("identity", "adjutant.setup.steps.identity", "step_identity"),
        ("messaging", "adjutant.setup.steps.messaging", "step_messaging"),
        ("features", "adjutant.setup.steps.features", "step_features"),
        ("service", "adjutant.setup.steps.service", "step_service"),
        ("autonomy", "adjutant.setup.steps.autonomy", "step_autonomy"),
    ]:
        try:
            import importlib

            mod = importlib.import_module(module_path)
            fn = getattr(mod, fn_name)
            fn(adj_dir)
        except (ImportError, AttributeError, NotImplementedError):
            wiz_warn(f"Step '{step_name}' not yet implemented — skipping")

    _show_completion(adj_dir)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: wizard [--repair] [--dry-run]"""
    import sys as _sys

    args = argv if argv is not None else _sys.argv[1:]
    dry_run = "--dry-run" in args
    repair = "--repair" in args

    if "--help" in args or "-h" in args:
        print("Usage: adjutant setup [--repair] [--dry-run]")
        print("")
        print("  --repair      Force repair mode on existing installation")
        print("  --dry-run     Walk through wizard without writing any files")
        return 0

    # Try to resolve existing adj_dir
    adj_dir: Path | None = None
    try:
        from adjutant.core.paths import init_adj_dir

        adj_dir = init_adj_dir()
    except Exception:
        pass

    try:
        run_wizard(adj_dir, dry_run=dry_run, repair=repair)
        return 0
    except SystemExit as exc:
        return int(exc.code) if exc.code is not None else 1
    except KeyboardInterrupt:
        print("\nCancelled.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
