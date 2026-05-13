"""
Unit tests for intent_shared.py — shared intent constants & utilities.

Tests the shared constants and utility functions used by both
IntentAgent and SurgicalAgent:
  - VALID_OPERATIONS, VALID_GOALS, VALID_LANGUAGES
  - EXT_LANG_MAP, FENCE_LANG_MAP
  - extract_target_and_language()
  - extract_code_block()
  - extract_entities()
  - infer_criticality()
  - infer_template_type()
"""

import pytest

from src.core.agents.intent_shared import (
    VALID_OPERATIONS,
    VALID_GOALS,
    VALID_LANGUAGES,
    EXT_LANG_MAP,
    FENCE_LANG_MAP,
    OP_KEYWORDS,
    GOAL_KEYWORDS,
    extract_target_and_language,
    extract_code_block,
    extract_entities,
    infer_criticality,
    infer_template_type,
)


# ============================================================
#  Test: Constants
# ============================================================

class TestValidConstants:
    """Tests for the constant frozensets and mappings."""

    def test_valid_operations_are_frozenset(self):
        """VALID_OPERATIONS should be an immutable frozenset."""
        assert isinstance(VALID_OPERATIONS, frozenset)

    def test_valid_operations_contains_create(self):
        """Should contain the CREATE operation."""
        assert "CREATE" in VALID_OPERATIONS

    def test_valid_operations_count(self):
        """Should contain exactly 8 operations."""
        assert len(VALID_OPERATIONS) == 8

    def test_valid_goals_are_frozenset(self):
        """VALID_GOALS should be an immutable frozenset."""
        assert isinstance(VALID_GOALS, frozenset)

    def test_valid_goals_contains_security_harden(self):
        """Should contain SECURITY_HARDEN goal."""
        assert "SECURITY_HARDEN" in VALID_GOALS

    def test_valid_languages_are_frozenset(self):
        """VALID_LANGUAGES should be an immutable frozenset."""
        assert isinstance(VALID_LANGUAGES, frozenset)

    def test_valid_languages_includes_python(self):
        """Should include python as a valid language."""
        assert "python" in VALID_LANGUAGES

    def test_ext_lang_map_py(self):
        """Should map .py extension to python."""
        assert EXT_LANG_MAP[".py"] == "python"

    def test_ext_lang_map_kt(self):
        """Should map .kt extension to kotlin."""
        assert EXT_LANG_MAP[".kt"] == "kotlin"

    def test_fence_lang_map_python_alias(self):
        """Should map 'py' fence to python."""
        assert FENCE_LANG_MAP["py"] == "python"

    def test_fence_lang_map_golang(self):
        """Should map 'golang' fence to go."""
        assert FENCE_LANG_MAP["golang"] == "go"


# ============================================================
#  Test: extract_target_and_language
# ============================================================

class TestExtractTargetAndLanguage:
    """Tests for extract_target_and_language()."""

    def test_module_reference_es(self):
        """Should extract target from Spanish module reference."""
        target, lang = extract_target_and_language("crear modulo auth.py")
        assert "auth.py" in target
        assert lang == "python"

    def test_file_reference_en(self):
        """Should extract target from English file reference."""
        target, lang = extract_target_and_language("create file user_service.kt")
        assert "user_service.kt" in target
        assert lang == "kotlin"

    def test_direct_file_reference(self):
        """Should extract target from direct file reference without keyword."""
        target, lang = extract_target_and_language("refactor auth.py")
        assert "auth.py" in target
        assert lang == "python"

    def test_language_override_en(self):
        """Should override language with explicit 'in Go' pattern."""
        target, lang = extract_target_and_language("create service in go")
        assert lang == "go"

    def test_language_override_es(self):
        """Should override language with explicit 'en Kotlin' pattern."""
        target, lang = extract_target_and_language("crear servicio en kotlin")
        assert lang == "kotlin"

    def test_default_language_python(self):
        """Should default to python when no language is detected."""
        target, lang = extract_target_and_language("crear modulo")
        assert lang == "python"

    def test_go_extension(self):
        """Should detect Go language from .go extension."""
        target, lang = extract_target_and_language("create file main.go")
        assert lang == "go"

    def test_rust_extension(self):
        """Should detect Rust language from .rs extension."""
        target, lang = extract_target_and_language("create module lib.rs")
        assert lang == "rust"


