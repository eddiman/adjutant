"""Model tier resolution.

Two distinct resolution chains — chat and KB:

Chat model (simpler — does NOT consult adjutant.yaml):
    state/telegram_model.txt → hardcoded default

KB model (full tier chain):
    "inherit" → state/telegram_model.txt → config cheap tier → hardcoded default
    "cheap"   → config cheap tier → hardcoded default
    "medium"  → config medium tier → hardcoded default
    "expensive" → config expensive tier → hardcoded default
    explicit  → used as-is

Matches bash chat.sh:get_model() and query.sh:_resolve_model().
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from adjutant.core.backend import ResolvedModel

if TYPE_CHECKING:
    from pathlib import Path

DEFAULT_MODEL = "anthropic/claude-haiku-4-5"
DEFAULT_CHAT_TIER = "cheap"

TIER_DEFAULTS: dict[str, str] = {
    "cheap": "anthropic/claude-haiku-4-5",
    "medium": "anthropic/claude-sonnet-4-6",
    "expensive": "anthropic/claude-opus-4-6",
}


def get_chat_model(state_dir: Path) -> str:
    """Get the current chat model (simpler chain — matches chat.sh:get_model).

    Resolution: state/telegram_model.txt → hardcoded default.
    Does NOT consult adjutant.yaml (that's only for KB tier resolution).

    Args:
        state_dir: Path to the state directory ($ADJ_DIR/state).

    Returns:
        The model identifier string.
    """
    model_file = state_dir / "telegram_model.txt"
    if model_file.exists():
        model = model_file.read_text().strip()
        if model:
            return model
    return DEFAULT_MODEL


def resolve_kb_model(
    kb_model: str,
    state_dir: Path,
    config: dict[str, Any] | None = None,
) -> str:
    """Resolve KB model tier to concrete model ID.

    Matches bash query.sh:_resolve_model().

    Resolution chain:
      "inherit"/"" → state/telegram_model.txt → config cheap tier → hardcoded default
      "cheap"/"medium"/"expensive" → config tier → hardcoded default
      anything else → used verbatim (explicit model ID)

    Args:
        kb_model: Model specification from kb.yaml (tier name or explicit ID).
        state_dir: Path to the state directory ($ADJ_DIR/state).
        config: Parsed adjutant.yaml config dict.

    Returns:
        Resolved model identifier string.
    """
    if kb_model in ("inherit", ""):
        # Try current chat model first
        model_file = state_dir / "telegram_model.txt"
        if model_file.exists():
            model = model_file.read_text().strip()
            if model:
                return model
        # Fall back to cheap tier
        kb_model = "cheap"

    if kb_model in TIER_DEFAULTS:
        # Check adjutant.yaml config first
        if config:
            llm = config.get("llm", {})
            models = llm.get("models", {})
            configured = models.get(kb_model)
            if configured:
                return str(configured)
        return TIER_DEFAULTS[kb_model]

    # Explicit model ID — use as-is
    return kb_model


def _configured_default_chat_model(config: dict[str, Any] | None = None) -> str:
    """Return messaging.telegram.default_model or a safe fallback."""
    if config:
        messaging = config.get("messaging", {})
        telegram = messaging.get("telegram", {})
        configured = telegram.get("default_model")
        if configured:
            return str(configured).strip()
    return DEFAULT_CHAT_TIER


def resolve_model_spec(
    model_spec: str | None,
    state_dir: Path | None = None,
    config: dict[str, Any] | None = None,
    *,
    default_to_chat: bool = False,
) -> ResolvedModel:
    """Resolve a tier or explicit model into concrete model + variant.

    Tier names resolve through adjutant.yaml and may carry a reasoning-effort
    variant. Explicit model IDs pass through unchanged with no variant.
    """
    spec = (model_spec or "").strip()
    if not spec:
        spec = _configured_default_chat_model(config) if default_to_chat else "cheap"

    if spec in ("inherit", ""):
        if state_dir is not None:
            model_file = state_dir / "telegram_model.txt"
            if model_file.exists():
                inherited = model_file.read_text().strip()
                if inherited:
                    return resolve_model_spec(inherited, state_dir, config)
        spec = "cheap"

    if spec in TIER_DEFAULTS:
        configured_model = TIER_DEFAULTS[spec]
        variant = None
        if config:
            llm = config.get("llm", {})
            models = llm.get("models", {})
            configured = models.get(spec)
            if configured:
                configured_model = str(configured)
            reasoning_effort = llm.get("reasoning_effort", {})
            configured_variant = reasoning_effort.get(spec)
            if configured_variant:
                variant = str(configured_variant)
        return ResolvedModel(model=configured_model, variant=variant, source=spec)

    return ResolvedModel(model=spec, variant=None, source="explicit")
