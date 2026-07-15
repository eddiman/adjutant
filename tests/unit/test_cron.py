"""Tests for src/adjutant/lifecycle/cron.py

Tests run_cron_prompt(), pulse_cron(), review_cron(), _notify_completion(),
_format_heartbeat().
No real opencode or filesystem I/O outside of tmp_path.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from adjutant.lifecycle.cron import (
    _format_heartbeat,
    _notify_completion,
    brief_cron,
    pulse_cron,
    review_cron,
    run_cron_prompt,
    self_assess_cron,
)


def _mock_backend(returncode: int = 0) -> MagicMock:
    """Return a mock backend with configurable returncode."""
    backend = MagicMock()
    backend.run_sync = MagicMock(return_value=returncode)
    backend.find_binary = MagicMock(return_value="/usr/bin/opencode")
    backend.name = "opencode"
    return backend


# ---------------------------------------------------------------------------
# run_cron_prompt
# ---------------------------------------------------------------------------


class TestRunCronPrompt:
    def test_skips_when_paused(self, tmp_path: Path) -> None:
        prompt = tmp_path / "pulse.md"
        prompt.write_text("Do not run")
        (tmp_path / "PAUSED").touch()

        with (
            patch("adjutant.lifecycle.cron.get_backend") as mock_backend,
            pytest.raises(SystemExit) as exc_info,
        ):
            run_cron_prompt(prompt, adj_dir=tmp_path, action="pulse")

        assert exc_info.value.code == 0
        mock_backend.assert_not_called()

    def test_runs_backend_with_prompt(self, tmp_path: Path) -> None:
        """Should call backend.run_sync with the prompt text."""
        prompt = tmp_path / "pulse.md"
        prompt.write_text("Do the thing")

        backend = _mock_backend()
        with (
            patch("adjutant.lifecycle.cron.get_backend", return_value=backend),
            pytest.raises(SystemExit) as exc_info,
        ):
            run_cron_prompt(prompt, adj_dir=tmp_path)

        assert exc_info.value.code == 0
        backend.run_sync.assert_called_once_with("Do the thing", workdir=tmp_path)

    def test_propagates_nonzero_exit_code(self, tmp_path: Path) -> None:
        """Should propagate backend's non-zero exit code via sys.exit."""
        prompt = tmp_path / "pulse.md"
        prompt.write_text("fail prompt")

        backend = _mock_backend(returncode=42)
        with (
            patch("adjutant.lifecycle.cron.get_backend", return_value=backend),
            pytest.raises(SystemExit) as exc_info,
        ):
            run_cron_prompt(prompt, adj_dir=tmp_path)

        assert exc_info.value.code == 42

    def test_writes_and_clears_active_operation(self, tmp_path: Path) -> None:
        """Should write state/active_operation.json before backend and remove it after."""
        prompt = tmp_path / "pulse.md"
        prompt.write_text("marker test")
        op_file = tmp_path / "state" / "active_operation.json"

        marker_existed_during_run = False

        def fake_run_sync(*_args: object, **_kwargs: object) -> int:
            nonlocal marker_existed_during_run
            marker_existed_during_run = op_file.is_file()
            return 0

        backend = _mock_backend()
        backend.run_sync = MagicMock(side_effect=fake_run_sync)

        with (
            patch("adjutant.lifecycle.cron.get_backend", return_value=backend),
            pytest.raises(SystemExit),
        ):
            run_cron_prompt(prompt, adj_dir=tmp_path, action="pulse", source="test")

        assert marker_existed_during_run, "Marker should exist while backend runs"
        assert not op_file.exists(), "Marker should be cleaned up after completion"

    def test_clears_marker_on_failure(self, tmp_path: Path) -> None:
        """Should clear the marker even when backend.run_sync raises."""
        prompt = tmp_path / "pulse.md"
        prompt.write_text("crash test")
        op_file = tmp_path / "state" / "active_operation.json"

        backend = _mock_backend()
        backend.run_sync = MagicMock(side_effect=OSError("boom"))

        with (
            patch("adjutant.lifecycle.cron.get_backend", return_value=backend),
            pytest.raises(OSError, match="boom"),
        ):
            run_cron_prompt(prompt, adj_dir=tmp_path, action="pulse", source="test")

        assert not op_file.exists(), "Marker should be cleaned up after failure"

    def test_marker_contains_action_and_source(self, tmp_path: Path) -> None:
        """Marker JSON should contain the action and source fields."""
        prompt = tmp_path / "pulse.md"
        prompt.write_text("check fields")
        op_file = tmp_path / "state" / "active_operation.json"

        captured_data: dict[str, object] = {}

        def fake_run_sync(*_args: object, **_kwargs: object) -> int:
            captured_data.update(json.loads(op_file.read_text()))
            return 0

        backend = _mock_backend()
        backend.run_sync = MagicMock(side_effect=fake_run_sync)

        with (
            patch("adjutant.lifecycle.cron.get_backend", return_value=backend),
            pytest.raises(SystemExit),
        ):
            run_cron_prompt(
                prompt,
                adj_dir=tmp_path,
                action="review",
                source="adjutant-web",
            )

        assert captured_data["action"] == "review"
        assert captured_data["source"] == "adjutant-web"
        assert "started_at" in captured_data
        assert "pid" in captured_data

    def test_raises_if_prompt_missing(self, tmp_path: Path) -> None:
        """Should raise SystemExit(1) when prompt file does not exist."""
        missing = tmp_path / "no_such_prompt.md"
        with pytest.raises(SystemExit) as exc_info:
            run_cron_prompt(missing, adj_dir=tmp_path)
        assert exc_info.value.code == 1

    def test_raises_if_backend_binary_missing(self, tmp_path: Path) -> None:
        """Should raise SystemExit(1) when backend binary is not on PATH."""
        prompt = tmp_path / "pulse.md"
        prompt.write_text("prompt text")

        backend = _mock_backend()
        backend.find_binary = MagicMock(return_value=None)

        with (
            patch("adjutant.lifecycle.cron.get_backend", return_value=backend),
            pytest.raises(SystemExit) as exc_info,
        ):
            run_cron_prompt(prompt, adj_dir=tmp_path)
        assert exc_info.value.code == 1

    def test_raises_if_backend_not_found(self, tmp_path: Path) -> None:
        """Should raise SystemExit(1) when get_backend raises BackendNotFoundError."""
        from adjutant.core.backend import BackendNotFoundError

        prompt = tmp_path / "pulse.md"
        prompt.write_text("prompt text")

        with (
            patch(
                "adjutant.lifecycle.cron.get_backend",
                side_effect=BackendNotFoundError("no backend"),
            ),
            pytest.raises(SystemExit) as exc_info,
        ):
            run_cron_prompt(prompt, adj_dir=tmp_path)
        assert exc_info.value.code == 1

    def test_raises_if_adj_dir_not_set(self, tmp_path: Path) -> None:
        """Should raise SystemExit(1) when adj_dir is None and ADJ_DIR env not set."""
        prompt = tmp_path / "pulse.md"
        prompt.write_text("x")

        env = {k: v for k, v in os.environ.items() if k not in ("ADJ_DIR", "ADJUTANT_DIR")}
        with patch.dict(os.environ, env, clear=True), pytest.raises(SystemExit) as exc_info:
            run_cron_prompt(prompt, adj_dir=None)
        assert exc_info.value.code == 1

    def test_uses_adj_dir_env_when_not_passed(self, tmp_path: Path) -> None:
        """Should fall back to $ADJ_DIR when adj_dir param is None."""
        prompt = tmp_path / "pulse.md"
        prompt.write_text("env-sourced")

        backend = _mock_backend()
        with (
            patch.dict(os.environ, {"ADJ_DIR": str(tmp_path)}),
            patch("adjutant.lifecycle.cron.get_backend", return_value=backend),
            pytest.raises(SystemExit) as exc_info,
        ):
            run_cron_prompt(prompt, adj_dir=None)

        assert exc_info.value.code == 0
        backend.run_sync.assert_called_once_with("env-sourced", workdir=tmp_path)


