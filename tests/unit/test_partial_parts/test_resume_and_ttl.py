"""Tests for resume_from_partial and TTL expiration."""

import asyncio
import time
import pytest
from unittest.mock import MagicMock, AsyncMock

from src.core.partial_reasoning import PartialReasoningManager
from ._fixtures import mock_orchestrator, mock_intent, mock_routing, mock_plan, mock_trial, manager


class TestResumeFromPartial:
    """Tests for resuming from partial reasoning state."""

    def test_invalid_token_returns_error(self, manager, mock_orchestrator):
        """Resuming with invalid token should return error."""
        result = asyncio.run(
            manager.resume_from_partial("nonexistent_token")
        )
        assert result["status"] == "ERROR"
        assert "Invalid or expired" in result["error"]

    def test_resume_with_all_subtasks_succeeded(self, manager, mock_orchestrator,
                                                 mock_intent, mock_routing,
                                                 mock_plan, mock_trial):
        """When all subtasks already succeeded, resume should validate and succeed."""
        result = manager.build_partial_reasoning_response(
            intent=mock_intent, routing=mock_routing, plan=mock_plan,
            ast_analysis={}, trial=mock_trial, start_time=time.time(),
        )
        token = result["resumption"]["token"]
        state = mock_orchestrator._pending_resumptions[token]
        state["subtask_results"] = [
            {"status": "SUCCESS", "code": "pass"},
            {"status": "CACHED", "code": "pass"},
        ]
        trial_pass = MagicMock()
        trial_pass.status = "PASS"
        mock_orchestrator.sandbox.validate_code = AsyncMock(return_value=trial_pass)
        resume_result = asyncio.run(
            manager.resume_from_partial(token)
        )
        assert resume_result["status"] == "SUCCESS"

    def test_resume_with_failed_subtasks_reexecutes(self, manager, mock_orchestrator,
                                                     mock_intent, mock_routing,
                                                     mock_plan, mock_trial):
        """When some subtasks failed, resume should re-execute them."""
        result = manager.build_partial_reasoning_response(
            intent=mock_intent, routing=mock_routing, plan=mock_plan,
            ast_analysis={}, trial=mock_trial, start_time=time.time(),
        )
        token = result["resumption"]["token"]
        state = mock_orchestrator._pending_resumptions[token]
        state["subtask_results"] = [
            {"status": "SUCCESS", "code": "pass"},
            {"status": "FAILED", "code": "", "message": "error"},
        ]
        mock_orchestrator._abortive.execute_subtask = AsyncMock(return_value={
            "status": "SUCCESS", "code": "def hello(): pass"
        })
        trial_pass = MagicMock()
        trial_pass.status = "PASS"
        mock_orchestrator.sandbox.validate_code = AsyncMock(return_value=trial_pass)
        resume_result = asyncio.run(
            manager.resume_from_partial(token)
        )
        mock_orchestrator._abortive.execute_subtask.assert_called()

    def test_resume_specific_subtask_index(self, manager, mock_orchestrator,
                                           mock_intent, mock_routing,
                                           mock_plan, mock_trial):
        """Resuming with subtask_index should only re-execute that subtask."""
        result = manager.build_partial_reasoning_response(
            intent=mock_intent, routing=mock_routing, plan=mock_plan,
            ast_analysis={}, trial=mock_trial, start_time=time.time(),
        )
        token = result["resumption"]["token"]
        state = mock_orchestrator._pending_resumptions[token]
        state["subtask_results"] = [
            {"status": "SUCCESS", "code": "pass"},
            {"status": "FAILED", "code": ""},
        ]
        mock_orchestrator._abortive.execute_subtask = AsyncMock(return_value={
            "status": "SUCCESS", "code": "def fixed(): pass"
        })
        trial_pass = MagicMock()
        trial_pass.status = "PASS"
        mock_orchestrator.sandbox.validate_code = AsyncMock(return_value=trial_pass)
        resume_result = asyncio.run(
            manager.resume_from_partial(token, subtask_index=1)
        )
        mock_orchestrator._abortive.execute_subtask.assert_called_once()

    def test_resume_deserializes_dict_subtasks(self, manager, mock_orchestrator,
                                               mock_intent, mock_routing,
                                               mock_plan, mock_trial):
        """Resume should reconstruct SubtaskDescriptors from dict representations."""
        result = manager.build_partial_reasoning_response(
            intent=mock_intent, routing=mock_routing, plan=mock_plan,
            ast_analysis={}, trial=mock_trial, start_time=time.time(),
        )
        token = result["resumption"]["token"]
        state = mock_orchestrator._pending_resumptions[token]
        state["subtasks"] = [
            {"message": "Isolate module", "target": "auth.py",
             "operation": "CREATE", "goal": "BUG_FIX",
             "solver_insights": {}, "mcts_hints": [],
             "parent_violations": [], "parent_context": {}, "depth": 0},
            {"message": "Apply mutation", "target": "auth.py",
             "operation": "REFACTOR", "goal": "COMPLEXITY_REDUCTION"},
        ]
        state["subtask_results"] = []
        mock_orchestrator._abortive.execute_subtask = AsyncMock(return_value={
            "status": "SUCCESS", "code": "pass"
        })
        trial_pass = MagicMock()
        trial_pass.status = "PASS"
        mock_orchestrator.sandbox.validate_code = AsyncMock(return_value=trial_pass)
        resume_result = asyncio.run(
            manager.resume_from_partial(token)
        )
        assert mock_orchestrator._abortive.execute_subtask.call_count == 2


