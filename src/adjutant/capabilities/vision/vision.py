"""AI vision analysis for images.

Replaces: scripts/capabilities/vision/vision.sh

Passes one or more image files to the active LLM backend and returns the
plain-text analysis. Used by screenshot.py for auto-captioning and by the
Telegram backend for handling received photos.

Model resolution order:
  1. features.vision.model from adjutant.yaml (must be cheap|medium|expensive)
  2. cheap (default tier)

Output: plain-text vision analysis, or an informative error message.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from adjutant.core.model import resolve_model_spec

# ---------------------------------------------------------------------------
# Model resolution
# ---------------------------------------------------------------------------

_DEFAULT_VISION_TIER = "cheap"
_DEFAULT_PROMPT = "Describe what you see in this image. Be concise and informative."
_DEFAULT_PROMPT_MULTI = "Describe what you see in these images. Be concise and informative."
_VISION_TIMEOUT = 240  # seconds — matches chat timeout
_VISION_TIERS = frozenset({"cheap", "medium", "expensive"})


def _get_vision_model_from_config(adj_dir: Path) -> str:
    """Read features.vision.model from adjutant.yaml."""
    try:
        from adjutant.core.config import load_typed_config

        config = load_typed_config(adj_dir / "adjutant.yaml")
        model = config.features.vision.model
        return model.strip() if model else _DEFAULT_VISION_TIER
    except Exception:  # noqa: BLE001 — fallback to default tier
        return _DEFAULT_VISION_TIER


def resolve_vision_model(adj_dir: Path) -> str:
    """Resolve the configured vision model tier."""
    model = _get_vision_model_from_config(adj_dir).strip()
    return model or _DEFAULT_VISION_TIER


def _validate_vision_model_setting(model: str) -> str | None:
    """Validate the configured vision model tier."""
    if model in _VISION_TIERS:
        return None
    return (
        "Vision is configured with an invalid model tier. "
        "Set `features.vision.model` to `cheap`, `medium`, or `expensive`."
    )


def resolve_vision_model_spec(adj_dir: Path, model: str | None = None):
    """Resolve the concrete vision model and optional reasoning-effort variant."""
    from adjutant.core.config import load_config

    return resolve_model_spec(
        model or resolve_vision_model(adj_dir),
        adj_dir / "state",
        load_config(adj_dir / "adjutant.yaml"),
        default_to_chat=False,
    )


# ---------------------------------------------------------------------------
# Core vision runner
# ---------------------------------------------------------------------------


def run_vision_multi(
    image_paths: list[str],
    prompt: str,
    adj_dir: Path,
    *,
    model: str | None = None,
) -> str:
    """Run vision analysis on one or more image files in a single LLM call.

    All images are passed to one opencode invocation via multiple -f flags so
    the model sees them together with shared context.

    Args:
        image_paths: List of absolute paths to image files. Must not be empty.
        prompt: The vision prompt to use.
        adj_dir: Adjutant root directory (for model resolution).
        model: Override model. If None, resolved via resolve_vision_model().

    Returns:
        Plain-text analysis from the LLM.
        Returns an informative message on model-not-found or timeout errors.
        Returns empty string if the LLM returned nothing.

    Raises:
        ValueError: If image_paths is empty.
        FileNotFoundError: If any path in image_paths does not exist.
    """
    from adjutant.core.backend import BackendNotFoundError, get_backend
    from adjutant.core.logging import adj_log

    if not image_paths:
        raise ValueError("No image paths provided.")

    for image_path in image_paths:
        img = Path(image_path)
        if not img.is_file():
            raise FileNotFoundError(f"Image file not found: {image_path}")

    if model is None:
        config_model = resolve_vision_model(adj_dir)
        config_error = _validate_vision_model_setting(config_model)
        if config_error:
            return config_error

    resolved = resolve_vision_model_spec(adj_dir, model)

    if len(image_paths) == 1:
        adj_log(
            "vision",
            f"Vision analysis: {image_paths[0]} using {resolved.model} variant={resolved.variant}",
        )
    else:
        adj_log(
            "vision",
            f"Vision analysis: {len(image_paths)} images using {resolved.model} variant={resolved.variant}",
        )

    backend = get_backend()
    if not backend.capabilities.vision:
        return f"The current backend (`{backend.name}`) doesn't support vision."

    files = [Path(p) for p in image_paths]
    result = asyncio.run(
        backend.run(
            prompt,
            model=resolved.model,
            variant=resolved.variant,
            files=files,
            timeout=_VISION_TIMEOUT,
        )
    )

    if result.error_type == "vision_unsupported":
        return (
            f"The configured vision model `{resolved.model}` doesn't support image analysis. "
            "Switch `features.vision.model` to a tier backed by a vision-capable model."
        )

    if result.timed_out:
        label = image_paths[0] if len(image_paths) == 1 else f"{len(image_paths)} images"
        adj_log("vision", f"Vision analysis timed out after {_VISION_TIMEOUT}s for {label}")
        return f"Vision analysis timed out after {_VISION_TIMEOUT}s. Try again in a moment."

    if result.error_type == "model_not_found":
        return (
            f"The configured vision model `{resolved.model}` isn't available. "
            "Update your tier mapping or switch `features.vision.model` to `cheap`, "
            "`medium`, or `expensive`."
        )

    if result.error_type == "auth_failure":
        return "Vision failed because the LLM backend is not authenticated."

    if result.error_type == "rate_limited":
        return "Vision is temporarily rate-limited. Try again in a moment."

    if result.error_type == "permission_denied":
        return "Vision failed because the backend denied access to the image file."

    if result.error_type in {"context_overflow", "parse_error", "error"}:
        if result.text.strip():
            return result.text.strip()
        return "Vision analysis failed due to a backend error. Try again."

    reply = result.text.strip()

    if reply:
        label = image_paths[0] if len(image_paths) == 1 else f"{len(image_paths)} images"
        adj_log("vision", f"Vision analysis complete for {label}")
        return reply
    else:
        label = image_paths[0] if len(image_paths) == 1 else f"{len(image_paths)} images"
        adj_log("vision", f"Vision analysis returned empty reply for {label}")
        return ""


def run_vision(
    image_path: str,
    prompt: str,
    adj_dir: Path,
    *,
    model: str | None = None,
) -> str:
    """Run vision analysis on a single image file.

    Convenience wrapper around run_vision_multi for the single-image case.

    Args:
        image_path: Absolute path to the image file.
        prompt: The vision prompt to use.
        adj_dir: Adjutant root directory (for model resolution).
        model: Override model. If None, resolved via resolve_vision_model().

    Returns:
        Plain-text analysis from the LLM.
        Returns an informative message on model-not-found or timeout errors.
        Returns empty string if the LLM returned nothing.

    Raises:
        FileNotFoundError: If image_path does not exist.
        ValueError: If image_path is empty.
    """
    if not image_path:
        raise ValueError("No image path provided.")

    return run_vision_multi([image_path], prompt, adj_dir, model=model)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: vision.py <image_path> [image_path2 ...] [--prompt PROMPT]

    All images are analysed together in a single LLM call.
    """
    args = argv if argv is not None else sys.argv[1:]

    if not args:
        sys.stderr.write("Usage: vision.py <image_path> [image_path2 ...] [--prompt PROMPT]\n")
        return 1

    # Parse --prompt flag
    prompt: str | None = None
    image_args: list[str] = []
    i = 0
    while i < len(args):
        if args[i] == "--prompt" and i + 1 < len(args):
            prompt = args[i + 1]
            i += 2
        else:
            image_args.append(args[i])
            i += 1

    if not image_args:
        sys.stderr.write("Error: No image paths provided.\n")
        return 1

    if prompt is None:
        prompt = _DEFAULT_PROMPT if len(image_args) == 1 else _DEFAULT_PROMPT_MULTI

    adj_dir_str = os.environ.get("ADJ_DIR", "").strip()
    if not adj_dir_str:
        sys.stderr.write("ERROR: ADJ_DIR not set\n")
        return 1

    adj_dir = Path(adj_dir_str)

    try:
        result = run_vision_multi(image_args, prompt, adj_dir)
        if result:
            print(result, end="")
            return 0
        else:
            sys.stderr.write(
                "I couldn't analyse the image(s) — the model returned an empty response.\n"
            )
            return 1
    except FileNotFoundError as e:
        sys.stderr.write(f"{e}\n")
        return 1
    except ValueError as e:
        sys.stderr.write(f"{e}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
