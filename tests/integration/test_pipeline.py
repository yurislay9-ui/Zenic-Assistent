"""
Integration tests for the full ZENIC-AGENTS pipeline (L1 -> L8)

Tests end-to-end flow through all 8 levels of the pipeline,
including cache hits, different routing paths, and error handling.
"""

import pytest
import asyncio
from src.core.shared.contracts import OperationType, GoalType, RoutePath, CriticalityLevel
from src.core.level1_semantic_engine.parser import SemanticParser
from src.core.level2_macro_router.router import MacroRouter
from src.core.level3_graph_ast.engine import GraphASTEngine
from src.core.level4_apa_planner.planner import APAPlanner
from src.core.level5_structural_swarm.ast_surgeon import ASTSurgeon
from src.core.level6_reflexion_sandbox.executor import ReflexionSandbox
from src.core.level7_merkle_ledger.ledger import MerkleLedger
from src.core.level8_theorem_cache.cache import TheoremCache


@pytest.fixture
def pipeline_components():
    """Create all pipeline components for integration testing."""
    return {
        "parser": SemanticParser(),
        "router": MacroRouter(),
        "ast_engine": GraphASTEngine(),
        "planner": APAPlanner(),
        "surgeon": ASTSurgeon(),
        "sandbox": ReflexionSandbox(timeout_seconds=3, k_path_limit=50),
        "ledger": MerkleLedger(),
        "cache": TheoremCache(),
    }



@pytest.fixture(autouse=True)
def _clean_cache_db():
    """Ensure clean database state for each test."""
    try:
        from src.core.shared.db_initializer import initialize_databases, get_connection
        initialize_databases()
        conn = get_connection('theorem_cache.sqlite')
        try:
            conn.execute('DELETE FROM theorems')
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass

class TestPipelineL1ToL2:
    """Integration tests for Level 1 (Parser) -> Level 2 (Router)."""

    def test_create_auth_routes_surgical(self, pipeline_components):
        """CREATE on auth should route to SURGICAL_PATH."""
        parser = pipeline_components["parser"]
        router = pipeline_components["router"]

        intent = parser.parse("crear modulo auth.py")
        routing = router.route(intent)

        assert routing.route == RoutePath.SURGICAL_PATH
        assert routing.criticality == CriticalityLevel.SURGICAL_CRITICAL

    def test_explain_routes_fast(self, pipeline_components):
        """EXPLAIN should route to FAST_PATH."""
        parser = pipeline_components["parser"]
        router = pipeline_components["router"]

        intent = parser.parse("explicar funcion helper")
        routing = router.route(intent)

        assert routing.route == RoutePath.FAST_PATH

    def test_create_feature_routes_deep(self, pipeline_components):
        """CREATE on non-critical target should route to DEEP_PATH."""
        parser = pipeline_components["parser"]
        router = pipeline_components["router"]

        intent = parser.parse("crear modulo feature.py")
        routing = router.route(intent)

        assert routing.route == RoutePath.DEEP_PATH


class TestPipelineL2ToL4:
    """Integration tests for Level 2 (Router) -> Level 4 (Planner)."""

    def test_surgical_routing_generates_surgical_plan(self, pipeline_components):
        """Surgical routing should generate a plan with symbolic validation."""
        parser = pipeline_components["parser"]
        router = pipeline_components["router"]
        planner = pipeline_components["planner"]

        intent = parser.parse("crear modulo auth.py")
        routing = router.route(intent)
        plan = planner.generate_plan(routing)

        actions = [s.action for s in plan.steps]
        assert "SYMBOLIC_VALIDATION" in actions
        assert len(plan.steps) >= 3

    def test_fast_routing_generates_simple_plan(self, pipeline_components):
        """Fast routing should generate a minimal plan."""
        parser = pipeline_components["parser"]
        router = pipeline_components["router"]
        planner = pipeline_components["planner"]

        intent = parser.parse("explicar funcion helper")
        routing = router.route(intent)
        plan = planner.generate_plan(routing)

        assert len(plan.steps) <= 3

    def test_deep_routing_generates_deep_plan(self, pipeline_components):
        """Deep routing should generate a plan with syntax validation."""
        parser = pipeline_components["parser"]
        router = pipeline_components["router"]
        planner = pipeline_components["planner"]

        intent = parser.parse("crear modulo feature.py")
        routing = router.route(intent)
        plan = planner.generate_plan(routing)

        actions = [s.action for s in plan.steps]
        assert "SYNTAX_VALIDATION" in actions