# ---------------------------------------------------------------------------
# pulse_cron
# ---------------------------------------------------------------------------


class TestPulseCron:
    def test_reads_pulse_md(self, tmp_path: Path) -> None:
        """pulse_cron() should run backend with prompts/pulse.md."""
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()
        (prompts_dir / "pulse.md").write_text("pulse text")

        backend = _mock_backend()
        with (
            patch("adjutant.lifecycle.cron.init_adj_dir", return_value=tmp_path),
            patch("adjutant.lifecycle.cron.get_backend", return_value=backend),
            pytest.raises(SystemExit) as exc_info,
        ):
            pulse_cron()

        assert exc_info.value.code == 0
        backend.run_sync.assert_called_once_with("pulse text", workdir=tmp_path)

    def test_raises_if_pulse_md_missing(self, tmp_path: Path) -> None:
        """pulse_cron() should raise SystemExit(1) if prompts/pulse.md is absent."""
        with (
            patch("adjutant.lifecycle.cron.init_adj_dir", return_value=tmp_path),
            pytest.raises(SystemExit) as exc_info,
        ):
            pulse_cron()
        assert exc_info.value.code == 1

    def test_accepts_explicit_adj_dir(self, tmp_path: Path) -> None:
        """pulse_cron(adj_dir=...) should skip init_adj_dir."""
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()
        (prompts_dir / "pulse.md").write_text("explicit")

        backend = _mock_backend()
        with (
            patch("adjutant.lifecycle.cron.get_backend", return_value=backend),
            pytest.raises(SystemExit),
        ):
            pulse_cron(adj_dir=tmp_path)

        backend.run_sync.assert_called_once()

    def test_passes_source_kwarg(self, tmp_path: Path) -> None:
        """pulse_cron(source=...) should pass source to the marker."""
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()
        (prompts_dir / "pulse.md").write_text("source test")
        op_file = tmp_path / "state" / "active_operation.json"

        captured_source = None

        def fake_run_sync(*_args: object, **_kwargs: object) -> int:
            nonlocal captured_source
            data = json.loads(op_file.read_text())
            captured_source = data["source"]
            return 0

        backend = _mock_backend()
        backend.run_sync = MagicMock(side_effect=fake_run_sync)

        with (
            patch("adjutant.lifecycle.cron.get_backend", return_value=backend),
            pytest.raises(SystemExit),
        ):
            pulse_cron(adj_dir=tmp_path, source="adjutant-web")

        assert captured_source == "adjutant-web"

    def test_raises_on_adj_dir_not_found(self) -> None:
        """pulse_cron() should raise SystemExit(1) on AdjutantDirNotFoundError."""
        from adjutant.core.paths import AdjutantDirNotFoundError

        with (
            patch(
                "adjutant.lifecycle.cron.init_adj_dir",
                side_effect=AdjutantDirNotFoundError("not found"),
            ),
            pytest.raises(SystemExit) as exc_info,
        ):
            pulse_cron()
        assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# review_cron
