"""Long-running durable operation worker process."""

from __future__ import annotations

import asyncio
import os
import signal
import sys
import time
from pathlib import Path

from adjutant.core.config import load_typed_config
from adjutant.core.env import require_telegram_credentials
from adjutant.core.logging import adj_log
from adjutant.core.process import PidLock
from adjutant.operations.delivery import DeliveryWorker
from adjutant.operations.models import OperationState
from adjutant.operations.recovery import recover_worker_state
from adjutant.operations.retention import run_retention
from adjutant.operations.store import OperationStore
from adjutant.operations.worker import OperationWorker

_LOCKDIR_NAME = "operation-worker.lock"


async def _maintenance_loop(adj_dir: Path, store: OperationStore) -> None:
    """Apply server limits and retention while the worker remains online."""
    config = load_typed_config(adj_dir / "adjutant.yaml")
    persistent = config.operations.persistent_opencode
    interval = max(1, persistent.health_interval_seconds)
    last_retention = 0.0
    manager = None
    if persistent.enabled:
        from adjutant.core.opencode_server import ManagedOpenCodeServer

        manager = ManagedOpenCodeServer(adj_dir, persistent)
    while True:
        try:
            recovered_operations, recovered_deliveries = recover_worker_state(
                adj_dir, store=store
            )
            if recovered_operations or recovered_deliveries:
                store.sync_active_snapshot()
            if manager is not None:
                active = store.list_operations(
                    states=(
                        OperationState.STARTING,
                        OperationState.RUNNING,
                        OperationState.CANCEL_REQUESTED,
                    ),
                    limit=500,
                )
                await manager.maintain(active_clients=len(active))
            if time.monotonic() - last_retention >= 3600:
                await run_retention(adj_dir, store=store)
                last_retention = time.monotonic()
        except Exception as exc:  # noqa: BLE001 - maintenance cannot stop execution
            adj_log("operations", f"Maintenance pass failed: {exc}")
        await asyncio.sleep(interval)


def _adj_dir() -> Path:
    raw = os.environ.get("ADJ_DIR", "").strip()
    if not raw:
        raise RuntimeError("ADJ_DIR not set.")
    return Path(raw)


async def main() -> None:
    adj_dir = _adj_dir()
    config = load_typed_config(adj_dir / "adjutant.yaml")
    if not config.operations.enabled:
        adj_log("operations", "Durable operations are disabled. Worker exiting.")
        return

    lock = PidLock(adj_dir / "state" / _LOCKDIR_NAME)
    if not lock.acquire():
        adj_log("operations", f"Another operation worker is running (PID {lock.held_pid}).")
        sys.exit(1)

    try:
        bot_token, chat_id = require_telegram_credentials(adj_dir / ".env")
        store = OperationStore(adj_dir)
        with store.keep_open():
            delivery = DeliveryWorker(
                adj_dir,
                bot_token=bot_token,
                chat_id=chat_id,
                store=store,
                worker_id=f"delivery-{os.getpid()}",
                max_attempts=config.operations.delivery_max_attempts,
                retry_base_seconds=config.operations.delivery_retry_base_seconds,
                lease_seconds=config.operations.timeouts.lease_seconds,
            )
            worker = OperationWorker(
                adj_dir,
                store=store,
                concurrency=config.operations.worker_concurrency,
                poll_interval_seconds=config.operations.poll_interval_seconds,
                lease_seconds=config.operations.timeouts.lease_seconds,
                startup_seconds=config.operations.timeouts.startup_seconds,
                connection_seconds=config.operations.timeouts.connection_seconds,
                runtime_seconds=config.operations.timeouts.runtime_seconds,
                progress_warning_seconds=config.operations.timeouts.progress_warning_seconds,
                cancellation_grace_seconds=config.operations.timeouts.cancellation_grace_seconds,
                delivery_worker=delivery,
            )
            loop = asyncio.get_running_loop()
            for signal_name in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(signal_name, worker.stop)
            maintenance = asyncio.create_task(_maintenance_loop(adj_dir, store))
            try:
                await worker.run_forever()
            finally:
                maintenance.cancel()
                await asyncio.gather(maintenance, return_exceptions=True)
                if config.operations.persistent_opencode.enabled:
                    from adjutant.core.opencode_server import ManagedOpenCodeServer

                    await ManagedOpenCodeServer(
                        adj_dir,
                        config.operations.persistent_opencode,
                    ).stop()
    finally:
        lock.release()
        adj_log("operations", "Operation worker stopped.")


if __name__ == "__main__":
    asyncio.run(main())
