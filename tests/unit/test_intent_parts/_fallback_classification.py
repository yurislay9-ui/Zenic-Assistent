"""Tests for IntentAgent fallback classification, goal, extraction, and criticality."""

import pytest

from src.core.agents.intent_agent import IntentAgent, VALID_OPERATIONS
from src.core.agents.schemas import IntentInput


# ============================================================
#  Test: Fallback Classification (TF-IDF + regex)
# ============================================================

class TestIntentAgentFallback:
    """Tests for deterministic fallback classification."""

    def test_create_operation_es(self, agent):
        """Should detect CREATE from Spanish messages."""
        result = agent.fallback(IntentInput(message="crear modulo auth.py"))
        assert result.operation == "CREATE"
        assert result.source == "fallback"

    def test_create_operation_en(self, agent):
        """Should detect CREATE from English messages."""
        result = agent.fallback(IntentInput(message="create new feature"))
        assert result.operation == "CREATE"

    def test_delete_operation_es(self, agent):
        """Should detect DELETE from Spanish messages."""
        result = agent.fallback(IntentInput(message="eliminar funcion process_data"))
        assert result.operation == "DELETE"

    def test_delete_operation_en(self, agent):
        """Should detect DELETE from English messages."""
        result = agent.fallback(IntentInput(message="delete unused code"))
        assert result.operation == "DELETE"

    def test_refactor_operation_es(self, agent):
        """Should detect REFACTOR from Spanish messages."""
        result = agent.fallback(IntentInput(message="refactorizar clase UserManager"))
        assert result.operation == "REFACTOR"

    def test_refactor_operation_en(self, agent):
        """Should detect REFACTOR from English messages."""
        result = agent.fallback(IntentInput(message="refactor the authentication module"))
        assert result.operation == "REFACTOR"

    def test_analyze_operation_es(self, agent):
        """Should detect ANALYZE from Spanish messages."""
        result = agent.fallback(IntentInput(message="analizar codigo"))
        assert result.operation == "ANALYZE"

    def test_analyze_operation_en(self, agent):
        """Should detect ANALYZE from English messages."""
        result = agent.fallback(IntentInput(message="analyze the code quality"))
        assert result.operation == "ANALYZE"

    def test_explain_operation_es(self, agent):
        """Should detect EXPLAIN from Spanish messages."""
        result = agent.fallback(IntentInput(message="explicar que hace esta funcion"))
        assert result.operation == "EXPLAIN"

    def test_explain_operation_en(self, agent):
        """Should detect EXPLAIN from English messages."""
        result = agent.fallback(IntentInput(message="explain how this code works"))
        assert result.operation == "EXPLAIN"

    def test_debug_operation_es(self, agent):
        """Should detect DEBUG from Spanish messages."""
        result = agent.fallback(IntentInput(message="debug error en login"))
        assert result.operation == "DEBUG"

    def test_debug_operation_en(self, agent):
        """Should detect DEBUG from English messages."""
        result = agent.fallback(IntentInput(message="fix the bug in payment"))
        assert result.operation == "DEBUG"

    def test_optimize_operation_es(self, agent):
        """Should detect OPTIMIZE from Spanish messages."""
        result = agent.fallback(IntentInput(message="optimizar rendimiento de query"))
        assert result.operation == "OPTIMIZE"

    def test_optimize_operation_en(self, agent):
        """Should detect OPTIMIZE from English messages."""
        result = agent.fallback(IntentInput(message="optimize performance of the module"))
        assert result.operation == "OPTIMIZE"

    def test_search_operation_es(self, agent):
        """Should detect SEARCH from Spanish messages."""
        result = agent.fallback(IntentInput(message="buscar definicion de clase"))
        assert result.operation == "SEARCH"

    def test_search_operation_en(self, agent):
        """Should detect SEARCH from English messages."""
        result = agent.fallback(IntentInput(message="find where this function is used"))
        assert result.operation == "SEARCH"


# ============================================================
#  Test: Goal Classification
# ============================================================

class TestIntentAgentGoalClassification:
    """Tests for goal classification in fallback mode."""

    def test_bug_fix_goal(self, agent):
        """Should classify bug fix goals."""
        result = agent.fallback(IntentInput(message="corregir error en login"))
        assert result.goal == "BUG_FIX"

    def test_feature_add_goal(self, agent):
        """Should classify feature add goals."""
        result = agent.fallback(IntentInput(message="agregar nueva funcionalidad"))
        assert result.goal == "FEATURE_ADD"

    def test_security_harden_goal(self, agent):
        """Should classify security hardening goals."""
        result = agent.fallback(IntentInput(message="mejorar seguridad de auth"))
        assert result.goal == "SECURITY_HARDEN"

    def test_performance_goal(self, agent):
        """Should classify performance goals."""
        result = agent.fallback(IntentInput(message="optimizar velocidad"))
        assert result.goal == "PERFORMANCE"


# ============================================================
#  Test: Target and Language Extraction
# ============================================================

class TestIntentAgentExtraction:
    """Tests for target, language, and entity extraction."""

    def test_target_extraction_file(self, agent):
        """Should extract file targets from messages."""
        result = agent.fallback(IntentInput(message="crear modulo auth.py"))
        assert "auth" in result.target.lower()

    def test_target_extraction_kotlin(self, agent):
        """Should extract Kotlin file targets."""
        result = agent.fallback(IntentInput(message="refactorizar archivo UserService.kt"))
        assert result.language == "kotlin"

    def test_target_extraction_javascript(self, agent):
        """Should extract JavaScript file targets."""
        result = agent.fallback(IntentInput(message="analizar codigo en app.js"))
        assert result.language == "javascript"

    def test_target_extraction_typescript(self, agent):
        """Should extract TypeScript file targets."""
        result = agent.fallback(IntentInput(message="revisar modulo api.ts"))
        assert result.language == "typescript"

    def test_code_block_extraction(self, agent):
        """Should extract code from markdown blocks."""
        code = "def hello():\n    print('hello')"
        result = agent.fallback(IntentInput(
            message=f"analizar ```python\n{code}\n```"
        ))
        assert result.language == "python"

    def test_default_language(self, agent):
        """Should default to python when no language detected."""
        result = agent.fallback(IntentInput(message="hacer algo"))
        assert result.language in ["python", ""]

    def test_entities_extraction_function(self, agent):
        """Should extract function entities."""
        result = agent.fallback(IntentInput(message="def process_data(): crear funcion"))
        assert result.entities.get("function") == "process_data"

    def test_entities_extraction_class(self, agent):
        """Should extract class entities."""
        result = agent.fallback(IntentInput(message="class UserManager: refactorizar"))
        assert result.entities.get("class") == "UserManager"


# ============================================================
#  Test: Criticality Inference
# ============================================================

class TestIntentAgentCriticality:
    """Tests for criticality inference."""

    def test_critical_auth(self, agent):
        """Should detect critical for auth-related requests."""
        result = agent.fallback(IntentInput(message="corregir error en login auth"))
        assert result.criticality == "critical"

    def test_critical_crypto(self, agent):
        """Should detect critical for crypto-related requests."""
        result = agent.fallback(IntentInput(message="mejorar seguridad crypto"))
        assert result.criticality == "critical"

    def test_moderate_database(self, agent):
        """Should detect moderate for database-related requests."""
        result = agent.fallback(IntentInput(message="crear modulo database"))
        assert result.criticality == "moderate"

    def test_standard(self, agent):
        """Should default to standard for normal requests."""
        result = agent.fallback(IntentInput(message="crear nueva funcion"))
        assert result.criticality == "standard"