# ---------------------------------------------------------------------------


class TestReviewCron:
    def test_reads_review_md(self, tmp_path: Path) -> None:
        """review_cron() should run backend with prompts/review.md."""
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()
        (prompts_dir / "review.md").write_text("review text")

        backend = _mock_backend()
        with (
            patch("adjutant.lifecycle.cron.init_adj_dir", return_value=tmp_path),
            patch("adjutant.lifecycle.cron.get_backend", return_value=backend),
            pytest.raises(SystemExit) as exc_info,
        ):
            review_cron()

        assert exc_info.value.code == 0
        backend.run_sync.assert_called_once_with("review text", workdir=tmp_path)

    def test_raises_if_review_md_missing(self, tmp_path: Path) -> None:
        with (
            patch("adjutant.lifecycle.cron.init_adj_dir", return_value=tmp_path),
            pytest.raises(SystemExit) as exc_info,
        ):
            review_cron()
        assert exc_info.value.code == 1

    def test_accepts_explicit_adj_dir(self, tmp_path: Path) -> None:
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()
        (prompts_dir / "review.md").write_text("explicit review")

        backend = _mock_backend()
        with (
            patch("adjutant.lifecycle.cron.get_backend", return_value=backend),
            pytest.raises(SystemExit),
        ):
            review_cron(adj_dir=tmp_path)

        backend.run_sync.assert_called_once()


# ---------------------------------------------------------------------------
# _format_heartbeat
# ---------------------------------------------------------------------------


