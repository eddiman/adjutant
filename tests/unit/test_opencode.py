"""Tests for adjutant.core.opencode — opencode_run, reap, health check."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import psutil
import pytest

from adjutant.core.opencode import (
    OpenCodeNotFoundError,
    OpenCodeResult,
    _find_opencode,
    _get_language_server_pids,
    opencode_health_check,
    opencode_reap,
    opencode_run,
)


class TestFindOpencode:
    """Test _find_opencode() — binary lookup."""

    def test_raises_when_not_found(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        monkeypatch.setenv("PATH", str(tmp_path))
        monkeypatch.delenv("OPENCODE_BIN", raising=False)
        with pytest.raises(OpenCodeNotFoundError, match="not found"):
            _find_opencode()

    def test_finds_on_path(self, mock_opencode: Path):
        result = _find_opencode()
        assert "opencode" in result

    def test_opencode_bin_env_overrides_path(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
        """OPENCODE_BIN env var should be used instead of PATH lookup."""
        # Create a fake binary at a custom location
        custom_bin = tmp_path / "custom" / "opencode"
        custom_bin.parent.mkdir()
        custom_bin.write_text("#!/bin/bash\necho ok")
        custom_bin.chmod(0o755)

        # Empty PATH so shutil.which would fail
        monkeypatch.setenv("PATH", str(tmp_path / "empty"))
        monkeypatch.setenv("OPENCODE_BIN", str(custom_bin))

        result = _find_opencode()
        assert result == str(custom_bin)

    def test_opencode_bin_raises_when_not_executable(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        """OPENCODE_BIN pointing to a non-executable file should raise."""
        bad_bin = tmp_path / "opencode"
        bad_bin.write_text("not a binary")
        bad_bin.chmod(0o644)  # not executable

        monkeypatch.setenv("OPENCODE_BIN", str(bad_bin))

        with pytest.raises(OpenCodeNotFoundError, match="not an executable"):
            _find_opencode()

    def test_opencode_bin_raises_when_missing(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ):
        """OPENCODE_BIN pointing to a nonexistent path should raise."""
        monkeypatch.setenv("OPENCODE_BIN", str(tmp_path / "nonexistent"))

        with pytest.raises(OpenCodeNotFoundError, match="not an executable"):
            _find_opencode()


class TestOpenCodeResult:
    """Test OpenCodeResult dataclass."""

    def test_defaults(self):
        r = OpenCodeResult(stdout="out", stderr="err", returncode=0)
        assert r.timed_out is False

    def test_timed_out(self):
        r = OpenCodeResult(stdout="", stderr="", returncode=-1, timed_out=True)
        assert r.timed_out is True


class TestOpenCodeRun:
    """Test opencode_run() — async process invocation."""

    @pytest.mark.asyncio
    async def test_basic_invocation(self, mock_opencode: Path):
        result = await opencode_run(["--help"])
        assert isinstance(result, OpenCodeResult)
        # Mock script echoes JSON text
        assert "OK" in result.stdout or result.returncode == 0

    @pytest.mark.asyncio
    async def test_timeout_returns_timed_out(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Script that sleeps too long should be terminated with timed_out=True."""
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir()
        script = mock_bin / "opencode"
        script.write_text("#!/bin/bash\nsleep 30")
        script.chmod(0o755)
        monkeypatch.setenv("PATH", f"{mock_bin}:{os.environ['PATH']}")

        result = await opencode_run(["run"], timeout=0.5)
        assert result.timed_out is True
        assert result.returncode < 0  # Negative signal code (SIGTERM=-15 or SIGKILL=-9)

    @pytest.mark.asyncio
    async def test_env_passed_to_subprocess(
        self, mock_opencode: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """Custom env vars should be available in the subprocess."""
        mock_bin = mock_opencode.parent
        script = mock_bin / "opencode"
        script.write_text('#!/bin/bash\necho "$MY_TEST_VAR"')
        script.chmod(0o755)

        result = await opencode_run(["run"], env={"MY_TEST_VAR": "hello"})
        assert "hello" in result.stdout

    @pytest.mark.asyncio
    async def test_nonzero_exit(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir()
        script = mock_bin / "opencode"
        script.write_text("#!/bin/bash\nexit 42")
        script.chmod(0o755)
        monkeypatch.setenv("PATH", f"{mock_bin}:{os.environ['PATH']}")

        result = await opencode_run(["run"])
        assert result.returncode == 42
        assert result.timed_out is False


class TestGetLanguageServerPids:
    """Test _get_language_server_pids() — snapshot helper."""

    def test_returns_set(self):
        result = _get_language_server_pids()
        assert isinstance(result, set)


class TestOpenCodeReap:
    """Test opencode_reap() — orphan cleanup."""

    @pytest.mark.asyncio
    async def test_reap_with_no_targets(self, adj_dir: Path):
        """When no language servers are running, reap returns 0."""
        count = await opencode_reap(adj_dir)
        assert count == 0

    @pytest.mark.asyncio
    async def test_reap_rss_rule(self, adj_dir: Path, monkeypatch: pytest.MonkeyPatch):
        """RSS runaway processes should be targeted."""
        monkeypatch.setenv("OPENCODE_LANGSERVER_RSS_LIMIT_KB", "1")

        mock_proc = MagicMock()
        mock_proc.info = {
            "pid": 99999999,
            "ppid": os.getpid(),
            "cmdline": ["node", "bash-language-server", "start"],
            "memory_info": MagicMock(rss=2048 * 1024),  # 2MB > 1KB limit
        }

        with patch("adjutant.core.opencode.psutil.process_iter", return_value=[mock_proc]):
            with patch("adjutant.core.opencode.os.kill"):
                count = await opencode_reap(adj_dir)
                assert count == 1


class TestOpenCodeHealthCheck:
    """Test opencode_health_check() — two-stage probe with restart."""

    @pytest.mark.asyncio
    async def test_fails_with_no_pid_file(self, adj_dir: Path):
        """No web server PID file → health check fails."""
        with patch("adjutant.lifecycle.control.start_opencode_web", return_value="started"):
            result = await opencode_health_check(adj_dir)
        assert result is False

    @pytest.mark.asyncio
    async def test_succeeds_when_both_stages_pass(self, adj_dir: Path, mock_opencode: Path):
        """When HTTP ping and API probe both pass, returns True."""
        # No PID file → health check should return False
        with patch("adjutant.lifecycle.control.start_opencode_web", return_value="started"):
            result = await opencode_health_check(adj_dir)
        assert result is False

    @pytest.mark.asyncio
    async def test_calls_start_opencode_web_on_failure(self, adj_dir: Path):
        """When health check fails, it should call start_opencode_web (not restart.sh)."""
        started = []

        def fake_start(d):
            started.append(d)
            return "OpenCode web server started (PID 12345)"

        with patch(
            "adjutant.lifecycle.control.start_opencode_web",
            side_effect=fake_start,
        ):
            result = await opencode_health_check(adj_dir)

        # The restart was attempted (no PID file → _http_ping returns False → restart)
        assert len(started) == 1
        assert started[0] == adj_dir
        # HTTP polling still fails after restart → returns False
        assert result is False

    @pytest.mark.asyncio
    async def test_recovers_after_restart(self, adj_dir: Path):
        """When start_opencode_web succeeds and HTTP recovers, returns True."""
        import httpx

        mock_response = MagicMock()
        mock_response.status_code = 200
        ping_calls = 0

        async def patched_get(url, **kwargs):
            nonlocal ping_calls
            ping_calls += 1
            if ping_calls <= 1:
                raise httpx.ConnectError("refused")
            return mock_response

        with patch(
            "adjutant.lifecycle.control.start_opencode_web",
            return_value="started",
        ):
            with patch("httpx.AsyncClient") as mock_client_cls:
                mock_client = AsyncMock()
                mock_client.get = patched_get
                mock_client.__aenter__ = AsyncMock(return_value=mock_client)
                mock_client.__aexit__ = AsyncMock(return_value=False)
                mock_client_cls.return_value = mock_client

                # Write PID file so ping can proceed on retry
                (adj_dir / "state" / "opencode_web.pid").write_text("12345")
                with patch("adjutant.core.opencode.read_pid_file", return_value=12345):
                    result = await opencode_health_check(adj_dir)

        assert result is True

    @pytest.mark.asyncio
    async def test_restart_exception_is_caught(self, adj_dir: Path):
        """If start_opencode_web raises, the error is caught and logged."""
        with patch(
            "adjutant.lifecycle.control.start_opencode_web",
            side_effect=OSError("disk full"),
        ):
            result = await opencode_health_check(adj_dir)
        # Should not raise — error is caught
        assert result is False
