"""Operation WAL lifetime across producer processes and worker crashes."""

from __future__ import annotations

import asyncio
import subprocess
import sys
import time
from typing import TYPE_CHECKING

import pytest

from adjutant.core.backend import LLMResult
from adjutant.operations.models import OperationState
from adjutant.operations.store import OperationStore
from adjutant.operations.worker import OperationWorker

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.asyncio
async def test_idle_worker_claims_work_from_another_process(adj_dir: Path) -> None:
    store = OperationStore(adj_dir)
    started = asyncio.Event()
    claims: list[tuple[str, float]] = []

    async def handler(operation):
        claims.append((operation.id, time.monotonic()))
        started.set()
        return LLMResult(text="done")

    worker = OperationWorker(adj_dir, store=store, handler=handler)
    with store.keep_open():
        task = asyncio.create_task(worker.run_forever())
        try:
            # Let the worker enter its normal 0.5-second idle sleep.
            await asyncio.sleep(0.05)
            producer = await asyncio.create_subprocess_exec(
                sys.executable,
                "-c",
                "import sys,time; from pathlib import Path; "
                "from adjutant.operations.store import OperationStore; "
                "s=OperationStore(Path(sys.argv[1])); "
                "op=s.create_operation(kind='prompt',source='test',payload={}); "
                "print(op.id,time.monotonic(),flush=True)",
                str(adj_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            output, error = await asyncio.wait_for(producer.communicate(), timeout=5)
            assert producer.returncode == 0, error.decode()
            operation_id, accepted_at = output.decode().strip().split()
            await asyncio.wait_for(started.wait(), timeout=2)
            assert claims[0][0] == operation_id
            # Retain the normal polling interval with scheduling allowance.
            assert claims[0][1] - float(accepted_at) < 1.0
        finally:
            worker.stop()
            await asyncio.wait_for(task, timeout=2)
        assert store.get_operation(operation_id).state is OperationState.SUCCEEDED


def test_crashed_connection_preserves_commits_and_lease_recovery(adj_dir: Path) -> None:
    producer = subprocess.run(
        [
            sys.executable,
            "-c",
            "import os,sys; from pathlib import Path; "
            "from adjutant.operations.store import OperationStore; "
            "from adjutant.operations.models import SideEffectClass; "
            "s=OperationStore(Path(sys.argv[1])); "
            "keeper=s.keep_open(); keeper.__enter__(); "
            "op=s.create_operation(kind='prompt',source='test',payload={},"
            "side_effect_class=SideEffectClass.READ_ONLY); "
            "s.claim_next('crashed-worker',lease_seconds=-1); "
            "print(op.id,flush=True); os._exit(0)",
            str(adj_dir),
        ],
        capture_output=True,
        text=True,
        timeout=5,
        check=True,
    )
    store = OperationStore(adj_dir)
    assert store.database_path.with_suffix(".sqlite3-wal").stat().st_size > 0
    with store.keep_open():
        assert store.recover_expired_leases() == (1, 0)
        claimed = store.claim_next("restarted-worker")
        assert claimed is not None
        assert claimed.id == producer.stdout.strip()
