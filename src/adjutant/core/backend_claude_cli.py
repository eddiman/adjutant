"""Claude Code CLI backend — uses ``claude -p`` with JSON output.

Requires the ``claude`` binary (Claude Code CLI) installed and authenticated
via ``claude login``. Uses ``--output-format json`` for structured output
and ``--system-prompt-file`` for agent definitions.

Security note: ``--dangerously-skip-permissions`` is required for non-interactive
subprocess mode. This bypasses deny rules in .claude/settings.json — hooks in
.claude/hooks/ are the primary technical defense for .env protection.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

from adjutant.core.backend import (
    BackendCapabilities,
    BackendNotFoundError,
    ExecutionEvent,
    ExecutionEventType,
    ExecutionRequest,
    ExecutionTimings,
    LLMResult,
)
from adjutant.core.logging import adj_log
from adjutant.lib.claude_json import parse_claude_json

# Model alias → Claude CLI model name
_ALIASES: dict[str, str] = {
    "haiku": "haiku",
    "sonnet": "sonnet",
    "opus": "opus",
    # Also accept full OpenCode-style IDs
    "anthropic/claude-haiku-4-5": "haiku",
    "anthropic/claude-sonnet-4-6": "sonnet",
    "anthropic/claude-opus-4-6": "opus",
}

# Cross-backend translation: OpenCode full ID → Claude CLI short name
_FROM_OPENCODE: dict[str, str] = {
    "anthropic/claude-haiku-4-5": "haiku",
    "anthropic/claude-sonnet-4-6": "sonnet",
    "anthropic/claude-opus-4-6": "opus",
}

# Cross-backend translation: Claude CLI short name → OpenCode full ID
_TO_OPENCODE: dict[str, str] = {
    "haiku": "anthropic/claude-haiku-4-5",
    "sonnet": "anthropic/claude-sonnet-4-6",
    "opus": "anthropic/claude-opus-4-6",
}

_IMAGE_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".gif", ".webp"})

_DEFAULT_ALLOWED_TOOLS = "Read,Glob,Grep,Edit,Write,Bash(*)"
_VISION_ALLOWED_TOOLS = "Read"


def _get_permission_args(agent: str | None = None) -> list[str]:
    """Build permission-related CLI args from config.

    Returns either --dangerously-skip-permissions (default "skip" mode)
    or --allowedTools with a whitelist ("allowlist" mode).
    """
    if agent == "vision":
        return ["--allowedTools", _VISION_ALLOWED_TOOLS]

    try:
        from adjutant.core.config import load_typed_config

        config = load_typed_config()
        mode = config.llm.permission_mode
        if mode == "allowlist":
            tools = config.llm.allowed_tools or _DEFAULT_ALLOWED_TOOLS
            return ["--allowedTools", tools]
    except Exception:  # noqa: BLE001
        pass
    return ["--dangerously-skip-permissions"]


def _find_claude() -> str:
    """Find the claude binary via CLAUDE_CODE_BIN env var or PATH."""
    env_bin = os.environ.get("CLAUDE_CODE_BIN")
    if env_bin:
        if os.path.isfile(env_bin) and os.access(env_bin, os.X_OK):
            return env_bin
        raise BackendNotFoundError(
            f"CLAUDE_CODE_BIN={env_bin} is set but is not an executable file"
        )
    path = shutil.which("claude")
    if path is None:
        raise BackendNotFoundError("claude not found on PATH")
    return path


def _extract_prompt_body(agent_file: Path) -> str:
    """Strip YAML frontmatter from an agent definition, return markdown body."""
    content = agent_file.read_text()
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            return parts[2].strip()
    return content


def _resolve_agent_file(agent: str, workdir: Path | None) -> Path | None:
    """Find the .opencode/agents/<agent>.md file for the given agent name."""
    if workdir:
        candidate = workdir / ".opencode" / "agents" / f"{agent}.md"
        if candidate.is_file():
            return candidate
    return None


class ClaudeCLIBackend:
    """LLMBackend implementation using the Claude Code CLI."""

    @property
    def name(self) -> str:
        return "claude-cli"

    @property
    def capabilities(self) -> BackendCapabilities:
        return BackendCapabilities(
            vision=True,
            model_listing=True,
            reaping=False,
            # web_server is False since the native CloudCLI web server
            # was retired in favor of adjutant's own web/app.
            web_server=False,
            remote_session=False,
            streaming=True,
            cost_tracking=True,
        )

    async def run(
        self,
        prompt: str,
        *,
        agent: str | None = None,
        workdir: Path | None = None,
        model: str | None = None,
        variant: str | None = None,
        session_id: str | None = None,
        startup_timeout: float | None = None,
        timeout: float | None = None,
        env: dict[str, str] | None = None,
        files: list[Path] | None = None,
        correlation_id: str | None = None,
    ) -> LLMResult:
        _ = variant  # Claude CLI does not expose a separate reasoning-effort flag.
        request_id = correlation_id or f"llm-{uuid.uuid4().hex[:12]}"
        # Inject image file paths into prompt so Claude CLI reads them via
        # its built-in Read tool (which supports multimodal image viewing).
        if files:
            image_files = [f for f in files if f.suffix.lower() in _IMAGE_EXTENSIONS]
            if image_files:
                paths_block = "\n".join(str(f) for f in image_files)
                prompt = (
                    f"First, read the following image file(s) using the Read tool, "
                    f"then answer the user's request.\n\n"
                    f"Image file(s):\n{paths_block}\n\n"
                    f"User request: {prompt}"
                )

        claude_bin = _find_claude()
        args = [claude_bin, "-p", "--output-format", "json"]

        if model:
            args += ["--model", self.resolve_alias(model)]

        # Agent prompt via --system-prompt-file
        tmp_prompt_path: Path | None = None
        if agent and workdir:
            agent_file = _resolve_agent_file(agent, workdir)
            if agent_file:
                body = _extract_prompt_body(agent_file)
                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".md", delete=False
                ) as prompt_file:
                    prompt_file.write(body)
                    tmp_prompt_path = Path(prompt_file.name)
                args += ["--system-prompt-file", str(tmp_prompt_path)]

        args.extend(_get_permission_args(agent))

        if session_id:
            args += ["--resume", session_id]

        args.append(prompt)

        run_env = os.environ.copy()
        if env:
            run_env.update(env)
        run_env.setdefault("ADJUTANT_CORRELATION_ID", request_id)

        start = time.monotonic()
        timed_out = False
        timeout_phase: str | None = None
        spawn_seconds = 0.0
        execution_seconds = 0.0
        cleanup_seconds = 0.0
        proc: asyncio.subprocess.Process | None = None
        try:
            spawn_started = time.monotonic()
            spawn_call = asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=run_env,
                cwd=str(workdir) if workdir else None,
            )
            try:
                if startup_timeout:
                    proc = await asyncio.wait_for(spawn_call, timeout=startup_timeout)
                else:
                    proc = await spawn_call
            except TimeoutError:
                spawn_seconds = time.monotonic() - spawn_started
                timed_out = True
                timeout_phase = "startup"
                stdout_bytes = b""
                stderr_bytes = b"Claude CLI process startup timed out"
            if proc is not None:
                spawn_seconds = time.monotonic() - spawn_started
                execution_started = time.monotonic()
                try:
                    if timeout:
                        stdout_bytes, stderr_bytes = await asyncio.wait_for(
                            proc.communicate(), timeout=timeout
                        )
                    else:
                        stdout_bytes, stderr_bytes = await proc.communicate()
                    execution_seconds = time.monotonic() - execution_started
                except TimeoutError:
                    execution_seconds = time.monotonic() - execution_started
                    cleanup_started = time.monotonic()
                    proc.terminate()
                    try:
                        await asyncio.wait_for(proc.wait(), timeout=2.0)
                    except TimeoutError:
                        proc.kill()
                        await proc.wait()
                    cleanup_seconds = time.monotonic() - cleanup_started
                    timed_out = True
                    timeout_phase = "runtime"
                    stdout_bytes = b""
        finally:
            if tmp_prompt_path:
                tmp_prompt_path.unlink(missing_ok=True)

        stdout = stdout_bytes.decode(errors="replace") if stdout_bytes else ""

        parse_started = time.monotonic()
        parsed = parse_claude_json(stdout)
        parse_seconds = time.monotonic() - parse_started
        elapsed = time.monotonic() - start
        result = LLMResult(
            text=parsed.text,
            session_id=parsed.session_id,
            error_type=parsed.error_type,
            returncode=proc.returncode if proc is not None and proc.returncode is not None else -1,
            timed_out=timed_out,
            timeout_phase=timeout_phase,
            cost_usd=parsed.cost_usd,
            correlation_id=request_id,
            timings=ExecutionTimings(
                spawn_seconds=spawn_seconds,
                execution_seconds=execution_seconds,
                cleanup_seconds=cleanup_seconds,
                parse_seconds=parse_seconds,
                total_seconds=elapsed,
            ),
        )
        if timed_out:
            result.error_type = "timeout"

        log_extra = f" | cost=${result.cost_usd:.4f}" if result.cost_usd else ""
        adj_log(
            "backend",
            f"[claude-cli] run id={request_id} completed in {elapsed:.1f}s"
            f" | spawn={spawn_seconds:.3f}s"
            f" execute={execution_seconds:.3f}s"
            f" cleanup={cleanup_seconds:.3f}s"
            f" parse={parse_seconds:.3f}s"
            f" | model={model} agent={agent}"
            f" | error_type={result.error_type}{log_extra}",
        )
        return result

    async def execute(self, request: ExecutionRequest) -> AsyncIterator[ExecutionEvent]:
        """Expose lifecycle events around Claude CLI's collected JSON response."""
        yield ExecutionEvent(
            type=ExecutionEventType.STARTED,
            public_message="Backend execution started",
            data={"correlation_id": request.correlation_id},
        )
        result = await self.run(
            request.prompt,
            agent=request.agent,
            workdir=request.workdir,
            model=request.model,
            variant=request.variant,
            session_id=request.session_id,
            startup_timeout=request.startup_timeout,
            timeout=request.timeout,
            env=request.env,
            files=request.files,
            correlation_id=request.correlation_id,
        )
        event_type = (
            ExecutionEventType.FAILED
            if result.error_type or result.returncode != 0
            else ExecutionEventType.COMPLETED
        )
        yield ExecutionEvent(
            type=event_type,
            public_message=(
                "Backend execution completed"
                if event_type is ExecutionEventType.COMPLETED
                else "Backend execution failed"
            ),
            session_id=result.session_id,
            error_type=result.error_type,
            result=result,
        )

    def run_detached(
        self,
        prompt: str,
        *,
        agent: str | None = None,
        workdir: Path | None = None,
        model: str | None = None,
        variant: str | None = None,
        log_path: Path | None = None,
    ) -> None:
        _ = variant  # Claude CLI does not expose a separate reasoning-effort flag.
        claude_bin = _find_claude()
        args = [claude_bin, "-p", "--output-format", "json"]

        if model:
            args += ["--model", self.resolve_alias(model)]

        # For detached runs, write agent prompt to a persistent file in workdir
        if agent and workdir:
            agent_file = _resolve_agent_file(agent, workdir)
            if agent_file:
                body = _extract_prompt_body(agent_file)
                prompt_file = workdir / ".claude" / ".tmp-agent-prompt.md"
                prompt_file.parent.mkdir(parents=True, exist_ok=True)
                prompt_file.write_text(body)
                args += ["--system-prompt-file", str(prompt_file)]

        args.extend(_get_permission_args())
        args.append(prompt)

        log_fh = open(log_path, "a") if log_path else None  # noqa: SIM115
        try:
            subprocess.Popen(
                args,
                stdout=log_fh or subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
                cwd=str(workdir) if workdir else None,
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
        claude_bin = _find_claude()
        args = [claude_bin, "-p", "--output-format", "json"]
        args.extend(_get_permission_args())
        args.append(prompt)

        start = time.monotonic()
        result = subprocess.run(  # noqa: S603
            args,
            timeout=timeout,
            cwd=str(workdir) if workdir else None,
        )
        elapsed = time.monotonic() - start

        adj_log(
            "backend",
            f"[claude-cli] run_sync completed in {elapsed:.1f}s | returncode={result.returncode}",
        )
        return result.returncode

    async def reap(self, adj_dir: Path) -> int:
        # Claude Code doesn't leak language-server processes
        return 0

    async def health_check(self, adj_dir: Path) -> bool:
        # Previously this also probed the CloudCLI web server's /health
        # endpoint. That native web server has been retired — adjutant's
        # own web/app is the remote access UI — so healthy now just means
        # "the claude binary is on PATH".
        _ = adj_dir  # unused — kept for protocol compatibility
        return self.find_binary() is not None

    async def list_models(self) -> str:
        return "haiku\nsonnet\nopus"

    def find_binary(self) -> str | None:
        try:
            return _find_claude()
        except BackendNotFoundError:
            return None

    def resolve_alias(self, alias: str) -> str:
        return _ALIASES.get(alias, alias)

    def translate_model_id(self, model_id: str) -> str:
        """Convert a model ID from another backend's format to this backend's."""
        return _FROM_OPENCODE.get(model_id, model_id)
