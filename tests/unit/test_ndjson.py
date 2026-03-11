"""Tests for adjutant.lib.ndjson — NDJSON parsing."""

from __future__ import annotations

from adjutant.lib.ndjson import NDJSONResult, check_model_not_found, parse_ndjson


class TestParseNdjson:
    """Test parse_ndjson() — NDJSON stream parsing."""

    def test_empty_input(self):
        result = parse_ndjson("")
        assert result.text == ""
        assert result.session_id is None
        assert result.error_type is None
        assert result.events == []

    def test_single_text_event(self):
        output = '{"type":"text","part":{"text":"Hello world"}}\n'
        result = parse_ndjson(output)
        assert result.text == "Hello world"

    def test_multiple_text_events_concatenated(self):
        output = (
            '{"type":"text","part":{"text":"Hello "}}\n{"type":"text","part":{"text":"world"}}\n'
        )
        result = parse_ndjson(output)
        assert result.text == "Hello world"

    def test_text_event_with_string_part(self):
        """part can be a string instead of an object."""
        output = '{"type":"text","part":"direct text"}\n'
        result = parse_ndjson(output)
        assert result.text == "direct text"

    def test_session_id_from_field(self):
        output = '{"type":"session.create","sessionID":"abc-123"}\n'
        result = parse_ndjson(output)
        assert result.session_id == "abc-123"

    def test_session_id_from_properties(self):
        output = '{"type":"session.create","properties":{"sessionID":"xyz-789"}}\n'
        result = parse_ndjson(output)
        assert result.session_id == "xyz-789"

    def test_first_session_id_wins(self):
        output = '{"type":"event","sessionID":"first"}\n{"type":"event","sessionID":"second"}\n'
        result = parse_ndjson(output)
        assert result.session_id == "first"

    def test_model_not_found_error_from_message(self):
        output = (
            '{"type":"error","error":{"name":"Error","data":{"message":"Model not found: foo"}}}\n'
        )
        result = parse_ndjson(output)
        assert result.error_type == "model_not_found"

    def test_model_not_found_error_from_name(self):
        output = '{"type":"error","error":{"name":"ModelNotFoundError","data":{}}}\n'
        result = parse_ndjson(output)
        assert result.error_type == "model_not_found"

    def test_generic_error(self):
        output = '{"type":"error","error":{"name":"SomeError","data":{}}}\n'
        result = parse_ndjson(output)
        assert result.error_type == "SomeError"

    def test_malformed_lines_skipped(self):
        output = 'not json at all\n{"type":"text","part":{"text":"OK"}}\n{"broken json\n'
        result = parse_ndjson(output)
        assert result.text == "OK"
        assert len(result.events) == 1

    def test_non_dict_lines_skipped(self):
        output = '"just a string"\n42\n[1, 2, 3]\n{"type":"text","part":{"text":"real"}}\n'
        result = parse_ndjson(output)
        assert result.text == "real"
        assert len(result.events) == 1

    def test_blank_lines_skipped(self):
        output = '\n\n{"type":"text","part":{"text":"OK"}}\n\n'
        result = parse_ndjson(output)
        assert result.text == "OK"

    def test_events_list_populated(self):
        output = (
            '{"type":"session.create","sessionID":"s1"}\n{"type":"text","part":{"text":"hi"}}\n'
        )
        result = parse_ndjson(output)
        assert len(result.events) == 2

    def test_error_with_non_dict_data(self):
        """error.data can be a string instead of dict."""
        output = '{"type":"error","error":{"name":"Err","data":"some string"}}\n'
        result = parse_ndjson(output)
        assert result.error_type == "Err"

    def test_error_with_no_name(self):
        output = '{"type":"error","error":{}}\n'
        result = parse_ndjson(output)
        assert result.error_type == "unknown_error"


class TestCheckModelNotFound:
    """Test check_model_not_found() — quick error detection."""

    def test_found_in_ndjson(self):
        output = '{"type":"error","error":{"name":"Error","data":{"message":"Model not found"}}}\n'
        assert check_model_not_found(output) is True

    def test_found_in_stderr(self):
        assert check_model_not_found("", stderr="ProviderModelNotFoundError: blah") is True

    def test_found_in_stderr_model_not_found(self):
        assert check_model_not_found("", stderr="Model not found") is True

    def test_not_found(self):
        output = '{"type":"text","part":{"text":"OK"}}\n'
        assert check_model_not_found(output, stderr="") is False

    def test_empty_inputs(self):
        assert check_model_not_found("", stderr="") is False
