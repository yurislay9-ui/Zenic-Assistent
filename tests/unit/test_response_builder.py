"""
Unit tests for Response Builder

Tests the OpenAI-compatible response builder functions:
- build_normal_response
- build_partial_reasoning_response
- build_error_response
- build_overloaded_response
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from src.server.response_builder import (
    build_normal_response,
    build_partial_reasoning_response,
    build_error_response,
    build_overloaded_response,
)


# ============================================================
#  Fixtures (shared with sub-modules)
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


from .test_resp_build_parts import *  # noqa: F401,F403
