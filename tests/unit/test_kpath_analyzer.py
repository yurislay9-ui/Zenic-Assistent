"""
ZENIC-AGENTS - K-Path Analyzer Unit Tests

Tests for src/core/shared/kpath_analyzer.py:
  - KPathAnalyzer initialization and k_limit
  - measure_dependency_depth (with mock DB)
  - estimate_code_k_paths (Python AST analysis)
  - estimate_code_k_paths (other languages via regex)
  - Edge cases: empty graph, missing nodes, malformed connections
"""

import ast
import json
import sqlite3
import tempfile

import pytest
from unittest.mock import patch, MagicMock

from src.core.shared.kpath_analyzer import KPathAnalyzer


# ============================================================
#  FIXTURE: In-memory DB with mock AST nodes
# ============================================================

@pytest.fixture
def mock_graph_db():
    """Create an in-memory SQLite DB with test AST nodes."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE ast_nodes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        file_path TEXT NOT NULL,
        node_type TEXT NOT NULL,
        name TEXT NOT NULL,
        start_byte INTEGER NOT NULL,
        end_byte INTEGER NOT NULL,
        content_hash TEXT NOT NULL,
        docstring TEXT,
        complexity INTEGER DEFAULT 1,
        connections TEXT DEFAULT '[]'
    )""")
    return conn


def _insert_node(conn, name, node_type="function", connections=None):
    """Helper to insert an AST node into the test DB."""
    connections_json = json.dumps(connections or [])
    conn.execute(
        "INSERT INTO ast_nodes (file_path, node_type, name, start_byte, end_byte, "
        "content_hash, connections) VALUES (?, ?, ?, 0, 0, 'hash', ?)",
        ("test.py", node_type, name, connections_json),
    )
    conn.commit()


# ============================================================
#  INITIALIZATION TESTS
# ============================================================

class TestKPathAnalyzerInit:
    """Tests for KPathAnalyzer initialization."""

    def test_default_k_limit(self):
        """Default k_limit should be 10."""
        analyzer = KPathAnalyzer()
        assert analyzer.k_limit == 10

    def test_custom_k_limit(self):
        """Should accept custom k_limit."""
        analyzer = KPathAnalyzer(k_limit=5)
        assert analyzer.k_limit == 5

    def test_k_limit_zero(self):
        """Should accept k_limit of 0."""
        analyzer = KPathAnalyzer(k_limit=0)
        assert analyzer.k_limit == 0


# ============================================================
#  MEASURE DEPENDENCY DEPTH TESTS (with mock DB)
# ============================================================

