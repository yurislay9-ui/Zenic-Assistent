"""
Tests for shared type payload classes: IntentPayload, RoutingPayload,
PlanStep, ExecutionPlan, SandboxResult, MerkleNode, ChatTypes.
"""

import pytest

from src.core.shared.types import (
    OperationType, GoalType, CriticalityLevel, RoutePath,
    IntentPayload, RoutingPayload, PlanStep, ExecutionPlan,
    SandboxResult, MerkleNode, ChatMessage, ChatRequest,
)


# ===========================================================================
#  Test: IntentPayload
# ===========================================================================

class TestIntentPayload:
    """Tests for IntentPayload data class."""

    def test_default_values(self):
        """Default values should match OperationType.SEARCH, etc."""
        payload = IntentPayload()
        assert payload.op == OperationType.SEARCH.value
        assert payload.target == "unknown"
        assert payload.goal == GoalType.FEATURE_ADD.value
        assert payload.scrap_query == ""
        assert payload.confidence == 0.0
        assert payload.language == "python"
        assert payload.raw_code == ""
        assert payload.context == ""

    def test_custom_values(self):
        """Should accept custom values."""
        payload = IntentPayload(
            op="CREATE", target="auth.py", goal="BUG_FIX",
            scrap_query="test", confidence=0.9,
            language="go", raw_code="func main(){}",
            context="debug"
        )
        assert payload.op == "CREATE"
        assert payload.target == "auth.py"
        assert payload.goal == "BUG_FIX"
        assert payload.confidence == 0.9
        assert payload.language == "go"

    def test_attributes_mutable(self):
        """IntentPayload attributes should be mutable."""
        payload = IntentPayload()
        payload.op = "DEBUG"
        assert payload.op == "DEBUG"


# ===========================================================================
#  Test: RoutingPayload
# ===========================================================================

class TestRoutingPayload:
    """Tests for RoutingPayload data class."""

    def test_default_values(self):
        """Default values should match CriticalityLevel.FAST_STANDARD."""
        payload = RoutingPayload()
        assert payload.criticality == CriticalityLevel.FAST_STANDARD.value
        assert payload.route == RoutePath.FAST_PATH.value
        assert payload.reason == ""
        assert isinstance(payload.intent, IntentPayload)

    def test_custom_intent(self):
        """Should accept a custom IntentPayload."""
        intent = IntentPayload(op="DEBUG")
        payload = RoutingPayload(intent=intent, criticality=3, route="SURGICAL_PATH_FULL")
        assert payload.intent.op == "DEBUG"
        assert payload.criticality == 3

    def test_reason_field(self):
        """Reason field should be settable."""
        payload = RoutingPayload(reason="High complexity")
        assert payload.reason == "High complexity"


# ===========================================================================
#  Test: PlanStep
# ===========================================================================

class TestPlanStep:
    """Tests for PlanStep data class."""

    def test_default_values(self):
        payload = PlanStep()
        assert payload.step_id == 0
        assert payload.action == "ANALYZE_CODE"
        assert payload.target_node_name == ""
        assert payload.source == "LOCAL_GRAPH"
        assert payload.constraints == {}

    def test_custom_values(self):
        payload = PlanStep(step_id=5, action="REPLACE_NODE",
                           target_node_name="auth.py:login",
                           source="REMOTE_GRAPH",
                           constraints={"max_complexity": 10})
        assert payload.step_id == 5
        assert payload.action == "REPLACE_NODE"
        assert payload.constraints == {"max_complexity": 10}

    def test_constraints_default_empty_dict(self):
        """Each PlanStep should have its own constraints dict."""
        p1 = PlanStep()
        p2 = PlanStep()
        p1.constraints["key"] = "val"
        assert "key" not in p2.constraints


# ===========================================================================
#  Test: ExecutionPlan
# ===========================================================================

class TestExecutionPlan:
    """Tests for ExecutionPlan data class."""

    def test_default_values(self):
        plan = ExecutionPlan()
        assert plan.plan_id == ""
        assert plan.steps == []
        assert plan.solver_status == "HEURISTIC_FALLBACK"
        assert plan.solver_proof is None
        assert plan.mcts_simulations == 0
        assert plan.mcts_depth_reached == 0

    def test_custom_values(self):
        steps = [PlanStep(step_id=1), PlanStep(step_id=2)]
        plan = ExecutionPlan(plan_id="p1", steps=steps,
                             solver_status="SAT", solver_proof="proof",
                             mcts_simulations=50, mcts_depth_reached=3)
        assert len(plan.steps) == 2
        assert plan.solver_status == "SAT"
        assert plan.mcts_simulations == 50


# ===========================================================================
#  Test: SandboxResult
# ===========================================================================

class TestSandboxResult:
    """Tests for SandboxResult data class."""

    def test_default_values(self):
        result = SandboxResult()
        assert result.status == "PASS"
        assert result.error_message == ""
        assert result.error_node is None
        assert result.warnings == []
        assert result.metrics == {}
        assert result.paths_explored == 0
        assert result.paths_pruned == 0

    def test_failure_result(self):
        result = SandboxResult(status="FAIL_SYNTAX", error_message="SyntaxError",
                               error_node="line 5", warnings=["deprecated"])
        assert result.status == "FAIL_SYNTAX"
        assert result.error_message == "SyntaxError"


# ===========================================================================
#  Test: MerkleNode
# ===========================================================================

class TestMerkleNode:
    """Tests for MerkleNode data class."""

    def test_default_values(self):
        node = MerkleNode()
        assert node.file_path == ""
        assert node.hash_sha256 == ""
        assert node.parent_hash == ""
        assert node.timestamp == 0
        assert node.operation == ""

    def test_custom_values(self):
        node = MerkleNode(file_path="/app/main.py", hash_sha256="abc123",
                          parent_hash="def456", timestamp=1700000000,
                          operation="CREATE")
        assert node.file_path == "/app/main.py"
        assert node.hash_sha256 == "abc123"


# ===========================================================================
#  Test: ChatMessage and ChatRequest
# ===========================================================================

class TestChatTypes:
    """Tests for ChatMessage and ChatRequest."""

    def test_chat_message_defaults(self):
        msg = ChatMessage()
        assert msg.role == "user"
        assert msg.content == ""

    def test_chat_message_custom(self):
        msg = ChatMessage(role="assistant", content="Hello!")
        assert msg.role == "assistant"
        assert msg.content == "Hello!"

    def test_chat_request_defaults(self):
        req = ChatRequest()
        assert req.model == "zenic-agents"
        assert req.messages == []
        assert req.temperature == 0.1
        assert req.max_tokens == 2000
        assert req.stream is False

    def test_chat_request_with_messages(self):
        msgs = [ChatMessage(role="user", content="hi")]
        req = ChatRequest(messages=msgs, temperature=0.7, max_tokens=500, stream=True)
        assert len(req.messages) == 1
        assert req.temperature == 0.7
        assert req.max_tokens == 500
        assert req.stream is True
