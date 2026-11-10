"""Operation daemon connection cleanup and ownership."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, Mock, patch

import pytest

from adjutant.core.config import AdjutantConfig
from adjutant.operations import daemon
from adjutant.operations.store import OperationStore

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [None, "construction", "execution"])
async def test_daemon_retains_connection_until_maintenance_stops(
    tmp_path: Path, failure: str | None
) -> None:
    config = AdjutantConfig()
    config.operations.enabled = True
    store = OperationStore(tmp_path)
    wal = store.database_path.with_suffix(".sqlite3-wal")
    maintenance_started = asyncio.Event()
    maintenance_stopped = asyncio.Event()
    worker = Mock()
    lock = Mock()

    async def maintenance(*_args):
        assert wal.exists()
        maintenance_started.set()
        try:
            await asyncio.Event().wait()
        finally:
            assert wal.exists()
            maintenance_stopped.set()

    async def run_forever():
        await asyncio.wait_for(maintenance_started.wait(), timeout=1)
        assert wal.exists()
        if failure == "execution":
            raise RuntimeError("execution failed")

    def released():
        assert not wal.exists()
        if failure != "construction":
            assert maintenance_stopped.is_set()

    worker.run_forever = AsyncMock(side_effect=run_forever)
    lock.release.side_effect = released
    loop = asyncio.get_running_loop()
    with (
        patch.object(daemon, "_adj_dir", return_value=tmp_path),
        patch.object(daemon, "load_typed_config", return_value=config),
        patch.object(daemon, "require_telegram_credentials", return_value=("token", "chat")),
        patch.object(daemon, "PidLock", return_value=lock),
        patch.object(daemon, "OperationStore", return_value=store),
        patch.object(daemon, "DeliveryWorker"),
        patch.object(daemon, "OperationWorker", return_value=worker) as factory,
        patch.object(daemon, "_maintenance_loop", side_effect=maintenance),
        patch.object(daemon, "adj_log"),
        patch.object(loop, "add_signal_handler"),
    ):
        if failure == "construction":
            factory.side_effect = RuntimeError("construction failed")
        if failure is None:
            await daemon.main()
        else:
            with pytest.raises(RuntimeError, match=f"{failure} failed"):
                await daemon.main()
        if failure != "construction":
            assert factory.call_args.kwargs["poll_interval_seconds"] == 0.5
    lock.release.assert_called_once()
