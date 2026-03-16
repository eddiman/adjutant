"""Unit tests for adjutant.capabilities.schedule.manage."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from adjutant.capabilities.schedule.manage import (
    _load_yaml_raw,
    _save_yaml_raw,
    _get_schedules,
    _resolve_path,
    resolve_command,
    _schedule_append,
    schedule_count,
    schedule_exists,
    schedule_list,
    schedule_get,
    schedule_get_field,
    schedule_add,
    schedule_remove,
    schedule_set_enabled,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_config(config_path: Path, schedules: list[dict]) -> None:
    """Write a minimal adjutant.yaml with given schedules."""
    import yaml

    config_path.parent.mkdir(parents=True, exist_ok=True)
    data = {"schedules": schedules}
    with open(config_path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)


def _config_path(adj_dir: Path) -> Path:
    return adj_dir / "adjutant.yaml"


# ---------------------------------------------------------------------------
# _load_yaml_raw / _save_yaml_raw
# ---------------------------------------------------------------------------


class TestLoadYamlRaw:
    def test_returns_empty_dict_when_missing(self, tmp_path: Path) -> None:
        result = _load_yaml_raw(tmp_path / "missing.yaml")
        assert result == {}

    def test_loads_valid_yaml(self, tmp_path: Path) -> None:
        path = tmp_path / "conf.yaml"
        path.write_text("key: value\n")
        assert _load_yaml_raw(path) == {"key": "value"}

    def test_returns_empty_dict_on_invalid_yaml(self, tmp_path: Path) -> None:
        path = tmp_path / "conf.yaml"
        path.write_text(": invalid: yaml: [\n")
        result = _load_yaml_raw(path)
        assert result == {}


class TestSaveYamlRaw:
    def test_writes_yaml(self, tmp_path: Path) -> None:
        path = tmp_path / "conf.yaml"
        _save_yaml_raw(path, {"foo": "bar"})
        content = path.read_text()
        assert "foo" in content
        assert "bar" in content

    def test_round_trips_schedules(self, tmp_path: Path) -> None:
        path = tmp_path / "conf.yaml"
        original = {"schedules": [{"name": "job1", "schedule": "0 9 * * *", "enabled": True}]}
        _save_yaml_raw(path, original)
        loaded = _load_yaml_raw(path)
        assert loaded["schedules"][0]["name"] == "job1"


# ---------------------------------------------------------------------------
# _get_schedules
# ---------------------------------------------------------------------------


class TestGetSchedules:
    def test_returns_empty_when_no_schedules_key(self) -> None:
        assert _get_schedules({}) == []

    def test_returns_empty_when_schedules_is_not_list(self) -> None:
        assert _get_schedules({"schedules": "bad"}) == []

    def test_filters_non_dicts(self) -> None:
        result = _get_schedules({"schedules": [{"name": "a"}, "bad", None]})
        assert len(result) == 1
        assert result[0]["name"] == "a"


# ---------------------------------------------------------------------------
# _resolve_path
# ---------------------------------------------------------------------------


class TestResolvePath:
    def test_absolute_path_unchanged(self, tmp_path: Path) -> None:
        assert _resolve_path("/abs/path", tmp_path) == "/abs/path"

    def test_relative_path_prepended(self, tmp_path: Path) -> None:
        result = _resolve_path("scripts/run.sh", tmp_path)
        assert result == str(tmp_path / "scripts/run.sh")


# ---------------------------------------------------------------------------
# resolve_command
# ---------------------------------------------------------------------------


class TestResolveCommand:
    def test_resolves_script(self, tmp_path: Path) -> None:
        entry = {"script": "/path/to/run.sh"}
        assert resolve_command(entry, tmp_path) == "/path/to/run.sh"

    def test_resolves_kb_command(self, tmp_path: Path) -> None:
        entry = {"kb_name": "mydb", "kb_operation": "fetch"}
        result = resolve_command(entry, tmp_path)
        # Should use Python CLI: python -m adjutant kb run <name> <op>
        assert "adjutant" in result
        assert "kb" in result
        assert "run" in result
        assert "mydb" in result
        assert "fetch" in result

    def test_returns_empty_when_no_command(self, tmp_path: Path) -> None:
        assert resolve_command({}, tmp_path) == ""


# ---------------------------------------------------------------------------
# Query API
# ---------------------------------------------------------------------------


class TestScheduleCount:
    def test_zero_when_no_config(self, tmp_path: Path) -> None:
        assert schedule_count(tmp_path / "missing.yaml") == 0

    def test_counts_entries(self, tmp_path: Path) -> None:
        cfg = _config_path(tmp_path)
        _write_config(
            cfg,
            [
                {"name": "job1", "schedule": "* * * * *"},
                {"name": "job2", "schedule": "* * * * *"},
            ],
        )
        assert schedule_count(cfg) == 2


class TestScheduleExists:
    def test_returns_false_when_not_found(self, tmp_path: Path) -> None:
        cfg = _config_path(tmp_path)
        _write_config(cfg, [])
        assert schedule_exists(cfg, "ghost") is False

    def test_returns_true_when_found(self, tmp_path: Path) -> None:
        cfg = _config_path(tmp_path)
        _write_config(cfg, [{"name": "job1"}])
        assert schedule_exists(cfg, "job1") is True


class TestScheduleList:
    def test_returns_all_entries(self, tmp_path: Path) -> None:
        cfg = _config_path(tmp_path)
        _write_config(cfg, [{"name": "a"}, {"name": "b"}])
        entries = schedule_list(cfg)
        assert len(entries) == 2
        assert {e["name"] for e in entries} == {"a", "b"}


class TestScheduleGet:
    def test_returns_entry(self, tmp_path: Path) -> None:
        cfg = _config_path(tmp_path)
        _write_config(cfg, [{"name": "job1", "schedule": "0 9 * * *"}])
        entry = schedule_get(cfg, "job1")
        assert entry is not None
        assert entry["schedule"] == "0 9 * * *"

    def test_returns_none_when_not_found(self, tmp_path: Path) -> None:
        cfg = _config_path(tmp_path)
        _write_config(cfg, [])
        assert schedule_get(cfg, "ghost") is None


class TestScheduleGetField:
    def test_returns_field_value(self, tmp_path: Path) -> None:
        cfg = _config_path(tmp_path)
        _write_config(cfg, [{"name": "job1", "schedule": "0 9 * * *"}])
        assert schedule_get_field(cfg, "job1", "schedule") == "0 9 * * *"

    def test_returns_empty_when_not_found(self, tmp_path: Path) -> None:
        cfg = _config_path(tmp_path)
        _write_config(cfg, [])
        assert schedule_get_field(cfg, "ghost", "schedule") == ""

    def test_returns_empty_for_missing_field(self, tmp_path: Path) -> None:
        cfg = _config_path(tmp_path)
        _write_config(cfg, [{"name": "job1"}])
        assert schedule_get_field(cfg, "job1", "nonexistent") == ""


# ---------------------------------------------------------------------------
# _schedule_append
# ---------------------------------------------------------------------------


class TestScheduleAppend:
    def test_appends_to_empty_config(self, tmp_path: Path) -> None:
        cfg = _config_path(tmp_path)
        cfg.parent.mkdir(parents=True, exist_ok=True)
        cfg.write_text("other: data\n")
        _schedule_append(cfg, "job1", "Test job", "0 9 * * *", "/scripts/run.sh")
        data = _load_yaml_raw(cfg)
        assert len(data["schedules"]) == 1
        assert data["schedules"][0]["name"] == "job1"

    def test_appends_to_existing_schedules(self, tmp_path: Path) -> None:
        cfg = _config_path(tmp_path)
        _write_config(cfg, [{"name": "existing"}])
        _schedule_append(cfg, "new-job", "New", "* * * * *", "/scripts/new.sh")
        data = _load_yaml_raw(cfg)
        assert len(data["schedules"]) == 2

    def test_default_logpath(self, tmp_path: Path) -> None:
        cfg = _config_path(tmp_path)
        cfg.parent.mkdir(parents=True, exist_ok=True)
        _schedule_append(cfg, "job1", "desc", "* * * * *", "/run.sh")
        data = _load_yaml_raw(cfg)
        assert data["schedules"][0]["log"] == "state/job1.log"

    def test_preserves_other_top_level_keys(self, tmp_path: Path) -> None:
        cfg = _config_path(tmp_path)
        cfg.parent.mkdir(parents=True, exist_ok=True)
        cfg.write_text("telegram:\n  token: abc\n")
        _schedule_append(cfg, "job1", "desc", "* * * * *", "/run.sh")
        data = _load_yaml_raw(cfg)
        assert data.get("telegram", {}).get("token") == "abc"


# ---------------------------------------------------------------------------
# schedule_add
# ---------------------------------------------------------------------------


class TestScheduleAdd:
    def test_adds_job(self, tmp_path: Path) -> None:
        cfg = _config_path(tmp_path)
        cfg.parent.mkdir(parents=True, exist_ok=True)
        schedule_add(cfg, "job1", "Test job", "0 9 * * *", "/scripts/run.sh")
        assert schedule_exists(cfg, "job1")

    def test_raises_on_invalid_name(self, tmp_path: Path) -> None:
        cfg = _config_path(tmp_path)
        cfg.parent.mkdir(parents=True, exist_ok=True)
        with pytest.raises(ValueError, match="lowercase"):
            schedule_add(cfg, "My Job!", "desc", "* * * * *", "/run.sh")

    def test_raises_if_already_exists(self, tmp_path: Path) -> None:
        cfg = _config_path(tmp_path)
        _write_config(cfg, [{"name": "job1"}])
        with pytest.raises(ValueError, match="already registered"):
            schedule_add(cfg, "job1", "desc", "* * * * *", "/run.sh")

    def test_calls_install_one_when_adj_dir_given(self, tmp_path: Path) -> None:
        cfg = _config_path(tmp_path)
        cfg.parent.mkdir(parents=True, exist_ok=True)
        with patch("adjutant.capabilities.schedule.install.install_one") as mock_install:
            schedule_add(
                cfg,
                "job1",
                "desc",
                "* * * * *",
                "/run.sh",
                adj_dir=tmp_path,
            )
        mock_install.assert_called_once_with(tmp_path, "job1")

    def test_does_not_call_install_without_adj_dir(self, tmp_path: Path) -> None:
        cfg = _config_path(tmp_path)
        cfg.parent.mkdir(parents=True, exist_ok=True)
        with patch("adjutant.capabilities.schedule.install.install_one") as mock_install:
            schedule_add(cfg, "job1", "desc", "* * * * *", "/run.sh")
        mock_install.assert_not_called()


# ---------------------------------------------------------------------------
# schedule_remove
# ---------------------------------------------------------------------------


class TestScheduleRemove:
    def test_removes_job(self, tmp_path: Path) -> None:
        cfg = _config_path(tmp_path)
        _write_config(cfg, [{"name": "job1"}, {"name": "job2"}])
        schedule_remove(cfg, "job1")
        assert not schedule_exists(cfg, "job1")
        assert schedule_exists(cfg, "job2")

    def test_raises_when_not_found(self, tmp_path: Path) -> None:
        cfg = _config_path(tmp_path)
        _write_config(cfg, [])
        with pytest.raises(ValueError, match="not found"):
            schedule_remove(cfg, "ghost")

    def test_calls_uninstall_when_adj_dir_given(self, tmp_path: Path) -> None:
        cfg = _config_path(tmp_path)
        _write_config(cfg, [{"name": "job1"}])
        with patch("adjutant.capabilities.schedule.install.uninstall_one") as mock_uninstall:
            schedule_remove(cfg, "job1", adj_dir=tmp_path)
        mock_uninstall.assert_called_once_with(tmp_path, "job1")


# ---------------------------------------------------------------------------
# schedule_set_enabled
# ---------------------------------------------------------------------------


class TestScheduleSetEnabled:
    def test_enables_job(self, tmp_path: Path) -> None:
        cfg = _config_path(tmp_path)
        _write_config(cfg, [{"name": "job1", "enabled": False}])
        schedule_set_enabled(cfg, "job1", True)
        entry = schedule_get(cfg, "job1")
        assert entry["enabled"] is True

    def test_disables_job(self, tmp_path: Path) -> None:
        cfg = _config_path(tmp_path)
        _write_config(cfg, [{"name": "job1", "enabled": True}])
        schedule_set_enabled(cfg, "job1", False)
        entry = schedule_get(cfg, "job1")
        assert entry["enabled"] is False

    def test_raises_when_not_found(self, tmp_path: Path) -> None:
        cfg = _config_path(tmp_path)
        _write_config(cfg, [])
        with pytest.raises(ValueError, match="not found"):
            schedule_set_enabled(cfg, "ghost", True)

    def test_calls_install_when_enabling_with_adj_dir(self, tmp_path: Path) -> None:
        cfg = _config_path(tmp_path)
        _write_config(cfg, [{"name": "job1", "enabled": False, "script": "/run.sh"}])
        with patch("adjutant.capabilities.schedule.install.install_one") as mock_install:
            schedule_set_enabled(cfg, "job1", True, adj_dir=tmp_path)
        mock_install.assert_called_once_with(tmp_path, "job1")

    def test_calls_uninstall_when_disabling_with_adj_dir(self, tmp_path: Path) -> None:
        cfg = _config_path(tmp_path)
        _write_config(cfg, [{"name": "job1", "enabled": True, "script": "/run.sh"}])
        with patch("adjutant.capabilities.schedule.install.uninstall_one") as mock_uninstall:
            schedule_set_enabled(cfg, "job1", False, adj_dir=tmp_path)
        mock_uninstall.assert_called_once_with(tmp_path, "job1")
