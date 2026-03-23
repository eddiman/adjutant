"""OpenCode backend — wraps core/opencode.py behind the LLMBackend protocol.

This is the existing backend path. All OpenCode-specific logic stays in
opencode.py; this module adapts it to the unified LLMBackend interface.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import time
from pathlib import Path

from adjutant.core.backend import BackendCapabilities, BackendNotFoundError, LLMResult
from adjutant.core.logging import adj_log
from adjutant.core.opencode import (
    OpenCodeNotFoundError,
    OpenCodeResult,
    _find_opencode,
    opencode_health_check,
    opencode_reap,
    opencode_run,
)
from adjutant.lib.ndjson import parse_ndjson

# Model alias → full OpenCode model ID
_ALIASES: dict[str, str] = {
    "haiku": "anthropic/claude-haiku-4-5",
    "sonnet": "anthropic/claude-sonnet-4-6",
    "opus": "anthropic/claude-opus-4-6",
}

# Reverse: full model ID → alias (used by translate_model_id)
_REVERSE_ALIASES: dict[str, str] = {v: k for k, v in _ALIASES.items()}


class OpenCodeBackend:
    """LLMBackend implementation using the OpenCode CLI."""

    @property
    def name(self) -> str:
        return "opencode"

    @property
    def capabilities(self) -> BackendCapabilities:
        return BackendCapabilities(
            vision=True,
            model_listing=True,
            reaping=True,
            web_server=True,
            remote_session=False,
            streaming=True,
            cost_tracking=False,
        )

    async def run(
        self,
        prompt: str,
        *,
        agent: str | None = None,
        workdir: Path | None = None,
        model: str | None = None,
        session_id: str | None = None,
        timeout: float | None = None,
        env: dict[str, str] | None = None,
        files: list[Path] | None = None,
    ) -> LLMResult:
        args: list[str] = ["run"]

        if agent:
            args += ["--agent", agent]
        if workdir:
            args += ["--dir", str(workdir)]
        args += ["--format", "json"]
        if model:
            args += ["--model", self.resolve_alias(model)]
        if session_id:
            args += ["--session", session_id]
        if files:
            for f in files:
                args += ["-f", str(f)]
        args.append(prompt)

        start = time.monotonic()
        try:
            oc_result: OpenCodeResult = await opencode_run(args, timeout=timeout, env=env)
        except OpenCodeNotFoundError as exc:
            raise BackendNotFoundError(str(exc)) from exc

        elapsed = time.monotonic() - start
        parsed = parse_ndjson(oc_result.stdout)

        result = LLMResult(
            text=parsed.text,
            session_id=parsed.session_id,
            error_type=parsed.error_type,
            returncode=oc_result.returncode,
            timed_out=oc_result.timed_out,
        )
        if oc_result.timed_out:
            result.error_type = "timeout"

        adj_log(
            "backend",
            f"[opencode] run completed in {elapsed:.1f}s"
            f" | model={model} agent={agent}"
            f" | error_type={result.error_type}",
        )
        return result

    def run_detached(
        self,
        prompt: str,
        *,
        agent: str | None = None,
        workdir: Path | None = None,
        model: str | None = None,
        log_path: Path | None = None,
    ) -> None:
        try:
            opencode_bin = _find_opencode()
        except OpenCodeNotFoundError as exc:
            raise BackendNotFoundError(str(exc)) from exc

        args = [opencode_bin, "run"]
        if agent:
            args += ["--agent", agent]
        if workdir:
            args += ["--dir", str(workdir)]
        args += ["--format", "json"]
        if model:
            args += ["--model", self.resolve_alias(model)]
        args.append(prompt)

        log_fh = open(log_path, "a") if log_path else None  # noqa: SIM115
        try:
            subprocess.Popen(
                args,
                stdout=log_fh or subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        finally:
            if log_fh is not None:
                log_fh.close()

    def run_sync(
        self,
        prompt: str,
        *,
        workdir: Path | None = None,
        timeout: float | None = None,
    ) -> int:
        try:
            opencode_bin = _find_opencode()
        except OpenCodeNotFoundError as exc:
            raise BackendNotFoundError(str(exc)) from exc

        args = [opencode_bin, "run"]
        if workdir:
            args += ["--dir", str(workdir)]
        args.append(prompt)

        start = time.monotonic()
        result = subprocess.run(args, timeout=timeout)  # noqa: S603
        elapsed = time.monotonic() - start

        adj_log(
            "backend",
            f"[opencode] run_sync completed in {elapsed:.1f}s"
            f" | returncode={result.returncode}",
        )
        return result.returncode

    async def reap(self, adj_dir: Path) -> int:
        return await opencode_reap(adj_dir)

    async def health_check(self, adj_dir: Path) -> bool:
        return await opencode_health_check(adj_dir)

    async def list_models(self) -> str:
        try:
            opencode_bin = _find_opencode()
        except OpenCodeNotFoundError as exc:
            raise BackendNotFoundError(str(exc)) from exc

        proc = await asyncio.create_subprocess_exec(
            opencode_bin,
            "models",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        return stdout.decode(errors="replace") if stdout else ""

    def find_binary(self) -> str | None:
        try:
            return _find_opencode()
        except OpenCodeNotFoundError:
            return None

    def resolve_alias(self, alias: str) -> str:
        return _ALIASES.get(alias, alias)

    def translate_model_id(self, model_id: str) -> str:
        return _REVERSE_ALIASES.get(model_id, model_id)