class TestFormatHeartbeat:
    def test_pulse_with_issues(self) -> None:
        data = {
            "kbs_checked": ["ixda", "portfolio"],
            "issues_found": ["IxDA: deadline Friday", "Portfolio: high concentration"],
            "escalated": False,
        }
        result = _format_heartbeat(data, "pulse", "cron")
        assert "2 KBs" in result
        assert "2 issues" in result
        assert "IxDA: deadline Friday" in result
        assert "Portfolio: high concentration" in result
        assert "Flagged" not in result

    def test_review_with_escalation(self) -> None:
        data = {
            "kbs_checked": ["portfolio"],
            "issues_found": [],
            "escalated": True,
        }
        result = _format_heartbeat(data, "review", "telegram")
        assert "portfolio" in result
        assert "All clear" in result
        assert "Flagged" in result

    def test_no_issues(self) -> None:
        data = {"kbs_checked": ["ixda"], "issues_found": [], "escalated": False}
        result = _format_heartbeat(data, "pulse", "adjutant-web")
        assert "ixda" in result
        assert "All clear" in result

    def test_truncates_many_issues(self) -> None:
        data = {
            "kbs_checked": ["ixda"],
            "issues_found": [f"issue {i}" for i in range(12)],
            "escalated": False,
        }
        result = _format_heartbeat(data, "pulse", "cron")
        assert "issue 7" in result  # 8th issue (0-indexed) is included
        assert "issue 8" not in result  # 9th is truncated
        assert "plus 4 more" in result

    def test_empty_data(self) -> None:
        result = _format_heartbeat({}, "pulse", "cron")
        assert "nothing to check" in result

    def test_single_issue_inlined(self) -> None:
        data = {
            "kbs_checked": ["ixda"],
            "issues_found": ["deadline approaching"],
            "escalated": False,
        }
        result = _format_heartbeat(data, "pulse", "cron")
        assert "one issue" in result
        assert "deadline approaching" in result


# ---------------------------------------------------------------------------
# _notify_completion
# ---------------------------------------------------------------------------


class TestNotifyCompletion:
    def test_silent_when_paused(self, tmp_path: Path) -> None:
        state_dir = tmp_path / "state"
        state_dir.mkdir()
        (tmp_path / "PAUSED").touch()
        (state_dir / "last_heartbeat.json").write_text(
            json.dumps({"kbs_checked": [], "issues_found": [], "escalated": False})
        )

        with patch("adjutant.messaging.telegram.notify.send_notify") as mock_notify:
            _notify_completion(tmp_path, "pulse", "cron")

        mock_notify.assert_not_called()

    def test_sends_notification_on_heartbeat(self, tmp_path: Path) -> None:
        """Should read heartbeat and call send_notify."""
        state_dir = tmp_path / "state"
        state_dir.mkdir()
        (state_dir / "last_heartbeat.json").write_text(
            json.dumps(
                {
                    "type": "pulse",
                    "kbs_checked": ["ixda"],
                    "issues_found": [],
                    "escalated": False,
                }
            )
        )

        with patch(
            "adjutant.messaging.telegram.notify.send_notify",
        ) as mock_notify:
            _notify_completion(tmp_path, "pulse", "cron")

        mock_notify.assert_called_once()
        msg = mock_notify.call_args[0][0]
        assert "ixda" in msg
        assert "All clear" in msg

    def test_silent_when_no_heartbeat(self, tmp_path: Path) -> None:
        """Should not crash when heartbeat file is missing."""
        (tmp_path / "state").mkdir()
        _notify_completion(tmp_path, "pulse", "cron")  # Should not raise

    def test_silent_on_budget_exceeded(self, tmp_path: Path) -> None:
        """Should swallow BudgetExceededError."""
        from adjutant.messaging.telegram.notify import BudgetExceededError

        state_dir = tmp_path / "state"
        state_dir.mkdir()
        (state_dir / "last_heartbeat.json").write_text(
            json.dumps(
                {
                    "type": "pulse",
                    "kbs_checked": [],
                    "issues_found": [],
                    "escalated": False,
                }
            )
        )

        with patch(
            "adjutant.messaging.telegram.notify.send_notify",
            side_effect=BudgetExceededError(3, 3),
        ):
            _notify_completion(tmp_path, "pulse", "cron")  # Should not raise

    def test_silent_on_missing_credentials(self, tmp_path: Path) -> None:
        """Should swallow RuntimeError from missing credentials."""
        state_dir = tmp_path / "state"
        state_dir.mkdir()
        (state_dir / "last_heartbeat.json").write_text(
            json.dumps(
                {
                    "type": "pulse",
                    "kbs_checked": [],
                    "issues_found": [],
                    "escalated": False,
                }
            )
        )

        with patch(
            "adjutant.messaging.telegram.notify.send_notify",
            side_effect=RuntimeError("no credentials"),
        ):
            _notify_completion(tmp_path, "pulse", "cron")  # Should not raise

    def test_not_called_on_nonzero_exit(self, tmp_path: Path) -> None:
        """run_cron_prompt should NOT notify when backend fails."""
        prompt = tmp_path / "pulse.md"
        prompt.write_text("fail test")

        backend = _mock_backend(returncode=1)
        with (
            patch("adjutant.lifecycle.cron.get_backend", return_value=backend),
            patch("adjutant.lifecycle.cron._notify_completion") as mock_notify,
            pytest.raises(SystemExit) as exc_info,
        ):
            run_cron_prompt(prompt, adj_dir=tmp_path, action="pulse", source="cron")

        assert exc_info.value.code == 1
        mock_notify.assert_not_called()

    def test_called_on_success(self, tmp_path: Path) -> None:
        """run_cron_prompt should notify on exit code 0."""
        prompt = tmp_path / "pulse.md"
        prompt.write_text("success test")

        backend = _mock_backend()
        with (
            patch("adjutant.lifecycle.cron.get_backend", return_value=backend),
            patch("adjutant.lifecycle.cron._notify_completion") as mock_notify,
            pytest.raises(SystemExit) as exc_info,
        ):
            run_cron_prompt(prompt, adj_dir=tmp_path, action="pulse", source="adjutant-web")

        assert exc_info.value.code == 0
        mock_notify.assert_called_once_with(tmp_path, "pulse", "adjutant-web")

    def test_not_called_for_unknown_action(self, tmp_path: Path) -> None:
        """run_cron_prompt should skip notification for action='unknown'."""
        prompt = tmp_path / "test.md"
        prompt.write_text("unknown")

        backend = _mock_backend()
        with (
            patch("adjutant.lifecycle.cron.get_backend", return_value=backend),
            patch("adjutant.lifecycle.cron._notify_completion") as mock_notify,
            pytest.raises(SystemExit),
        ):
            run_cron_prompt(prompt, adj_dir=tmp_path, action="unknown", source="cron")

        mock_notify.assert_not_called()