# ============================================================
#  TTL EXPIRATION TESTS
# ============================================================

class TestTTLExpiration:
    """Tests for TTL-based cleanup of resumption entries."""

    def test_expired_entries_cleaned_on_build(self, manager, mock_orchestrator,
                                              mock_intent, mock_routing,
                                              mock_plan, mock_trial):
        """Old resumption entries should be cleaned up when building new ones."""
        old_token = "old_expired_token"
        mock_orchestrator._pending_resumptions[old_token] = {
            "token": old_token,
            "created_at": time.time() - 3600,
            "subtasks": [],
            "subtask_results": [],
            "original_intent": {},
            "partial_code": "",
        }
        result = manager.build_partial_reasoning_response(
            intent=mock_intent, routing=mock_routing, plan=mock_plan,
            ast_analysis={}, trial=mock_trial, start_time=time.time(),
        )
        assert old_token not in mock_orchestrator._pending_resumptions
        new_token = result["resumption"]["token"]
        assert new_token in mock_orchestrator._pending_resumptions

    def test_max_count_enforcement(self, manager, mock_orchestrator,
                                   mock_intent, mock_routing,
                                   mock_plan, mock_trial):
        """When more than 100 entries exist, oldest should be evicted."""
        for i in range(101):
            mock_orchestrator._pending_resumptions[f"token_{i:04d}"] = {
                "token": f"token_{i:04d}",
                "created_at": time.time() - (101 - i),
                "subtasks": [],
                "subtask_results": [],
                "original_intent": {},
                "partial_code": "",
            }
        result = manager.build_partial_reasoning_response(
            intent=mock_intent, routing=mock_routing, plan=mock_plan,
            ast_analysis={}, trial=mock_trial, start_time=time.time(),
        )
        assert len(mock_orchestrator._pending_resumptions) <= 102

    def test_recent_entries_not_expired(self, manager, mock_orchestrator,
                                        mock_intent, mock_routing,
                                        mock_plan, mock_trial):
        """Recent entries should NOT be cleaned up."""
        recent_token = "recent_token"
        mock_orchestrator._pending_resumptions[recent_token] = {
            "token": recent_token,
            "created_at": time.time(),
            "subtasks": [],
            "subtask_results": [],
            "original_intent": {},
            "partial_code": "",
        }
        result = manager.build_partial_reasoning_response(
            intent=mock_intent, routing=mock_routing, plan=mock_plan,
            ast_analysis={}, trial=mock_trial, start_time=time.time(),
        )
        assert recent_token in mock_orchestrator._pending_resumptions
