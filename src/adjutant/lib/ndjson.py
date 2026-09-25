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
from typing import Any


@dataclass
class NDJSONResult:
    """Parsed result from an NDJSON stream."""

    text: str = ""
    session_id: str | None = None
    error_type: str | None = None
    events: list[dict[str, Any]] = field(default_factory=list)


class IncrementalNDJSONParser:
    """Parse OpenCode records as lines arrive while bounding retained events."""

    def __init__(self, *, retain_events: int | None = None) -> None:
        self._retain_events = retain_events
        self._events: list[dict[str, Any]] = []
        self._text_parts: list[str] = []
        self._session_id: str | None = None
        self._error_type: str | None = None

    def feed_line(self, line: str) -> dict[str, Any] | None:
        """Consume one line and return its JSON object when valid."""
        line = line.strip()
        if not line:
            return None
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            return None
        if not isinstance(record, dict):
            return None

        self._events.append(record)
        if self._retain_events is not None and len(self._events) > self._retain_events:
            del self._events[: len(self._events) - self._retain_events]

        if self._session_id is None:
            session_id = record.get("sessionID")
            if session_id:
                self._session_id = str(session_id)
        if record.get("type") == "session.create":
            properties = record.get("properties", {})
            if isinstance(properties, dict):
                session_id = properties.get("sessionID")
                if session_id and self._session_id is None:
                    self._session_id = str(session_id)

        if record.get("type") == "error":
            error = record.get("error", {})
            if isinstance(error, dict):
                name = error.get("name", "")
                data = error.get("data", {})
                message = data.get("message", "") if isinstance(data, dict) else ""
                if "Model not found" in message or "ModelNotFound" in name:
                    self._error_type = "model_not_found"
                elif not self._error_type:
                    self._error_type = name or "unknown_error"

        if record.get("type") == "text":
            part = record.get("part", {})
            if isinstance(part, dict):
                self._text_parts.append(str(part.get("text", "")))
            elif isinstance(part, str):
                self._text_parts.append(part)
        return record

    def result(self) -> NDJSONResult:
        """Return the accumulated semantic result."""
        return NDJSONResult(
            text="".join(self._text_parts),
            session_id=self._session_id,
            error_type=self._error_type,
            events=list(self._events),
        )


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
    parser = IncrementalNDJSONParser()
    for line in output.splitlines():
        parser.feed_line(line)
    return parser.result()


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
    return bool("Model not found" in stderr or "ProviderModelNotFoundError" in stderr)
