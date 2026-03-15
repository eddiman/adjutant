"""Tests for src/adjutant/lifecycle/update.py"""

from __future__ import annotations

import tarfile
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from adjutant.lifecycle.update import (
    _parse_version,
    semver_lt,
    get_current_version,
    get_latest_version,
    backup_current,
    _should_exclude,
    download_and_apply,
    update,
)


class TestSemver:
    def test_lt_basic(self) -> None:
        assert semver_lt("1.0.0", "1.0.1") is True
        assert semver_lt("1.0.0", "1.0.0") is False
        assert semver_lt("2.0.0", "1.9.9") is False

    def test_strips_v_prefix(self) -> None:
        assert semver_lt("v1.0.0", "v1.1.0") is True
        assert semver_lt("v2.0.0", "v1.9.9") is False

    def test_minor_and_patch(self) -> None:
        assert semver_lt("1.2.3", "1.2.4") is True
        assert semver_lt("1.3.0", "1.2.9") is False

    def test_parse_partial(self) -> None:
        assert _parse_version("1.0") == (1, 0, 0)
        assert _parse_version("2") == (2, 0, 0)


class TestGetCurrentVersion:
    def test_reads_version_file(self, tmp_path: Path) -> None:
        (tmp_path / "VERSION").write_text("v1.2.3\n")
        assert get_current_version(tmp_path) == "v1.2.3"

    def test_returns_unknown_when_missing(self, tmp_path: Path) -> None:
        assert get_current_version(tmp_path) == "unknown"

    def test_strips_whitespace(self, tmp_path: Path) -> None:
        (tmp_path / "VERSION").write_text("  v2.0.0  \n")
        assert get_current_version(tmp_path) == "v2.0.0"


class TestGetLatestVersion:
    def test_returns_tag_name(self) -> None:
        mock_client = MagicMock()
        mock_client.get.return_value = {"tag_name": "v3.0.0"}

        with patch("adjutant.lib.http.get_client", return_value=mock_client):
            result = get_latest_version("owner/repo")

        assert result == "v3.0.0"

    def test_raises_on_no_tag(self) -> None:
        mock_client = MagicMock()
        mock_client.get.return_value = {}

        with (
            patch("adjutant.lib.http.get_client", return_value=mock_client),
            pytest.raises(RuntimeError, match="No releases found"),
        ):
            get_latest_version("owner/repo")

    def test_raises_on_api_failure(self) -> None:
        mock_client = MagicMock()
        mock_client.get.side_effect = Exception("network error")

        with (
            patch("adjutant.lib.http.get_client", return_value=mock_client),
            pytest.raises(RuntimeError, match="Could not reach GitHub API"),
        ):
            get_latest_version("owner/repo")


class TestBackupCurrent:
    def test_copies_existing_dirs(self, tmp_path: Path) -> None:
        adj_dir = tmp_path
        (adj_dir / "scripts").mkdir()
        (adj_dir / "scripts" / "foo.sh").write_text("#!/bin/bash")
        (adj_dir / "VERSION").write_text("v1.0.0")

        backup_path = backup_current(adj_dir, quiet=True)

        assert backup_path.is_dir()
        assert (backup_path / "scripts" / "foo.sh").is_file()
        assert (backup_path / "VERSION").is_file()

    def test_skips_missing_dirs(self, tmp_path: Path) -> None:
        # None of the backup dirs exist — should not fail
        backup_path = backup_current(tmp_path, quiet=True)
        assert backup_path.is_dir()


class TestShouldExclude:
    def test_excludes_adjutant_yaml(self) -> None:
        assert _should_exclude("adjutant.yaml") is True

    def test_excludes_env(self) -> None:
        assert _should_exclude(".env") is True

    def test_excludes_journal_subpath(self) -> None:
        assert _should_exclude("journal/2026-01-01.md") is True

    def test_does_not_exclude_scripts(self) -> None:
        assert _should_exclude("scripts/lifecycle/update.sh") is False

    def test_does_not_exclude_src(self) -> None:
        assert _should_exclude("src/adjutant/cli.py") is False


