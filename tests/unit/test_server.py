"""
Unit tests for src/server/ - Response Builder

Tests for the OpenAI-compatible response building functions.
"""

import pytest
from src.server.response_builder import (
    build_normal_response,
    build_partial_reasoning_response,
    build_error_response,
    build_overloaded_response,
)


@pytest.fixture
def sample_result():
    """Typical pipeline result."""
    return {
        "status": "SUCCESS",
        "code": "print('hello')",
        "hash": "abc123def456",
        "processing_time_ms": 150,
        "route": "SURGICAL",
        "criticality": 3,
        "solver_status": "SAT",
        "solver_proof": None,
        "mcts_simulations": 100,
        "mcts_depth_reached": 5,
        "ast_analysis": {"language": "python"},
        "explanations": ["Code generated for CREATE"],
        "warnings": [],
    }


@pytest.fixture
def sample_data():
    """Typical request data."""
    return {"model": "zenic-agents"}


class TestBuildNormalResponse:
    """Tests for build_normal_response."""

    def test_basic_structure(self, sample_data, sample_result):
        """Should return OpenAI-compatible structure."""
        resp = build_normal_response(sample_data, sample_result, "test msg")
        assert resp["object"] == "chat.completion"
        assert "choices" in resp
        assert "usage" in resp
        assert "zenic_metadata" in resp

    def test_content_includes_status(self, sample_data, sample_result):
        """Content should include the status."""
        resp = build_normal_response(sample_data, sample_result, "test msg")
        content = resp["choices"][0]["message"]["content"]
        assert "SUCCESS" in content

    def test_content_includes_code(self, sample_data, sample_result):
        """Content should include code block when present."""
        resp = build_normal_response(sample_data, sample_result, "test msg")
        content = resp["choices"][0]["message"]["content"]
        assert "```python" in content

    def test_metadata_fields(self, sample_data, sample_result):
        """Metadata should include all pipeline metrics."""
        resp = build_normal_response(sample_data, sample_result, "test msg")
        meta = resp["zenic_metadata"]
        assert meta["status"] == "SUCCESS"
        assert meta["processing_time_ms"] == 150
        assert meta["solver_status"] == "SAT"
        assert meta["mcts_simulations"] == 100

    def test_with_governor(self, sample_data, sample_result):
        """Should include RAM/CPU info when governor provided."""
        # Create a mock governor
        class MockGovernor:
            def get_status(self):
                return {"ram_usage_mb": 512, "ram_limit_mb": 2048,
                        "cpu_usage_pct": 25.0}

        resp = build_normal_response(sample_data, sample_result, "test",
                                     governor=MockGovernor())
        content = resp["choices"][0]["message"]["content"]
        assert "RAM" in content
        assert "CPU" in content
        assert resp["zenic_metadata"]["platform"] == "termux-proot"

    def test_without_governor(self, sample_data, sample_result):
        """Should work without governor (TUI mode)."""
        resp = build_normal_response(sample_data, sample_result, "test")
        assert "platform" not in resp["zenic_metadata"]

    def test_warnings_included(self, sample_data):
        """Should include warnings when present."""
        result = {**sample_data, "status": "SUCCESS", "code": "",
                  "warnings": ["Deprecation warning"], "hash": "N/A",
                  "processing_time_ms": 100, "route": "FAST",
                  "criticality": 1, "solver_status": "N/A",
                  "mcts_simulations": 0, "mcts_depth_reached": 0}
        resp = build_normal_response(sample_data, result, "test")
        content = resp["choices"][0]["message"]["content"]
        assert "Warnings" in content


class TestBuildPartialReasoningResponse:
    """Tests for build_partial_reasoning_response."""

    def test_basic_structure(self):
        """Should return OpenAI-compatible partial reasoning structure."""
        data = {"model": "zenic-agents"}
        result = {
            "partial_reasoning": True,
            "partial_reasoning_payload": {
                "content": "Subdividing task...",
                "tool_calls": [{"id": "tc1", "type": "function"}],
                "finish_reason": "tool_calls",
            },
            "processing_time_ms": 200,
            "route": "SURGICAL",
            "criticality": 3,
            "solver_status": "TIMEOUT",
        }
        resp = build_partial_reasoning_response(data, result, "test")
        assert resp["choices"][0]["finish_reason"] == "tool_calls"
        assert resp["zenic_metadata"]["partial_reasoning"] is True

    def test_tool_calls_present(self):
        """Should include tool_calls in the response."""
        data = {"model": "zenic-agents"}
        result = {
            "partial_reasoning": True,
            "partial_reasoning_payload": {
                "tool_calls": [{"id": "tc1"}],
            },
        }
        resp = build_partial_reasoning_response(data, result, "test")
        assert len(resp["choices"][0]["message"]["tool_calls"]) >= 1


class TestBuildErrorResponse:
    """Tests for build_error_response."""

    def test_basic_structure(self):
        """Should return OpenAI-compatible error structure."""
        resp = build_error_response("Something went wrong")
        assert resp["object"] == "chat.completion"
        assert "Internal Error" in resp["choices"][0]["message"]["content"]

    def test_error_message_included(self):
        """Should include the error message."""
        resp = build_error_response("test error msg")
        content = resp["choices"][0]["message"]["content"]
        assert "test error msg" in content

    def test_zero_usage(self):
        """Error responses should have zero usage."""
        resp = build_error_response("err")
        assert resp["usage"]["total_tokens"] == 0


class TestBuildOverloadedResponse:
    """Tests for build_overloaded_response."""

    def test_structure(self):
        """Should return server overloaded error."""
        resp = build_overloaded_response()
        assert resp["error"]["type"] == "server_overloaded"
        assert "RAM" in resp["error"]["message"]
