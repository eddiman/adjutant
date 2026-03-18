"""Tests for src/adjutant/lifecycle/cron.py

Tests run_cron_prompt(), pulse_cron(), review_cron(), _notify_completion(),
_format_heartbeat().
No real opencode or filesystem I/O outside of tmp_path.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from adjutant.lifecycle.cron import (
    _format_heartbeat,
    _notify_completion,
    pulse_cron,
    review_cron,
    run_cron_prompt,
)


def _mock_run_ok() -> subprocess.CompletedProcess[bytes]:
    """Return a CompletedProcess with returncode 0."""
    return subprocess.CompletedProcess(args=[], returncode=0)


# ---------------------------------------------------------------------------
# run_cron_prompt
# ---------------------------------------------------------------------------


class TestRunCronPrompt:
    def test_runs_opencode_with_prompt(self, tmp_path: Path) -> None:
        """Should call subprocess.run with opencode and the prompt text."""
        prompt = tmp_path / "pulse.md"
        prompt.write_text("Do the thing")

        with (
            patch("adjutant.lifecycle.cron._find_opencode", return_value="/usr/bin/opencode"),
            patch("subprocess.run", return_value=_mock_run_ok()) as mock_run,
            pytest.raises(SystemExit) as exc_info,
        ):
            run_cron_prompt(prompt, adj_dir=tmp_path)

        assert exc_info.value.code == 0
        mock_run.assert_called_once_with(
            ["/usr/bin/opencode", "run", "--dir", str(tmp_path), "Do the thing"],
        )

    def test_propagates_nonzero_exit_code(self, tmp_path: Path) -> None:
        """Should propagate opencode's non-zero exit code via sys.exit."""
        prompt = tmp_path / "pulse.md"
        prompt.write_text("fail prompt")

        fail_result = subprocess.CompletedProcess(args=[], returncode=42)
        with (
            patch("adjutant.lifecycle.cron._find_opencode", return_value="/usr/bin/opencode"),
            patch("subprocess.run", return_value=fail_result),
            pytest.raises(SystemExit) as exc_info,
        ):
            run_cron_prompt(prompt, adj_dir=tmp_path)

        assert exc_info.value.code == 42

    def test_writes_and_clears_active_operation(self, tmp_path: Path) -> None:
        """Should write state/active_operation.json before opencode and remove it after."""
        prompt = tmp_path / "pulse.md"
        prompt.write_text("marker test")
        op_file = tmp_path / "state" / "active_operation.json"

        marker_existed_during_run = False

        def fake_run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[bytes]:
            nonlocal marker_existed_during_run
            marker_existed_during_run = op_file.is_file()
            return _mock_run_ok()

        with (
            patch("adjutant.lifecycle.cron._find_opencode", return_value="/usr/bin/opencode"),
            patch("subprocess.run", side_effect=fake_run),
            pytest.raises(SystemExit),
        ):
            run_cron_prompt(prompt, adj_dir=tmp_path, action="pulse", source="test")

        assert marker_existed_during_run, "Marker should exist while opencode runs"
        assert not op_file.exists(), "Marker should be cleaned up after completion"

    def test_clears_marker_on_failure(self, tmp_path: Path) -> None:
        """Should clear the marker even when subprocess.run raises."""
        prompt = tmp_path / "pulse.md"
        prompt.write_text("crash test")
        op_file = tmp_path / "state" / "active_operation.json"

        with (
            patch("adjutant.lifecycle.cron._find_opencode", return_value="/usr/bin/opencode"),
            patch("subprocess.run", side_effect=OSError("boom")),
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

        def fake_run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[bytes]:
            captured_data.update(json.loads(op_file.read_text()))
            return _mock_run_ok()

        with (
            patch("adjutant.lifecycle.cron._find_opencode", return_value="/usr/bin/opencode"),
            patch("subprocess.run", side_effect=fake_run),
            pytest.raises(SystemExit),
        ):
            run_cron_prompt(
                prompt,
                adj_dir=tmp_path,
                action="review",
                source="mariposa",
            )

        assert captured_data["action"] == "review"
        assert captured_data["source"] == "mariposa"
        assert "started_at" in captured_data
        assert "pid" in captured_data

    def test_raises_if_prompt_missing(self, tmp_path: Path) -> None:
        """Should raise SystemExit(1) when prompt file does not exist."""
        missing = tmp_path / "no_such_prompt.md"
        with pytest.raises(SystemExit) as exc_info:
            run_cron_prompt(missing, adj_dir=tmp_path)
        assert exc_info.value.code == 1

    def test_raises_if_opencode_missing(self, tmp_path: Path) -> None:
        """Should raise SystemExit(1) when opencode is not on PATH."""
        prompt = tmp_path / "pulse.md"
        prompt.write_text("prompt text")

        with patch("shutil.which", return_value=None), pytest.raises(SystemExit) as exc_info:
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

        with (
            patch.dict(os.environ, {"ADJ_DIR": str(tmp_path)}),
            patch("adjutant.lifecycle.cron._find_opencode", return_value="/usr/bin/opencode"),
            patch("subprocess.run", return_value=_mock_run_ok()) as mock_run,
            pytest.raises(SystemExit) as exc_info,
        ):
            run_cron_prompt(prompt, adj_dir=None)

        assert exc_info.value.code == 0
        mock_run.assert_called_once_with(
            ["/usr/bin/opencode", "run", "--dir", str(tmp_path), "env-sourced"],
        )


# ---------------------------------------------------------------------------
# pulse_cron
# ---------------------------------------------------------------------------


class TestPulseCron:
    def test_reads_pulse_md(self, tmp_path: Path) -> None:
        """pulse_cron() should run opencode with prompts/pulse.md."""
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()
        (prompts_dir / "pulse.md").write_text("pulse text")

        with (
            patch("adjutant.lifecycle.cron.init_adj_dir", return_value=tmp_path),
            patch("adjutant.lifecycle.cron._find_opencode", return_value="/usr/bin/opencode"),
            patch("subprocess.run", return_value=_mock_run_ok()) as mock_run,
            pytest.raises(SystemExit) as exc_info,
        ):
            pulse_cron()

        assert exc_info.value.code == 0
        mock_run.assert_called_once_with(
            ["/usr/bin/opencode", "run", "--dir", str(tmp_path), "pulse text"],
        )

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

        with (
            patch("adjutant.lifecycle.cron._find_opencode", return_value="/usr/bin/opencode"),
            patch("subprocess.run", return_value=_mock_run_ok()) as mock_run,
            pytest.raises(SystemExit),
        ):
            pulse_cron(adj_dir=tmp_path)

        mock_run.assert_called_once()

    def test_passes_source_kwarg(self, tmp_path: Path) -> None:
        """pulse_cron(source=...) should pass source to the marker."""
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()
        (prompts_dir / "pulse.md").write_text("source test")
        op_file = tmp_path / "state" / "active_operation.json"

        captured_source = None

        def fake_run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[bytes]:
            nonlocal captured_source
            data = json.loads(op_file.read_text())
            captured_source = data["source"]
            return _mock_run_ok()

        with (
            patch("adjutant.lifecycle.cron._find_opencode", return_value="/usr/bin/opencode"),
            patch("subprocess.run", side_effect=fake_run),
            pytest.raises(SystemExit),
        ):
            pulse_cron(adj_dir=tmp_path, source="mariposa")

        assert captured_source == "mariposa"

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
        """review_cron() should run opencode with prompts/review.md."""
        prompts_dir = tmp_path / "prompts"
        prompts_dir.mkdir()
        (prompts_dir / "review.md").write_text("review text")

        with (
            patch("adjutant.lifecycle.cron.init_adj_dir", return_value=tmp_path),
            patch("adjutant.lifecycle.cron._find_opencode", return_value="/usr/bin/opencode"),
            patch("subprocess.run", return_value=_mock_run_ok()) as mock_run,
            pytest.raises(SystemExit) as exc_info,
        ):
            review_cron()

        assert exc_info.value.code == 0
        mock_run.assert_called_once_with(
            ["/usr/bin/opencode", "run", "--dir", str(tmp_path), "review text"],
        )

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

        with (
            patch("adjutant.lifecycle.cron._find_opencode", return_value="/usr/bin/opencode"),
            patch("subprocess.run", return_value=_mock_run_ok()) as mock_run,
            pytest.raises(SystemExit),
        ):
            review_cron(adj_dir=tmp_path)

        mock_run.assert_called_once()


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
        assert "Pulse completed" in result
        assert "ixda, portfolio" in result
        assert "IxDA: deadline Friday" in result
        assert "Source: cron" in result
        assert "Escalated" not in result

    def test_review_with_escalation(self) -> None:
        data = {
            "kbs_checked": ["portfolio"],
            "issues_found": [],
            "escalated": True,
        }
        result = _format_heartbeat(data, "review", "telegram")
        assert "Review completed" in result
        assert "Escalated" in result
        assert "Source: telegram" in result

    def test_no_issues(self) -> None:
        data = {"kbs_checked": ["ixda"], "issues_found": [], "escalated": False}
        result = _format_heartbeat(data, "pulse", "mariposa")
        assert "Issues:" not in result
        assert "Source: mariposa" in result

    def test_truncates_many_issues(self) -> None:
        data = {
            "kbs_checked": ["ixda"],
            "issues_found": [f"issue {i}" for i in range(12)],
            "escalated": False,
        }
        result = _format_heartbeat(data, "pulse", "cron")
        assert "issue 7" in result  # 8th issue (0-indexed) is included
        assert "issue 8" not in result  # 9th is truncated
        assert "and 4 more" in result

    def test_empty_data(self) -> None:
        result = _format_heartbeat({}, "pulse", "cron")
        assert "Pulse completed" in result
        assert "Source: cron" in result


# ---------------------------------------------------------------------------
# _notify_completion
# ---------------------------------------------------------------------------


class TestNotifyCompletion:
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
        assert "Pulse completed" in msg
        assert "ixda" in msg

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
        """run_cron_prompt should NOT notify when opencode fails."""
        prompt = tmp_path / "pulse.md"
        prompt.write_text("fail test")

        fail_result = subprocess.CompletedProcess(args=[], returncode=1)
        with (
            patch("adjutant.lifecycle.cron._find_opencode", return_value="/usr/bin/opencode"),
            patch("subprocess.run", return_value=fail_result),
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

        with (
            patch("adjutant.lifecycle.cron._find_opencode", return_value="/usr/bin/opencode"),
            patch("subprocess.run", return_value=_mock_run_ok()),
            patch("adjutant.lifecycle.cron._notify_completion") as mock_notify,
            pytest.raises(SystemExit) as exc_info,
        ):
            run_cron_prompt(prompt, adj_dir=tmp_path, action="pulse", source="mariposa")

        assert exc_info.value.code == 0
        mock_notify.assert_called_once_with(tmp_path, "pulse", "mariposa")

    def test_not_called_for_unknown_action(self, tmp_path: Path) -> None:
        """run_cron_prompt should skip notification for action='unknown'."""
        prompt = tmp_path / "test.md"
        prompt.write_text("unknown")

        with (
            patch("adjutant.lifecycle.cron._find_opencode", return_value="/usr/bin/opencode"),
            patch("subprocess.run", return_value=_mock_run_ok()),
            patch("adjutant.lifecycle.cron._notify_completion") as mock_notify,
            pytest.raises(SystemExit),
        ):
            run_cron_prompt(prompt, adj_dir=tmp_path, action="unknown", source="cron")

        mock_notify.assert_not_called()