class TestDownloadAndApply:
    def _make_tarball(self, tmp_path: Path, version: str) -> Path:
        """Create a minimal release tarball at tmp_path/adjutant.tar.gz."""
        src_dir = tmp_path / "src"
        # Simulates extracted tree: adjutant-v1.0.0/scripts/foo.sh
        root = src_dir / f"adjutant-{version}"
        (root / "scripts").mkdir(parents=True)
        (root / "scripts" / "foo.sh").write_text("#!/bin/bash\necho hi\n")
        (root / "VERSION").write_text(f"{version}\n")
        # excluded file — should NOT be copied
        (root / "adjutant.yaml").write_text("instance:\n  name: adjutant\n")

        tarball = tmp_path / "adjutant.tar.gz"
        with tarfile.open(tarball, "w:gz") as tar:
            tar.add(root, arcname=root.name)
        return tarball

    def test_applies_non_excluded_files(self, tmp_path: Path) -> None:
        import httpx as _httpx

        adj_dir = tmp_path / "install"
        adj_dir.mkdir()
        tarball = self._make_tarball(tmp_path, "v1.1.0")

        # Mock for the tarball download (stream context)
        mock_stream_resp = MagicMock()
        mock_stream_resp.raise_for_status = MagicMock()
        mock_stream_resp.__enter__ = MagicMock(return_value=mock_stream_resp)
        mock_stream_resp.__exit__ = MagicMock(return_value=False)
        mock_stream_resp.iter_bytes = MagicMock(return_value=[tarball.read_bytes()])

        # Two httpx.Client() calls: first for tarball, second for checksum.
        # The checksum client should return a 404 to skip verification.
        mock_tarball_http = MagicMock()
        mock_tarball_http.__enter__ = MagicMock(return_value=mock_tarball_http)
        mock_tarball_http.__exit__ = MagicMock(return_value=False)
        mock_tarball_http.stream.return_value = mock_stream_resp

        mock_checksum_http = MagicMock()
        mock_checksum_http.__enter__ = MagicMock(return_value=mock_checksum_http)
        mock_checksum_http.__exit__ = MagicMock(return_value=False)
        mock_cs_resp = MagicMock()
        mock_cs_resp.raise_for_status.side_effect = _httpx.HTTPStatusError(
            "404", request=MagicMock(), response=MagicMock(status_code=404)
        )
        mock_checksum_http.get.return_value = mock_cs_resp

        with patch(
            "adjutant.lifecycle.update.httpx.Client",
            side_effect=[mock_tarball_http, mock_checksum_http],
        ):
            download_and_apply("v1.1.0", adj_dir, quiet=True)

        assert (adj_dir / "scripts" / "foo.sh").is_file()
        assert (adj_dir / "VERSION").is_file()
        # Excluded file should NOT be written
        assert not (adj_dir / "adjutant.yaml").is_file()


class TestUpdate:
    def test_already_up_to_date(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        (tmp_path / "VERSION").write_text("v2.0.0")

        with patch("adjutant.lifecycle.update.get_latest_version", return_value="v2.0.0"):
            update(tmp_path, quiet=False)

        out, _ = capsys.readouterr()
        # Should report "Already up to date"
        assert "up to date" in out.lower() or "up to date" in _

    def test_check_only_does_not_download(self, tmp_path: Path) -> None:
        (tmp_path / "VERSION").write_text("v1.0.0")

        with (
            patch("adjutant.lifecycle.update.get_latest_version", return_value="v2.0.0"),
            patch("adjutant.lifecycle.update.download_and_apply") as mock_dl,
        ):
            update(tmp_path, check_only=True)

        mock_dl.assert_not_called()

    def test_auto_yes_skips_confirm(self, tmp_path: Path) -> None:
        (tmp_path / "VERSION").write_text("v1.0.0")

        with (
            patch("adjutant.lifecycle.update.get_latest_version", return_value="v2.0.0"),
            patch("adjutant.lifecycle.update.backup_current", return_value=tmp_path / ".backup"),
            patch("adjutant.lifecycle.update.download_and_apply"),
            patch("adjutant.lifecycle.update._run_doctor"),
            patch("adjutant.lifecycle.update._warn_if_listener_running"),
        ):
            # Should not block on input()
            update(tmp_path, auto_yes=True, quiet=True)
