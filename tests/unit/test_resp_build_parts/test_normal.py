"""
Tests for build_normal_response function.
"""

import os
import sys
import time
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.server.response_builder import build_normal_response


class TestBuildNormalResponse:
    """Tests for build_normal_response function."""

    def test_returns_dict(self, sample_data, sample_result, sample_user_msg):
        """Should return a dictionary."""
        response = build_normal_response(sample_data, sample_result, sample_user_msg)
        assert isinstance(response, dict)

    def test_has_openai_compatible_fields(self, sample_data, sample_result, sample_user_msg):
        """Should include OpenAI-compatible response fields."""
        response = build_normal_response(sample_data, sample_result, sample_user_msg)
        assert "id" in response
        assert "object" in response
        assert "created" in response
        assert "model" in response
        assert "choices" in response
        assert "usage" in response

    def test_object_type(self, sample_data, sample_result, sample_user_msg):
        """object field should be 'chat.completion'."""
        response = build_normal_response(sample_data, sample_result, sample_user_msg)
        assert response["object"] == "chat.completion"

    def test_model_field(self, sample_data, sample_result, sample_user_msg):
        """model field should match data model or default."""
        response = build_normal_response(sample_data, sample_result, sample_user_msg)
        assert response["model"] == "zenic-agents"

    def test_model_default(self, sample_result, sample_user_msg):
        """Should default to 'zenic-agents' when data has no model."""
        data = {}
        response = build_normal_response(data, sample_result, sample_user_msg)
        assert response["model"] == "zenic-agents"

    def test_choices_structure(self, sample_data, sample_result, sample_user_msg):
        """choices should be a list with proper structure."""
        response = build_normal_response(sample_data, sample_result, sample_user_msg)
        assert isinstance(response["choices"], list)
        assert len(response["choices"]) >= 1
        choice = response["choices"][0]
        assert "index" in choice
        assert "message" in choice
        assert "finish_reason" in choice
        assert choice["finish_reason"] == "stop"

    def test_message_structure(self, sample_data, sample_result, sample_user_msg):
        """message should have role and content."""
        response = build_normal_response(sample_data, sample_result, sample_user_msg)
        msg = response["choices"][0]["message"]
        assert msg["role"] == "assistant"
        assert isinstance(msg["content"], str)
        assert len(msg["content"]) > 0

    def test_usage_structure(self, sample_data, sample_result, sample_user_msg):
        """usage should have prompt_tokens, completion_tokens, total_tokens."""
        response = build_normal_response(sample_data, sample_result, sample_user_msg)
        usage = response["usage"]
        assert "prompt_tokens" in usage
        assert "completion_tokens" in usage
        assert "total_tokens" in usage
        assert usage["total_tokens"] == usage["prompt_tokens"] + usage["completion_tokens"]

    def test_zenic_metadata_present(self, sample_data, sample_result, sample_user_msg):
        """Should include zenic_metadata in response."""
        response = build_normal_response(sample_data, sample_result, sample_user_msg)
        assert "zenic_metadata" in response
        meta = response["zenic_metadata"]
        assert meta["status"] == "PASS"
        assert meta["hash"] == "abc123"
        assert meta["processing_time_ms"] == 150

    def test_zenic_metadata_solver_info(self, sample_data, sample_result, sample_user_msg):
        """zenic_metadata should include solver type and status."""
        response = build_normal_response(sample_data, sample_result, sample_user_msg)
        meta = response["zenic_metadata"]
        assert "solver_type" in meta
        assert meta["solver_status"] == "PROVEN"

    def test_zenic_metadata_mcts_info(self, sample_data, sample_result, sample_user_msg):
        """zenic_metadata should include MCTS simulation info."""
        response = build_normal_response(sample_data, sample_result, sample_user_msg)
        meta = response["zenic_metadata"]
        assert meta["mcts_simulations"] == 50
        assert meta["mcts_depth_reached"] == 3

    def test_zenic_metadata_symbolic_execution(self, sample_data, sample_result, sample_user_msg):
        """zenic_metadata should flag symbolic_execution as True."""
        response = build_normal_response(sample_data, sample_result, sample_user_msg)
        assert response["zenic_metadata"]["symbolic_execution"] is True

    def test_content_includes_status(self, sample_data, sample_result, sample_user_msg):
        """Response content should include the status."""
        response = build_normal_response(sample_data, sample_result, sample_user_msg)
        content = response["choices"][0]["message"]["content"]
        assert "PASS" in content

    def test_content_includes_code(self, sample_data, sample_result, sample_user_msg):
        """Response content should include generated code block."""
        response = build_normal_response(sample_data, sample_result, sample_user_msg)
        content = response["choices"][0]["message"]["content"]
        assert "```" in content
        assert "hello" in content

    def test_content_includes_explanations(self, sample_data, sample_result, sample_user_msg):
        """Response content should include explanations."""
        response = build_normal_response(sample_data, sample_result, sample_user_msg)
        content = response["choices"][0]["message"]["content"]
        assert "Code generated successfully" in content

    def test_with_warnings(self, sample_data, sample_user_msg):
        """Should include warnings in response content."""
        result = {
            "status": "PASS",
            "warnings": ["Potential issue detected"],
            "processing_time_ms": 100,
            "route": "FAST_PATH",
            "hash": "xyz",
            "solver_status": "HEURISTIC",
            "mcts_simulations": 0,
            "mcts_depth_reached": 0,
            "paths_explored": 0,
            "paths_pruned": 0,
            "criticality": 1,
        }
        response = build_normal_response(sample_data, result, sample_user_msg)
        content = response["choices"][0]["message"]["content"]
        assert "Warning" in content

    def test_with_cache_hit(self, sample_data, sample_user_msg):
        """Should include cache hit info when present."""
        result = {
            "status": "PASS",
            "cache_source": "memory",
            "cache_hits": 5,
            "processing_time_ms": 10,
            "route": "FAST_PATH",
            "hash": "h1",
            "solver_status": "N/A",
            "mcts_simulations": 0,
            "mcts_depth_reached": 0,
            "paths_explored": 0,
            "paths_pruned": 0,
            "criticality": 1,
        }
        response = build_normal_response(sample_data, result, sample_user_msg)
        content = response["choices"][0]["message"]["content"]
        assert "Cache hit" in content

    def test_with_governor(self, sample_data, sample_result, sample_user_msg):
        """Should include resource info when governor is provided."""
        class MockGovernor:
            def get_status(self):
                return {
                    "ram_usage_mb": 500,
                    "ram_limit_mb": 2048,
                    "cpu_usage_pct": 30.0,
                }

        response = build_normal_response(
            sample_data, sample_result, sample_user_msg, governor=MockGovernor()
        )
        content = response["choices"][0]["message"]["content"]
        assert "RAM" in content
        assert "CPU" in content
        assert response["zenic_metadata"]["platform"] == "termux-proot"

    def test_without_governor(self, sample_data, sample_result, sample_user_msg):
        """Should not include resource info when no governor."""
        response = build_normal_response(sample_data, sample_result, sample_user_msg)
        content = response["choices"][0]["message"]["content"]
        assert "platform" not in response["zenic_metadata"]

    def test_id_starts_with_zenic(self, sample_data, sample_result, sample_user_msg):
        """Response ID should start with "zenic-"."""
        response = build_normal_response(sample_data, sample_result, sample_user_msg)
        assert response["id"].startswith('zenic-')

    def test_created_is_timestamp(self, sample_data, sample_result, sample_user_msg):
        """created field should be a valid timestamp."""
        response = build_normal_response(sample_data, sample_result, sample_user_msg)
        now = int(time.time())
        assert abs(response["created"] - now) <= 5
