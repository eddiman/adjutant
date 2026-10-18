"""Tests for adjutant.core.opencode — opencode_run, reap, health check."""

from __future__ import annotations

import asyncio
import os
import sys
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from adjutant.core.opencode import (
    OpenCodeNotFoundError,
    OpenCodeResult,
    _find_opencode,
    opencode_health_check,
    opencode_reap,
    opencode_run,
)

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.backend_opencode


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
    async def test_spawn_callback_receives_owned_process_identity(
        self, mock_opencode: Path
    ) -> None:
        evidence: list[dict[str, int | float | None]] = []

        result = await opencode_run(["--help"], on_spawn=evidence.append)

        assert result.returncode == 0
        assert len(evidence) == 1
        assert isinstance(evidence[0]["pid"], int)
        assert isinstance(evidence[0]["pid_create_time"], float)
        assert isinstance(evidence[0]["process_group_id"], int)

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
    async def test_startup_timeout_is_separate_from_runtime(self) -> None:
        async def slow_spawn(*args, **kwargs):
            await asyncio.sleep(10)

        with (
            patch("adjutant.core.opencode._find_opencode", return_value="/fake/opencode"),
            patch(
                "adjutant.core.opencode.asyncio.create_subprocess_exec",
                side_effect=slow_spawn,
            ),
        ):
            result = await opencode_run(
                ["run"],
                startup_timeout=0.01,
                timeout=60,
            )

        assert result.timed_out is True
        assert result.timeout_phase == "startup"

    @pytest.mark.asyncio
    async def test_timeout_preserves_partial_output(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir()
        script = mock_bin / "opencode"
        script.write_text(
            '#!/bin/bash\nprintf \'{"type":"text","part":{"text":"partial"}}\\n\'\nsleep 30\n'
        )
        script.chmod(0o755)
        monkeypatch.setenv("PATH", f"{mock_bin}:{os.environ['PATH']}")

        result = await opencode_run(["run"], timeout=0.2)

        assert result.timed_out is True
        assert "partial" in result.stdout

    @pytest.mark.asyncio
    async def test_cancellation_terminates_owned_process_group(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir()
        script = mock_bin / "opencode"
        script.write_text("#!/bin/bash\nsleep 30\n")
        script.chmod(0o755)
        monkeypatch.setenv("PATH", f"{mock_bin}:{os.environ['PATH']}")

        task = asyncio.create_task(opencode_run(["run"]))
        await asyncio.sleep(0.1)
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=2)

    @pytest.mark.asyncio
    async def test_timeout_does_not_terminate_unrelated_process(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir()
        script = mock_bin / "opencode"
        script.write_text("#!/bin/bash\nsleep 30\n")
        script.chmod(0o755)
        monkeypatch.setenv("PATH", f"{mock_bin}:{os.environ['PATH']}")

        unrelated = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            "import time; time.sleep(30)",
            start_new_session=True,
        )
        try:
            result = await opencode_run(["run"], timeout=0.2)
            assert result.timed_out is True
            assert unrelated.returncode is None
        finally:
            unrelated.terminate()
            await unrelated.wait()

    @pytest.mark.asyncio
    async def test_concurrent_invocations_own_separate_process_groups(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir()
        script = mock_bin / "opencode"
        script.write_text(
            "#!/bin/bash\n"
            'if [ "$1" = timeout ]; then\n'
            "  sleep 30\n"
            "else\n"
            "  sleep 0.5\n"
            "  echo survivor-done\n"
            "fi\n"
        )
        script.chmod(0o755)
        monkeypatch.setenv("PATH", f"{mock_bin}:{os.environ['PATH']}")

        survivor_task = asyncio.create_task(opencode_run(["survivor"], timeout=2))
        await asyncio.sleep(0.05)
        timed_out = await opencode_run(["timeout"], timeout=0.2)
        survivor = await survivor_task

        assert timed_out.timed_out is True
        assert survivor.timed_out is False
        assert "survivor-done" in survivor.stdout

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

    @pytest.mark.asyncio
    async def test_publishes_stdout_line_before_process_finishes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir()
        script = mock_bin / "opencode"
        script.write_text("#!/bin/bash\necho first-event\nsleep 0.5\necho final-event\n")
        script.chmod(0o755)
        monkeypatch.setenv("PATH", f"{mock_bin}:{os.environ['PATH']}")
        first_line = asyncio.Event()
        lines: list[str] = []

        async def on_line(line: str) -> None:
            lines.append(line)
            first_line.set()

        task = asyncio.create_task(opencode_run(["run"], on_stdout_line=on_line))
        await asyncio.wait_for(first_line.wait(), timeout=0.25)

        assert task.done() is False
        result = await task
        assert lines == ["first-event", "final-event"]
        assert result.returncode == 0

    @pytest.mark.asyncio
    async def test_drains_large_stderr_without_deadlock(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mock_bin = tmp_path / "bin"
        mock_bin.mkdir()
        script = mock_bin / "opencode"
        script.write_text(
            "#!/bin/bash\npython3 -c 'import sys; sys.stderr.write(\"x\" * 1000000)'\necho done\n"
        )
        script.chmod(0o755)
        monkeypatch.setenv("PATH", f"{mock_bin}:{os.environ['PATH']}")

        result = await opencode_run(["run"], timeout=2)

        assert result.timed_out is False
        assert "done" in result.stdout
        assert len(result.stderr.encode()) <= 256 * 1024


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

        with (
            patch("adjutant.core.opencode.psutil.process_iter", return_value=[mock_proc]),
            patch("adjutant.core.opencode.os.kill"),
        ):
            count = await opencode_reap(adj_dir)
            assert count == 1


class TestOpenCodeHealthCheck:
    """Test opencode_health_check() — verifies the opencode binary is callable.

    The old two-stage probe (HTTP ping + API probe + web server restart)
    was removed along with the native `opencode web` server. The health
    check is now a plain binary availability check.
    """

    @pytest.mark.asyncio
    async def test_returns_true_when_binary_present(
        self, adj_dir: Path, mock_opencode: Path
    ) -> None:
        """When the opencode binary is on PATH, health check returns True."""
        result = await opencode_health_check(adj_dir)
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_binary_missing(self, adj_dir: Path) -> None:
        """When the opencode binary is not found, health check returns False."""
        import adjutant.core.opencode as opencode_mod

        with patch.object(
            opencode_mod,
            "_find_opencode",
            side_effect=opencode_mod.OpenCodeNotFoundError("not found"),
        ):
            result = await opencode_health_check(adj_dir)
        assert result is False

    @pytest.mark.asyncio
    async def test_accepts_none_adj_dir(self, mock_opencode: Path) -> None:
        """adj_dir is optional now that the check doesn't touch state/."""
        result = await opencode_health_check(None)
        assert result is True
