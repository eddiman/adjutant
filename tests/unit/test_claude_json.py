"""Tests for Claude Code JSON output parser."""

from __future__ import annotations

import json

import pytest

from adjutant.lib.claude_json import ClaudeJSONResult, _classify_claude_error, parse_claude_json

pytestmark = pytest.mark.backend_claude_cli


class TestParseClaude:
    def test_success(self):
        data = {
            "result": "Hello world",
            "session_id": "uuid-123",
            "is_error": False,
            "cost_usd": 0.0042,
        }
        r = parse_claude_json(json.dumps(data))
        assert r.text == "Hello world"
        assert r.session_id == "uuid-123"
        assert r.is_error is False
        assert r.error_type is None
        assert r.cost_usd == 0.0042

    def test_error_model_not_found(self):
        data = {"result": "Model not found: bad-model", "is_error": True}
        r = parse_claude_json(json.dumps(data))
        assert r.is_error is True
        assert r.error_type == "model_not_found"

    def test_error_auth_failure(self):
        data = {"result": "Not authenticated. Please log in with `claude login`.", "is_error": True}
        r = parse_claude_json(json.dumps(data))
        assert r.error_type == "auth_failure"

    def test_error_rate_limited(self):
        data = {"result": "Rate limit exceeded. Too many requests.", "is_error": True}
        r = parse_claude_json(json.dumps(data))
        assert r.error_type == "rate_limited"

    def test_error_context_overflow(self):
        data = {"result": "Context length exceeded, max tokens reached", "is_error": True}
        r = parse_claude_json(json.dumps(data))
        assert r.error_type == "context_overflow"

    def test_error_permission_denied(self):
        data = {"result": "Permission denied: cannot write to /etc/passwd", "is_error": True}
        r = parse_claude_json(json.dumps(data))
        assert r.error_type == "permission_denied"

    def test_error_unclassified(self):
        data = {"result": "Something weird happened", "is_error": True}
        r = parse_claude_json(json.dumps(data))
        assert r.error_type == "error"

    def test_empty_input(self):
        r = parse_claude_json("")
        assert r.error_type == "parse_error"

    def test_invalid_json(self):
        r = parse_claude_json("not json at all")
        assert r.error_type == "parse_error"

    def test_non_dict_json(self):
        r = parse_claude_json('"just a string"')
        assert r.error_type == "parse_error"

    def test_missing_fields_use_defaults(self):
        r = parse_claude_json("{}")
        assert r.text == ""
        assert r.session_id is None
        assert r.is_error is False
        assert r.error_type is None
        assert r.cost_usd is None


class TestClassifyError:
    def test_model_not_found(self):
        assert _classify_claude_error("Model not found: xyz") == "model_not_found"
        assert _classify_claude_error("Invalid model specified") == "model_not_found"

    def test_auth_variants(self):
        assert _classify_claude_error("Not authenticated") == "auth_failure"
        assert _classify_claude_error("Authentication required") == "auth_failure"
        assert _classify_claude_error("Unauthorized access") == "auth_failure"
        assert _classify_claude_error("Subscription expired") == "auth_failure"
        assert _classify_claude_error("Please log in first") == "auth_failure"

    def test_rate_limit_variants(self):
        assert _classify_claude_error("Rate limit hit") == "rate_limited"
        assert _classify_claude_error("Too many requests") == "rate_limited"
        assert _classify_claude_error("Request throttled") == "rate_limited"

    def test_context_overflow_variants(self):
        assert _classify_claude_error("Context length exceeded") == "context_overflow"
        assert _classify_claude_error("Input too long") == "context_overflow"
        assert _classify_claude_error("Max tokens exceeded") == "context_overflow"
        assert _classify_claude_error("Token limit reached") == "context_overflow"

    def test_permission_denied(self):
        assert _classify_claude_error("Permission denied") == "permission_denied"
        assert _classify_claude_error("Operation not allowed") == "permission_denied"

    def test_unknown_fallback(self):
        assert _classify_claude_error("CPU on fire") == "error"
