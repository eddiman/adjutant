"""Unit tests for adjutant.capabilities.vision.vision."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from adjutant.core.backend import LLMResult
from adjutant.capabilities.vision.vision import (
    _DEFAULT_VISION_TIER,
    resolve_vision_model,
    run_vision,
    run_vision_multi,
    main,
)


def _llm_result(text="", error_type=None, timed_out=False):
    return LLMResult(text=text, error_type=error_type, timed_out=timed_out)


def _mock_backend(result=None):
    backend = MagicMock()
    backend.run = AsyncMock(return_value=result or _llm_result())
    return backend


# ---------------------------------------------------------------------------
# resolve_vision_model
# ---------------------------------------------------------------------------


class TestResolveVisionModel:
    def test_returns_config_model_when_set(self, tmp_path: Path) -> None:
        with patch(
            "adjutant.capabilities.vision.vision._get_vision_model_from_config",
            return_value="medium",
        ):
            model = resolve_vision_model(tmp_path)
        assert model == "medium"

    def test_falls_back_to_default_tier_when_config_missing(self, tmp_path: Path) -> None:
        with patch(
            "adjutant.capabilities.vision.vision._get_vision_model_from_config",
            return_value="",
        ):
            model = resolve_vision_model(tmp_path)
        assert model == _DEFAULT_VISION_TIER

    def test_strips_config_model(self, tmp_path: Path) -> None:
        with patch(
            "adjutant.capabilities.vision.vision._get_vision_model_from_config",
            return_value="  expensive  ",
        ):
            model = resolve_vision_model(tmp_path)
        assert model == "expensive"


# ---------------------------------------------------------------------------
# run_vision
# ---------------------------------------------------------------------------


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
        backend = _mock_backend(_llm_result(text="A cat on a mat"))
        with (
            patch("adjutant.core.backend.get_backend", return_value=backend),
            patch("adjutant.core.logging.adj_log"),
            patch(
                "adjutant.capabilities.vision.vision.resolve_vision_model_spec",
                return_value=MagicMock(model="github-copilot/gpt-5.4-mini", variant="medium"),
            ),
        ):
            result = run_vision(str(img), "Describe this image.", tmp_path)
        assert result == "A cat on a mat"

    def test_returns_model_not_found_message(self, tmp_path: Path) -> None:
        img = tmp_path / "image.png"
        img.write_bytes(b"fake png")
        backend = _mock_backend(_llm_result(error_type="model_not_found"))
        with (
            patch("adjutant.core.backend.get_backend", return_value=backend),
            patch("adjutant.core.logging.adj_log"),
            patch(
                "adjutant.capabilities.vision.vision.resolve_vision_model_spec",
                return_value=MagicMock(model="bad-model", variant=None),
            ),
        ):
            result = run_vision(str(img), "Describe", tmp_path)
        assert "vision" in result.lower() or "model" in result.lower()

    def test_returns_empty_string_when_no_reply(self, tmp_path: Path) -> None:
        img = tmp_path / "image.png"
        img.write_bytes(b"fake png")
        backend = _mock_backend(_llm_result(text="   "))
        with (
            patch("adjutant.core.backend.get_backend", return_value=backend),
            patch("adjutant.core.logging.adj_log"),
            patch(
                "adjutant.capabilities.vision.vision.resolve_vision_model_spec",
                return_value=MagicMock(model="github-copilot/gpt-5.4-mini", variant=None),
            ),
        ):
            result = run_vision(str(img), "Describe", tmp_path)
        assert result == ""

    def test_returns_timeout_message_when_timed_out(self, tmp_path: Path) -> None:
        img = tmp_path / "image.png"
        img.write_bytes(b"fake png")
        backend = _mock_backend(_llm_result(timed_out=True))
        with (
            patch("adjutant.core.backend.get_backend", return_value=backend),
            patch("adjutant.core.logging.adj_log"),
            patch(
                "adjutant.capabilities.vision.vision.resolve_vision_model_spec",
                return_value=MagicMock(model="github-copilot/gpt-5.4-mini", variant=None),
            ),
        ):
            result = run_vision(str(img), "Describe", tmp_path)
        assert "timed out" in result.lower()

    def test_uses_override_model(self, tmp_path: Path) -> None:
        img = tmp_path / "image.png"
        img.write_bytes(b"fake png")
        backend = _mock_backend(_llm_result(text="ok"))
        with (
            patch("adjutant.core.backend.get_backend", return_value=backend),
            patch("adjutant.core.logging.adj_log"),
        ):
            run_vision(str(img), "Describe", tmp_path, model="override-model")
        call_kwargs = backend.run.call_args[1]
        assert call_kwargs["model"] == "override-model"
        assert call_kwargs["variant"] is None


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
        backend = _mock_backend(_llm_result(text="A cat on a mat"))
        with (
            patch("adjutant.core.backend.get_backend", return_value=backend),
            patch("adjutant.core.logging.adj_log"),
            patch(
                "adjutant.capabilities.vision.vision.resolve_vision_model_spec",
                return_value=MagicMock(model="github-copilot/gpt-5.4-mini", variant=None),
            ),
        ):
            result = run_vision_multi([str(img)], "Describe.", tmp_path)
        assert result == "A cat on a mat"

    def test_returns_text_on_success_multi(self, tmp_path: Path) -> None:
        img1 = tmp_path / "a.png"
        img2 = tmp_path / "b.png"
        img1.write_bytes(b"fake png 1")
        img2.write_bytes(b"fake png 2")
        backend = _mock_backend(_llm_result(text="Two images described."))
        with (
            patch("adjutant.core.backend.get_backend", return_value=backend),
            patch("adjutant.core.logging.adj_log"),
            patch(
                "adjutant.capabilities.vision.vision.resolve_vision_model_spec",
                return_value=MagicMock(model="github-copilot/gpt-5.4-mini", variant=None),
            ),
        ):
            result = run_vision_multi([str(img1), str(img2)], "Describe both.", tmp_path)
        assert result == "Two images described."

    def test_passes_files_to_backend(self, tmp_path: Path) -> None:
        img1 = tmp_path / "a.png"
        img2 = tmp_path / "b.png"
        img3 = tmp_path / "c.png"
        img1.write_bytes(b"x")
        img2.write_bytes(b"x")
        img3.write_bytes(b"x")
        backend = _mock_backend(_llm_result(text="ok"))
        with (
            patch("adjutant.core.backend.get_backend", return_value=backend),
            patch("adjutant.core.logging.adj_log"),
            patch(
                "adjutant.capabilities.vision.vision.resolve_vision_model_spec",
                return_value=MagicMock(model="github-copilot/gpt-5.4-mini", variant=None),
            ),
        ):
            run_vision_multi([str(img1), str(img2), str(img3)], "Describe.", tmp_path)
        call_kwargs = backend.run.call_args[1]
        files = call_kwargs["files"]
        assert len(files) == 3

    def test_timeout_returns_message(self, tmp_path: Path) -> None:
        img = tmp_path / "image.png"
        img.write_bytes(b"fake png")
        backend = _mock_backend(_llm_result(timed_out=True))
        with (
            patch("adjutant.core.backend.get_backend", return_value=backend),
            patch("adjutant.core.logging.adj_log"),
            patch(
                "adjutant.capabilities.vision.vision.resolve_vision_model_spec",
                return_value=MagicMock(model="github-copilot/gpt-5.4-mini", variant=None),
            ),
        ):
            result = run_vision_multi([str(img)], "Describe", tmp_path)
        assert "timed out" in result.lower()

    def test_model_not_found_returns_message(self, tmp_path: Path) -> None:
        img = tmp_path / "image.png"
        img.write_bytes(b"fake png")
        backend = _mock_backend(_llm_result(error_type="model_not_found"))
        with (
            patch("adjutant.core.backend.get_backend", return_value=backend),
            patch("adjutant.core.logging.adj_log"),
            patch(
                "adjutant.capabilities.vision.vision.resolve_vision_model_spec",
                return_value=MagicMock(model="bad-model", variant=None),
            ),
        ):
            result = run_vision_multi([str(img)], "Describe", tmp_path)
        assert "model" in result.lower()

    def test_empty_reply_returns_empty_string(self, tmp_path: Path) -> None:
        img = tmp_path / "image.png"
        img.write_bytes(b"fake png")
        backend = _mock_backend(_llm_result(text="   "))
        with (
            patch("adjutant.core.backend.get_backend", return_value=backend),
            patch("adjutant.core.logging.adj_log"),
            patch(
                "adjutant.capabilities.vision.vision.resolve_vision_model_spec",
                return_value=MagicMock(model="github-copilot/gpt-5.4-mini", variant=None),
            ),
        ):
            result = run_vision_multi([str(img)], "Describe", tmp_path)
        assert result == ""

    def test_invalid_configured_tier_returns_message(self, tmp_path: Path) -> None:
        img = tmp_path / "image.png"
        img.write_bytes(b"fake png")
        with patch(
            "adjutant.capabilities.vision.vision.resolve_vision_model",
            return_value="not-a-tier",
        ):
            result = run_vision_multi([str(img)], "Describe", tmp_path)
        assert "cheap" in result and "medium" in result and "expensive" in result

    def test_vision_unsupported_returns_message(self, tmp_path: Path) -> None:
        img = tmp_path / "image.png"
        img.write_bytes(b"fake png")
        backend = _mock_backend(_llm_result(error_type="vision_unsupported", text="unsupported"))
        with (
            patch("adjutant.core.backend.get_backend", return_value=backend),
            patch("adjutant.core.logging.adj_log"),
            patch(
                "adjutant.capabilities.vision.vision.resolve_vision_model_spec",
                return_value=MagicMock(model="github-copilot/gpt-5.4-mini", variant=None),
            ),
        ):
            result = run_vision_multi([str(img)], "Describe", tmp_path)
        assert "doesn't support image analysis" in result


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