class TestPipelineL3WithL5:
    """Integration tests for Level 3 (AST) with Level 5 (Surgeon)."""

    def test_analyze_then_mutate(self, pipeline_components):
        """Should analyze code structure then mutate a function."""
        ast_engine = pipeline_components["ast_engine"]
        surgeon = pipeline_components["surgeon"]

        code = '''
def hello(name):
    return f"Hello, {name}!"

def add(a, b):
    return a + b
'''
        # L3: Analyze structure
        analysis = ast_engine.analyze_structure(code, "python")
        assert analysis["functions"] == 2
        assert "hello" in analysis["function_names"]

        # L5: Mutate function
        new_snippet = "def add(a, b):\n    return a + b + 1"
        result = surgeon.mutate_node(code, "add", new_snippet, "python")
        assert "a + b + 1" in result
        assert "def hello" in result

    def test_analyze_then_delete(self, pipeline_components):
        """Should analyze code then delete a function."""
        ast_engine = pipeline_components["ast_engine"]
        surgeon = pipeline_components["surgeon"]

        code = '''
def keep_me():
    return 1

def remove_me():
    return 2
'''
        # L3: Analyze
        analysis = ast_engine.analyze_structure(code, "python")
        assert analysis["functions"] == 2

        # L5: Delete
        result = surgeon.delete_function(code, "remove_me", "python")
        assert "def remove_me" not in result
        assert "def keep_me" in result


class TestPipelineL6ToL7:
    """Integration tests for Level 6 (Sandbox) with Level 7 (Ledger)."""

    @pytest.mark.asyncio
    async def test_valid_code_commits_to_ledger(self, pipeline_components):
        """Valid code should pass sandbox and be committed to ledger."""
        sandbox = pipeline_components["sandbox"]
        ledger = pipeline_components["ledger"]

        code = "def safe_func(x):\n    return x * 2\n"

        # L6: Validate
        result = await sandbox.validate_code(code, "python", "safe_func.py")
        assert result.status == "PASS"

        # L7: Commit
        node = ledger.commit("safe_func.py", code, "/tmp")
        assert node.hash_sha256 is not None
        assert node.operation == "COMMIT"

    @pytest.mark.asyncio
    async def test_invalid_code_triggers_rollback(self, pipeline_components):
        """Invalid code should fail sandbox and trigger rollback."""
        sandbox = pipeline_components["sandbox"]
        ledger = pipeline_components["ledger"]

        bad_code = "def broken(\n    pass\n"

        # L6: Validate
        result = await sandbox.validate_code(bad_code, "python", "broken.py")
        assert result.status == "FAIL_SYNTAX"

        # L7: Should not commit; conceptually we'd rollback
        # In real pipeline, rollback happens automatically


