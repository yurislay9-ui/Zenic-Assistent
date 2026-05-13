"""
Tests for SurgicalAgent fallback classification and goal classification.
"""

import pytest

from src.core.agents.surgical_agent import VALID_OPERATIONS
from src.core.agents.schemas import IntentInput


# ============================================================
#  Test: Fallback Classification (TF-IDF + regex)
# ============================================================

class TestSurgicalAgentFallback:
    """Tests for deterministic fallback classification."""

    def test_create_operation_es(self, agent):
        result = agent.fallback(IntentInput(message="crear modulo auth.py"))
        assert result.operation == "CREATE"
        assert result.source == "tfidf"

    def test_create_operation_en(self, agent):
        result = agent.fallback(IntentInput(message="create new feature"))
        assert result.operation == "CREATE"

    def test_delete_operation_es(self, agent):
        result = agent.fallback(IntentInput(message="eliminar funcion process_data"))
        assert result.operation == "DELETE"

    def test_debug_operation_es(self, agent):
        result = agent.fallback(IntentInput(message="debug error en login"))
        assert result.operation == "DEBUG"

    def test_debug_operation_en(self, agent):
        result = agent.fallback(IntentInput(message="fix the bug in payment"))
        assert result.operation == "DEBUG"

    def test_optimize_operation_es(self, agent):
        result = agent.fallback(IntentInput(message="optimizar rendimiento"))
        assert result.operation == "OPTIMIZE"

    def test_search_operation_es(self, agent):
        result = agent.fallback(IntentInput(message="buscar definicion de clase"))
        assert result.operation == "SEARCH"

    def test_refactor_operation_en(self, agent):
        result = agent.fallback(IntentInput(message="refactor the auth module"))
        assert result.operation == "REFACTOR"

    def test_analyze_operation_en(self, agent):
        result = agent.fallback(IntentInput(message="analyze the code quality"))
        assert result.operation == "ANALYZE"

    def test_explain_operation_en(self, agent):
        result = agent.fallback(IntentInput(message="explain how this code works"))
        assert result.operation == "EXPLAIN"


# ============================================================
#  Test: Goal Classification
# ============================================================

class TestSurgicalAgentGoalClassification:
    """Tests for goal classification in fallback mode."""

    def test_bug_fix_goal(self, agent):
        result = agent.fallback(IntentInput(message="corregir error en login"))
        assert result.goal == "BUG_FIX"

    def test_feature_add_goal(self, agent):
        result = agent.fallback(IntentInput(message="agregar nueva funcionalidad"))
        assert result.goal == "FEATURE_ADD"

    def test_security_harden_goal(self, agent):
        result = agent.fallback(IntentInput(message="mejorar seguridad auth"))
        assert result.goal == "SECURITY_HARDEN"

    def test_performance_goal(self, agent):
        result = agent.fallback(IntentInput(message="optimizar velocidad"))
        assert result.goal == "PERFORMANCE"


# ============================================================
#  Test: Target and Language Extraction
# ============================================================

class TestSurgicalAgentExtraction:
    """Tests for target, language, and entity extraction."""

    def test_target_extraction_file(self, agent):
        result = agent.fallback(IntentInput(message="crear modulo auth.py"))
        assert "auth" in result.target.lower()

    def test_target_extraction_kotlin(self, agent):
        result = agent.fallback(IntentInput(message="refactorizar UserService.kt"))
        assert result.language == "kotlin"

    def test_target_extraction_javascript(self, agent):
        result = agent.fallback(IntentInput(message="analizar codigo en app.js"))
        assert result.language == "javascript"

    def test_code_block_extraction(self, agent):
        code = "def hello():\n    print('hello')"
        result = agent.fallback(IntentInput(
            message=f"analizar ```python\n{code}\n```"
        ))
        assert result.language == "python"

    def test_entities_extraction_function(self, agent):
        result = agent.fallback(IntentInput(message="def process_data(): crear funcion"))
        assert result.entities.get("function") == "process_data"

    def test_entities_extraction_class(self, agent):
        result = agent.fallback(IntentInput(message="class UserManager: refactorizar"))
        assert result.entities.get("class") == "UserManager"


# ============================================================
#  Test: Criticality Inference
# ============================================================

class TestSurgicalAgentCriticality:
    """Tests for criticality inference."""

    def test_critical_auth(self, agent):
        result = agent.fallback(IntentInput(message="corregir error en login auth"))
        assert result.criticality == "critical"

    def test_critical_crypto(self, agent):
        result = agent.fallback(IntentInput(message="mejorar seguridad crypto"))
        assert result.criticality == "critical"

    def test_moderate_database(self, agent):
        result = agent.fallback(IntentInput(message="crear modulo database"))
        assert result.criticality == "moderate"

    def test_standard(self, agent):
        result = agent.fallback(IntentInput(message="crear nueva funcion"))
        assert result.criticality == "standard"