# ============================================================
#  Test: extract_code_block
# ============================================================

class TestExtractCodeBlock:
    """Tests for extract_code_block()."""

    def test_python_fenced_block(self):
        """Should extract Python code from fenced block."""
        msg = "Here is code:\n```python\ndef hello():\n    print('hi')\n```\nDone"
        lang, code = extract_code_block(msg)
        assert lang == "python"
        assert "def hello():" in code

    def test_kotlin_fenced_block(self):
        """Should extract Kotlin code from fenced block."""
        msg = "```kotlin\nfun main() {}\n```"
        lang, code = extract_code_block(msg)
        assert lang == "kotlin"
        assert "fun main()" in code

    def test_no_code_block(self):
        """Should return empty strings when no code block found."""
        lang, code = extract_code_block("just plain text no code")
        assert lang == ""
        assert code == ""

    def test_fenced_block_without_language(self):
        """Should default to python for fenced blocks without language tag."""
        msg = "```\nimport os\nprint('hi')\n```"
        lang, code = extract_code_block(msg)
        assert lang == "python"
        assert "import os" in code

    def test_inline_code_with_def(self):
        """Should detect inline code with 'def ' keyword."""
        msg = "use `def process_data(): return True and check it`"
        lang, code = extract_code_block(msg)
        assert lang == "python"
        assert "def process_data()" in code

    def test_go_fence_alias(self):
        """Should map 'golang' fence to 'go' language."""
        msg = "```golang\nfunc main() {}\n```"
        lang, code = extract_code_block(msg)
        assert lang == "go"


# ============================================================
#  Test: extract_entities
# ============================================================

class TestExtractEntities:
    """Tests for extract_entities()."""

    def test_file_entities(self):
        """Should extract file references."""
        entities = extract_entities("refactor auth.py and user_service.kt")
        assert "auth.py" in entities["files"]
        assert "user_service.kt" in entities["files"]

    def test_class_entities(self):
        """Should extract class names."""
        entities = extract_entities("create class UserManager")
        assert "UserManager" in entities["classes"]

    def test_function_entities(self):
        """Should extract function names."""
        entities = extract_entities("def process_data and function calculate")
        assert "process_data" in entities["functions"]
        assert "calculate" in entities["functions"]

    def test_number_entities(self):
        """Should extract numbers."""
        entities = extract_entities("discount of 16% and 0.5 ratio")
        assert len(entities["numbers"]) >= 2
        # Regex captures digits+optional_decimal+optional_percent,
        # so '16' or '16%' and '0.5' are both extracted
        assert any("16" in n for n in entities["numbers"])
        assert "0.5" in entities["numbers"]

    def test_no_entities(self):
        """Should return empty dict for messages with no entities."""
        entities = extract_entities("just some plain words")
        assert entities == {}


# ============================================================
#  Test: infer_criticality
# ============================================================

