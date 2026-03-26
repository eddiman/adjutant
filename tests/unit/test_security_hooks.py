"""Tests for Claude CLI security hooks (.claude/hooks/).

Validates that the hook scripts correctly block .env access vectors
and allow legitimate operations.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

# Path to the hooks directory
HOOKS_DIR = Path(__file__).parent.parent.parent / ".claude" / "hooks"
BLOCK_ENV_ACCESS = HOOKS_DIR / "block-env-access.sh"
BLOCK_ENV_READ = HOOKS_DIR / "block-env-read.sh"


@pytest.mark.backend_claude_cli
class TestBlockEnvAccessHook:
    """Tests for block-env-access.sh (Bash tool hook)."""

    def _run_hook(self, command: str) -> subprocess.CompletedProcess[str]:
        """Run the hook with a simulated tool input containing the given command."""
        tool_input = json.dumps({"command": command})
        return subprocess.run(
            ["bash", str(BLOCK_ENV_ACCESS)],
            input=tool_input,
            capture_output=True,
            text=True,
        )

    # --- Should BLOCK ---

    def test_blocks_cat_env(self):
        result = self._run_hook("cat .env")
        assert result.returncode == 2

    def test_blocks_head_env(self):
        result = self._run_hook("head .env")
        assert result.returncode == 2

    def test_blocks_tail_env(self):
        result = self._run_hook("tail .env")
        assert result.returncode == 2

    def test_blocks_less_env(self):
        result = self._run_hook("less .env")
        assert result.returncode == 2

    def test_blocks_source_env(self):
        result = self._run_hook("source .env")
        assert result.returncode == 2

    def test_blocks_dot_source_env(self):
        result = self._run_hook(". .env")
        assert result.returncode == 2

    def test_blocks_printenv(self):
        result = self._run_hook("printenv")
        assert result.returncode == 2

    def test_blocks_env_dump(self):
        result = self._run_hook("env")
        assert result.returncode == 2

    def test_blocks_grep_env(self):
        result = self._run_hook("grep TOKEN .env")
        assert result.returncode == 2

    def test_blocks_awk_env(self):
        result = self._run_hook("awk -F= '{print $2}' .env")
        assert result.returncode == 2

    def test_blocks_sed_env(self):
        result = self._run_hook("sed -n '/TOKEN/p' .env")
        assert result.returncode == 2

    # --- Should ALLOW ---

    def test_allows_cat_regular_file(self):
        result = self._run_hook("cat README.md")
        assert result.returncode == 0

    def test_allows_cat_env_example(self):
        result = self._run_hook("cat .env.example")
        assert result.returncode == 0

    def test_allows_grep_on_regular_file(self):
        result = self._run_hook("grep TODO src/main.py")
        assert result.returncode == 0

    def test_allows_ls(self):
        result = self._run_hook("ls -la")
        assert result.returncode == 0

    def test_allows_python_command(self):
        result = self._run_hook("python -m adjutant status")
        assert result.returncode == 0

    def test_allows_empty_input(self):
        result = subprocess.run(
            ["bash", str(BLOCK_ENV_ACCESS)],
            input="{}",
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0


@pytest.mark.backend_claude_cli
class TestBlockEnvReadHook:
    """Tests for block-env-read.sh (Read tool hook)."""

    def _run_hook(self, file_path: str) -> subprocess.CompletedProcess[str]:
        """Run the hook with a simulated tool input containing the given file path."""
        tool_input = json.dumps({"file_path": file_path})
        return subprocess.run(
            ["bash", str(BLOCK_ENV_READ)],
            input=tool_input,
            capture_output=True,
            text=True,
        )

    # --- Should BLOCK ---

    def test_blocks_env(self):
        result = self._run_hook(".env")
        assert result.returncode == 2

    def test_blocks_nested_env(self):
        result = self._run_hook("path/to/.env")
        assert result.returncode == 2

    def test_blocks_absolute_env(self):
        result = self._run_hook("/home/user/project/.env")
        assert result.returncode == 2

    # --- Should ALLOW ---

    def test_allows_env_example(self):
        result = self._run_hook(".env.example")
        assert result.returncode == 0

    def test_allows_regular_file(self):
        result = self._run_hook("src/adjutant/core/config.py")
        assert result.returncode == 0

    def test_allows_yaml_file(self):
        result = self._run_hook("adjutant.yaml.example")
        assert result.returncode == 0

    def test_allows_markdown_file(self):
        result = self._run_hook("docs/guides/backends.md")
        assert result.returncode == 0

    def test_allows_empty_input(self):
        result = subprocess.run(
            ["bash", str(BLOCK_ENV_READ)],
            input="{}",
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0


class TestHookFilesExist:
    """Verify hook files exist and are executable."""

    def test_block_env_access_exists(self):
        assert BLOCK_ENV_ACCESS.is_file(), f"Missing: {BLOCK_ENV_ACCESS}"

    def test_block_env_read_exists(self):
        assert BLOCK_ENV_READ.is_file(), f"Missing: {BLOCK_ENV_READ}"

    def test_block_env_access_executable(self):
        import os

        assert os.access(BLOCK_ENV_ACCESS, os.X_OK), f"Not executable: {BLOCK_ENV_ACCESS}"

    def test_block_env_read_executable(self):
        import os

        assert os.access(BLOCK_ENV_READ, os.X_OK), f"Not executable: {BLOCK_ENV_READ}"

    def test_block_env_access_has_shebang(self):
        content = BLOCK_ENV_ACCESS.read_text()
        assert content.startswith("#!/"), f"Missing shebang in {BLOCK_ENV_ACCESS}"

    def test_block_env_read_has_shebang(self):
        content = BLOCK_ENV_READ.read_text()
        assert content.startswith("#!/"), f"Missing shebang in {BLOCK_ENV_READ}"
