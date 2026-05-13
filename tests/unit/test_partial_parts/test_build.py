"""Tests for build_partial_reasoning_response."""

import time
import pytest
from unittest.mock import MagicMock

from src.core.partial_reasoning import PartialReasoningManager
from ._fixtures import mock_orchestrator, mock_intent, mock_routing, mock_plan, mock_trial, manager


class TestBuildPartialReasoningResponse:
    """Tests for building partial reasoning responses."""

    def test_returns_partial_reasoning_status(self, manager, mock_intent, mock_routing,
                                              mock_plan, mock_trial):
        """Response should have status PARTIAL_REASONING."""
        result = manager.build_partial_reasoning_response(
            intent=mock_intent,
            routing=mock_routing,
            plan=mock_plan,
            ast_analysis={"complexity": "high"},
            trial=mock_trial,
            start_time=time.time(),
        )
        assert result["status"] == "PARTIAL_REASONING"
        assert result["partial_reasoning"] is True

    def test_includes_resumption_token(self, manager, mock_intent, mock_routing,
                                       mock_plan, mock_trial):
        """Response should include a resumption token."""
        result = manager.build_partial_reasoning_response(
            intent=mock_intent, routing=mock_routing, plan=mock_plan,
            ast_analysis={}, trial=mock_trial, start_time=time.time(),
        )
        assert "resumption" in result
        assert "token" in result["resumption"]
        assert len(result["resumption"]["token"]) > 0

    def test_stores_resumption_state(self, manager, mock_intent, mock_routing,
                                     mock_plan, mock_trial, mock_orchestrator):
        """Resumption state should be stored in the orchestrator."""
        result = manager.build_partial_reasoning_response(
            intent=mock_intent, routing=mock_routing, plan=mock_plan,
            ast_analysis={}, trial=mock_trial, start_time=time.time(),
        )
        token = result["resumption"]["token"]
        assert token in mock_orchestrator._pending_resumptions
        state = mock_orchestrator._pending_resumptions[token]
        assert state["original_intent"]["op"] == "CREATE"
        assert state["original_intent"]["target"] == "auth.py"

    def test_includes_tool_calls(self, manager, mock_intent, mock_routing,
                                 mock_plan, mock_trial):
        """Response should include zenith_mcts_plan tool calls."""
        result = manager.build_partial_reasoning_response(
            intent=mock_intent, routing=mock_routing, plan=mock_plan,
            ast_analysis={}, trial=mock_trial, start_time=time.time(),
        )
        payload = result["partial_reasoning_payload"]
        assert "tool_calls" in payload
        assert len(payload["tool_calls"]) >= 1
        assert payload["tool_calls"][0]["function"]["name"] == "zenith_mcts_plan"

    def test_includes_solver_type(self, manager, mock_intent, mock_routing,
                                  mock_plan, mock_trial):
        """Response should include solver type from plan."""
        result = manager.build_partial_reasoning_response(
            intent=mock_intent, routing=mock_routing, plan=mock_plan,
            ast_analysis={}, trial=mock_trial, start_time=time.time(),
        )
        assert "Z3" in result["explanations"][0] or "SMT" in result["explanations"][0]

    def test_includes_usage_metadata(self, manager, mock_intent, mock_routing,
                                     mock_plan, mock_trial):
        """Response should include usage_metadata with k-path info."""
        result = manager.build_partial_reasoning_response(
            intent=mock_intent, routing=mock_routing, plan=mock_plan,
            ast_analysis={}, trial=mock_trial, start_time=time.time(),
        )
        assert "usage_metadata" in result
        assert result["usage_metadata"]["zenith_k_path_eval"] == 50
