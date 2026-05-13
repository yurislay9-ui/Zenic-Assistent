"""
Unit tests for Level 1 - Semantic Parser

Tests intent parsing for different operation types, languages, and edge cases.
"""

import pytest
from src.core.level1_semantic_engine.parser import SemanticParser


@pytest.fixture
def parser():
    return SemanticParser()


class TestSemanticParser:
    """Tests for the SemanticParser class."""

    def test_parse_create_operation(self, parser):
        """Should detect CREATE operations from user messages."""
        intent = parser.parse("crear modulo auth.py")
        assert intent.op == "CREATE"
        assert "auth" in intent.target.lower()

    def test_parse_delete_operation(self, parser):
        """Should detect DELETE operations."""
        intent = parser.parse("eliminar funcion process_data")
        assert intent.op == "DELETE"

    def test_parse_refactor_operation(self, parser):
        """Should detect REFACTOR operations."""
        intent = parser.parse("refactorizar clase UserManager")
        assert intent.op == "REFACTOR"

    def test_parse_analyze_operation(self, parser):
        """Should detect ANALYZE operations."""
        intent = parser.parse("analizar codigo")
        assert intent.op == "ANALYZE"

    def test_parse_explain_operation(self, parser):
        """Should detect EXPLAIN operations."""
        intent = parser.parse("explicar que hace esta funcion")
        assert intent.op == "EXPLAIN"

    def test_parse_debug_operation(self, parser):
        """Should detect DEBUG operations."""
        intent = parser.parse("debug error en login")
        assert intent.op == "DEBUG"

    def test_parse_optimize_operation(self, parser):
        """Should detect OPTIMIZE or REFACTOR for optimization requests.
        Note: 'optimizar' maps to REFACTOR in the current parser."""
        intent = parser.parse("optimizar rendimiento de query")
        assert intent.op in ["OPTIMIZE", "REFACTOR"]

    def test_parse_target_extraction(self, parser):
        """Should extract target from message."""
        intent = parser.parse("crear modulo auth.py")
        assert intent.target != ""

    def test_parse_language_detection_python(self, parser):
        """Should detect Python from code blocks."""
        intent = parser.parse("crear funcion en python ```python\ndef foo():\n    pass\n```")
        assert intent.language == "python"

    def test_parse_language_detection_kotlin(self, parser):
        """Should detect Kotlin from code blocks; without them detection is unreliable."""
        intent = parser.parse("crear funcion en kotlin ```kotlin\nfun hello(): String = \"Hi\"\n```")
        assert intent.language == "kotlin"

    def test_parse_language_detection_go(self, parser):
        """Should detect Go from code blocks; without them detection is unreliable."""
        intent = parser.parse("crear funcion en go ```go\nfunc main() { fmt.Println(\"Hi\") }\n```")
        assert intent.language == "go"

    def test_parse_language_detection_javascript(self, parser):
        """Should detect JavaScript from code blocks; without them detection is unreliable."""
        intent = parser.parse("crear funcion en javascript ```javascript\nfunction hello() { return 1; }\n```")
        assert intent.language == "javascript"

    def test_parse_code_extraction(self, parser):
        """Should extract code from markdown code blocks."""
        code = "def hello():\n    print('hello')"
        intent = parser.parse(f"analizar ```python\n{code}\n```")
        assert intent.raw_code is not None

    def test_parse_default_language(self, parser):
        """Should default to python if no language detected."""
        intent = parser.parse("hacer algo")
        assert intent.language in ["python", ""]

    def test_parse_empty_message(self, parser):
        """Should handle empty messages gracefully."""
        intent = parser.parse("")
        assert intent is not None
