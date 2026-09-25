"""Tests for the owned persistent OpenCode server transport."""

from __future__ import annotations

import asyncio
import json
import os
import stat
import textwrap
import time
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from adjutant.core.config import PersistentOpenCodeConfig
from adjutant.core.opencode_server import (
    ManagedOpenCodeServer,
    OpenCodeServerDrainingError,
    OpenCodeServerError,
)

if TYPE_CHECKING:
    from pathlib import Path


def _fake_opencode(tmp_path: Path) -> Path:
    script = tmp_path / "opencode"
    script.write_text(
        textwrap.dedent(
            """\
            #!/usr/bin/env python3
            import signal
            import sys
            import time

            signal.signal(signal.SIGTERM, lambda *_args: sys.exit(0))
            while True:
                time.sleep(1)
            """
        )
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return script


@pytest.mark.asyncio
async def test_managed_server_starts_reuses_and_stops(tmp_path: Path, monkeypatch) -> None:
    binary = _fake_opencode(tmp_path)
    monkeypatch.setenv("OPENCODE_BIN", str(binary))
    config = PersistentOpenCodeConfig(
        enabled=True,
        startup_timeout_seconds=5,
        health_interval_seconds=1,
        idle_timeout_seconds=600,
    )
    manager = ManagedOpenCodeServer(tmp_path, config)
    with (
        patch.object(manager, "_available_port", return_value=45678),
        patch(
            "adjutant.core.opencode_server.OpenCodeServerClient.health",
            return_value={"healthy": True, "version": "fake-1"},
        ),
    ):
        first = await manager.ensure_ready()
        try:
            second = await manager.ensure_ready()
            assert first.reused is False
            assert second.reused is True
            assert second.instance_id == first.instance_id
            assert second.pid == first.pid
            assert manager.status()["owned_process_alive"] is True
            mode = stat.S_IMODE((tmp_path / "state" / "opencode-server.secret").stat().st_mode)
            assert mode == 0o600
            state = json.loads((tmp_path / "state" / "opencode-server.json").read_text())
            assert "password" not in state
        finally:
            assert await manager.stop() is True


@pytest.mark.asyncio
async def test_soft_limit_drains_without_interrupting_active_client(
    tmp_path: Path, monkeypatch
) -> None:
    binary = _fake_opencode(tmp_path)
    monkeypatch.setenv("OPENCODE_BIN", str(binary))
    manager = ManagedOpenCodeServer(
        tmp_path,
        PersistentOpenCodeConfig(
            enabled=True,
            startup_timeout_seconds=5,
            health_interval_seconds=1,
            idle_timeout_seconds=600,
            soft_memory_mb=1,
        ),
    )
    with (
        patch.object(manager, "_available_port", return_value=45679),
        patch(
            "adjutant.core.opencode_server.OpenCodeServerClient.health",
            return_value={"healthy": True, "version": "fake-1"},
        ),
    ):
        await manager.ensure_ready()
    monkeypatch.setattr(manager, "_rss_bytes", lambda _pid: 2 * 1024 * 1024)
    try:
        assert await manager.maintain(active_clients=1) == "draining"
        assert manager.status()["owned_process_alive"] is True
        with pytest.raises(OpenCodeServerDrainingError, match="draining"):
            await manager.ensure_ready()
        monkeypatch.setattr(manager, "_rss_bytes", lambda _pid: 0)
        assert await manager.maintain(active_clients=0) == "soft_limit_stopped"
        assert manager.status()["owned_process_alive"] is False
    finally:
        await manager.stop()


def test_state_does_not_claim_reused_pid(tmp_path: Path) -> None:
    manager = ManagedOpenCodeServer(tmp_path, PersistentOpenCodeConfig(enabled=True))
    manager.state_dir.mkdir(parents=True)
    manager.state_path.write_text(
        json.dumps(
            {
                "instance_id": "stale",
                "pid": os.getpid(),
                "pid_create_time": 0.0,
                "url": "http://127.0.0.1:1",
                "port": 1,
                "username": "opencode",
                "status": "ready",
                "started_at": 0.0,
                "last_used_at": 0.0,
            }
        )
    )
    assert asyncio.run(manager.stop()) is False


@pytest.mark.asyncio
async def test_failed_server_respects_restart_backoff(tmp_path: Path) -> None:
    manager = ManagedOpenCodeServer(
        tmp_path,
        PersistentOpenCodeConfig(enabled=True, restart_backoff_seconds=60),
    )
    manager.state_dir.mkdir(parents=True)
    manager.state_path.write_text(
        json.dumps(
            {
                "instance_id": "failed-instance",
                "pid": 999_999,
                "pid_create_time": 0.0,
                "url": "http://127.0.0.1:1",
                "port": 1,
                "username": "opencode",
                "status": "failed",
                "started_at": 0.0,
                "last_used_at": time.time(),
                "last_error": "startup failed",
            }
        )
    )

    with pytest.raises(OpenCodeServerError, match="restart backoff active"):
        await manager.ensure_ready()
