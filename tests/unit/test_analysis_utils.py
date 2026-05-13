"""
Unit tests for src/core/analysis_utils.py - AnalysisUtils

Tests:
- generate_quality_report: report formatting and alerts
- explain_code: AST-based code explanation
- explain_concept: concept explanation from intent
- analyze_and_respond: analysis response formatting
- general_response: general response formatting
- full_analysis: full analysis report
- apply_fix: code fix application
- check_dependencies: dependency checking via orchestrator
- log_request: request logging to DB
"""

import json
import pytest
from unittest.mock import MagicMock, patch, PropertyMock

from src.core.analysis_utils import AnalysisUtils


# ===========================================================================
#  Fixtures
# ===========================================================================

@pytest.fixture
def utils_no_orch():
    """AnalysisUtils without orchestrator."""
    return AnalysisUtils(orchestrator=None)


@pytest.fixture
def utils_with_orch():
    """AnalysisUtils with a mock orchestrator that has an ast_engine."""
    orch = MagicMock()
    orch.ast_engine = MagicMock()
    return AnalysisUtils(orchestrator=orch)


@pytest.fixture
def sample_intent():
    """A mock intent payload."""
    intent = MagicMock()
    intent.op = "CREATE"
    intent.target = "auth_module"
    intent.goal = "FEATURE_ADD"
    intent.confidence = 0.85
    intent.language = "python"
    return intent


@pytest.fixture
def sample_analysis():
    """Typical AST analysis dict."""
    return {
        "functions": 5,
        "classes": 2,
        "max_complexity": 8,
        "avg_complexity": 3.5,
        "total_complexity": 30,
        "function_names": ["foo", "bar", "baz", "qux", "quux"],
        "class_names": ["MyClass", "OtherClass"],
    }


# ===========================================================================
#  Test: generate_quality_report
# ===========================================================================

class TestGenerateQualityReport:
    """Tests for the static generate_quality_report method."""

    def test_basic_report_structure(self, sample_analysis):
        """Report should contain key metrics."""
        report = AnalysisUtils.generate_quality_report(sample_analysis, "code", "python")
        assert "QUALITY REPORT" in report
        assert "Functions: 5" in report
        assert "Classes: 2" in report
        assert "Max complexity: 8" in report
        assert "Avg complexity: 3.5" in report

    def test_high_complexity_alert(self):
        """Should alert when max_complexity > 10."""
        analysis = {"functions": 3, "classes": 1, "max_complexity": 15,
                     "avg_complexity": 5, "total_complexity": 20}
        report = AnalysisUtils.generate_quality_report(analysis, "code", "python")
        assert "ALERT" in report
        assert "complexity >10" in report

    def test_high_total_complexity_alert(self):
        """Should alert when total_complexity > 50."""
        analysis = {"functions": 10, "classes": 5, "max_complexity": 8,
                     "avg_complexity": 6, "total_complexity": 60}
        report = AnalysisUtils.generate_quality_report(analysis, "code", "python")
        assert "ALERT" in report
        assert "High total complexity" in report

    def test_no_alerts_for_low_complexity(self, sample_analysis):
        """Should not include alerts for low complexity code."""
        report = AnalysisUtils.generate_quality_report(sample_analysis, "code", "python")
        assert "ALERT" not in report

    def test_missing_keys_default_to_zero(self):
        """Missing analysis keys should default to 0."""
        report = AnalysisUtils.generate_quality_report({}, "code", "python")
        assert "Functions: 0" in report
        assert "Classes: 0" in report


# ===========================================================================
#  Test: explain_code
# ===========================================================================

