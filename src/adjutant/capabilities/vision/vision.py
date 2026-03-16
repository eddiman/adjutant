"""AI vision analysis for images.

Replaces: scripts/capabilities/vision/vision.sh

Passes one or more image files to an LLM via opencode run --file and returns
the plain-text analysis. Used by screenshot.py for auto-captioning and by
the Telegram backend for handling received photos.

Model resolution order:
  1. features.vision.model from adjutant.yaml
  2. state/telegram_model.txt (session model set by /model command)
  3. anthropic/claude-haiku-4-5 (hardcoded fallback)

Output: plain-text vision analysis, or an informative error message.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Model resolution
# ---------------------------------------------------------------------------

_FALLBACK_MODEL = "anthropic/claude-haiku-4-5"
_DEFAULT_PROMPT = "Describe what you see in this image. Be concise and informative."
_DEFAULT_PROMPT_MULTI = "Describe what you see in these images. Be concise and informative."
_VISION_TIMEOUT = 240  # seconds — matches chat timeout


def _get_vision_model_from_config(adj_dir: Path) -> str:
    """Read features.vision.model from adjutant.yaml. Returns '' if missing."""
    try:
        from adjutant.core.config import load_typed_config

        config = load_typed_config(adj_dir / "adjutant.yaml")
        model = config.features.vision.model
        return model.strip() if model else ""
    except Exception:  # noqa: BLE001 — fallback to default model
        return ""


def _get_session_model(adj_dir: Path) -> str:
    """Read the current session model from state/telegram_model.txt."""
    model_file = adj_dir / "state" / "telegram_model.txt"
    if model_file.is_file():
        return model_file.read_text().strip()
    return ""


def resolve_vision_model(adj_dir: Path) -> str:
    """Resolve the vision model using the priority chain."""
    model = _get_vision_model_from_config(adj_dir)
    if model:
        return model
    model = _get_session_model(adj_dir)
    if model:
        return model
    return _FALLBACK_MODEL


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
    from adjutant.core.logging import adj_log
    from adjutant.core.opencode import opencode_run
    from adjutant.lib.ndjson import parse_ndjson

    if not image_paths:
        raise ValueError("No image paths provided.")

    for image_path in image_paths:
        img = Path(image_path)
        if not img.is_file():
            raise FileNotFoundError(f"Image file not found: {image_path}")

    resolved_model = model or resolve_vision_model(adj_dir)

    if len(image_paths) == 1:
        adj_log("vision", f"Vision analysis: {image_paths[0]} using {resolved_model}")
    else:
        adj_log(
            "vision",
            f"Vision analysis: {len(image_paths)} images using {resolved_model}",
        )

    # Build args with one -f flag per image
    file_args: list[str] = []
    for image_path in image_paths:
        file_args += ["-f", image_path]

    args = [
        "run",
        "--model",
        resolved_model,
        "--format",
        "json",
        *file_args,
        "--",
        prompt,
    ]

    result = asyncio.run(opencode_run(args, timeout=_VISION_TIMEOUT))

    if result.timed_out:
        label = image_paths[0] if len(image_paths) == 1 else f"{len(image_paths)} images"
        adj_log("vision", f"Vision analysis timed out after {_VISION_TIMEOUT}s for {label}")
        return f"Vision analysis timed out after {_VISION_TIMEOUT}s. Try again in a moment."

    parsed = parse_ndjson(result.stdout)

    if parsed.error_type == "model_not_found":
        return (
            "The selected model doesn't support vision. "
            "Try switching to claude-haiku-4-5 with /model anthropic/claude-haiku-4-5."
        )

    reply = parsed.text.strip()

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
