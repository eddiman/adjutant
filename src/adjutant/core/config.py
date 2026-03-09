"""YAML configuration loading.

Loads adjutant.yaml using PyYAML. No dedicated config.sh exists in bash —
config values are read by the agent (which has native YAML support) or
extracted ad-hoc by individual scripts. This module provides a clean
Python interface.

Uses dataclasses (not pydantic — deferred to Phase 3 optional extra).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


def load_config(config_path: Path | None = None) -> dict[str, Any]:
    """Load adjutant.yaml and return as a plain dict.

    Args:
        config_path: Explicit path to config file.
                     Defaults to $ADJ_DIR/adjutant.yaml.

    Returns:
        Parsed YAML as a dictionary. Returns empty dict if file is missing
        or contains invalid YAML.
    """
    if config_path is None:
        adj_dir = os.environ.get("ADJ_DIR", "").strip()
        if not adj_dir:
            return {}
        config_path = Path(adj_dir) / "adjutant.yaml"

    if not config_path.is_file():
        return {}

    try:
        with open(config_path) as f:
            data = yaml.safe_load(f)
        # yaml.safe_load returns None for empty files
        return data if isinstance(data, dict) else {}
    except (yaml.YAMLError, OSError):
        return {}


def get_config_value(config: dict[str, Any], *keys: str, default: Any = None) -> Any:
    """Safely get a nested config value.

    Usage:
        get_config_value(config, "llm", "models", "cheap")
        get_config_value(config, "messaging", "telegram", "rate_limit", "messages_per_minute")

    Args:
        config: The config dictionary.
        *keys: Path of keys to traverse.
        default: Value to return if any key is missing.

    Returns:
        The value at the nested key path, or ``default`` if not found.
    """
    current: Any = config
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
        if current is None:
            return default
    return current


def is_feature_enabled(config: dict[str, Any], feature: str) -> bool:
    """Check if a feature is enabled in the config.

    Args:
        config: The config dictionary.
        feature: Feature name (e.g. "news", "screenshot", "vision", "search").

    Returns:
        True if features.<feature>.enabled is truthy.
    """
    return bool(get_config_value(config, "features", feature, "enabled", default=False))
