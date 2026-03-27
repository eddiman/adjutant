"""Tests for src/adjutant/setup/steps/backend.py"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

if TYPE_CHECKING:
    from pathlib import Path


class TestStepBackendChoice:
    """Verify the wiz_choose off-by-one fix: choice 1 → opencode, 2 → claude-cli."""

    def _run(self, tmp_path: Path, choice: int, perm_choice: int = 1) -> dict[str, str]:
        from adjutant.setup.steps.backend import step_backend

        responses = iter([choice, perm_choice])
        with (
            patch(
                "adjutant.setup.steps.backend.wiz_choose",
                side_effect=lambda *a: next(responses),
            ),
            patch("adjutant.setup.steps.backend._write_backend_to_yaml"),
        ):
            return step_backend(tmp_path, dry_run=True)

    def test_choice_1_gives_opencode(self, tmp_path: Path) -> None:
        result = self._run(tmp_path, choice=1)
        assert result["backend"] == "opencode"
        assert "permission_mode" not in result

    def test_choice_2_gives_claude_cli(self, tmp_path: Path) -> None:
        result = self._run(tmp_path, choice=2, perm_choice=1)
        assert result["backend"] == "claude-cli"

    def test_choice_2_perm_1_gives_skip(self, tmp_path: Path) -> None:
        result = self._run(tmp_path, choice=2, perm_choice=1)
        assert result.get("permission_mode") == "skip"

    def test_choice_2_perm_2_gives_allowlist(self, tmp_path: Path) -> None:
        result = self._run(tmp_path, choice=2, perm_choice=2)
        assert result.get("permission_mode") == "allowlist"

    def test_only_choice_1_yields_opencode(self, tmp_path: Path) -> None:
        """wiz_choose is 1-based so choice 1 is the only path to opencode."""
        result = self._run(tmp_path, choice=1)
        assert result["backend"] == "opencode"


class TestWriteBackendToYaml:
    def test_writes_backend_to_config(self, tmp_path: Path) -> None:
        import yaml

        config = tmp_path / "adjutant.yaml"
        config.write_text("instance:\n  name: test\nllm:\n  backend: opencode\n")

        from adjutant.setup.steps.backend import _write_backend_to_yaml

        _write_backend_to_yaml(tmp_path, {"backend": "claude-cli", "permission_mode": "skip"})

        data = yaml.safe_load(config.read_text())
        assert data["llm"]["backend"] == "claude-cli"
        assert data["llm"]["permission_mode"] == "skip"

    def test_no_op_when_config_missing(self, tmp_path: Path) -> None:
        from adjutant.setup.steps.backend import _write_backend_to_yaml

        # Should not raise even if adjutant.yaml doesn't exist
        _write_backend_to_yaml(tmp_path, {"backend": "opencode"})

    def test_does_not_overwrite_other_llm_keys(self, tmp_path: Path) -> None:
        import yaml

        config = tmp_path / "adjutant.yaml"
        config.write_text(
            "llm:\n  backend: opencode\n  models:\n    cheap: haiku\n    medium: sonnet\n"
        )

        from adjutant.setup.steps.backend import _write_backend_to_yaml

        _write_backend_to_yaml(tmp_path, {"backend": "claude-cli"})

        data = yaml.safe_load(config.read_text())
        assert data["llm"]["backend"] == "claude-cli"
        assert data["llm"]["models"]["cheap"] == "haiku"
