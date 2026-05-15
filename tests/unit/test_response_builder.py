"""
Unit tests for Response Builder

NOTE: src.server.response_builder has been removed (server module deleted).
These tests are disabled. The response builder was part of the OpenAI-compatible
API server which is no longer available.
"""

import pytest

# Server module removed — response builder no longer available
# from src.server.response_builder import (
#     build_normal_response,
#     build_partial_reasoning_response,
#     build_error_response,
#     build_overloaded_response,
# )

pytestmark = pytest.mark.skip(reason="src.server.response_builder removed — server module deleted")


# ============================================================
#  Fixtures (kept for sub-module compatibility)
# ============================================================

@pytest.fixture
def sample_data():
    """Sample request data dict."""
    return {"model": "zenic-agents", "messages": [{"role": "user", "content": "hello"}]}


@pytest.fixture
def sample_result():
    """Sample orchestrator result dict."""
    return {
        "status": "PASS",
        "explanations": ["Code generated successfully"],
        "code": "def hello():\n    return 'world'",
        "warnings": [],
        "cache_source": "",
        "cache_hits": 0,
        "processing_time_ms": 150,
        "route": "FAST_PATH",
        "hash": "abc123",
        "solver_status": "PROVEN",
        "mcts_simulations": 50,
        "mcts_depth_reached": 3,
        "paths_explored": 10,
        "paths_pruned": 2,
        "solver_proof": "All constraints satisfied",
        "criticality": 1,
        "ast_analysis": {"language": "python"},
    }


@pytest.fixture
def sample_user_msg():
    """Sample user message."""
    return "Generate a hello world function"

# Sub-module imports disabled — response builder removed
# from .test_resp_build_parts import *  # noqa: F401,F403
