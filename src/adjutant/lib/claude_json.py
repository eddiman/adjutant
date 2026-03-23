"""Claude Code ``--output-format json`` parser.

Claude Code's ``-p --output-format json`` emits a single JSON object:

    {
      "result": "The assembled text response",
      "session_id": "uuid-string",
      "is_error": false,
      "cost_usd": 0.0042,
      "usage": {"input_tokens": 1234, "output_tokens": 567}
    }
"""

from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass
class ClaudeJSONResult:
    """Parsed result from Claude Code JSON output."""

    text: str = ""
    session_id: str | None = None
    error_type: str | None = None
    is_error: bool = False
    cost_usd: float | None = None


def parse_claude_json(output: str) -> ClaudeJSONResult:
    """Parse Claude Code ``--output-format json`` output.

    Args:
        output: Raw stdout from ``claude -p --output-format json``.

    Returns:
        ClaudeJSONResult with extracted fields.
    """
    if not output.strip():
        return ClaudeJSONResult(error_type="parse_error")

    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        return ClaudeJSONResult(error_type="parse_error")

    if not isinstance(data, dict):
        return ClaudeJSONResult(error_type="parse_error")

    is_error = data.get("is_error", False)
    error_type = None
    if is_error:
        error_type = _classify_claude_error(data.get("result", ""))

    return ClaudeJSONResult(
        text=data.get("result", ""),
        session_id=data.get("session_id"),
        is_error=is_error,
        cost_usd=data.get("cost_usd"),
        error_type=error_type,
    )


def _classify_claude_error(result_text: str) -> str:
    """Map Claude Code error text to the common error taxonomy.

    Claude Code's --output-format json sets is_error=true and puts the error
    description in the result field. We pattern-match on known error messages
    to classify into actionable error types.
    """
    text = result_text.lower()

    if "model not found" in text or "invalid model" in text:
        return "model_not_found"

    if any(
        s in text
        for s in [
            "not authenticated",
            "authentication",
            "login required",
            "unauthorized",
            "forbidden",
            "subscription",
            "please log in",
            "session expired",
        ]
    ):
        return "auth_failure"

    if any(s in text for s in ["rate limit", "too many requests", "throttl", "capacity"]):
        return "rate_limited"

    if any(
        s in text
        for s in ["context length", "too long", "max tokens", "context window", "token limit"]
    ):
        return "context_overflow"

    if any(s in text for s in ["permission denied", "not allowed", "permission"]):
        return "permission_denied"

    return "error"
