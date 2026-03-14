"""Unit tests for adjutant.capabilities.vision.vision."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from adjutant.capabilities.vision.vision import (
    _FALLBACK_MODEL,
    resolve_vision_model,
    run_vision,
    main,
)


# ---------------------------------------------------------------------------
# resolve_vision_model
# ---------------------------------------------------------------------------


class TestResolveVisionModel:
    def test_returns_config_model_when_set(self, tmp_path: Path) -> None:
        with patch(
            "adjutant.capabilities.vision.vision._get_vision_model_from_config",
            return_value="anthropic/claude-opus-4",
        ):
            model = resolve_vision_model(tmp_path)
        assert model == "anthropic/claude-opus-4"

    def test_falls_back_to_session_model(self, tmp_path: Path) -> None:
        state_dir = tmp_path / "state"
        state_dir.mkdir()
        (state_dir / "telegram_model.txt").write_text("openai/gpt-4o\n")
        with patch(
            "adjutant.capabilities.vision.vision._get_vision_model_from_config",
            return_value="",
        ):
            model = resolve_vision_model(tmp_path)
        assert model == "openai/gpt-4o"

    def test_falls_back_to_hardcoded_fallback(self, tmp_path: Path) -> None:
        with (
            patch(
                "adjutant.capabilities.vision.vision._get_vision_model_from_config",
                return_value="",
            ),
            patch(
                "adjutant.capabilities.vision.vision._get_session_model",
                return_value="",
            ),
        ):
            model = resolve_vision_model(tmp_path)
        assert model == _FALLBACK_MODEL

    def test_config_model_takes_priority_over_session(self, tmp_path: Path) -> None:
        state_dir = tmp_path / "state"
        state_dir.mkdir()
        (state_dir / "telegram_model.txt").write_text("session-model\n")
        with patch(
            "adjutant.capabilities.vision.vision._get_vision_model_from_config",
            return_value="config-model",
        ):
            model = resolve_vision_model(tmp_path)
        assert model == "config-model"

    def test_session_model_stripped(self, tmp_path: Path) -> None:
        state_dir = tmp_path / "state"
        state_dir.mkdir()
        (state_dir / "telegram_model.txt").write_text("  model-with-spaces  \n")
        with patch(
            "adjutant.capabilities.vision.vision._get_vision_model_from_config",
            return_value="",
        ):
            model = resolve_vision_model(tmp_path)
        assert model == "model-with-spaces"


# ---------------------------------------------------------------------------
# run_vision
# ---------------------------------------------------------------------------


def _make_ndjson_result(text="", error_type=""):
    m = MagicMock()
    m.text = text
    m.error_type = error_type
    return m


def _make_opencode_result(stdout="", timed_out=False):
    m = MagicMock()
    m.stdout = stdout
    m.timed_out = timed_out
    return m


class TestRunVision:
    def test_raises_value_error_on_empty_path(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="No image path"):
            run_vision("", "prompt", tmp_path)

    def test_raises_file_not_found_when_missing(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            run_vision(str(tmp_path / "nonexistent.png"), "prompt", tmp_path)

    def test_returns_text_on_success(self, tmp_path: Path) -> None:
        img = tmp_path / "image.png"
        img.write_bytes(b"fake png")

        with (
            patch(
                "adjutant.core.opencode.opencode_run",
                return_value=_make_opencode_result("ndjson output"),
            ),
            patch(
                "adjutant.lib.ndjson.parse_ndjson",
                return_value=_make_ndjson_result(text="A cat on a mat"),
            ),
            patch("adjutant.core.logging.adj_log"),
            patch(
                "adjutant.capabilities.vision.vision.resolve_vision_model",
                return_value="anthropic/claude-haiku-4-5",
            ),
        ):
            result = run_vision(str(img), "Describe this image.", tmp_path)

        assert result == "A cat on a mat"

    def test_returns_model_not_found_message(self, tmp_path: Path) -> None:
        img = tmp_path / "image.png"
        img.write_bytes(b"fake png")

        with (
            patch(
                "adjutant.core.opencode.opencode_run",
                return_value=_make_opencode_result(""),
            ),
            patch(
                "adjutant.lib.ndjson.parse_ndjson",
                return_value=_make_ndjson_result(error_type="model_not_found"),
            ),
            patch("adjutant.core.logging.adj_log"),
            patch(
                "adjutant.capabilities.vision.vision.resolve_vision_model",
                return_value="bad-model",
            ),
        ):
            result = run_vision(str(img), "Describe", tmp_path)

        assert "vision" in result.lower() or "model" in result.lower()

    def test_returns_empty_string_when_no_reply(self, tmp_path: Path) -> None:
        img = tmp_path / "image.png"
        img.write_bytes(b"fake png")

        with (
            patch(
                "adjutant.core.opencode.opencode_run",
                return_value=_make_opencode_result(""),
            ),
            patch(
                "adjutant.lib.ndjson.parse_ndjson",
                return_value=_make_ndjson_result(text="   "),
            ),
            patch("adjutant.core.logging.adj_log"),
            patch(
                "adjutant.capabilities.vision.vision.resolve_vision_model",
                return_value=_FALLBACK_MODEL,
            ),
        ):
            result = run_vision(str(img), "Describe", tmp_path)

        assert result == ""

    def test_returns_timeout_message_when_timed_out(self, tmp_path: Path) -> None:
        img = tmp_path / "image.png"
        img.write_bytes(b"fake png")

        with (
            patch(
                "adjutant.core.opencode.opencode_run",
                return_value=_make_opencode_result("", timed_out=True),
            ),
            patch("adjutant.core.logging.adj_log"),
            patch(
                "adjutant.capabilities.vision.vision.resolve_vision_model",
                return_value=_FALLBACK_MODEL,
            ),
        ):
            result = run_vision(str(img), "Describe", tmp_path)

        assert "timed out" in result.lower()

    def test_uses_override_model(self, tmp_path: Path) -> None:
        img = tmp_path / "image.png"
        img.write_bytes(b"fake png")

        captured_args = {}

        async def mock_opencode_run(args, timeout=None):
            captured_args["args"] = args
            return _make_opencode_result("")

        with (
            patch(
                "adjutant.core.opencode.opencode_run",
                side_effect=mock_opencode_run,
            ),
            patch(
                "adjutant.lib.ndjson.parse_ndjson",
                return_value=_make_ndjson_result(text="ok"),
            ),
            patch("adjutant.core.logging.adj_log"),
        ):
            run_vision(str(img), "Describe", tmp_path, model="override-model")

        assert "override-model" in captured_args["args"]


# ---------------------------------------------------------------------------
# main (CLI)
# ---------------------------------------------------------------------------


class TestMain:
    def test_returns_1_on_no_args(self) -> None:
        rc = main([])
        assert rc == 1

    def test_returns_1_when_adj_dir_not_set(self) -> None:
        env = {k: v for k, v in os.environ.items() if k != "ADJ_DIR"}
        with patch.dict(os.environ, env, clear=True):
            rc = main(["/path/to/image.png"])
        assert rc == 1

    def test_returns_0_on_success(self, tmp_path: Path) -> None:
        img = tmp_path / "image.png"
        img.write_bytes(b"fake png")
        with (
            patch.dict(os.environ, {"ADJ_DIR": str(tmp_path)}),
            patch(
                "adjutant.capabilities.vision.vision.run_vision",
                return_value="A descriptive caption",
            ),
        ):
            rc = main([str(img)])
        assert rc == 0

    def test_returns_1_when_empty_result(self, tmp_path: Path) -> None:
        img = tmp_path / "image.png"
        img.write_bytes(b"fake png")
        with (
            patch.dict(os.environ, {"ADJ_DIR": str(tmp_path)}),
            patch(
                "adjutant.capabilities.vision.vision.run_vision",
                return_value="",
            ),
        ):
            rc = main([str(img)])
        assert rc == 1

    def test_returns_1_on_file_not_found(self, tmp_path: Path) -> None:
        with (
            patch.dict(os.environ, {"ADJ_DIR": str(tmp_path)}),
            patch(
                "adjutant.capabilities.vision.vision.run_vision",
                side_effect=FileNotFoundError("no file"),
            ),
        ):
            rc = main([str(tmp_path / "missing.png")])
        assert rc == 1
