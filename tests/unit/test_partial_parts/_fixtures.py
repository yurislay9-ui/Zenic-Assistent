"""Shared fixtures for partial reasoning tests — imported into test files."""

import time
import threading
import pytest
from unittest.mock import MagicMock, AsyncMock

from src.core.partial_reasoning import PartialReasoningManager
from src.core.subtask_descriptor import SubtaskDescriptor


@pytest.fixture
def mock_orchestrator():
    """Create a mock ZenicOrchestrator with all required attributes."""
    orch = MagicMock()
    orch.sandbox = MagicMock()
    orch.sandbox.k_path_limit = 50
    orch.sandbox.validate_code = AsyncMock()

    orch._abortive = MagicMock()
    orch._abortive.generate_subtasks = MagicMock(return_value=[
        SubtaskDescriptor(message="Subtask isolation", target="auth.py",
                          operation="CREATE", goal="BUG_FIX"),
        SubtaskDescriptor(message="Subtask mutation", target="auth.py",
                          operation="CREATE", goal="COMPLEXITY_REDUCTION"),
    ])
    orch._abortive.execute_subtask = AsyncMock(return_value={
        "status": "SUCCESS", "code": "def hello(): pass", "message": ""
    })
    orch._abortive.merge_subtask_results = MagicMock(return_value="def hello(): pass")

    orch._pending_resumptions = {}
    orch._resumptions_lock = threading.Lock()

    orch._isolation_manager = MagicMock()
    workspace = MagicMock()
    workspace.sandbox_id = "ws-test-123"
    orch._isolation_manager.create_workspace = MagicMock(return_value=workspace)
    orch._isolation_manager.release_workspace = MagicMock()

    orch.cache = MagicMock()
    orch.cache.save = MagicMock()

    orch.ledger = MagicMock()
    node = MagicMock()
    node.hash_sha256 = "abc123def456"
    orch.ledger.commit = MagicMock(return_value=node)
    orch.ledger.snapshot = MagicMock()
    orch.ledger.rollback = MagicMock()

    return orch


@pytest.fixture
def mock_intent():
    """Create a mock IntentPayload."""
    intent = MagicMock()
    intent.op = "CREATE"
    intent.target = "auth.py"
    intent.goal = "FEATURE_ADD"
    intent.language = "python"
    intent.raw_code = "def authenticate(): pass"
    intent.scrap_query = ""
    intent.confidence = 0.85
    return intent


@pytest.fixture
def mock_routing():
    """Create a mock RoutingResult."""
    routing = MagicMock()
    routing.route = "DEEP_PATH_CONSTRAINT"
    routing.criticality = 2
    return routing


@pytest.fixture
def mock_plan():
    """Create a mock plan with solver proof."""
    plan = MagicMock()
    plan.solver_status = "TIMEOUT"
    plan.solver_proof = {"solver_type": "Z3", "timeout_ms": 5000}
    return plan


@pytest.fixture
def mock_trial():
    """Create a mock TrialResult."""
    trial = MagicMock()
    trial.error_message = "K-Path limit exceeded"
    trial.warnings = ["High complexity detected"]
    trial.paths_explored = 50
    trial.paths_pruned = 120
    trial.status = "FAIL_K_PATH"
    return trial


@pytest.fixture
def manager(mock_orchestrator):
    """Create a PartialReasoningManager with mocked orchestrator."""
    return PartialReasoningManager(mock_orchestrator)
