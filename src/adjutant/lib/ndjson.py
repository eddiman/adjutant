"""NDJSON parser for OpenCode output.

OpenCode with ``--format json`` produces NDJSON (newline-delimited JSON).
This module extracts:
- Accumulated text from ``{"type": "text"}`` events
- Session ID from ``session.create`` events
- Model-not-found errors from error events

Matches the parsing patterns in bash chat.sh and query.sh.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field


@dataclass
class NDJSONResult:
    """Parsed result from an NDJSON stream."""

    text: str = ""
    session_id: str | None = None
    error_type: str | None = None
    events: list[dict] = field(default_factory=list)


def parse_ndjson(output: str) -> NDJSONResult:
    """Parse NDJSON output from opencode.

    Handles:
    - Text accumulation from ``{"type": "text"}`` events
    - Session ID from events with ``sessionID`` field
    - ModelNotFound detection from error events
    - Malformed lines are silently skipped (matches bash behavior)

    Args:
        output: Raw NDJSON string (newline-delimited JSON lines).

    Returns:
        NDJSONResult with accumulated text, session_id, and error info.
    """
    result = NDJSONResult()
    text_parts: list[str] = []

    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue  # Skip malformed lines

        if not isinstance(record, dict):
            continue

        result.events.append(record)

        # Extract session ID (first one wins)
        if result.session_id is None:
            sid = record.get("sessionID")
            if sid:
                result.session_id = str(sid)

        # Check for session.create event (also carries session ID)
        if record.get("type") == "session.create":
            properties = record.get("properties", {})
            if isinstance(properties, dict):
                sid = properties.get("sessionID")
                if sid and result.session_id is None:
                    result.session_id = str(sid)

        # Check for errors — specifically model-not-found
        if record.get("type") == "error":
            error = record.get("error", {})
            if isinstance(error, dict):
                name = error.get("name", "")
                data = error.get("data", {})
                msg = data.get("message", "") if isinstance(data, dict) else ""

                if "Model not found" in msg or "ModelNotFound" in name:
                    result.error_type = "model_not_found"
                elif not result.error_type:
                    result.error_type = name or "unknown_error"

        # Accumulate text from text events
        if record.get("type") == "text":
            part = record.get("part", {})
            if isinstance(part, dict):
                text_parts.append(part.get("text", ""))
            elif isinstance(part, str):
                text_parts.append(part)

    result.text = "".join(text_parts)
    return result


def check_model_not_found(output: str, stderr: str = "") -> bool:
    """Quick check for model-not-found errors in output or stderr.

    Checks both the NDJSON stream and raw stderr for the error pattern.
    Matches bash behavior of checking both channels.

    Args:
        output: NDJSON stdout from opencode.
        stderr: Raw stderr from opencode.

    Returns:
        True if a model-not-found error was detected.
    """
    # Check NDJSON events
    result = parse_ndjson(output)
    if result.error_type == "model_not_found":
        return True

    # Check raw stderr
    if "Model not found" in stderr or "ProviderModelNotFoundError" in stderr:
        return True

    return False
