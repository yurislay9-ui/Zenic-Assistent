"""
Tests for Layer 8: Verdict Engine agents (A40-A43).

All 4 agents tested:
  - A40 DeterministicPipeline (7 deterministic tasks)
  - A41 EvidenceCollectorV18
  - A42 ConsensusResolverV18
  - A43 VerdictEngineV18
"""

import pytest

from src.core.agents.verdict import (
    DeterministicPipeline,
    EvidenceCollectorV18,
    ConsensusResolverV18,
    VerdictEngineV18,
)
from src.core.agents.schemas import (
    PipelineResult,
    Evidence,
    EvidenceType,
    ConsensusResult,
    Verdict,
    VerdictInput,
    VerdictOutput,
    SecurityResult,
    SyntaxResult,
    CriticalityResult,
    IntentResult,
    ValidationIssue,
)


# ======================================================================
# A40 DeterministicPipeline Tests
# ======================================================================



class TestDeterministicPipeline:
    """A40: Execute all 7 deterministic tasks without AI."""

    def setup_method(self):
        self.pipeline = DeterministicPipeline()

    # --- Full pipeline execution ---

    def test_full_pipeline_string_input(self):
        """String input should run all 7 tasks."""
        result = self.pipeline.execute("Create a new API endpoint in app.py")
        assert isinstance(result, PipelineResult)
        assert result.classify is not None
        assert result.extract is not None
        assert result.pattern is not None
        assert result.fill is not None
        assert result.generate is not None
        assert result.explain is not None
        assert result.subtask is not None
        assert result.source == "deterministic"

    def test_full_pipeline_dict_input(self):
        """Dict input should run all 7 tasks."""
        result = self.pipeline.execute({
            "text": "Refactor the user auth module",
            "code": "def login(): pass",
            "language": "python",
        })
        assert isinstance(result, PipelineResult)
        assert result.classify is not None

    def test_full_pipeline_empty_input(self):
        """Empty input should still return PipelineResult."""
        result = self.pipeline.execute("")
        assert isinstance(result, PipelineResult)

    # --- Task 1: classify_intent ---

    def test_classify_create(self):
        """'create' should classify as CREATE."""
        result = self.pipeline.classify_intent("Create a new feature")
        assert result["operation"] == "CREATE"
        assert result["confidence"] > 0

    def test_classify_refactor(self):
        """'refactor' should classify as REFACTOR."""
        result = self.pipeline.classify_intent("Refactor the codebase")
        assert result["operation"] == "REFACTOR"

    def test_classify_delete(self):
        """'delete' should classify as DELETE."""
        result = self.pipeline.classify_intent("Delete the old module")
        assert result["operation"] == "DELETE"

    def test_classify_debug(self):
        """'fix' should classify as DEBUG."""
        result = self.pipeline.classify_intent("Fix the login bug")
        assert result["operation"] == "DEBUG"

    def test_classify_analyze(self):
        """'analyze' should classify as ANALYZE."""
        result = self.pipeline.classify_intent("Analyze the performance metrics")
        assert result["operation"] == "ANALYZE"

    def test_classify_optimize(self):
        """'optimize' should classify as OPTIMIZE."""
        result = self.pipeline.classify_intent("Optimize performance and speed up latency")
        assert result["operation"] in ("OPTIMIZE", "ANALYZE")

    def test_classify_es(self):
        """Spanish keywords should work."""
        result = self.pipeline.classify_intent("Crear una nueva funcionalidad")
        assert result["operation"] == "CREATE"

    def test_classify_goal_feature(self):
        """'feature' should set goal to FEATURE_ADD."""
        result = self.pipeline.classify_intent("Add a new feature for reporting")
        assert result["goal"] == "FEATURE_ADD"

    def test_classify_goal_security(self):
        """'security' should set goal to SECURITY_HARDEN."""
        result = self.pipeline.classify_intent("Fix security vulnerability in auth")
        assert result["goal"] == "SECURITY_HARDEN"

    def test_classify_empty(self):
        """Empty text should return SEARCH with 0 confidence."""
        result = self.pipeline.classify_intent("")
        assert result["operation"] == "SEARCH"
        assert result["confidence"] == 0.0

    # --- Task 2: extract_entities ---

    def test_extract_python_file(self):
        result = self.pipeline.extract_entities("Edit app.py to add endpoint")
        assert result["file"] == "app.py"
        assert result["lang"] == "python"

    def test_extract_javascript_file(self):
        result = self.pipeline.extract_entities("Fix bug in utils.js")
        assert result["file"] == "utils.js"
        assert result["lang"] == "javascript"

    def test_extract_function_name(self):
        result = self.pipeline.extract_entities("Fix the def process_data function")
        assert result["function"] == "process_data"

    def test_extract_language_from_keywords(self):
        result = self.pipeline.extract_entities("Write python code for data processing")
        assert result["lang"] == "python"

    def test_extract_no_file(self):
        result = self.pipeline.extract_entities("Fix the authentication system")
        assert result["file"] == ""

    def test_extract_empty(self):
        result = self.pipeline.extract_entities("")
        assert result["lang"] == "unknown"

    # --- Task 3: suggest_pattern ---

    def test_suggest_async(self):
        result = self.pipeline.suggest_pattern("handler", "Implement async processing")
        assert result["result"] == "async_await_pattern"

    def test_suggest_validator(self):
        result = self.pipeline.suggest_pattern("input", "Add validate and check data")
        assert result["result"] == "validator_pattern"

    def test_suggest_security(self):
        result = self.pipeline.suggest_pattern("auth", "Add security and authentication")
        assert result["result"] == "security_pattern"

    def test_suggest_default(self):
        result = self.pipeline.suggest_pattern("target", "Do something random")
        assert result["result"] == "default_pattern"
        assert result["confidence"] < 0.5

    # --- Task 4: fill_template_gaps ---

    def test_fill_gaps_with_context(self):
        template = "def __GAP_NAME__(): return __GAP_TYPE__"
        result = self.pipeline.fill_template_gaps(template, {"name": "process", "type": "str"})
        assert "process" in result["result"]
        assert "str" in result["result"]
        assert "__GAP_" not in result["result"]

    def test_fill_gaps_with_defaults(self):
        template = "def __GAP_NAME__(): pass"
        result = self.pipeline.fill_template_gaps(template, {})
        assert "generated" in result["result"]
        assert "__GAP_" not in result["result"]

    def test_fill_no_gaps(self):
        template = "def hello(): pass"
        result = self.pipeline.fill_template_gaps(template, {})
        assert result["result"] == template
        assert result["confidence"] == 1.0

    def test_fill_empty_template(self):
        result = self.pipeline.fill_template_gaps("", {})
        assert result["result"] == ""

    # --- Task 5: generate_pattern ---

    def test_generate_validator_python(self):
        result = self.pipeline.generate_pattern("validate input data", "python")
        assert "def" in result["result"]
        assert result["confidence"] > 0.5

    def test_generate_async_python(self):
        result = self.pipeline.generate_pattern("async await processing", "python")
        assert "async def" in result["result"]

    def test_generate_javascript(self):
        result = self.pipeline.generate_pattern("default", "javascript")
        assert result["result"] != ""

    def test_generate_default_pattern(self):
        result = self.pipeline.generate_pattern("something random", "python")
        assert result["result"] != ""
        assert result["confidence"] < 0.6

    # --- Task 6: explain_violation ---

    def test_explain_eval(self):
        result = self.pipeline.explain_violation("code", ["eval_call"])
        assert "code execution" in result["result"].lower() or "eval" in result["result"].lower()
        assert result["confidence"] == 0.95

    def test_explain_exec(self):
        result = self.pipeline.explain_violation("code", ["exec_call"])
        assert "exec" in result["result"].lower()

    def test_explain_multiple(self):
        result = self.pipeline.explain_violation("code", ["eval_call", "os_system"])
        assert len(result["result"]) > 20

    def test_explain_unknown_violation(self):
        result = self.pipeline.explain_violation("code", ["custom_issue"])
        assert "custom_issue" in result["result"]

    def test_explain_no_violations(self):
        result = self.pipeline.explain_violation("code", [])
        assert "No violations" in result["result"]

    # --- Task 7: describe_subtask ---

    def test_describe_subtask(self):
        result = self.pipeline.describe_subtask("app.py", "refactor")
        assert "refactor" in result["result"]
        assert "app" in result["result"]

    def test_describe_subtask_sanitizes(self):
        result = self.pipeline.describe_subtask("My Module.py", "create")
        assert " " not in result["result"]
        assert result["result"].islower() or "_" in result["result"]

    def test_describe_subtask_short_name(self):
        result = self.pipeline.describe_subtask("", "")
        assert result["result"] == "unnamed_subtask"

    # --- Fallback ---

    def test_fallback_returns_pipeline_result(self):
        result = self.pipeline.fallback(None)
        assert isinstance(result, PipelineResult)
        assert result.source == "fallback"


# ======================================================================
# A41 EvidenceCollectorV18 Tests
# ======================================================================

