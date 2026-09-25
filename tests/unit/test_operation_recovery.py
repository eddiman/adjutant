"""Tests for bounded cleanup after expired operation leases."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from adjutant.operations.recovery import _terminate_owned_process


def test_terminates_only_matching_owned_process_group() -> None:
    process = MagicMock()
    process.create_time.return_value = 123.0
    process.cmdline.return_value = ["/usr/bin/opencode", "run"]
    process.wait.return_value = 0

    with (
        patch("adjutant.operations.recovery.psutil.Process", return_value=process),
        patch("adjutant.operations.recovery.os.getpgrp", return_value=50),
        patch("adjutant.operations.recovery.os.killpg") as killpg,
    ):
        stopped = _terminate_owned_process(
            100,
            123.0,
            process_group_id=100,
            expected_terms=("opencode",),
        )

    assert stopped is True
    killpg.assert_called_once()
    process.wait.assert_called_once_with(timeout=2)


def test_refuses_reused_pid_or_unexpected_command() -> None:
    reused = MagicMock()
    reused.create_time.return_value = 999.0
    reused.cmdline.return_value = ["/usr/bin/opencode", "run"]
    unrelated = MagicMock()
    unrelated.create_time.return_value = 123.0
    unrelated.cmdline.return_value = ["/usr/bin/python", "service.py"]

    with patch(
        "adjutant.operations.recovery.psutil.Process",
        side_effect=[reused, unrelated],
    ):
        reused_stopped = _terminate_owned_process(
            100,
            123.0,
            process_group_id=100,
            expected_terms=("opencode",),
        )
        unrelated_stopped = _terminate_owned_process(
            101,
            123.0,
            process_group_id=101,
            expected_terms=("opencode",),
        )

    assert reused_stopped is False
    assert unrelated_stopped is False
    reused.terminate.assert_not_called()
    unrelated.terminate.assert_not_called()
