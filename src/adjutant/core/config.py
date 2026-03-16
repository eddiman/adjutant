"""YAML configuration loading.

Provides two APIs:
- Dict-based (load_config, get_config_value, is_feature_enabled): lightweight,
  used by code that only needs to pluck a few values from the config.
- Typed model (AdjutantConfig, load_typed_config): full typed hierarchy with
  defaults for every field, suitable for code that needs the full config.

Requires pydantic>=2.0 (a core dependency of this package).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Typed config models
# ---------------------------------------------------------------------------


class InstanceConfig(BaseModel):
    name: str = "adjutant"


class IdentityConfig(BaseModel):
    soul: str = "identity/soul.md"
    heart: str = "identity/heart.md"
    registry: str = "identity/registry.md"


class TelegramRateLimitConfig(BaseModel):
    messages_per_minute: int = 10
    window_seconds: int = 60
    backoff_exponential: bool = True


class TelegramConfig(BaseModel):
    session_timeout_seconds: int = 7200
    chat_timeout_seconds: int = 240
    default_model: str = "anthropic/claude-haiku-4-5"
    rate_limit: TelegramRateLimitConfig = Field(default_factory=TelegramRateLimitConfig)


class MessagingConfig(BaseModel):
    backend: str = "telegram"
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)


class ModelsConfig(BaseModel):
    cheap: str = "anthropic/claude-haiku-4-5"
    medium: str = "anthropic/claude-sonnet-4-6"
    expensive: str = "anthropic/claude-opus-4-5"


class CapsConfig(BaseModel):
    session_tokens: int = 44000
    session_window_hours: int = 5
    weekly_tokens: int = 350000


class LLMConfig(BaseModel):
    backend: str = "opencode"
    models: ModelsConfig = Field(default_factory=ModelsConfig)
    caps: CapsConfig = Field(default_factory=CapsConfig)


class FeatureConfig(BaseModel):
    enabled: bool = False
    config_path: str | None = None
    model: str | None = None


class FeaturesConfig(BaseModel):
    news: FeatureConfig = Field(default_factory=FeatureConfig)
    screenshot: FeatureConfig = Field(default_factory=FeatureConfig)
    vision: FeatureConfig = Field(
        default_factory=lambda: FeatureConfig(model="opencode-go/Kimi-K2.5")
    )
    search: FeatureConfig = Field(default_factory=FeatureConfig)
    usage_tracking: FeatureConfig = Field(default_factory=FeatureConfig)


class HeartbeatConfig(BaseModel):
    enabled: bool = False


class ScheduleConfig(BaseModel):
    name: str = ""
    description: str = ""
    schedule: str = ""
    script: str = ""
    log: str = ""
    enabled: bool = False


class PlatformConfig(BaseModel):
    service_manager: str = "launchd"
    process_manager: str = "pidfile"


class QuietHoursConfig(BaseModel):
    enabled: bool = False
    start: str = "22:00"
    end: str = "07:00"


class NotificationsConfig(BaseModel):
    max_per_day: int = 3
    quiet_hours: QuietHoursConfig = Field(default_factory=QuietHoursConfig)


class SecurityConfig(BaseModel):
    prompt_injection_guard: bool = True
    env_file: str = ".env"
    log_unknown_senders: bool = True
    rate_limiting: bool = True


class JournalConfig(BaseModel):
    retention_days: int = 30
    news_retention_days: int = 14
    log_max_size_kb: int = 5120
    log_rotations: int = 3


class DebugConfig(BaseModel):
    dry_run: bool = False
    verbose_logging: bool = False
    mock_llm: bool = False


class AdjutantConfig(BaseModel):
    """Full typed configuration for Adjutant.

    Usage:
        config = AdjutantConfig.load(Path("adjutant.yaml"))
        print(config.instance.name)
        print(config.llm.models.cheap)
    """

    instance: InstanceConfig = Field(default_factory=InstanceConfig)
    identity: IdentityConfig = Field(default_factory=IdentityConfig)
    messaging: MessagingConfig = Field(default_factory=MessagingConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    features: FeaturesConfig = Field(default_factory=FeaturesConfig)
    heartbeat: HeartbeatConfig = Field(default_factory=HeartbeatConfig)
    schedules: list[ScheduleConfig] = Field(default_factory=list)
    platform: PlatformConfig = Field(default_factory=PlatformConfig)
    notifications: NotificationsConfig = Field(default_factory=NotificationsConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    journal: JournalConfig = Field(default_factory=JournalConfig)
    debug: DebugConfig = Field(default_factory=DebugConfig)

    @classmethod
    def load(cls, path: Path) -> AdjutantConfig:
        """Load config from a YAML file. Returns defaults if file is missing."""
        if not path.exists():
            return cls()
        try:
            with open(path) as f:
                data = yaml.safe_load(f) or {}
            if not isinstance(data, dict):
                return cls()
            return cls.model_validate(data)
        except (yaml.YAMLError, OSError, Exception):
            return cls()

    def get_model(self, tier: str) -> str:
        """Return the model string for a tier (cheap/medium/expensive)."""
        model = getattr(self.llm.models, tier, None)
        return model if model is not None else self.llm.models.cheap

    def get_schedule(self, name: str) -> ScheduleConfig | None:
        """Return a ScheduleConfig by name, or None if not found."""
        for schedule in self.schedules:
            if schedule.name == name:
                return schedule
        return None

    def is_feature_enabled(self, feature: str) -> bool:
        """Return True if features.<feature>.enabled is True."""
        feature_config = getattr(self.features, feature, None)
        if feature_config is None:
            return False
        return bool(getattr(feature_config, "enabled", False))


# ---------------------------------------------------------------------------
# Dict-based API (lightweight, no pydantic overhead for simple lookups)
# ---------------------------------------------------------------------------


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
        return data if isinstance(data, dict) else {}
    except (yaml.YAMLError, OSError):
        return {}


def load_typed_config(config_path: Path | None = None) -> AdjutantConfig:
    """Load adjutant.yaml and return as a typed AdjutantConfig.

    Args:
        config_path: Explicit path to config file.
                     Defaults to $ADJUTANT_HOME or $ADJ_DIR / adjutant.yaml.

    Returns:
        AdjutantConfig with defaults for any missing fields.
    """
    if config_path is None:
        adj_home = os.environ.get("ADJUTANT_HOME") or os.environ.get("ADJ_DIR")
        if not adj_home:
            return AdjutantConfig()
        config_path = Path(adj_home) / "adjutant.yaml"

    return AdjutantConfig.load(config_path)


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
