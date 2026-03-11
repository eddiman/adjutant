"""Tests for adjutant.core.paths — ADJ_DIR resolution."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from adjutant.core.paths import (
    AdjutantDirNotFoundError,
    _walk_up_for,
    get_adj_dir,
    init_adj_dir,
    resolve_adj_dir,
)


class TestResolveAdjDir:
    """Test resolve_adj_dir() resolution chain."""

    def test_adjutant_home_override(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """ADJUTANT_HOME env var takes priority over everything."""
        adj = tmp_path / "my-adjutant"
        adj.mkdir()
        monkeypatch.setenv("ADJUTANT_HOME", str(adj))
        assert resolve_adj_dir() == adj

    def test_adjutant_home_nonexistent_raises(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """ADJUTANT_HOME pointing to nonexistent dir raises."""
        monkeypatch.setenv("ADJUTANT_HOME", str(tmp_path / "nope"))
        with pytest.raises(AdjutantDirNotFoundError, match="non-existent"):
            resolve_adj_dir()

    def test_walk_up_adjutant_root_marker(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Walk up finds .adjutant-root marker file."""
        monkeypatch.delenv("ADJUTANT_HOME", raising=False)
        root = tmp_path / "project"
        root.mkdir()
        (root / ".adjutant-root").touch()
        nested = root / "scripts" / "common"
        nested.mkdir(parents=True)
        assert resolve_adj_dir(start_dir=nested) == root

    def test_walk_up_adjutant_yaml_legacy(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Walk up finds adjutant.yaml as legacy fallback."""
        monkeypatch.delenv("ADJUTANT_HOME", raising=False)
        root = tmp_path / "project"
        root.mkdir()
        (root / "adjutant.yaml").write_text("instance:\n  name: test\n")
        nested = root / "scripts" / "common"
        nested.mkdir(parents=True)
        assert resolve_adj_dir(start_dir=nested) == root

    def test_adjutant_root_takes_priority_over_yaml(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """.adjutant-root is preferred over adjutant.yaml."""
        monkeypatch.delenv("ADJUTANT_HOME", raising=False)
        root = tmp_path / "project"
        root.mkdir()
        (root / ".adjutant-root").touch()
        (root / "adjutant.yaml").write_text("test: true\n")
        assert resolve_adj_dir(start_dir=root) == root

    def test_home_fallback(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Falls back to ~/.adjutant if it exists."""
        monkeypatch.delenv("ADJUTANT_HOME", raising=False)
        home_adj = tmp_path / "fakehome" / ".adjutant"
        home_adj.mkdir(parents=True)
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "fakehome"))
        # Start from a dir with no markers
        start = tmp_path / "nowhere"
        start.mkdir()
        assert resolve_adj_dir(start_dir=start) == home_adj

    def test_no_dir_found_raises(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Raises when no adjutant dir can be found."""
        monkeypatch.delenv("ADJUTANT_HOME", raising=False)
        # Point home to empty dir (no ~/.adjutant)
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "empty"))
        (tmp_path / "empty").mkdir()
        start = tmp_path / "start"
        start.mkdir()
        with pytest.raises(AdjutantDirNotFoundError):
            resolve_adj_dir(start_dir=start)

    def test_spaces_in_path(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Handles paths with spaces."""
        adj = tmp_path / "my project" / "adjutant dir"
        adj.mkdir(parents=True)
        monkeypatch.setenv("ADJUTANT_HOME", str(adj))
        assert resolve_adj_dir() == adj


class TestInitAndGetAdjDir:
    """Test init_adj_dir() and get_adj_dir()."""

    def test_init_exports_to_environ(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """init_adj_dir sets both ADJ_DIR and ADJUTANT_DIR in os.environ."""
        adj = tmp_path / ".adjutant"
        adj.mkdir()
        monkeypatch.setenv("ADJUTANT_HOME", str(adj))
        monkeypatch.delenv("ADJ_DIR", raising=False)
        monkeypatch.delenv("ADJUTANT_DIR", raising=False)

        result = init_adj_dir()
        assert result == adj
        assert os.environ["ADJ_DIR"] == str(adj)
        assert os.environ["ADJUTANT_DIR"] == str(adj)

    def test_get_adj_dir_after_init(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """get_adj_dir() returns the path set by init_adj_dir()."""
        adj = tmp_path / ".adjutant"
        adj.mkdir()
        monkeypatch.setenv("ADJUTANT_HOME", str(adj))
        init_adj_dir()
        assert get_adj_dir() == adj

    def test_get_adj_dir_without_init_raises(self, monkeypatch: pytest.MonkeyPatch):
        """get_adj_dir() raises if ADJ_DIR is not set."""
        monkeypatch.delenv("ADJ_DIR", raising=False)
        with pytest.raises(AdjutantDirNotFoundError, match="not set"):
            get_adj_dir()


class TestWalkUpFor:
    """Test the _walk_up_for helper."""

    def test_finds_marker_in_current_dir(self, tmp_path: Path):
        (tmp_path / "marker.txt").touch()
        assert _walk_up_for(tmp_path, "marker.txt") == tmp_path

    def test_finds_marker_in_parent(self, tmp_path: Path):
        (tmp_path / "marker.txt").touch()
        child = tmp_path / "a" / "b" / "c"
        child.mkdir(parents=True)
        assert _walk_up_for(child, "marker.txt") == tmp_path

    def test_returns_none_when_not_found(self, tmp_path: Path):
        assert _walk_up_for(tmp_path, "nonexistent-marker") is None