class TestInferCriticality:
    """Tests for infer_criticality()."""

    def test_critical_delete_with_security(self):
        """DELETE + SECURITY_HARDEN should be critical."""
        assert infer_criticality("DELETE", "SECURITY_HARDEN") == "critical"

    def test_critical_refactor_with_bug_fix(self):
        """REFACTOR + BUG_FIX should be critical."""
        assert infer_criticality("REFACTOR", "BUG_FIX") == "critical"

    def test_critical_auth_target_with_security(self):
        """Auth target + SECURITY_HARDEN should be critical."""
        assert infer_criticality("CREATE", "SECURITY_HARDEN", "auth") == "critical"

    def test_critical_payment_target_with_delete(self):
        """Payment target + DELETE should be critical."""
        assert infer_criticality("DELETE", "FEATURE_ADD", "payment") == "critical"

    def test_moderate_auth_target(self):
        """Auth target without security op/goal should be moderate."""
        assert infer_criticality("CREATE", "FEATURE_ADD", "auth") == "moderate"

    def test_moderate_delete_alone(self):
        """DELETE without critical goal should be moderate."""
        assert infer_criticality("DELETE", "FEATURE_ADD") == "moderate"

    def test_moderate_security_harden_alone(self):
        """SECURITY_HARDEN without critical op should be moderate."""
        assert infer_criticality("CREATE", "SECURITY_HARDEN") == "moderate"

    def test_standard_safe(self):
        """CREATE + FEATURE_ADD with no critical target should be standard."""
        assert infer_criticality("CREATE", "FEATURE_ADD") == "standard"

    def test_standard_search_explain(self):
        """SEARCH + READABILITY should be standard."""
        assert infer_criticality("SEARCH", "READABILITY") == "standard"


# ============================================================
#  Test: infer_template_type
# ============================================================

class TestInferTemplateType:
    """Tests for infer_template_type()."""

    def test_auth_system(self):
        """Should detect auth_system template."""
        assert infer_template_type("CREATE", "login page with jwt") == "auth_system"

    def test_crud_dashboard(self):
        """Should detect crud_dashboard template."""
        assert infer_template_type("CREATE", "management panel") == "crud_dashboard"

    def test_inventory(self):
        """Should detect inventory template."""
        assert infer_template_type("CREATE", "stock inventory system") == "inventory"

    def test_invoice_billing(self):
        """Should detect invoice_billing template."""
        assert infer_template_type("CREATE", "invoice payment system") == "invoice_billing"

    def test_task_manager(self):
        """Should detect task_manager template."""
        assert infer_template_type("CREATE", "task project manager") == "task_manager"

    def test_crm(self):
        """Should detect crm template."""
        assert infer_template_type("CREATE", "customer sales CRM") == "crm"

    def test_web_api(self):
        """Should detect web_api template."""
        assert infer_template_type("CREATE", "REST API endpoint") == "web_api"

    def test_notification(self):
        """Should detect notification template."""
        assert infer_template_type("CREATE", "alert notification system") == "notification"

    def test_generic_fallback(self):
        """Should return generic for unrecognized descriptions."""
        assert infer_template_type("CREATE", "some random thing") == "generic"

    def test_empty_description(self):
        """Should return generic for empty description."""
        assert infer_template_type("CREATE", "") == "generic"


# ============================================================
#  Test: Keyword Maps Completeness
# ============================================================

class TestKeywordMaps:
    """Tests for keyword map completeness and consistency."""

    def test_op_keywords_covers_all_operations(self):
        """OP_KEYWORDS should have entries for all VALID_OPERATIONS."""
        for op in VALID_OPERATIONS:
            assert op in OP_KEYWORDS, f"Missing OP_KEYWORDS entry for {op}"

    def test_goal_keywords_covers_all_goals(self):
        """GOAL_KEYWORDS should have entries for all VALID_GOALS."""
        for goal in VALID_GOALS:
            assert goal in GOAL_KEYWORDS, f"Missing GOAL_KEYWORDS entry for {goal}"

    def test_op_keywords_are_lists(self):
        """Each OP_KEYWORDS entry should be a list of strings."""
        for op, kws in OP_KEYWORDS.items():
            assert isinstance(kws, list), f"OP_KEYWORDS[{op}] should be list"
            for kw in kws:
                assert isinstance(kw, str), f"Keyword {kw} in OP_KEYWORDS[{op}] should be str"

    def test_goal_keywords_are_lists(self):
        """Each GOAL_KEYWORDS entry should be a list of strings."""
        for goal, kws in GOAL_KEYWORDS.items():
            assert isinstance(kws, list), f"GOAL_KEYWORDS[{goal}] should be list"