class TestMeasureDependencyDepth:
    """Tests for KPathAnalyzer.measure_dependency_depth()."""

    def test_missing_node_returns_zero_depth(self, mock_graph_db):
        """Should return depth 0 for non-existent node."""
        analyzer = KPathAnalyzer(k_limit=10)
        with patch("src.core.shared.db_initializer.get_connection", return_value=mock_graph_db):
            result = analyzer.measure_dependency_depth("nonexistent_function")
        assert result["depth"] == 0
        assert result["nodes_affected"] == 0
        assert result["exceeds_limit"] is False

    def test_single_node_no_connections(self, mock_graph_db):
        """Single node without connections should have depth 0."""
        _insert_node(mock_graph_db, "isolated_func")

        analyzer = KPathAnalyzer(k_limit=10)
        with patch("src.core.shared.db_initializer.get_connection", return_value=mock_graph_db):
            result = analyzer.measure_dependency_depth("isolated_func")

        assert result["nodes_affected"] >= 1
        assert result["depth"] == 0
        assert result["exceeds_limit"] is False

    def test_two_connected_nodes(self, mock_graph_db):
        """Two connected nodes should have depth 1."""
        _insert_node(mock_graph_db, "func_a", connections=["call:func_b"])
        _insert_node(mock_graph_db, "func_b")

        analyzer = KPathAnalyzer(k_limit=10)
        with patch("src.core.shared.db_initializer.get_connection", return_value=mock_graph_db):
            result = analyzer.measure_dependency_depth("func_a")

        assert result["nodes_affected"] >= 2
        assert result["depth"] >= 1

    def test_chain_of_three_nodes(self, mock_graph_db):
        """Three-node chain should have depth 2."""
        _insert_node(mock_graph_db, "func_a", connections=["call:func_b"])
        _insert_node(mock_graph_db, "func_b", connections=["call:func_c"])
        _insert_node(mock_graph_db, "func_c")

        analyzer = KPathAnalyzer(k_limit=10)
        with patch("src.core.shared.db_initializer.get_connection", return_value=mock_graph_db):
            result = analyzer.measure_dependency_depth("func_a")

        assert result["nodes_affected"] >= 3
        assert result["depth"] >= 2

    def test_exceeds_k_limit(self, mock_graph_db):
        """Should flag when affected nodes exceed k_limit."""
        # Create 12 connected nodes
        for i in range(12):
            connections = [f"call:node_{i+1}"] if i < 11 else []
            _insert_node(mock_graph_db, f"node_{i}", connections=connections)

        analyzer = KPathAnalyzer(k_limit=5)
        with patch("src.core.shared.db_initializer.get_connection", return_value=mock_graph_db):
            result = analyzer.measure_dependency_depth("node_0")

        assert result["exceeds_limit"] is True

    def test_within_k_limit(self, mock_graph_db):
        """Should not flag when affected nodes are within k_limit."""
        _insert_node(mock_graph_db, "small_a", connections=["call:small_b"])
        _insert_node(mock_graph_db, "small_b")

        analyzer = KPathAnalyzer(k_limit=10)
        with patch("src.core.shared.db_initializer.get_connection", return_value=mock_graph_db):
            result = analyzer.measure_dependency_depth("small_a")

        assert result["exceeds_limit"] is False

    def test_malformed_connections_json(self, mock_graph_db):
        """Should handle malformed JSON in connections column."""
        mock_graph_db.execute(
            "INSERT INTO ast_nodes (file_path, node_type, name, start_byte, end_byte, "
            "content_hash, connections) VALUES (?, ?, ?, 0, 0, 'hash', ?)",
            ("test.py", "function", "bad_json_func", "not valid json"),
        )
        mock_graph_db.commit()

        analyzer = KPathAnalyzer(k_limit=10)
        with patch("src.core.shared.db_initializer.get_connection", return_value=mock_graph_db):
            result = analyzer.measure_dependency_depth("bad_json_func")
        # Should not crash; connections parsed as empty
        assert isinstance(result["nodes_affected"], int)

    def test_connection_without_colon(self, mock_graph_db):
        """Should handle connections without ':' separator."""
        _insert_node(mock_graph_db, "simple_caller", connections=["func_callee"])
        _insert_node(mock_graph_db, "func_callee")

        analyzer = KPathAnalyzer(k_limit=10)
        with patch("src.core.shared.db_initializer.get_connection", return_value=mock_graph_db):
            result = analyzer.measure_dependency_depth("simple_caller")
        assert result["nodes_affected"] >= 1

    def test_result_includes_affected_nodes(self, mock_graph_db):
        """Result should include list of affected nodes."""
        _insert_node(mock_graph_db, "root_func", connections=["call:leaf_func"])
        _insert_node(mock_graph_db, "leaf_func")

        analyzer = KPathAnalyzer(k_limit=10)
        with patch("src.core.shared.db_initializer.get_connection", return_value=mock_graph_db):
            result = analyzer.measure_dependency_depth("root_func")

        assert "affected_nodes" in result
        assert isinstance(result["affected_nodes"], list)
        assert len(result["affected_nodes"]) > 0


# ============================================================
#  ESTIMATE CODE K-PATHS (PYTHON) TESTS
# ============================================================

