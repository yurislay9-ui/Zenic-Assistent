"""
ZENIC-AGENTS - DAGOrchestrator Tests

Tests for the DAG-based orchestrator:
  - DAGNode and PIPELINE_DAG structure
  - ZenicMetaRouter routing: fallback transitions, criticality paths
  - _resolve_transition: direct, wildcard, dynamic, and default transitions
  - _apply_f5_corrections: auto-fix for common security issues
  - DAG execution flow basics
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from dataclasses import dataclass

from src.core.dag_orchestrator import (
    DAGNode,
    PIPELINE_DAG,
    ZenicMetaRouter,
)


# ============================================================
#  DAG STRUCTURE TESTS
# ============================================================

class TestDAGStructure:
    """Tests for the PIPELINE_DAG definition."""

    def test_pipeline_has_required_nodes(self):
        """PIPELINE_DAG should contain all expected nodes."""
        required = [
            "CACHE_CHECK", "INTENT", "CONTEXT_PREPARE", "AST_ANALYZE",
            "THEOREM_CACHE", "ROUTE", "CRITICALITY_ROUTE", "PLAN",
            "SOLVER_VERIFY", "EXECUTE_STEPS", "VALIDATE", "ABORTIVE",
            "SANDBOX", "PARTIAL_REASONING", "LEDGER_COMMIT",
            "LEDGER_ROLLBACK", "THEOREM_SAVE", "MEMORY_SAVE", "DONE",
        ]
        for node in required:
            assert node in PIPELINE_DAG, f"Missing node: {node}"

    def test_done_node_has_no_transitions(self):
        """DONE node should have empty transitions and no default_next."""
        done = PIPELINE_DAG["DONE"]
        assert done.transitions == {}
        assert done.default_next == ""

    def test_cache_check_transitions(self):
        """CACHE_CHECK should transition to DONE on hit, INTENT on miss."""
        node = PIPELINE_DAG["CACHE_CHECK"]
        assert node.transitions["hit"] == "DONE"
        assert node.transitions["miss"] == "INTENT"

    def test_plan_transitions(self):
        """PLAN should have transitions for abortive, low_crit, standard, high_crit."""
        node = PIPELINE_DAG["PLAN"]
        assert "abortive" in node.transitions
        assert "low_crit" in node.transitions
        assert "standard" in node.transitions
        assert "high_crit" in node.transitions

    def test_sandbox_transitions(self):
        """SANDBOX should transition based on trial status."""
        node = PIPELINE_DAG["SANDBOX"]
        assert node.transitions["PASS"] == "LEDGER_COMMIT"
        assert node.transitions["FAIL_K_PATH"] == "PARTIAL_REASONING"
        assert node.transitions["FAIL"] == "LEDGER_ROLLBACK"

    def test_validate_max_retries(self):
        """VALIDATE node should have max_retries=3 for F5 correction loop."""
        node = PIPELINE_DAG["VALIDATE"]
        assert node.max_retries == 3

    def test_solver_verify_max_retries(self):
        """SOLVER_VERIFY should have max_retries=2."""
        node = PIPELINE_DAG["SOLVER_VERIFY"]
        assert node.max_retries == 2

    def test_all_transitions_reference_valid_nodes(self):
        """All transition targets should reference nodes in the DAG."""
        for node_name, node in PIPELINE_DAG.items():
            for result, target in node.transitions.items():
                if result != "*":
                    assert target in PIPELINE_DAG, (
                        f"Node {node_name} transitions[{result}] = {target} not in DAG"
                    )

    def test_all_default_next_reference_valid_nodes(self):
        """All default_next values should reference nodes in the DAG (or be empty)."""
        for node_name, node in PIPELINE_DAG.items():
            if node.default_next:
                assert node.default_next in PIPELINE_DAG, (
                    f"Node {node_name} default_next={node.default_next} not in DAG"
                )

    def test_dag_node_dataclass(self):
        """DAGNode should be a dataclass with expected fields."""
        node = DAGNode(
            name="TEST",
            exec_method="_exec_test",
            transitions={"ok": "NEXT"},
            default_next="FALLBACK",
            criticality_skip=["FAST"],
            max_retries=2,
        )
        assert node.name == "TEST"
        assert node.exec_method == "_exec_test"
        assert node.transitions["ok"] == "NEXT"
        assert node.default_next == "FALLBACK"
        assert node.criticality_skip == ["FAST"]
        assert node.max_retries == 2


# ============================================================
#  ZENIC AGENT ROUTING TESTS
# ============================================================

class TestZenicMetaRouterRouting:
    """Tests for ZenicMetaRouter fallback routing."""

    def test_intent_transitions_all_ops(self):
        """All operation types should have INTENT transitions."""
        agent = ZenicMetaRouter()
        for op in ["CREATE", "REFACTOR", "DELETE", "SEARCH",
                    "ANALYZE", "EXPLAIN", "DEBUG", "OPTIMIZE"]:
            result = agent.fallback({"current_node": "INTENT", "result": "",
                                     "context": {"operation": op}})
            assert result == "CONTEXT_PREPARE"

    def test_intent_unknown_op_uses_default(self):
        """Unknown operation should fall back to AST_ANALYZE."""
        agent = ZenicMetaRouter()
        result = agent.fallback({"current_node": "INTENT", "result": "",
                                 "context": {"operation": "UNKNOWN_OP"}})
        assert result == "AST_ANALYZE"

    def test_criticality_paths_numeric(self):
        """Numeric criticality levels should map to correct paths."""
        agent = ZenicMetaRouter()
        assert agent.CRITICALITY_PATHS[1] == "low_crit"
        assert agent.CRITICALITY_PATHS[2] == "standard"
        assert agent.CRITICALITY_PATHS[3] == "high_crit"

    def test_criticality_paths_string(self):
        """String criticality levels should map to correct paths."""
        agent = ZenicMetaRouter()
        assert agent.CRITICALITY_PATHS["FAST"] == "low_crit"
        assert agent.CRITICALITY_PATHS["STANDARD"] == "standard"
        assert agent.CRITICALITY_PATHS["DEEP"] == "high_crit"
        assert agent.CRITICALITY_PATHS["SURGICAL_CRITICAL"] == "high_crit"
        assert agent.CRITICALITY_PATHS["DEEP_MODERATE"] == "standard"
        assert agent.CRITICALITY_PATHS["FAST_STANDARD"] == "low_crit"

    def test_fallback_plan_low_crit(self):
        """PLAN node fallback with low criticality should return low_crit."""
        agent = ZenicMetaRouter()
        result = agent.fallback({
            "current_node": "PLAN",
            "result": "",
            "context": {"criticality": "FAST_STANDARD"},
        })
        assert result == "low_crit"

    def test_fallback_plan_high_crit(self):
        """PLAN node fallback with high criticality should return high_crit."""
        agent = ZenicMetaRouter()
        result = agent.fallback({
            "current_node": "PLAN",
            "result": "",
            "context": {"criticality": "SURGICAL_CRITICAL"},
        })
        assert result == "high_crit"

    def test_fallback_uses_dag_transitions(self):
        """For non-INTENT/PLAN nodes, fallback should use DAG transitions."""
        agent = ZenicMetaRouter()
        result = agent.fallback({
            "current_node": "CACHE_CHECK",
            "result": "hit",
            "context": {},
        })
        assert result == "DONE"

    def test_fallback_wildcard_transition(self):
        """Fallback should match wildcard '*' transitions."""
        agent = ZenicMetaRouter()
        result = agent.fallback({
            "current_node": "CONTEXT_PREPARE",
            "result": "anything",
            "context": {},
        })
        assert result == "AST_ANALYZE"

    def test_fallback_unknown_node_returns_done(self):
        """Fallback for unknown node should return DONE."""
        agent = ZenicMetaRouter()
        result = agent.fallback({
            "current_node": "NONEXISTENT_NODE",
            "result": "",
            "context": {},
        })
        assert result == "DONE"

    def test_build_prompt_returns_tuple(self):
        """build_prompt should return (system, user) tuple."""
        agent = ZenicMetaRouter()
        result = agent.build_prompt({
            "current_node": "INTENT",
            "result": "CREATE",
            "context": {"operation": "CREATE", "goal": "ADD", "criticality": "standard"},
        })
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert "pipeline router" in result[0].lower()

    def test_parse_response_valid_node(self):
        """parse_response should return a valid node name."""
        agent = ZenicMetaRouter()
        result = agent.parse_response("INTENT", {})
        assert result == "INTENT"

    def test_parse_response_invalid_returns_none(self):
        """parse_response with invalid text should return None."""
        agent = ZenicMetaRouter()
        result = agent.parse_response("NOT_A_NODE_AT_ALL", {})
        assert result is None

    def test_parse_response_case_insensitive(self):
        """parse_response should be case-insensitive."""
        agent = ZenicMetaRouter()
        result = agent.parse_response("intent", {})
        assert result == "INTENT"

    def test_parse_response_partial_match(self):
        """parse_response should find node names within text."""
        agent = ZenicMetaRouter()
        result = agent.parse_response("The next step is PLAN", {})
        assert result == "PLAN"


# ============================================================
#  F5 CORRECTION TESTS
# ============================================================

class TestF5Corrections:
    """Tests for the _apply_f5_corrections auto-fix method."""

    @pytest.fixture
    def orchestrator_for_f5(self):
        """Create a minimal mock orchestrator to test _apply_f5_corrections."""
        # We can't easily instantiate DAGOrchestrator due to complex __init__,
        # so we test the method logic directly by creating a minimal object
        from src.core.dag_orchestrator import DAGOrchestrator
        with patch.object(DAGOrchestrator, "__init__", lambda self: None):
            orch = DAGOrchestrator()
        return orch

    def test_dangerous_eval_correction(self, orchestrator_for_f5):
        """eval() should be replaced with ast.literal_eval()."""
        code = "result = eval(user_input)"
        issue = MagicMock()
        issue.code = "dangerous_eval"
        issue.severity = "error"

        corrected = orchestrator_for_f5._apply_f5_corrections(code, [issue], "python")
        assert "ast.literal_eval" in corrected
        assert "import ast" in corrected

    def test_command_injection_correction(self, orchestrator_for_f5):
        """os.system() should be replaced with subprocess.run()."""
        code = "os.system('ls -la')"
        issue = MagicMock()
        issue.code = "command_injection"
        issue.severity = "error"

        corrected = orchestrator_for_f5._apply_f5_corrections(code, [issue], "python")
        assert "subprocess.run" in corrected
        assert "import subprocess" in corrected

    def test_shell_injection_correction(self, orchestrator_for_f5):
        """shell=True should be replaced with shell=False."""
        code = "subprocess.run(cmd, shell=True)"
        issue = MagicMock()
        issue.code = "shell_injection"
        issue.severity = "error"

        corrected = orchestrator_for_f5._apply_f5_corrections(code, [issue], "python")
        assert "shell=False" in corrected

    def test_pickle_deserialization_correction(self, orchestrator_for_f5):
        """pickle.loads should be replaced with json.loads."""
        code = "data = pickle.loads(raw)"
        issue = MagicMock()
        issue.code = "pickle_deserialization"
        issue.severity = "error"

        corrected = orchestrator_for_f5._apply_f5_corrections(code, [issue], "python")
        assert "json.loads" in corrected

    def test_bare_except_correction(self, orchestrator_for_f5):
        """Bare except: should be replaced with except Exception:."""
        code = "try:\n    pass\nexcept:\n    pass"
        issue = MagicMock()
        issue.code = "bare_except"
        issue.severity = "error"

        corrected = orchestrator_for_f5._apply_f5_corrections(code, [issue], "python")
        assert "except Exception:" in corrected

    def test_weak_hash_md5_correction(self, orchestrator_for_f5):
        """hashlib.md5 should be replaced with hashlib.sha256."""
        code = "digest = hashlib.md5(data.encode()).hexdigest()"
        issue = MagicMock()
        issue.code = "weak_hash_md5"
        issue.severity = "error"

        corrected = orchestrator_for_f5._apply_f5_corrections(code, [issue], "python")
        assert "hashlib.sha256" in corrected

    def test_warning_severity_not_corrected(self, orchestrator_for_f5):
        """Issues with severity='warning' should NOT trigger corrections."""
        code = "result = eval(user_input)"
        issue = MagicMock()
        issue.code = "dangerous_eval"
        issue.severity = "warning"

        corrected = orchestrator_for_f5._apply_f5_corrections(code, [issue], "python")
        assert corrected == code  # No changes

    def test_no_issues_returns_unchanged(self, orchestrator_for_f5):
        """Code with no issues should be returned unchanged."""
        code = "def hello(): return 'world'"
        corrected = orchestrator_for_f5._apply_f5_corrections(code, [], "python")
        assert corrected == code

    def test_multiple_corrections_applied(self, orchestrator_for_f5):
        """Multiple issues should all be corrected."""
        code = "result = eval(x)\nos.system(cmd)"
        issue1 = MagicMock()
        issue1.code = "dangerous_eval"
        issue1.severity = "error"
        issue2 = MagicMock()
        issue2.code = "command_injection"
        issue2.severity = "error"

        corrected = orchestrator_for_f5._apply_f5_corrections(code, [issue1, issue2], "python")
        assert "ast.literal_eval" in corrected
        assert "subprocess.run" in corrected
