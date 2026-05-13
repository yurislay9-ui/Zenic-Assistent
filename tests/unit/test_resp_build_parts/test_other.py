"""
Tests for build_partial_reasoning_response, build_error_response, and build_overloaded_response.
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.server.response_builder import (
    build_partial_reasoning_response,
    build_error_response,
    build_overloaded_response,
)


# ============================================================
#  build_partial_reasoning_response Tests
# ============================================================

class TestBuildPartialReasoningResponse:
    """Tests for build_partial_reasoning_response function."""

    def test_returns_dict(self, sample_data, sample_user_msg):
        """Should return a dictionary."""
        result = {"processing_time_ms": 100, "route": "DEEP_PATH", "criticality": 2}
        response = build_partial_reasoning_response(sample_data, result, sample_user_msg)
        assert isinstance(response, dict)

    def test_has_openai_compatible_fields(self, sample_data, sample_user_msg):
        """Should include OpenAI-compatible response fields."""
        result = {"partial_reasoning_payload": {"content": "Thinking..."}}
        response = build_partial_reasoning_response(sample_data, result, sample_user_msg)
        assert "id" in response
        assert "object" in response
        assert "choices" in response

    def test_tool_calls_in_message(self, sample_data, sample_user_msg):
        """Should include tool_calls in message when provided."""
        tool_calls = [{"id": "tc1", "type": "function", "function": {"name": "subdivide"}}]
        result = {
            "partial_reasoning_payload": {
                "tool_calls": tool_calls,
            },
            "processing_time_ms": 100,
        }
        response = build_partial_reasoning_response(sample_data, result, sample_user_msg)
        msg = response["choices"][0]["message"]
        assert "tool_calls" in msg
        assert len(msg["tool_calls"]) == 1

    def test_finish_reason_tool_calls(self, sample_data, sample_user_msg):
        """finish_reason should default to 'tool_calls'."""
        result = {"partial_reasoning_payload": {}}
        response = build_partial_reasoning_response(sample_data, result, sample_user_msg)
        assert response["choices"][0]["finish_reason"] == "tool_calls"

    def test_custom_finish_reason(self, sample_data, sample_user_msg):
        """Should respect custom finish_reason from payload."""
        result = {
            "partial_reasoning_payload": {
                "finish_reason": "stop",
            }
        }
        response = build_partial_reasoning_response(sample_data, result, sample_user_msg)
        assert response["choices"][0]["finish_reason"] == "stop"

    def test_zenic_metadata_partial_reasoning(self, sample_data, sample_user_msg):
        """zenic_metadata should indicate partial_reasoning."""
        result = {"processing_time_ms": 50, "route": "SURGICAL_PATH", "criticality": 3}
        response = build_partial_reasoning_response(sample_data, result, sample_user_msg)
        meta = response["zenic_metadata"]
        assert meta["partial_reasoning"] is True
        assert meta["status"] == "PARTIAL_REASONING"

    def test_content_from_payload(self, sample_data, sample_user_msg):
        """Should use content from partial_reasoning_payload."""
        result = {
            "partial_reasoning_payload": {
                "content": "Analyzing code structure...",
            }
        }
        response = build_partial_reasoning_response(sample_data, result, sample_user_msg)
        msg = response["choices"][0]["message"]
        assert msg["content"] == "Analyzing code structure..."

    def test_content_fallback_to_explanations(self, sample_data, sample_user_msg):
        """Should fallback to explanations when no content in payload."""
        result = {
            "partial_reasoning_payload": {},
            "explanations": ["Step 1 done"],
        }
        response = build_partial_reasoning_response(sample_data, result, sample_user_msg)
        content = response["choices"][0]["message"]["content"]
        assert content == "Step 1 done"

    def test_usage_metadata(self, sample_data, sample_user_msg):
        """Should use usage_metadata from result if available."""
        usage = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
        result = {
            "partial_reasoning_payload": {},
            "usage_metadata": usage,
        }
        response = build_partial_reasoning_response(sample_data, result, sample_user_msg)
        assert response["usage"] == usage


# ============================================================
#  build_error_response Tests
# ============================================================

class TestBuildErrorResponse:
    """Tests for build_error_response function."""

    def test_returns_dict(self):
        """Should return a dictionary."""
        response = build_error_response("Something went wrong")
        assert isinstance(response, dict)

    def test_has_openai_compatible_fields(self):
        """Should include OpenAI-compatible response fields."""
        response = build_error_response("Error occurred")
        assert "id" in response
        assert "object" in response
        assert "created" in response
        assert "model" in response
        assert "choices" in response
        assert "usage" in response

    def test_object_type(self):
        """object field should be 'chat.completion'."""
        response = build_error_response("Error")
        assert response["object"] == "chat.completion"

    def test_error_in_content(self):
        """Error message should appear in response content."""
        response = build_error_response("Division by zero")
        content = response["choices"][0]["message"]["content"]
        assert "Division by zero" in content

    def test_content_includes_error_header(self):
        """Content should include the internal error header."""
        response = build_error_response("Test error")
        content = response["choices"][0]["message"]["content"]
        assert "Internal Error" in content

    def test_content_includes_retry_suggestion(self):
        """Content should suggest reformulating the request."""
        response = build_error_response("Failed")
        content = response["choices"][0]["message"]["content"]
        assert "reformulating" in content.lower()

    def test_model_is_zenic(self):
        """model should be 'zenic-agents'."""
        response = build_error_response("Error")
        assert response["model"] == "zenic-agents"

    def test_finish_reason_stop(self):
        """finish_reason should be 'stop'."""
        response = build_error_response("Error")
        assert response["choices"][0]["finish_reason"] == "stop"

    def test_usage_zero_tokens(self):
        """usage should have zero tokens for errors."""
        response = build_error_response("Error")
        assert response["usage"]["prompt_tokens"] == 0
        assert response["usage"]["completion_tokens"] == 0
        assert response["usage"]["total_tokens"] == 0

    def test_role_assistant(self):
        """message role should be 'assistant'."""
        response = build_error_response("Error")
        assert response["choices"][0]["message"]["role"] == "assistant"

    def test_empty_error_message(self):
        """Should handle empty error message."""
        response = build_error_response("")
        assert isinstance(response, dict)
        assert "choices" in response

    def test_long_error_message(self):
        """Should handle very long error messages."""
        long_msg = "Error: " + "x" * 10000
        response = build_error_response(long_msg)
        assert isinstance(response, dict)


# ============================================================
#  build_overloaded_response Tests
# ============================================================

class TestBuildOverloadedResponse:
    """Tests for build_overloaded_response function."""

    def test_returns_dict(self):
        """Should return a dictionary."""
        response = build_overloaded_response()
        assert isinstance(response, dict)

    def test_has_error_field(self):
        """Should include 'error' key."""
        response = build_overloaded_response()
        assert "error" in response

    def test_error_type_server_overloaded(self):
        """Error type should be 'server_overloaded'."""
        response = build_overloaded_response()
        assert response["error"]["type"] == "server_overloaded"

    def test_error_message_mentions_ram(self):
        """Error message should mention RAM critical."""
        response = build_overloaded_response()
        assert "RAM" in response["error"]["message"]

    def test_error_message_mentions_retry(self):
        """Error message should suggest retrying."""
        response = build_overloaded_response()
        assert "retry" in response["error"]["message"].lower()

    def test_no_choices_field(self):
        """Overloaded response should not have choices (it's an error, not a completion)."""
        response = build_overloaded_response()
        assert "choices" not in response

    def test_consistent_structure(self):
        """Should have consistent structure across calls."""
        r1 = build_overloaded_response()
        r2 = build_overloaded_response()
        assert r1.keys() == r2.keys()
        assert r1["error"].keys() == r2["error"].keys()
