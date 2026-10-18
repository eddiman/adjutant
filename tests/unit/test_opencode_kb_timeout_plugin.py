"""Installed-runtime checks for the scoped OpenCode KB timeout hook."""

from __future__ import annotations

import json
import pathlib
import shutil
import subprocess

import pytest

PLUGIN = pathlib.Path(__file__).parents[2] / ".opencode" / "plugins" / "adjutant-kb-timeout.js"


def _run_hook(tmp_path: pathlib.Path, command: str) -> dict[str, object]:
    if shutil.which("node") is None:
        pytest.skip("Node.js is not installed")
    helper = tmp_path / "adjutant"
    helper.write_text(
        "#!/bin/sh\n"
        "printf '%s\\n' "
        "'{\"attempt_id\":\"attempt-1\",\"deadline_at\":9999999999,"
        "\"operation_id\":\"op-parent\",\"timeout_ms\":321000}'\n"
    )
    helper.chmod(0o755)
    script = """
import { pathToFileURL } from 'node:url';
const plugin = await import(pathToFileURL(process.argv[1]));
const hooks = await plugin.AdjutantKbTimeout({directory: process.argv[2]});
const output = {args: {command: process.argv[3]}};
try {
  await hooks['tool.execute.before'](
    {tool: 'bash', sessionID: 'ses-1', callID: 'call-1'}, output,
  );
  console.log(JSON.stringify({ok: true, args: output.args}));
} catch (error) {
  console.log(JSON.stringify({ok: false, error: String(error)}));
}
"""
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script, str(PLUGIN), str(tmp_path), command],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def test_hook_extends_only_recognized_standalone_kb_command(
    tmp_path: pathlib.Path,
) -> None:
    result = _run_hook(
        tmp_path,
        'ADJUTANT_PARENT_OPERATION_ID=op-parent ./adjutant kb query notes "Question?"',
    )

    assert result["ok"] is True
    args = result["args"]
    assert isinstance(args, dict)
    assert args["timeout"] == 321000
    assert "ADJUTANT_ORIGIN_SESSION_ID=ses-1" in args["command"]
    assert "ADJUTANT_ORIGIN_TOOL_CALL_ID=call-1" in args["command"]


def test_hook_leaves_unrelated_shell_command_unchanged(tmp_path: pathlib.Path) -> None:
    result = _run_hook(tmp_path, "python long_task.py")

    assert result == {"ok": True, "args": {"command": "python long_task.py"}}


def test_hook_accepts_shell_metacharacters_inside_quoted_argument(
    tmp_path: pathlib.Path,
) -> None:
    result = _run_hook(
        tmp_path,
        'ADJUTANT_PARENT_OPERATION_ID=op-parent ./adjutant kb query notes "R&D; status"',
    )

    assert result["ok"] is True
    assert result["args"]["timeout"] == 321000


def test_hook_rejects_compound_command_on_privileged_path(tmp_path: pathlib.Path) -> None:
    result = _run_hook(
        tmp_path,
        "ADJUTANT_PARENT_OPERATION_ID=op-parent ./adjutant kb query notes question | tee out",
    )

    assert result["ok"] is False
    assert "standalone" in str(result["error"])