class TestEstimateCodeKPathsPython:
    """Tests for KPathAnalyzer.estimate_code_k_paths() with Python."""

    def setup_method(self):
        self.analyzer = KPathAnalyzer(k_limit=10)

    def test_simple_code_no_branches(self):
        """Code without branches should have k-path count of 1."""
        code = "x = 1\ny = 2\nz = x + y"
        result = self.analyzer.estimate_code_k_paths(code, language="python")
        assert result == 1

    def test_single_if_branch(self):
        """Single if statement should produce 2 paths."""
        code = "if x > 0:\n    y = 1"
        result = self.analyzer.estimate_code_k_paths(code, language="python")
        assert result == 2

    def test_multiple_branches(self):
        """Multiple branches should produce 2^n paths (capped at 1000)."""
        code = "if a:\n    pass\nif b:\n    pass\nif c:\n    pass"
        result = self.analyzer.estimate_code_k_paths(code, language="python")
        assert result == 8  # 2^3

    def test_while_loop_counts(self):
        """While loops should count as branches."""
        code = "while x > 0:\n    x -= 1"
        result = self.analyzer.estimate_code_k_paths(code, language="python")
        assert result == 2

    def test_for_loop_counts(self):
        """For loops should count as branches."""
        code = "for item in items:\n    process(item)"
        result = self.analyzer.estimate_code_k_paths(code, language="python")
        assert result == 2

    def test_exception_handler_counts(self):
        """Exception handlers should count as branches."""
        code = "try:\n    risky()\nexcept Exception:\n    handle()"
        result = self.analyzer.estimate_code_k_paths(code, language="python")
        assert result == 2

    def test_bool_op_counts(self):
        """BoolOp (and/or) should add extra branches."""
        code = "if a and b:\n    pass"
        result = self.analyzer.estimate_code_k_paths(code, language="python")
        # if counts as 1, BoolOp with 2 values adds 1 more
        assert result >= 4

    def test_syntax_error_returns_1(self):
        """Invalid Python should return 1."""
        code = "def broken(:\n    pass"
        result = self.analyzer.estimate_code_k_paths(code, language="python")
        assert result == 1

    def test_capped_at_1000(self):
        """Results should be capped at 1000."""
        # 10 if statements = 2^10 = 1024, capped at 1000
        code = "\n".join(["if x: pass"] * 10)
        result = self.analyzer.estimate_code_k_paths(code, language="python")
        assert result == 1000


# ============================================================
#  ESTIMATE CODE K-PATHS (OTHER LANGUAGES) TESTS
# ============================================================

class TestEstimateCodeKPathsOther:
    """Tests for estimate_code_k_paths with non-Python languages."""

    def setup_method(self):
        self.analyzer = KPathAnalyzer(k_limit=10)

    def test_javascript_branches(self):
        """Should detect branches in JavaScript code."""
        code = "if (x) { doSomething(); } else { doOther(); }"
        result = self.analyzer.estimate_code_k_paths(code, language="javascript")
        assert result >= 2

    def test_kotlin_branches(self):
        """Should detect branches in Kotlin code."""
        code = "if (x > 0) { y = 1 }"
        result = self.analyzer.estimate_code_k_paths(code, language="kotlin")
        assert result >= 1

    def test_go_branches(self):
        """Should detect branches in Go code."""
        code = "if x > 0 { y = 1 }"
        result = self.analyzer.estimate_code_k_paths(code, language="go")
        assert result >= 1

    def test_unknown_language_fallback(self):
        """Unknown languages should use a basic pattern."""
        code = "if something then else"
        result = self.analyzer.estimate_code_k_paths(code, language="cobol")
        assert result >= 1


# ============================================================
#  DB CONNECTION ERROR HANDLING TESTS
# ============================================================

class TestDBConnectionErrors:
    """Tests for error handling in measure_dependency_depth."""

    def test_db_connection_error_returns_safe_default(self):
        """Should return safe default if DB connection fails."""
        analyzer = KPathAnalyzer(k_limit=10)
        with patch("src.core.shared.db_initializer.get_connection",
                    side_effect=Exception("DB connection failed")):
            result = analyzer.measure_dependency_depth("any_func")
        assert result["depth"] == 0
        assert result["nodes_affected"] == 0
        assert result["exceeds_limit"] is False
        assert "error" in result

    def test_query_error_returns_safe_default(self, mock_graph_db):
        """Should handle query errors gracefully."""
        # Drop the table to trigger errors
        mock_graph_db.execute("DROP TABLE ast_nodes")
        mock_graph_db.commit()

        analyzer = KPathAnalyzer(k_limit=10)
        with patch("src.core.shared.db_initializer.get_connection", return_value=mock_graph_db):
            result = analyzer.measure_dependency_depth("any_func")
        # Should handle the missing table error
        assert isinstance(result, dict)