class TestExplainCode:
    """Tests for the static explain_code method."""

    def test_explains_python_function(self):
        """Should extract function info from Python code."""
        code = 'def hello(name):\n    """Greet."""\n    return f"Hello {name}"'
        result = AnalysisUtils.explain_code(code, "python", {})
        assert "CODE ANALYSIS" in result
        assert "Function: hello" in result
        assert "name" in result  # arg listed

    def test_explains_python_class(self):
        """Should extract class info from Python code."""
        code = 'class Foo:\n    """A foo."""\n    def bar(self):\n        pass'
        result = AnalysisUtils.explain_code(code, "python", {})
        assert "Class: Foo" in result
        assert "bar" in result  # method listed

    def test_syntax_error_handling(self):
        """Should handle syntax errors gracefully."""
        code = "def broken("
        result = AnalysisUtils.explain_code(code, "python", {})
        assert "Syntax error" in result

    def test_includes_ast_metrics(self, sample_analysis):
        """Should append AST metrics when provided."""
        code = "x = 1"
        result = AnalysisUtils.explain_code(code, "python", sample_analysis)
        assert "Metrics: 5 functions, 2 classes" in result

    def test_non_python_language(self):
        """Non-python language should skip AST parsing."""
        code = "func main() {}"
        result = AnalysisUtils.explain_code(code, "go", {})
        assert "CODE ANALYSIS" in result
        # No function extraction for Go via AST
        assert "Function:" not in result


# ===========================================================================
#  Test: explain_concept
# ===========================================================================

class TestExplainConcept:
    """Tests for the static explain_concept method."""

    def test_includes_operation(self, sample_intent):
        """Should include the operation type."""
        result = AnalysisUtils.explain_concept(sample_intent)
        assert "CREATE" in result

    def test_includes_target_and_goal(self, sample_intent):
        """Should include target and goal."""
        result = AnalysisUtils.explain_concept(sample_intent)
        assert "auth_module" in result
        assert "FEATURE_ADD" in result

    def test_includes_confidence(self, sample_intent):
        """Should include confidence score."""
        result = AnalysisUtils.explain_concept(sample_intent)
        assert "0.85" in result


# ===========================================================================
#  Test: analyze_and_respond
# ===========================================================================

class TestAnalyzeAndRespond:
    """Tests for the static analyze_and_respond method."""

    def test_includes_operation(self, sample_intent, sample_analysis):
        """Should include the operation in header."""
        result = AnalysisUtils.analyze_and_respond("code", sample_intent, sample_analysis)
        assert "ANALYSIS" in result
        assert "CREATE" in result

    def test_includes_complexity(self, sample_intent, sample_analysis):
        """Should include avg complexity."""
        result = AnalysisUtils.analyze_and_respond("code", sample_intent, sample_analysis)
        assert "3.5" in result

    def test_empty_analysis(self, sample_intent):
        """Should handle empty analysis gracefully."""
        result = AnalysisUtils.analyze_and_respond("code", sample_intent, None)
        assert "ANALYSIS" in result


# ===========================================================================
#  Test: general_response
# ===========================================================================

class TestGeneralResponse:
    """Tests for the static general_response method."""

    def test_includes_intent_fields(self, sample_intent):
        """Should include op, target, goal, language."""
        result = AnalysisUtils.general_response(sample_intent)
        assert "CREATE" in result
        assert "auth_module" in result
        assert "FEATURE_ADD" in result
        assert "python" in result

    def test_prompt_for_code(self, sample_intent):
        """Should prompt user to include code."""
        result = AnalysisUtils.general_response(sample_intent)
        assert "```python" in result


# ===========================================================================
#  Test: full_analysis
# ===========================================================================

class TestFullAnalysis:
    """Tests for the static full_analysis method."""

    def test_full_report_structure(self, sample_intent, sample_analysis):
        """Should include language, operation, and metrics."""
        result = AnalysisUtils.full_analysis("code", sample_intent, sample_analysis, "python")
        assert "FULL ANALYSIS" in result
        assert "Language: python" in result
        assert "Operation: CREATE" in result
        assert "Functions: 5" in result
        assert "Classes: 2" in result
        assert "Max complexity: 8" in result

    def test_no_analysis(self, sample_intent):
        """Should handle None analysis."""
        result = AnalysisUtils.full_analysis("code", sample_intent, None, "python")
        assert "FULL ANALYSIS" in result
        assert "Language: python" in result

    def test_empty_analysis(self, sample_intent):
        """Should handle empty analysis dict."""
        result = AnalysisUtils.full_analysis("code", sample_intent, {}, "go")
        assert "Language: go" in result