# ---------------------------------------------------------------------------
# brief_cron / self_assess_cron
# ---------------------------------------------------------------------------


class TestBriefCron:
    def test_reads_morning_brief_prompt(self, tmp_path: Path) -> None:
        """brief_cron should read prompts/morning_brief.md and run backend."""
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()
        (prompts_dir / "morning_brief.md").write_text("Morning brief prompt")

        backend = _mock_backend()
        with (
            patch("adjutant.lifecycle.cron.get_backend", return_value=backend),
            patch("adjutant.lifecycle.cron.init_adj_dir", return_value=tmp_path),
            pytest.raises(SystemExit) as exc_info,
        ):
            brief_cron(adj_dir=tmp_path)

        assert exc_info.value.code == 0
        backend.run_sync.assert_called_once_with("Morning brief prompt", workdir=tmp_path)

    def test_exits_1_when_prompt_missing(self, tmp_path: Path) -> None:
        """brief_cron should exit 1 when prompts/morning_brief.md is missing."""
        with pytest.raises(SystemExit) as exc_info:
            brief_cron(adj_dir=tmp_path)

        assert exc_info.value.code == 1


class TestSelfAssessCron:
    def test_reads_self_assess_prompt(self, tmp_path: Path) -> None:
        """self_assess_cron should read prompts/self_assess.md and run backend."""
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()
        (prompts_dir / "self_assess.md").write_text("Self assessment prompt")

        backend = _mock_backend()
        with (
            patch("adjutant.lifecycle.cron.get_backend", return_value=backend),
            patch("adjutant.lifecycle.cron.init_adj_dir", return_value=tmp_path),
            pytest.raises(SystemExit) as exc_info,
        ):
            self_assess_cron(adj_dir=tmp_path)

        assert exc_info.value.code == 0
        backend.run_sync.assert_called_once_with("Self assessment prompt", workdir=tmp_path)

    def test_exits_1_when_prompt_missing(self, tmp_path: Path) -> None:
        """self_assess_cron should exit 1 when prompts/self_assess.md is missing."""
        with pytest.raises(SystemExit) as exc_info:
            self_assess_cron(adj_dir=tmp_path)

        assert exc_info.value.code == 1
