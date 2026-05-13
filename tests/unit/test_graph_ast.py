"""
Unit tests for Level 3 - Graph AST Engine

Tests AST parsing for Python and other languages, node storage, and queries.
"""

import pytest
from src.core.level3_graph_ast.engine import GraphASTEngine


@pytest.fixture
def engine():
    return GraphASTEngine()


PYTHON_CODE = '''
import os
import sys
from pathlib import Path

def hello(name: str) -> str:
    """Greet someone."""
    return f"Hello, {name}!"

class User:
    """User model."""
    def __init__(self, name: str):
        self.name = name

    def greet(self):
        if self.name:
            return hello(self.name)
        return "Hello, stranger!"
'''

KOTLIN_CODE = '''
fun main() {
    println("Hello")
}

companion object Factory {
    fun create(): User = User()
}
'''

GO_CODE = '''
package main

import "fmt"

func main() {
    fmt.Println("Hello")
}

func (u *User) Greet() string {
    return "Hello"
}
'''

JAVASCRIPT_CODE = '''
function hello(name) {
    return "Hello, " + name;
}

const greet = (name) => hello(name);

async function fetchData() {
    const res = await fetch("/api");
    return res.json();
}
'''

RUST_CODE = '''
pub fn main() {
    println!("Hello");
}

fn process(data: &str) -> String {
    data.to_string()
}
'''


class TestGraphASTEnginePython:
    """Tests for Python AST parsing."""

    def test_parse_python_functions(self, engine):
        """Should detect all function definitions."""
        nodes = engine.scan_code(PYTHON_CODE, "test.py", "python")
        func_names = [n["name"] for n in nodes if n["node_type"] == "function"]
        assert "hello" in func_names

    def test_parse_python_classes(self, engine):
        """Should detect class definitions."""
        nodes = engine.scan_code(PYTHON_CODE, "test.py", "python")
        class_names = [n["name"] for n in nodes if n["node_type"] == "class"]
        assert "User" in class_names

    def test_parse_python_imports(self, engine):
        """Should detect import statements."""
        nodes = engine.scan_code(PYTHON_CODE, "test.py", "python")
        imports = [n for n in nodes if n["node_type"] == "import"]
        assert len(imports) >= 2

    def test_cyclomatic_complexity(self, engine):
        """Should calculate cyclomatic complexity correctly."""
        nodes = engine.scan_code(PYTHON_CODE, "test.py", "python")
        greet_func = [n for n in nodes if n["name"] == "greet"]
        assert len(greet_func) > 0, "Should find 'greet' function in parsed code"
        # greet() has an if, so complexity >= 2
        assert greet_func[0]["complexity"] >= 2

    def test_extract_calls(self, engine):
        """Should extract function call dependencies."""
        nodes = engine.scan_code(PYTHON_CODE, "test.py", "python")
        greet_func = [n for n in nodes if n["name"] == "greet"]
        assert len(greet_func) > 0, "Should find 'greet' function in parsed code"
        import json
        calls = json.loads(greet_func[0].get("connections", "[]"))
        # greet() calls hello()
        assert any("hello" in str(c) for c in calls)

    def test_class_connections(self, engine):
        """Should extract class method connections."""
        nodes = engine.scan_code(PYTHON_CODE, "test.py", "python")
        user_class = [n for n in nodes if n["name"] == "User"]
        assert len(user_class) > 0, "Should find 'User' class in parsed code"
        import json
        conns = json.loads(user_class[0].get("connections", "[]"))
        method_conns = [c for c in conns if str(c).startswith("method:")]
        assert len(method_conns) >= 1

    def test_syntax_error_handling(self, engine):
        """Should handle syntax errors gracefully."""
        bad_code = "def broken(\n    pass"
        nodes = engine.scan_code(bad_code, "broken.py", "python")
        assert isinstance(nodes, list)

    def test_analyze_structure(self, engine):
        """Should return proper structure analysis."""
        result = engine.analyze_structure(PYTHON_CODE, "python")
        assert result["functions"] >= 1
        assert result["classes"] >= 1
        assert "function_names" in result
        assert "class_names" in result


class TestGraphASTEngineRegex:
    """Tests for regex-based parsing of other languages."""

    def test_parse_kotlin(self, engine):
        """Should detect Kotlin functions."""
        nodes = engine.scan_code(KOTLIN_CODE, "test.kt", "kotlin")
        assert len(nodes) >= 1

    def test_parse_go(self, engine):
        """Should detect Go functions."""
        nodes = engine.scan_code(GO_CODE, "test.go", "go")
        assert len(nodes) >= 1

    def test_parse_javascript(self, engine):
        """Should detect JavaScript functions."""
        nodes = engine.scan_code(JAVASCRIPT_CODE, "test.js", "javascript")
        assert len(nodes) >= 1

    def test_parse_rust(self, engine):
        """Should detect Rust functions."""
        nodes = engine.scan_code(RUST_CODE, "test.rs", "rust")
        assert len(nodes) >= 1

    def test_regex_nodes_are_functions(self, engine):
        """Regex-parsed nodes should be type 'function'."""
        nodes = engine.scan_code(KOTLIN_CODE, "test.kt", "kotlin")
        for node in nodes:
            assert node["node_type"] == "function"


class TestGraphASTEngineStorage:
    """Tests for node storage and retrieval."""

    def test_get_node_info(self, engine):
        """Should retrieve stored nodes by name."""
        engine.scan_code(PYTHON_CODE, "test.py", "python")
        results = engine.get_node_info("hello")
        assert len(results) >= 1
        assert results[0]["name"] == "hello"

    def test_get_node_info_partial_match(self, engine):
        """Should support partial name matching."""
        engine.scan_code(PYTHON_CODE, "test.py", "python")
        results = engine.get_node_info("Us")
        assert len(results) >= 1

    def test_get_node_info_not_found(self, engine):
        """Should return empty list for non-existent nodes."""
        results = engine.get_node_info("nonexistent_function_xyz")
        assert results == []

    def test_content_hash_generated(self, engine):
        """Each node should have a content_hash."""
        nodes = engine.scan_code(PYTHON_CODE, "test.py", "python")
        for node in nodes:
            assert node["content_hash"] is not None
            assert len(node["content_hash"]) > 0
