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
from pathlib import Path

from adjutant.core.backend import BackendCapabilities, BackendNotFoundError, LLMResult
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


def _get_permission_args() -> list[str]:
    """Build permission-related CLI args from config.

    Returns either --dangerously-skip-permissions (default "skip" mode)
    or --allowedTools with a whitelist ("allowlist" mode).
    """
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
            vision=False,
            model_listing=False,
            reaping=False,
            web_server=True,
            remote_session=False,
            streaming=False,
            cost_tracking=True,
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
        # Vision guard: Claude CLI has no native image input
        if files:
            image_files = [f for f in files if f.suffix.lower() in _IMAGE_EXTENSIONS]
            if image_files:
                return LLMResult(
                    text=(
                        "Vision (image analysis) is not supported on the Claude CLI backend. "
                        "Switch to the opencode backend for image analysis."
                    ),
                    error_type="vision_unsupported",
                )

        claude_bin = _find_claude()
        args = [claude_bin, "-p", "--output-format", "json"]

        if model:
            args += ["--model", self.resolve_alias(model)]

        # Agent prompt via --system-prompt-file
        tmp_prompt_file = None
        if agent and workdir:
            agent_file = _resolve_agent_file(agent, workdir)
            if agent_file:
                body = _extract_prompt_body(agent_file)
                tmp_prompt_file = tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False)
                tmp_prompt_file.write(body)
                tmp_prompt_file.close()
                args += ["--system-prompt-file", tmp_prompt_file.name]

        args.extend(_get_permission_args())

        if session_id:
            args += ["--resume", session_id]

        args.append(prompt)

        run_env = os.environ.copy()
        if env:
            run_env.update(env)

        start = time.monotonic()
        timed_out = False
        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=run_env,
                cwd=str(workdir) if workdir else None,
            )
            try:
                if timeout:
                    stdout_bytes, stderr_bytes = await asyncio.wait_for(
                        proc.communicate(), timeout=timeout
                    )
                else:
                    stdout_bytes, stderr_bytes = await proc.communicate()
            except TimeoutError:
                proc.terminate()
                try:
                    await asyncio.wait_for(proc.wait(), timeout=2.0)
                except TimeoutError:
                    proc.kill()
                    await proc.wait()
                timed_out = True
                stdout_bytes = b""
                stderr_bytes = b""
        finally:
            if tmp_prompt_file:
                Path(tmp_prompt_file.name).unlink(missing_ok=True)

        elapsed = time.monotonic() - start
        stdout = stdout_bytes.decode(errors="replace") if stdout_bytes else ""

        parsed = parse_claude_json(stdout)
        result = LLMResult(
            text=parsed.text,
            session_id=parsed.session_id,
            error_type=parsed.error_type,
            returncode=proc.returncode if proc.returncode is not None else -1,
            timed_out=timed_out,
            cost_usd=parsed.cost_usd,
        )
        if timed_out:
            result.error_type = "timeout"

        log_extra = f" | cost=${result.cost_usd:.4f}" if result.cost_usd else ""
        adj_log(
            "backend",
            f"[claude-cli] run completed in {elapsed:.1f}s"
            f" | model={model} agent={agent}"
            f" | error_type={result.error_type}{log_extra}",
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
        if not self.find_binary():
            return False
        # Check if CloudCLI web server is running
        from adjutant.core.process import read_pid_file

        pid_file = adj_dir / "state" / "cloudcli_web.pid"
        pid = read_pid_file(pid_file)
        if pid is None:
            return True  # No web server expected if PID file absent

        # PID alive — try HTTP health endpoint
        port = int(os.environ.get("CLOUDCLI_PORT", "3001"))
        try:
            import httpx

            with httpx.Client(timeout=3.0) as client:
                resp = client.get(f"http://localhost:{port}/health")
                data = resp.json()
                return data.get("status") == "ok"
        except Exception:  # noqa: BLE001 — network/parse errors are a health failure
            return False

    async def list_models(self) -> str:
        return (
            "Available models (Claude CLI):\n"
            "  haiku   — Claude Haiku 4.5 (fast, cheap)\n"
            "  sonnet  — Claude Sonnet 4.6 (balanced)\n"
            "  opus    — Claude Opus 4.6 (most capable)\n"
        )

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