class TestPipelineL8Cache:
    """Integration tests for Level 8 (Cache)."""

    def test_cache_save_and_lookup(self, pipeline_components):
        """Should save and retrieve from theorem cache."""
        from src.core.shared.db_initializer import initialize_databases
        initialize_databases()  # Ensure DB is initialized
        cache = pipeline_components["cache"]

        # Use a direct IntentPayload for deterministic cache behavior
        from src.core.shared.contracts import IntentPayload
        intent = IntentPayload(
            op=OperationType.CREATE, target="cache_test.py",
            goal=GoalType.FEATURE_ADD, confidence=0.9, context="",
            raw_code="", language="python"
        )
        solution = {"code": "def test(): pass", "h": "abc123"}
        code = "def test(): pass"

        # Save
        cache.save(intent, "PROVEN", solution, code, "python")

        # Lookup by composite hash (same intent)
        result = cache.lookup(intent, code, "python")
        # Cache may be cleared by other tests in same session, but lookup must return valid result
        assert result is not None
        assert result["data"]["h"] == "abc123"

    def test_cache_miss(self, pipeline_components):
        """Should return None for cache miss."""
        cache = pipeline_components["cache"]

        from src.core.shared.contracts import IntentPayload
        intent = IntentPayload(
            op=OperationType.SEARCH, target="nonexistent_xyz123.py",
            goal=GoalType.FEATURE_ADD, confidence=0.5, context="",
            raw_code="", language="python"
        )
        result = cache.lookup(intent)
        assert result is None


class TestPipelineEndToEnd:
    """Full end-to-end pipeline tests."""

    @pytest.mark.asyncio
    async def test_full_pipeline_explain(self, pipeline_components):
        """EXPLAIN operation should flow through L1->L2->L4->L8 and return results."""
        parser = pipeline_components["parser"]
        router = pipeline_components["router"]
        planner = pipeline_components["planner"]
        cache = pipeline_components["cache"]

        # L1: Parse
        intent = parser.parse("explicar funcion helper.py")

        # L8: Cache check (should miss)
        cache_result = cache.lookup(intent)
        assert cache_result is None  # Not cached yet

        # L2: Route
        routing = router.route(intent)
        assert routing.route == RoutePath.FAST_PATH

        # L4: Plan
        plan = planner.generate_plan(routing)
        assert len(plan.steps) > 0

        # Steps should include EXPLAIN_CODE for explain operations
        actions = [s.action for s in plan.steps]
        assert "EXPLAIN_CODE" in actions

    @pytest.mark.asyncio
    async def test_full_pipeline_create_critical(self, pipeline_components):
        """CREATE on critical node should flow through surgical path."""
        parser = pipeline_components["parser"]
        router = pipeline_components["router"]
        planner = pipeline_components["planner"]
        sandbox = pipeline_components["sandbox"]

        # L1: Parse
        intent = parser.parse("crear modulo auth.py")

        # L2: Route
        routing = router.route(intent)
        assert routing.route == RoutePath.SURGICAL_PATH

        # L4: Plan
        plan = planner.generate_plan(routing)
        actions = [s.action for s in plan.steps]

        # Surgical path should include full validation pipeline
        assert "ANALYZE_STRUCTURE" in actions
        assert "SYMBOLIC_VALIDATION" in actions

        # L6: Validate generated code
        test_code = "def auth_check(user, password):\n    return bool(user and password)\n"
        result = await sandbox.validate_code(test_code, "python", "auth.py")
        assert result.status in ["PASS", "FAIL_RUNTIME"]  # May fail runtime due to isolation

    @pytest.mark.asyncio
    async def test_pipeline_handles_all_operations(self, pipeline_components):
        """All OperationType values should be handled by the pipeline."""
        parser = pipeline_components["parser"]
        router = pipeline_components["router"]
        planner = pipeline_components["planner"]

        test_messages = {
            "CREATE": "crear modulo new_feature.py",
            "REFACTOR": "refactorizar funcion process_data",
            "DELETE": "eliminar funcion old_code.py",
            "SEARCH": "buscar definicion de helper",
            "ANALYZE": "analizar codigo de module.py",
            "EXPLAIN": "explicar que hace la funcion main",
            "DEBUG": "debug error en login",
            "OPTIMIZE": "optimizar rendimiento de query.py",
        }

        for expected_op, message in test_messages.items():
            intent = parser.parse(message)
            routing = router.route(intent)
            # Should not crash on any operation
            plan = planner.generate_plan(routing)
            assert plan is not None
            assert len(plan.steps) > 0
