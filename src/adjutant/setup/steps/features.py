"""Step 5: Feature Selection.

Replaces: scripts/setup/steps/features.sh

Asks which optional features to enable and updates adjutant.yaml.

Module-level state (set by step_features):
  WIZARD_FEATURES_NEWS       — bool
  WIZARD_FEATURES_SCREENSHOT — bool
  WIZARD_FEATURES_VISION     — bool
  WIZARD_FEATURES_SEARCH     — bool
  WIZARD_FEATURES_USAGE      — bool
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from typing import TYPE_CHECKING

from adjutant.setup.wizard import (
    BOLD,
    CYAN,
    RESET,
    wiz_confirm,
    wiz_info,
    wiz_ok,
    wiz_secret,
    wiz_step,
    wiz_warn,
)

if TYPE_CHECKING:
    from pathlib import Path

# Module-level wizard state
WIZARD_FEATURES_NEWS: bool = False
WIZARD_FEATURES_SCREENSHOT: bool = False
WIZARD_FEATURES_VISION: bool = True
WIZARD_FEATURES_SEARCH: bool = False
WIZARD_FEATURES_USAGE: bool = True

_DEFAULT_NEWS_CONFIG = {
    "keywords": ["AI agent", "autonomous agent", "LLM", "Claude", "GPT"],
    "sources": {
        "hackernews": {
            "enabled": True,
            "max_items": 30,
            "lookback_hours": 24,
        },
        "reddit": {
            "enabled": False,
            "subreddits": ["MachineLearning", "LocalLLaMA"],
            "max_items": 20,
            "lookback_hours": 24,
        },
        "blogs": {
            "enabled": False,
            "urls": [],
        },
    },
    "analysis": {
        "prefilter_limit": 10,
        "top_n": 5,
        "model": "anthropic/claude-haiku-4-5",
    },
    "delivery": {
        "telegram": True,
        "journal": True,
    },
    "deduplication": {"window_days": 30},
    "cleanup": {
        "raw_retention_days": 7,
        "analyzed_retention_days": 7,
    },
}


def _playwright_available() -> bool:
    if shutil.which("npx") is None:
        return False
    try:
        result = subprocess.run(
            ["npx", "playwright", "--version"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        return result.returncode == 0
    except Exception:  # noqa: BLE001 — graceful degradation on check failure
        return False


def _read_env_key(env_file: Path, key: str) -> str:
    if not env_file.is_file():
        return ""
    for line in env_file.read_text().splitlines():
        if line.startswith(f"{key}="):
            return line[len(key) + 1 :].strip().strip("'\"")
    return ""


def _write_brave_key(adj_dir: Path, key: str) -> None:
    env_file = adj_dir / ".env"
    if not env_file.is_file():
        env_file.write_text("")
        env_file.chmod(0o600)

    content = env_file.read_text()
    lines = content.splitlines()
    updated = False
    new_lines: list[str] = []
    for line in lines:
        if line.startswith("BRAVE_API_KEY="):
            new_lines.append(f"BRAVE_API_KEY={key}")
            updated = True
        else:
            new_lines.append(line)
    if not updated:
        new_lines.append("")
        new_lines.append("# Brave Search API — /search command and agent web search")
        new_lines.append(f"BRAVE_API_KEY={key}")
    env_file.write_text("\n".join(new_lines) + "\n")
    env_file.chmod(0o600)


def _update_feature_in_yaml(adj_dir: Path, feature: str, enabled: bool) -> None:
    """Toggle a feature's enabled: flag in adjutant.yaml using PyYAML."""
    config_path = adj_dir / "adjutant.yaml"
    if not config_path.is_file():
        return
    try:
        import yaml

        with open(config_path) as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            return
        features = data.setdefault("features", {})
        if not isinstance(features, dict):
            return
        feat_block = features.setdefault(feature, {})
        if not isinstance(feat_block, dict):
            features[feature] = {"enabled": enabled}
        else:
            feat_block["enabled"] = enabled
        with open(config_path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    except Exception:  # noqa: BLE001 — best-effort config write
        pass


def _update_config(adj_dir: Path, *, dry_run: bool = False) -> None:
    if dry_run:
        wiz_ok("[DRY RUN] Would update features in adjutant.yaml")
        return
    _update_feature_in_yaml(adj_dir, "news", WIZARD_FEATURES_NEWS)
    _update_feature_in_yaml(adj_dir, "screenshot", WIZARD_FEATURES_SCREENSHOT)
    _update_feature_in_yaml(adj_dir, "vision", WIZARD_FEATURES_VISION)
    _update_feature_in_yaml(adj_dir, "search", WIZARD_FEATURES_SEARCH)
    _update_feature_in_yaml(adj_dir, "usage_tracking", WIZARD_FEATURES_USAGE)

    # Sync news_briefing schedule entry
    config_path = adj_dir / "adjutant.yaml"
    try:
        from adjutant.capabilities.schedule.manage import schedule_exists, schedule_set_enabled

        if schedule_exists(config_path, "news_briefing"):
            schedule_set_enabled(config_path, "news_briefing", WIZARD_FEATURES_NEWS)
    except Exception:  # noqa: BLE001 — best-effort schedule toggle
        pass


def step_features(adj_dir: Path, *, dry_run: bool = False) -> bool:
    """Run Step 5: Feature Selection.

    Returns:
        True always.
    """
    global WIZARD_FEATURES_NEWS, WIZARD_FEATURES_SCREENSHOT
    global WIZARD_FEATURES_VISION, WIZARD_FEATURES_SEARCH, WIZARD_FEATURES_USAGE

    wiz_step(5, 7, "Features")
    print("", file=sys.stderr)

    # ── News briefing ────────────────────────────────────────────────────────
    news_hint = "" if shutil.which("opencode") else " (requires opencode)"
    if wiz_confirm(f"Enable news briefing?{news_hint} (fetches AI news daily)", "N"):
        WIZARD_FEATURES_NEWS = True
        wiz_ok("News briefing enabled")

        news_config = adj_dir / "news_config.json"
        if not news_config.is_file():
            if dry_run:
                wiz_ok("[DRY RUN] Would create default news_config.json")
            else:
                news_config.write_text(json.dumps(_DEFAULT_NEWS_CONFIG, indent=2) + "\n")
                wiz_info("Created default news_config.json")

        print("", file=sys.stderr)
        print(f"  {BOLD}Configuring news sources:{RESET}", file=sys.stderr)
        print("", file=sys.stderr)
        print(
            f"  Edit {BOLD}{adj_dir}/news_config.json{RESET} to customise what you receive:",
            file=sys.stderr,
        )
        print("", file=sys.stderr)
        wiz_info("Run 'adjutant news' to test the briefing manually after setup")
    else:
        WIZARD_FEATURES_NEWS = False
        wiz_info("News briefing disabled")
    print("", file=sys.stderr)

    # ── Screenshot ───────────────────────────────────────────────────────────
    telegram_enabled = getattr(
        sys.modules.get("adjutant.setup.steps.messaging"), "WIZARD_TELEGRAM_ENABLED", True
    )
    if not telegram_enabled:
        WIZARD_FEATURES_SCREENSHOT = False
        wiz_info("Screenshot disabled (requires Telegram)")
    else:
        screenshot_available = _playwright_available()
        if screenshot_available:
            if wiz_confirm("Enable screenshot capability?", "Y"):
                WIZARD_FEATURES_SCREENSHOT = True
                wiz_ok("Screenshot enabled")
            else:
                WIZARD_FEATURES_SCREENSHOT = False
                wiz_info("Screenshot disabled")
        else:
            wiz_warn("Screenshot requires Playwright (not installed)")
            if wiz_confirm("Enable anyway? (you can install Playwright later)", "N"):
                WIZARD_FEATURES_SCREENSHOT = True
                wiz_ok(
                    "Screenshot enabled (install Playwright with: npx playwright install chromium)"
                )
            else:
                WIZARD_FEATURES_SCREENSHOT = False
                wiz_info("Screenshot disabled")
    print("", file=sys.stderr)

    # ── Vision ───────────────────────────────────────────────────────────────
    if not telegram_enabled:
        WIZARD_FEATURES_VISION = False
        wiz_info("Vision disabled (requires Telegram)")
    else:
        if wiz_confirm("Enable vision capability? (analyze photos sent to bot)", "Y"):
            WIZARD_FEATURES_VISION = True
            wiz_ok("Vision enabled")
        else:
            WIZARD_FEATURES_VISION = False
            wiz_info("Vision disabled")
    print("", file=sys.stderr)

    # ── Web search ───────────────────────────────────────────────────────────
    if wiz_confirm("Enable web search? (Brave Search API — no bot detection, low token cost)", "Y"):
        env_file = adj_dir / ".env"
        existing_key = _read_env_key(env_file, "BRAVE_API_KEY")

        if existing_key and existing_key != "your-brave-api-key-here":
            WIZARD_FEATURES_SEARCH = True
            wiz_ok("Web search enabled (existing API key found)")
        else:
            print("", file=sys.stderr)
            print(f"  {BOLD}Brave Search API key required{RESET}", file=sys.stderr)
            print("  Free tier: 2,000 queries/month", file=sys.stderr)
            print(
                f"  Get a key at: {CYAN}https://api.search.brave.com{RESET}",
                file=sys.stderr,
            )
            print("", file=sys.stderr)
            brave_key = wiz_secret("Paste your Brave API key (or press Enter to skip)")
            print("", file=sys.stderr)

            if brave_key:
                if not dry_run:
                    _write_brave_key(adj_dir, brave_key)
                WIZARD_FEATURES_SEARCH = True
                wiz_ok("Web search enabled")
                wiz_info("Key saved to .env")
            else:
                WIZARD_FEATURES_SEARCH = False
                wiz_info(
                    "Web search disabled (no key provided"
                    " — add BRAVE_API_KEY to .env later to enable)"
                )
    else:
        WIZARD_FEATURES_SEARCH = False
        wiz_info("Web search disabled")
    print("", file=sys.stderr)

    # ── Usage tracking ───────────────────────────────────────────────────────
    if wiz_confirm("Enable usage tracking?", "Y"):
        WIZARD_FEATURES_USAGE = True
        wiz_ok("Usage tracking enabled")
    else:
        WIZARD_FEATURES_USAGE = False
        wiz_info("Usage tracking disabled")

    # Save config
    _update_config(adj_dir, dry_run=dry_run)
    print("", file=sys.stderr)
    wiz_ok("Feature configuration saved")

    return True