# ===========================================================================
#  Test: apply_fix
# ===========================================================================

class TestApplyFix:
    """Tests for apply_fix method."""

    def test_python_fix_delegates_to_code_transformer(self, utils_no_orch):
        """apply_fix with python should delegate to CodeTransformer."""
        with patch("src.core.code_transformer.CodeTransformer") as MockCT:
            MockCT.fix_python.return_value = "fixed_code"
            result = utils_no_orch.apply_fix("broken code", MagicMock(), "python")
            MockCT.fix_python.assert_called_once()
            assert result == "fixed_code"

    def test_non_python_returns_original(self, utils_no_orch):
        """apply_fix with non-python language should return original code."""
        result = utils_no_orch.apply_fix("some code", MagicMock(), "go")
        assert result == "some code"

    def test_empty_code_returns_empty(self, utils_no_orch):
        """apply_fix with empty code should return empty string."""
        result = utils_no_orch.apply_fix("", MagicMock(), "python")
        assert result == ""


# ===========================================================================
#  Test: check_dependencies
# ===========================================================================

class TestCheckDependencies:
    """Tests for check_dependencies method."""

    def test_no_orchestrator_returns_message(self, utils_no_orch):
        """Without orchestrator, should return 'No orchestrator' message."""
        result = utils_no_orch.check_dependencies("code", "target.py", "python")
        assert len(result) == 1
        assert "No orchestrator" in result[0]

    def test_no_ast_engine_returns_message(self):
        """Without ast_engine on orchestrator, should return 'No AST engine' message."""
        orch = MagicMock(spec=[])
        utils = AnalysisUtils(orchestrator=orch)
        result = utils.check_dependencies("code", "target.py", "python")
        assert len(result) == 1
        assert "No AST engine" in result[0]

    def test_with_nodes_returns_deps(self, utils_with_orch):
        """With ast_engine returning nodes, should format dependencies."""
        utils_with_orch._orchestrator.ast_engine.get_node_info.return_value = [
            {"node_type": "function", "name": "foo", "connections": json.dumps(["bar", "baz"])},
        ]
        result = utils_with_orch.check_dependencies("code", "target", "python")
        assert len(result) == 1
        assert "foo" in result[0]
        assert "bar" in result[0]

    def test_no_nodes_returns_not_found(self, utils_with_orch):
        """When no nodes found for target, should return 'No dependencies'."""
        utils_with_orch._orchestrator.ast_engine.get_node_info.return_value = []
        result = utils_with_orch.check_dependencies("code", "missing.py", "python")
        assert len(result) == 1
        assert "No dependencies found" in result[0]


# ===========================================================================
#  Test: log_request
# ===========================================================================

class TestLogRequest:
    """Tests for log_request method."""

    @patch("src.core.analysis_utils.get_connection")
    def test_successful_log(self, mock_get_conn, sample_intent):
        """Should insert a row into the request_log DB."""
        mock_conn = MagicMock()
        mock_get_conn.return_value = mock_conn
        AnalysisUtils.log_request(sample_intent, "SUCCESS", 150)
        mock_conn.execute.assert_called_once()
        mock_conn.commit.assert_called_once()

    @patch("src.core.analysis_utils.get_connection")
    def test_log_with_cache_hit(self, mock_get_conn, sample_intent):
        """Should pass cache_hit flag through."""
        mock_conn = MagicMock()
        mock_get_conn.return_value = mock_conn
        AnalysisUtils.log_request(sample_intent, "CACHED", 10, cache_hit=True)
        call_args = mock_conn.execute.call_args[0][1]
        assert call_args[-1] == 1  # cache_hit=True -> int(True)=1

    @patch("src.core.analysis_utils.get_connection")
    def test_db_error_handled_gracefully(self, mock_get_conn, sample_intent):
        """Should not raise when DB fails."""
        mock_get_conn.side_effect = Exception("DB down")
        # Should not raise
        AnalysisUtils.log_request(sample_intent, "SUCCESS", 100)
