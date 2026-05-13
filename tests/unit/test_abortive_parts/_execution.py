"""Tests for subtask execution, handle_abortive_protocol, and workspace management."""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from src.core.abortive_protocol import (
    AbortiveProtocol,
    ABORTIVE_SANDBOX_TTL_MIN,
)
from src.core.subtask_descriptor import SubtaskDescriptor

from .conftest import _make_mock_intent, _make_mock_plan


# ============================================================
#  Test: execute_subtask
# ============================================================

class TestAbortiveExecuteSubtask:
    """Tests for subtask execution."""

    @pytest.mark.asyncio
    async def test_execute_subtask_max_depth(self, protocol):
        """Should return MAX_DEPTH_REACHED at max depth."""
        ap, orch = protocol
        subtask = SubtaskDescriptor(message="test", depth=5)
        result = await ap.execute_subtask(subtask, depth=5, max_depth=2)
        assert result["status"] == "MAX_DEPTH_REACHED"

    @pytest.mark.asyncio
    async def test_execute_subtask_parse_error(self, protocol):
        """Should handle parse errors gracefully."""
        ap, orch = protocol
        orch.parser.parse.side_effect = Exception("Parse failed")
        subtask = SubtaskDescriptor(message="bad input")
        result = await ap.execute_subtask(subtask, depth=0, max_depth=2)
        assert result["status"] == "ERROR"
        assert "Parse error" in result["message"]

    @pytest.mark.asyncio
    async def test_execute_subtask_cache_hit(self, protocol):
        """Should return cached result on cache hit."""
        ap, orch = protocol
        mock_intent = _make_mock_intent()
        orch.parser.parse.return_value = mock_intent
        orch.cache.lookup.return_value = {"data": {"code": "cached_code"}}

        subtask = SubtaskDescriptor(message="create auth.py")
        result = await ap.execute_subtask(subtask, depth=0, max_depth=2)
        assert result["status"] == "CACHED"
        assert result["code"] == "cached_code"

    @pytest.mark.asyncio
    async def test_execute_subtask_string_legacy(self, protocol):
        """Should handle plain string subtask (legacy)."""
        ap, orch = protocol
        mock_intent = _make_mock_intent()
        orch.parser.parse.return_value = mock_intent
        orch.cache.lookup.return_value = {"data": {"code": "legacy_code"}}

        result = await ap.execute_subtask("create module test.py", depth=0, max_depth=2)
        assert result["status"] == "CACHED"


# ============================================================
#  Test: handle_abortive_protocol
# ============================================================

class TestAbortiveHandleProtocol:
    """Tests for the full abortive protocol flow."""

    @pytest.mark.asyncio
    async def test_abortive_creates_isolated_workspace(self, protocol):
        """Should create an isolated workspace for the protocol."""
        ap, orch = protocol
        intent = _make_mock_intent()
        routing = MagicMock()
        routing.route = "DEEP_PATH_CONSTRAINT"
        routing.criticality = 3
        plan = _make_mock_plan()
        ast_analysis = {}

        # Mock sandbox validation to FAIL so we don't commit
        mock_trial = MagicMock()
        mock_trial.status = "FAIL"
        mock_trial.error_message = "Test failure"
        mock_trial.warnings = []
        mock_trial.paths_explored = 0
        mock_trial.paths_pruned = 0
        orch.sandbox.validate_code = AsyncMock(return_value=mock_trial)

        # Mock the subtask generation to return empty subtasks
        with patch.object(ap, 'generate_subtasks', return_value=[]):
            result = await ap.handle_abortive_protocol(
                intent, routing, plan, ast_analysis, start_time=0.0
            )

        # Should have created workspace
        orch._isolation_manager.create_workspace.assert_called()

    @pytest.mark.asyncio
    async def test_abortive_rollback_on_start(self, protocol):
        """Should perform rollback at the start of the protocol."""
        ap, orch = protocol
        intent = _make_mock_intent()
        routing = MagicMock()
        routing.route = "DEEP_PATH_CONSTRAINT"
        routing.criticality = 3
        plan = _make_mock_plan()
        ast_analysis = {}

        mock_trial = MagicMock()
        mock_trial.status = "FAIL"
        mock_trial.error_message = "Test failure"
        mock_trial.warnings = []
        mock_trial.paths_explored = 0
        mock_trial.paths_pruned = 0
        orch.sandbox.validate_code = AsyncMock(return_value=mock_trial)

        with patch.object(ap, 'generate_subtasks', return_value=[]):
            await ap.handle_abortive_protocol(
                intent, routing, plan, ast_analysis, start_time=0.0
            )

        orch.ledger.rollback.assert_called()


# ============================================================
#  Test: Workspace Management
# ============================================================

class TestAbortiveWorkspace:
    """Tests for workspace isolation and management."""

    @pytest.mark.asyncio
    async def test_workspace_created_with_ttl(self, protocol):
        """Should create workspace with appropriate TTL."""
        ap, orch = protocol
        intent = _make_mock_intent()
        routing = MagicMock()
        routing.route = "DEEP_PATH_CONSTRAINT"
        routing.criticality = 3
        plan = _make_mock_plan()
        ast_analysis = {}

        mock_trial = MagicMock()
        mock_trial.status = "FAIL"
        mock_trial.error_message = "Test failure"
        mock_trial.warnings = []
        mock_trial.paths_explored = 0
        mock_trial.paths_pruned = 0
        orch.sandbox.validate_code = AsyncMock(return_value=mock_trial)

        with patch.object(ap, 'generate_subtasks', return_value=[]):
            await ap.handle_abortive_protocol(
                intent, routing, plan, ast_analysis, start_time=0.0
            )

        # Verify workspace created with TTL
        call_args = orch._isolation_manager.create_workspace.call_args
        ttl = call_args[1]["ttl_seconds"]
        assert ttl >= ABORTIVE_SANDBOX_TTL_MIN
