"""Tests for the OpenCode backend wrapper."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from adjutant.core.backend import LLMResult
from adjutant.core.backend_opencode import OpenCodeBackend
from adjutant.core.opencode import OpenCodeResult


@pytest.mark.backend_opencode
class TestOpenCodeBackend:
    @pytest.mark.asyncio
    async def test_run_passes_variant_to_opencode(self) -> None:
        backend = OpenCodeBackend()
        with patch(
            "adjutant.core.backend_opencode.opencode_run",
            new=AsyncMock(
                return_value=OpenCodeResult(
                    stdout='{"type":"text","part":{"text":"OK"}}', stderr="", returncode=0
                )
            ),
        ) as mock_run:
            result = await backend.run("hello", model="github-copilot/gpt-5.4", variant="xhigh")

        assert isinstance(result, LLMResult)
        args = mock_run.await_args.args[0]
        assert "--variant" in args
        assert "xhigh" in args

    def test_run_detached_passes_variant_to_opencode(self, tmp_path: Path) -> None:
        backend = OpenCodeBackend()
        with (
            patch(
                "adjutant.core.backend_opencode._find_opencode", return_value="/usr/bin/opencode"
            ),
            patch("subprocess.Popen") as mock_popen,
        ):
            backend.run_detached(
                "hello",
                workdir=tmp_path,
                model="github-copilot/gpt-5.4",
                variant="medium",
            )

        args = mock_popen.call_args.args[0]
        assert "--variant" in args
        assert "medium" in args
