"""
Unit tests for Level 8 - Theorem Cache

Tests skeleton hash generation, composite hash lookups, and cache save/lookup.
"""

import pytest
from src.core.level8_theorem_cache.cache import TheoremCache
from src.core.shared.contracts import IntentPayload, OperationType
from src.core.shared.db_initializer import initialize_databases


@pytest.fixture(autouse=True)
def _init_db():
    """Ensure the theorems table exists before any test runs."""
    initialize_databases()
    # Clean the cache table for test isolation
    from src.core.shared.db_initializer import get_connection
    conn = get_connection("theorem_cache.sqlite")
    conn.execute("DELETE FROM theorems")
    conn.commit()
    conn.close()


@pytest.fixture
def cache():
    return TheoremCache()


@pytest.fixture
def sample_intent():
    return IntentPayload(
        op=OperationType.CREATE,
        target="auth",
        goal="FEATURE_ADD",
        confidence=0.9,
        context="",
        raw_code="",
        language="python",
    )


PYTHON_CODE = '''
def authenticate(user: str, password: str) -> bool:
    if user and password:
        return check_credentials(user, password)
    return False
'''


class TestTheoremCache:
    """Tests for the TheoremCache class."""

    def test_skeleton_hash_python(self, cache):
        """Should generate consistent skeleton hash for Python code."""
        hash1 = cache._skeleton_hash(PYTHON_CODE, "python")
        hash2 = cache._skeleton_hash(PYTHON_CODE, "python")
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA256 hex

    def test_skeleton_hash_different_code(self, cache):
        """Different code structures should produce different hashes."""
        code1 = "def f():\n    return 1"
        code2 = "class A:\n    pass"
        hash1 = cache._skeleton_hash(code1, "python")
        hash2 = cache._skeleton_hash(code2, "python")
        assert hash1 != hash2

    def test_skeleton_hash_normalizes_names(self, cache):
        """Skeleton hash should be invariant to variable names."""
        code1 = "def foo(x, y):\n    if x:\n        return y"
        code2 = "def bar(a, b):\n    if a:\n        return b"
        hash1 = cache._skeleton_hash(code1, "python")
        hash2 = cache._skeleton_hash(code2, "python")
        # Same structure: 1 function, 2 args, 1 if, 1 return
        assert hash1 == hash2

    def test_composite_hash(self, cache, sample_intent):
        """Composite hash should be deterministic."""
        hash1 = cache._hash(sample_intent)
        hash2 = cache._hash(sample_intent)
        assert hash1 == hash2

    def test_lookup_empty_cache(self, cache, sample_intent):
        """Lookup on empty cache should return None."""
        result = cache.lookup(sample_intent)
        assert result is None

    def test_save_and_lookup_composite(self, cache, sample_intent):
        """Save then lookup by composite hash should succeed."""
        solution = {"code": "def auth(): pass", "h": "abc123"}
        cache.save(sample_intent, "PROVEN", solution, PYTHON_CODE, "python")

        result = cache.lookup(sample_intent, PYTHON_CODE, "python")
        assert result is not None
        assert result["source"] == "composite_hash"
        assert result["data"]["h"] == "abc123"

    def test_save_and_lookup_skeleton(self, cache, sample_intent):
        """Save then lookup by skeleton hash should work for structurally similar code."""
        solution = {"code": "def auth(): pass", "h": "abc456"}
        cache.save(sample_intent, "PROVEN", solution, PYTHON_CODE, "python")

        # Create a different intent with same structure but different names
        similar_intent = IntentPayload(
            op=OperationType.CREATE,
            target="login",
            goal="FEATURE_ADD",
            confidence=0.9,
            context="",
            raw_code="",
            language="python",
        )

        # Use structurally identical code (same skeleton)
        result = cache.lookup(similar_intent, PYTHON_CODE, "python")
        # Should find via skeleton hash (same structure, different composite hash)
        assert result is not None, "Skeleton hash lookup should find structurally similar code"
        assert result["source"] == "skeleton_hash"

    def test_hit_counter_increments(self, cache, sample_intent):
        """Multiple lookups should increment hit counter.
        Note: hit_count shows the value at query time (before increment),
        so first lookup returns 0, second returns 1, etc."""
        solution = {"code": "def auth(): pass", "h": "xyz789"}
        cache.save(sample_intent, "PROVEN", solution, PYTHON_CODE, "python")

        # First lookup - counter was 0, now becomes 1
        result1 = cache.lookup(sample_intent, PYTHON_CODE, "python")
        assert result1 is not None

        # Second lookup - counter was 1, now becomes 2
        result2 = cache.lookup(sample_intent, PYTHON_CODE, "python")
        assert result2 is not None
        # Second lookup should show incremented count
        assert result2["hits"] > result1["hits"]

    def test_skeleton_hash_regex_fallback(self, cache):
        """Non-Python code should use regex-based skeleton hash."""
        js_code = "function hello(name) { return 'Hello ' + name; }"
        hash_val = cache._skeleton_hash(js_code, "javascript")
        assert len(hash_val) == 64

    def test_syntax_error_skeleton_hash(self, cache):
        """Should handle syntax errors gracefully in skeleton hash."""
        bad_code = "def broken(\n    pass"
        hash_val = cache._skeleton_hash(bad_code, "python")
        assert len(hash_val) == 64  # Falls back to regex
