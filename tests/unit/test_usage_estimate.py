"""Unit tests for adjutant.observability.usage_estimate."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from adjutant.observability.usage_estimate import (
    _compute_cost,
    _sum_tokens_since,
    format_report,
    log_usage,
    main,
)


# ---------------------------------------------------------------------------
# _compute_cost
# ---------------------------------------------------------------------------


class TestComputeCost:
    def test_sonnet(self):
        # 1M input at $3 → $3; 1M output at $15 → $15; total $18
        cost = _compute_cost(1_000_000, 1_000_000, "sonnet")
        assert abs(cost - 18.0) < 1e-6

    def test_opus(self):
        # 1M input at $5 → $5; 1M output at $25 → $25; total $30
        cost = _compute_cost(1_000_000, 1_000_000, "opus")
        assert abs(cost - 30.0) < 1e-6

    def test_zero_tokens(self):
        assert _compute_cost(0, 0, "sonnet") == 0.0

    def test_unknown_model_defaults_to_sonnet(self):
        cost_unknown = _compute_cost(1000, 500, "unknown_model")
        cost_sonnet = _compute_cost(1000, 500, "sonnet")
        assert abs(cost_unknown - cost_sonnet) < 1e-9

    def test_small_operation(self):
        # 3000 input + 500 output sonnet
        cost = _compute_cost(3000, 500, "sonnet")
        expected = (3000 * 3 + 500 * 15) / 1_000_000
        assert abs(cost - expected) < 1e-9


# ---------------------------------------------------------------------------
# _sum_tokens_since
# ---------------------------------------------------------------------------


class TestSumTokensSince:
    def test_empty_file(self, tmp_path):
        log = tmp_path / "usage_log.jsonl"
        log.write_text("")
        assert _sum_tokens_since(log, "2000-01-01T00:00:00Z") == 0

    def test_missing_file(self, tmp_path):
        assert _sum_tokens_since(tmp_path / "no.jsonl", "2000-01-01T00:00:00Z") == 0

    def test_all_in_window(self, tmp_path):
        log = tmp_path / "usage_log.jsonl"
        entries = [
            {"timestamp": "2025-06-15T10:00:00Z", "total": 1000},
            {"timestamp": "2025-06-15T11:00:00Z", "total": 2000},
        ]
        log.write_text("\n".join(json.dumps(e) for e in entries) + "\n")
        assert _sum_tokens_since(log, "2025-06-15T09:00:00Z") == 3000

    def test_some_before_window(self, tmp_path):
        log = tmp_path / "usage_log.jsonl"
        entries = [
            {"timestamp": "2025-06-14T10:00:00Z", "total": 500},  # before
            {"timestamp": "2025-06-15T10:00:00Z", "total": 1500},  # in window
        ]
        log.write_text("\n".join(json.dumps(e) for e in entries) + "\n")
        assert _sum_tokens_since(log, "2025-06-15T00:00:00Z") == 1500

    def test_bad_json_line_skipped(self, tmp_path):
        log = tmp_path / "usage_log.jsonl"
        log.write_text('{"timestamp":"2025-06-15T10:00:00Z","total":100}\n{bad json}\n')
        assert _sum_tokens_since(log, "2025-01-01T00:00:00Z") == 100


# ---------------------------------------------------------------------------
# log_usage
# ---------------------------------------------------------------------------


class TestLogUsage:
    def test_creates_log_file(self, tmp_path):
        (tmp_path / "state").mkdir()
        with patch(
            "adjutant.observability.usage_estimate._window_start",
            return_value="2000-01-01T00:00:00Z",
        ):
            result = log_usage("test_op", 1000, 500, adj_dir=tmp_path)

        log_path = tmp_path / "state" / "usage_log.jsonl"
        assert log_path.exists()
        line = json.loads(log_path.read_text().strip())
        assert line["operation"] == "test_op"
        assert line["input"] == 1000
        assert line["output"] == 500
        assert line["total"] == 1500
        assert "timestamp" in line
        assert "cost_equiv" in line

    def test_returns_summary(self, tmp_path):
        (tmp_path / "state").mkdir()
        with patch(
            "adjutant.observability.usage_estimate._window_start",
            return_value="2000-01-01T00:00:00Z",
        ):
            result = log_usage("pulse", 3000, 500, model="sonnet", adj_dir=tmp_path)

        assert result["operation"] == "pulse"
        assert result["total"] == 3500
        assert result["session_total"] == 3500
        assert result["week_total"] == 3500
        assert isinstance(result["session_pct"], float)
        assert isinstance(result["cost"], float)

    def test_appends_to_existing(self, tmp_path):
        state = tmp_path / "state"
        state.mkdir()
        log_path = state / "usage_log.jsonl"
        log_path.write_text(
            json.dumps(
                {
                    "timestamp": "2025-01-01T00:00:00Z",
                    "operation": "old",
                    "model": "sonnet",
                    "input": 100,
                    "output": 50,
                    "total": 150,
                    "cost_equiv": 0.0,
                }
            )
            + "\n"
        )
        with patch(
            "adjutant.observability.usage_estimate._window_start",
            return_value="2000-01-01T00:00:00Z",
        ):
            log_usage("new_op", 200, 100, adj_dir=tmp_path)
        lines = log_path.read_text().strip().split("\n")
        assert len(lines) == 2

    def test_missing_adj_dir_raises(self, monkeypatch):
        monkeypatch.delenv("ADJ_DIR", raising=False)
        with pytest.raises(RuntimeError):
            log_usage("test", 100, 50)

    def test_opus_model(self, tmp_path):
        (tmp_path / "state").mkdir()
        with patch(
            "adjutant.observability.usage_estimate._window_start",
            return_value="2000-01-01T00:00:00Z",
        ):
            result = log_usage("reflect", 15000, 2000, model="opus", adj_dir=tmp_path)

        log_path = tmp_path / "state" / "usage_log.jsonl"
        entry = json.loads(log_path.read_text().strip())
        assert entry["model"] == "opus"
        expected_cost = (15000 * 5 + 2000 * 25) / 1_000_000
        assert abs(entry["cost_equiv"] - round(expected_cost, 4)) < 1e-9


# ---------------------------------------------------------------------------
# format_report
# ---------------------------------------------------------------------------


class TestFormatReport:
    def _make_summary(self, session_pct=10.0):
        return {
            "operation": "pulse",
            "model": "sonnet",
            "input": 3000,
            "output": 500,
            "total": 3500,
            "cost": 0.0165,
            "session_total": int(44000 * session_pct / 100),
            "session_cap": 44000,
            "session_pct": session_pct,
            "week_total": 10000,
            "week_cap": 350000,
            "week_pct": 2.9,
        }

    def test_contains_operation(self):
        report = format_report(self._make_summary(), colour=False)
        assert "pulse" in report
        assert "3500" in report

    def test_healthy_message(self):
        report = format_report(self._make_summary(10.0), colour=False)
        assert "healthy" in report

    def test_moderate_message(self):
        report = format_report(self._make_summary(60.0), colour=False)
        assert "moderate" in report

    def test_approaching_message(self):
        report = format_report(self._make_summary(85.0), colour=False)
        assert "approaching" in report.lower() or "slow down" in report.lower()

    def test_colour_disabled(self):
        report = format_report(self._make_summary(), colour=False)
        assert "\033[" not in report

    def test_colour_enabled(self):
        report = format_report(self._make_summary(), colour=True)
        assert "\033[" in report


# ---------------------------------------------------------------------------
# main()
# ---------------------------------------------------------------------------


class TestMain:
    def test_no_args_shows_usage(self, capsys):
        rc = main(["prog"])
        assert rc == 1
        out = capsys.readouterr().out
        assert "Usage:" in out

    def test_zero_input_shows_usage(self, capsys):
        rc = main(["prog", "test", "0", "500"])
        assert rc == 1

    def test_valid_invocation(self, tmp_path, monkeypatch, capsys):
        (tmp_path / "state").mkdir()
        monkeypatch.setenv("ADJ_DIR", str(tmp_path))
        with patch(
            "adjutant.observability.usage_estimate._window_start",
            return_value="2000-01-01T00:00:00Z",
        ):
            rc = main(["prog", "pulse", "3000", "500"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "pulse" in out or "3500" in out

    def test_opus_model_arg(self, tmp_path, monkeypatch, capsys):
        (tmp_path / "state").mkdir()
        monkeypatch.setenv("ADJ_DIR", str(tmp_path))
        with patch(
            "adjutant.observability.usage_estimate._window_start",
            return_value="2000-01-01T00:00:00Z",
        ):
            rc = main(["prog", "reflect", "15000", "2000", "opus"])
        assert rc == 0

    def test_missing_adj_dir(self, monkeypatch, capsys):
        monkeypatch.delenv("ADJ_DIR", raising=False)
        rc = main(["prog", "test", "1000", "500"])
        assert rc == 1
