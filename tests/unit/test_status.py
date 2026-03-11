"""Unit tests for adjutant.observability.status."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from adjutant.observability.status import (
    _cron_human,
    _format_timestamp,
    _heartbeat_section,
    _notifications_section,
    _actions_section,
    _schedules_section,
    _status_line,
    get_status,
    main,
)


# ---------------------------------------------------------------------------
# _cron_human
# ---------------------------------------------------------------------------


class TestCronHuman:
    def test_every_n_minutes(self):
        assert _cron_human("*/15 * * * *") == "every 15 minutes"

    def test_every_hour_at_minute(self):
        assert _cron_human("30 * * * *") == "every hour at :30"

    def test_specific_time_weekdays(self):
        assert _cron_human("0 9 * * 1-5") == "at 09:00, weekdays"

    def test_specific_time_every_day(self):
        assert _cron_human("0 8 * * *") == "at 08:00, every day"

    def test_multiple_hours(self):
        result = _cron_human("0 9,17 * * 1-5")
        assert "09:00" in result
        assert "17:00" in result
        assert "weekdays" in result

    def test_weekends(self):
        assert "weekends" in _cron_human("0 10 * * 0,6")

    def test_specific_day(self):
        assert "Mondays" in _cron_human("0 9 * * 1")
        assert "Fridays" in _cron_human("0 9 * * 5")
        assert "Sundays" in _cron_human("0 9 * * 0")

    def test_fallback_bad_input(self):
        # Bad expr → returned verbatim
        assert _cron_human("not a cron") == "not a cron"

    def test_fallback_unknown_dow(self):
        result = _cron_human("0 9 * * 2-4")
        assert "dow=2-4" in result


# ---------------------------------------------------------------------------
# _format_timestamp
# ---------------------------------------------------------------------------


class TestFormatTimestamp:
    def test_valid_iso(self):
        result = _format_timestamp("2025-06-15T09:30:00Z")
        assert "09:30" in result
        assert "15" in result

    def test_empty_string(self):
        assert _format_timestamp("") == ""

    def test_invalid(self):
        assert _format_timestamp("not-a-date") == "not-a-date"


# ---------------------------------------------------------------------------
# _status_line
# ---------------------------------------------------------------------------


class TestStatusLine:
    def test_running(self, tmp_path):
        line = _status_line(tmp_path)
        assert "running" in line

    def test_killed(self, tmp_path):
        (tmp_path / "KILLED").touch()
        line = _status_line(tmp_path)
        assert "killed" in line.lower()

    def test_paused(self, tmp_path):
        (tmp_path / "PAUSED").touch()
        line = _status_line(tmp_path)
        assert "paused" in line.lower()

    def test_killed_takes_priority(self, tmp_path):
        (tmp_path / "KILLED").touch()
        (tmp_path / "PAUSED").touch()
        line = _status_line(tmp_path)
        assert "killed" in line.lower()


# ---------------------------------------------------------------------------
# _heartbeat_section
# ---------------------------------------------------------------------------


class TestHeartbeatSection:
    def test_no_file(self, tmp_path):
        (tmp_path / "state").mkdir()
        result = _heartbeat_section(tmp_path)
        assert "No autonomous cycles" in result

    def test_with_file(self, tmp_path):
        state = tmp_path / "state"
        state.mkdir()
        hb = {
            "timestamp": "2025-06-15T09:00:00Z",
            "type": "pulse",
            "trigger": "cron",
            "action": "Reviewed journal",
            "project": "myproject",
        }
        (state / "last_heartbeat.json").write_text(json.dumps(hb))
        result = _heartbeat_section(tmp_path)
        assert "Last cycle ran" in result
        assert "pulse" in result
        assert "cron" in result
        assert "myproject" in result
        assert "Reviewed journal" in result

    def test_partial_file(self, tmp_path):
        state = tmp_path / "state"
        state.mkdir()
        (state / "last_heartbeat.json").write_text(
            json.dumps({"timestamp": "2025-06-15T09:00:00Z"})
        )
        result = _heartbeat_section(tmp_path)
        assert "Last cycle ran" in result

    def test_bad_json(self, tmp_path):
        state = tmp_path / "state"
        state.mkdir()
        (state / "last_heartbeat.json").write_text("{bad json")
        result = _heartbeat_section(tmp_path)
        assert "No autonomous cycles" in result


# ---------------------------------------------------------------------------
# _notifications_section
# ---------------------------------------------------------------------------


class TestNotificationsSection:
    def test_no_count_file(self, tmp_path):
        (tmp_path / "state").mkdir()
        result = _notifications_section(tmp_path)
        assert "No notifications" in result
        assert "3" in result  # default max

    def test_with_count(self, tmp_path):
        from datetime import datetime

        state = tmp_path / "state"
        state.mkdir()
        today = datetime.now().strftime("%Y-%m-%d")
        (state / f"notify_count_{today}.txt").write_text("2")
        result = _notifications_section(tmp_path)
        assert "2 of" in result

    def test_zero_count(self, tmp_path):
        from datetime import datetime

        state = tmp_path / "state"
        state.mkdir()
        today = datetime.now().strftime("%Y-%m-%d")
        (state / f"notify_count_{today}.txt").write_text("0")
        result = _notifications_section(tmp_path)
        assert "No notifications" in result


# ---------------------------------------------------------------------------
# _actions_section
# ---------------------------------------------------------------------------


class TestActionsSection:
    def test_no_file(self, tmp_path):
        (tmp_path / "state").mkdir()
        assert _actions_section(tmp_path) == ""

    def test_with_actions(self, tmp_path):
        state = tmp_path / "state"
        state.mkdir()
        actions = [
            {"ts": "2025-06-15T09:00:00Z", "type": "pulse", "agent": "main"},
            {"ts": "2025-06-15T10:00:00Z", "type": "reply"},
        ]
        (state / "actions.jsonl").write_text("\n".join(json.dumps(a) for a in actions) + "\n")
        result = _actions_section(tmp_path)
        assert "Recent actions:" in result
        assert "pulse" in result
        assert "main" in result
        assert "reply" in result

    def test_last_5_only(self, tmp_path):
        state = tmp_path / "state"
        state.mkdir()
        actions = [{"ts": f"2025-06-15T0{i}:00:00Z", "type": f"action_{i}"} for i in range(8)]
        (state / "actions.jsonl").write_text("\n".join(json.dumps(a) for a in actions) + "\n")
        result = _actions_section(tmp_path)
        # action_0, action_1, action_2 should not appear (only last 5)
        assert "action_0" not in result
        assert "action_7" in result

    def test_empty_file(self, tmp_path):
        state = tmp_path / "state"
        state.mkdir()
        (state / "actions.jsonl").write_text("")
        assert _actions_section(tmp_path) == ""


# ---------------------------------------------------------------------------
# _schedules_section
# ---------------------------------------------------------------------------


class TestSchedulesSection:
    def test_no_schedules(self, tmp_path, monkeypatch):
        def _fake_load(adj_dir):
            return []

        monkeypatch.setattr("adjutant.observability.status._load_schedules", _fake_load)
        result = _schedules_section(tmp_path)
        assert "No scheduled jobs" in result

    def test_active_schedule(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "adjutant.observability.status._load_schedules",
            lambda d: [
                {
                    "name": "daily",
                    "description": "Daily digest",
                    "schedule": "0 8 * * *",
                    "enabled": True,
                    "notify": False,
                }
            ],
        )
        monkeypatch.setattr(
            "adjutant.observability.status._live_crontab",
            lambda: "# adjutant:daily\n0 8 * * * some-script",
        )
        result = _schedules_section(tmp_path)
        assert "Active jobs:" in result
        assert "daily" in result

    def test_inactive_disabled(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "adjutant.observability.status._load_schedules",
            lambda d: [
                {
                    "name": "weekly",
                    "description": "Weekly thing",
                    "schedule": "0 9 * * 1",
                    "enabled": False,
                    "notify": False,
                }
            ],
        )
        result = _schedules_section(tmp_path)
        assert "Inactive jobs:" in result
        assert "[disabled]" in result

    def test_not_in_crontab(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "adjutant.observability.status._load_schedules",
            lambda d: [
                {
                    "name": "missing",
                    "description": "Missing job",
                    "schedule": "0 9 * * *",
                    "enabled": True,
                    "notify": False,
                }
            ],
        )
        monkeypatch.setattr(
            "adjutant.observability.status._live_crontab",
            lambda: "",  # empty crontab
        )
        result = _schedules_section(tmp_path)
        assert "[not in crontab]" in result


# ---------------------------------------------------------------------------
# get_status integration
# ---------------------------------------------------------------------------


class TestGetStatus:
    def test_returns_string(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ADJ_DIR", str(tmp_path))
        (tmp_path / "state").mkdir()
        monkeypatch.setattr("adjutant.observability.status._load_schedules", lambda d: [])
        result = get_status(tmp_path)
        assert isinstance(result, str)
        assert (
            "running" in result.lower() or "killed" in result.lower() or "paused" in result.lower()
        )

    def test_missing_adj_dir_raises(self, monkeypatch):
        monkeypatch.delenv("ADJ_DIR", raising=False)
        with pytest.raises(RuntimeError):
            get_status()


# ---------------------------------------------------------------------------
# main()
# ---------------------------------------------------------------------------


class TestMain:
    def test_main_success(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setenv("ADJ_DIR", str(tmp_path))
        (tmp_path / "state").mkdir()
        monkeypatch.setattr("adjutant.observability.status._load_schedules", lambda d: [])
        rc = main()
        assert rc == 0
        out = capsys.readouterr().out
        assert len(out) > 0

    def test_main_no_adj_dir(self, monkeypatch, capsys):
        monkeypatch.delenv("ADJ_DIR", raising=False)
        rc = main()
        assert rc == 1
