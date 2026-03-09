"""Tests for src/adjutant/setup/steps/schedule_wizard.py"""

from __future__ import annotations

import os
import stat
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from adjutant.setup.steps.schedule_wizard import (
    _add_schedule_to_yaml,
    _install_crontab,
    _schedule_exists,
    _validate_cron,
    main,
    schedule_wizard,
)


# ---------------------------------------------------------------------------
# _validate_cron
# ---------------------------------------------------------------------------


class TestValidateCron:
    def test_valid_five_fields(self) -> None:
        assert _validate_cron("0 8 * * 1-5") is True

    def test_valid_with_multiple_spaces(self) -> None:
        assert _validate_cron("*/30  *  *  *  *") is True

    def test_invalid_four_fields(self) -> None:
        assert _validate_cron("0 8 * *") is False

    def test_invalid_six_fields(self) -> None:
        assert _validate_cron("0 8 * * 1 extra") is False

    def test_empty_string(self) -> None:
        assert _validate_cron("") is False


# ---------------------------------------------------------------------------
# _schedule_exists
# ---------------------------------------------------------------------------


class TestScheduleExists:
    def _make_config(self, tmp_path: Path, job_name: str) -> Path:
        cfg = tmp_path / "adjutant.yaml"
        cfg.write_text(f'schedules:\n  - name: "{job_name}"\n    schedule: "0 8 * * 1-5"\n')
        return tmp_path

    def test_returns_true_when_job_exists(self, tmp_path: Path) -> None:
        self._make_config(tmp_path, "portfolio-fetch")
        assert _schedule_exists(tmp_path, "portfolio-fetch") is True

    def test_returns_false_when_job_missing(self, tmp_path: Path) -> None:
        self._make_config(tmp_path, "other-job")
        assert _schedule_exists(tmp_path, "portfolio-fetch") is False

    def test_returns_false_when_no_config(self, tmp_path: Path) -> None:
        assert _schedule_exists(tmp_path, "any-job") is False

    def test_returns_false_when_no_schedules_section(self, tmp_path: Path) -> None:
        cfg = tmp_path / "adjutant.yaml"
        cfg.write_text("instance:\n  name: test\n")
        assert _schedule_exists(tmp_path, "any-job") is False


# ---------------------------------------------------------------------------
# _add_schedule_to_yaml
# ---------------------------------------------------------------------------


class TestAddScheduleToYaml:
    def test_appends_entry_when_schedules_exists(self, tmp_path: Path) -> None:
        cfg = tmp_path / "adjutant.yaml"
        cfg.write_text("instance:\n  name: test\nschedules:\n")

        _add_schedule_to_yaml(
            tmp_path, "my-job", "My job", "0 8 * * *", "/path/script.sh", "state/my-job.log"
        )

        content = cfg.read_text()
        assert 'name: "my-job"' in content
        assert 'description: "My job"' in content
        assert 'schedule: "0 8 * * *"' in content
        assert "enabled: true" in content

    def test_creates_schedules_section_when_missing(self, tmp_path: Path) -> None:
        cfg = tmp_path / "adjutant.yaml"
        cfg.write_text("instance:\n  name: test\n")

        _add_schedule_to_yaml(
            tmp_path, "new-job", "New", "0 9 * * 1-5", "/bin/run.sh", "state/new-job.log"
        )

        content = cfg.read_text()
        assert "schedules:" in content
        assert 'name: "new-job"' in content

    def test_creates_config_when_missing(self, tmp_path: Path) -> None:
        _add_schedule_to_yaml(tmp_path, "job1", "Desc", "* * * * *", "/s.sh", "s.log")
        cfg = tmp_path / "adjutant.yaml"
        assert cfg.is_file()
        assert 'name: "job1"' in cfg.read_text()


# ---------------------------------------------------------------------------
# _install_crontab
# ---------------------------------------------------------------------------


class TestInstallCrontab:
    def test_installs_crontab_entry(self, tmp_path: Path) -> None:
        script = tmp_path / "run.sh"
        script.write_text("#!/bin/bash\necho ok\n")
        log = tmp_path / "run.log"

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            _install_crontab(tmp_path, "test-job", "0 8 * * *", str(script), str(log))

        # Called once to read existing crontab, once to write
        assert mock_run.call_count == 2
        # The write call should pipe the cron line
        write_call_input = mock_run.call_args_list[1][1]["input"]
        assert "adjutant:test-job" in write_call_input

    def test_raises_on_crontab_failure(self, tmp_path: Path) -> None:
        import subprocess

        script = tmp_path / "run.sh"
        script.touch()
        log = tmp_path / "run.log"

        with patch(
            "subprocess.run",
            side_effect=subprocess.CalledProcessError(1, "crontab"),
        ):
            with pytest.raises(RuntimeError, match="crontab install failed"):
                _install_crontab(tmp_path, "job", "0 * * * *", str(script), str(log))


# ---------------------------------------------------------------------------
# main (CLI)
# ---------------------------------------------------------------------------


class TestMain:
    def test_returns_1_when_adj_dir_not_set(self) -> None:
        env = {k: v for k, v in os.environ.items() if k != "ADJ_DIR"}
        with patch.dict(os.environ, env, clear=True):
            rc = main([])
        assert rc == 1

    def test_returns_0_after_wizard(self, tmp_path: Path) -> None:
        with (
            patch.dict(os.environ, {"ADJ_DIR": str(tmp_path)}),
            patch(
                "adjutant.setup.steps.schedule_wizard.schedule_wizard",
                return_value=None,
            ) as mock_wiz,
        ):
            rc = main([])
        assert rc == 0
        mock_wiz.assert_called_once_with(tmp_path)

    def test_returns_1_on_keyboard_interrupt(self, tmp_path: Path) -> None:
        with (
            patch.dict(os.environ, {"ADJ_DIR": str(tmp_path)}),
            patch(
                "adjutant.setup.steps.schedule_wizard.schedule_wizard",
                side_effect=KeyboardInterrupt,
            ),
        ):
            rc = main([])
        assert rc == 1
