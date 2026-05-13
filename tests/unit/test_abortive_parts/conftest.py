"""Shared fixtures and helpers for abortive_protocol tests."""

import pytest
from unittest.mock import MagicMock, AsyncMock

from src.core.abortive_protocol import AbortiveProtocol
from src.core.shared.contracts import OperationType


# ============================================================
#  Helper Functions
# ============================================================

def _make_mock_intent(op="CREATE", target="auth.py", goal="FEATURE_ADD",
                      language="python", raw_code=""):
    """Create a mock intent object."""
    intent = MagicMock()
    intent.op = op
    intent.target = target
    intent.goal = goal
    intent.language = language
    intent.raw_code = raw_code
    return intent


def _make_mock_plan(solver_status="TIMEOUT_SUBDIVIDE_REQUIRED"):
    """Create a mock plan object."""
    plan = MagicMock()
    plan.solver_status = solver_status
    plan.solver_proof = {"timeout_ms": 15000, "verified": False}
    plan.mcts_simulations = 10
    plan.mcts_depth_reached = 3
    plan.steps = []
    return plan


def _make_mock_orchestrator():
    """Create a mock orchestrator with all required components."""
    orch = MagicMock()
    orch._code_gen = MagicMock()
    orch._code_gen.extract_solver_insights.return_value = {}
    orch.sandbox = MagicMock()
    orch.sandbox.timeout_seconds = 30
    orch.ledger = MagicMock()
    orch.ledger.rollback = MagicMock()
    orch.ledger.snapshot = MagicMock()
    orch.ledger.commit.return_value = MagicMock(hash_sha256="abc123def456789")
    orch.cache = MagicMock()
    orch.cache.lookup.return_value = None
    orch.cache.save = MagicMock()
    orch._analysis = MagicMock()
    orch._analysis.log_request = MagicMock()
    orch._partial_reasoning = MagicMock()
    orch._partial_reasoning.build_partial_reasoning_response.return_value = {
        "status": "PARTIAL", "code": ""
    }
    orch.settings = MagicMock()

    # Isolation manager
    mock_workspace = MagicMock()
    mock_workspace.sandbox_id = "ws_test_123"
    orch._isolation_manager = MagicMock()
    orch._isolation_manager.create_workspace.return_value = mock_workspace
    orch._isolation_manager.release_workspace = MagicMock()

    return orch


# ============================================================
#  Fixtures
# ============================================================

@pytest.fixture
def protocol():
    """AbortiveProtocol with mock orchestrator."""
    orch = _make_mock_orchestrator()
    return AbortiveProtocol(orch), orch
