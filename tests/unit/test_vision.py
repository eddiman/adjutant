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
    run_vision_multi,
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
# run_vision_multi
# ---------------------------------------------------------------------------


class TestRunVisionMulti:
    def test_raises_value_error_on_empty_list(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="No image paths"):
            run_vision_multi([], "prompt", tmp_path)

    def test_raises_file_not_found_for_missing_path(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            run_vision_multi([str(tmp_path / "missing.png")], "prompt", tmp_path)

    def test_raises_file_not_found_for_any_missing_path(self, tmp_path: Path) -> None:
        img = tmp_path / "real.png"
        img.write_bytes(b"fake png")
        with pytest.raises(FileNotFoundError):
            run_vision_multi([str(img), str(tmp_path / "missing.png")], "prompt", tmp_path)

    def test_returns_text_on_success_single(self, tmp_path: Path) -> None:
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
                return_value=_FALLBACK_MODEL,
            ),
        ):
            result = run_vision_multi([str(img)], "Describe.", tmp_path)

        assert result == "A cat on a mat"

    def test_returns_text_on_success_multi(self, tmp_path: Path) -> None:
        img1 = tmp_path / "a.png"
        img2 = tmp_path / "b.png"
        img1.write_bytes(b"fake png 1")
        img2.write_bytes(b"fake png 2")

        with (
            patch(
                "adjutant.core.opencode.opencode_run",
                return_value=_make_opencode_result("ndjson output"),
            ),
            patch(
                "adjutant.lib.ndjson.parse_ndjson",
                return_value=_make_ndjson_result(text="Two images described."),
            ),
            patch("adjutant.core.logging.adj_log"),
            patch(
                "adjutant.capabilities.vision.vision.resolve_vision_model",
                return_value=_FALLBACK_MODEL,
            ),
        ):
            result = run_vision_multi([str(img1), str(img2)], "Describe both.", tmp_path)

        assert result == "Two images described."

    def test_builds_multiple_f_flags(self, tmp_path: Path) -> None:
        img1 = tmp_path / "a.png"
        img2 = tmp_path / "b.png"
        img3 = tmp_path / "c.png"
        img1.write_bytes(b"x")
        img2.write_bytes(b"x")
        img3.write_bytes(b"x")

        captured: dict[str, list[str]] = {}

        async def mock_opencode_run(args: list[str], timeout: float | None = None) -> object:
            captured["args"] = args
            return _make_opencode_result("")

        with (
            patch("adjutant.core.opencode.opencode_run", side_effect=mock_opencode_run),
            patch("adjutant.lib.ndjson.parse_ndjson", return_value=_make_ndjson_result(text="ok")),
            patch("adjutant.core.logging.adj_log"),
            patch(
                "adjutant.capabilities.vision.vision.resolve_vision_model",
                return_value=_FALLBACK_MODEL,
            ),
        ):
            run_vision_multi([str(img1), str(img2), str(img3)], "Describe.", tmp_path)

        args = captured["args"]
        # Each image should appear preceded by -f
        f_indices = [i for i, a in enumerate(args) if a == "-f"]
        assert len(f_indices) == 3
        assert args[f_indices[0] + 1] == str(img1)
        assert args[f_indices[1] + 1] == str(img2)
        assert args[f_indices[2] + 1] == str(img3)

    def test_timeout_returns_message(self, tmp_path: Path) -> None:
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
            result = run_vision_multi([str(img)], "Describe", tmp_path)

        assert "timed out" in result.lower()

    def test_model_not_found_returns_message(self, tmp_path: Path) -> None:
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
            result = run_vision_multi([str(img)], "Describe", tmp_path)

        assert "model" in result.lower()

    def test_empty_reply_returns_empty_string(self, tmp_path: Path) -> None:
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
            result = run_vision_multi([str(img)], "Describe", tmp_path)

        assert result == ""


# ---------------------------------------------------------------------------
# run_vision delegates to run_vision_multi
# ---------------------------------------------------------------------------


class TestRunVisionDelegates:
    def test_single_delegates_to_multi(self, tmp_path: Path) -> None:
        img = tmp_path / "image.png"
        img.write_bytes(b"fake png")

        with patch(
            "adjutant.capabilities.vision.vision.run_vision_multi",
            return_value="delegated result",
        ) as mock_multi:
            result = run_vision(str(img), "Describe", tmp_path, model="test-model")

        mock_multi.assert_called_once_with([str(img)], "Describe", tmp_path, model="test-model")
        assert result == "delegated result"

    def test_raises_value_error_on_empty_path(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="No image path"):
            run_vision("", "prompt", tmp_path)


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
                "adjutant.capabilities.vision.vision.run_vision_multi",
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
                "adjutant.capabilities.vision.vision.run_vision_multi",
                return_value="",
            ),
        ):
            rc = main([str(img)])
        assert rc == 1

    def test_returns_1_on_file_not_found(self, tmp_path: Path) -> None:
        with (
            patch.dict(os.environ, {"ADJ_DIR": str(tmp_path)}),
            patch(
                "adjutant.capabilities.vision.vision.run_vision_multi",
                side_effect=FileNotFoundError("no file"),
            ),
        ):
            rc = main([str(tmp_path / "missing.png")])
        assert rc == 1

    def test_multi_images_passed_to_multi(self, tmp_path: Path) -> None:
        img1 = tmp_path / "a.png"
        img2 = tmp_path / "b.png"
        img1.write_bytes(b"x")
        img2.write_bytes(b"x")

        with (
            patch.dict(os.environ, {"ADJ_DIR": str(tmp_path)}),
            patch(
                "adjutant.capabilities.vision.vision.run_vision_multi",
                return_value="Combined analysis",
            ) as mock_multi,
        ):
            rc = main([str(img1), str(img2)])

        assert rc == 0
        called_paths = mock_multi.call_args[0][0]
        assert str(img1) in called_paths
        assert str(img2) in called_paths

    def test_prompt_flag_parsed(self, tmp_path: Path) -> None:
        img = tmp_path / "image.png"
        img.write_bytes(b"x")

        with (
            patch.dict(os.environ, {"ADJ_DIR": str(tmp_path)}),
            patch(
                "adjutant.capabilities.vision.vision.run_vision_multi",
                return_value="ok",
            ) as mock_multi,
        ):
            main([str(img), "--prompt", "Custom prompt here"])

        called_prompt = mock_multi.call_args[0][1]
        assert called_prompt == "Custom prompt here"
