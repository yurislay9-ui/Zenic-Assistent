"""
Unit tests for src/core/orchestrator.py - ZenicOrchestrator

Tests:
- ZenicOrchestrator inherits from BaseOrchestrator
- Sequential pipeline execution (execute method)
- Cache hit returns CACHED status
- Sandbox PASS -> SUCCESS result
- Sandbox FAIL -> ROLLBACK result
- Theorem cache hit returns CACHED status
"""

import time
import pytest
from unittest.mock import MagicMock, patch, AsyncMock, PropertyMock

from src.core.orchestrator_base import BaseOrchestrator


# ---------------------------------------------------------------------------
#  Helper: Build a ZenicOrchestrator with all dependencies mocked.
#
#  Strategy: patch the _init_* methods on BaseOrchestrator so the
#  constructor completes without real side-effects, then manually
#  set up the attributes that execute() depends on.
# ---------------------------------------------------------------------------

def _make_mock_orchestrator():
    """Create a ZenicOrchestrator with all _init_* methods mocked out."""
    # Side effect: _init_ai_architecture must set self._semantic, _ai, _memory
    # because the __init__ code accesses self._semantic.is_loaded after calling it.
    def _init_ai_side_effect(self_orch, semantic, ai, memory):
        self_orch._semantic = semantic
        self_orch._ai = ai
        self_orch._memory = memory

    with patch.object(BaseOrchestrator, "_init_common_state"), \
         patch.object(BaseOrchestrator, "_init_pipeline_components"), \
         patch.object(BaseOrchestrator, "_init_ai_architecture", _init_ai_side_effect), \
         patch.object(BaseOrchestrator, "_init_extended_with_defaults"), \
         patch.object(BaseOrchestrator, "_init_decomposed_modules"), \
         patch.object(BaseOrchestrator, "_init_agent_framework"), \
         patch.object(BaseOrchestrator, "_init_god_level_improvements"), \
         patch.object(BaseOrchestrator, "_scan_project"), \
         patch("src.core.orchestrator.load_settings", return_value={"project_dir": "."}), \
         patch("src.core.orchestrator.SemanticEngine") as MockSE, \
         patch("src.core.orchestrator.MiniAIEngine") as MockAI, \
         patch("src.core.orchestrator.SmartMemory") as MockMem, \
         patch("src.core.orchestrator.StepDispatcher"):

        mock_sem = MagicMock(is_loaded=False)
        MockSE.return_value = mock_sem
        mock_ai = MagicMock(is_loaded=False)
        MockAI.return_value = mock_ai
        mock_mem = MagicMock()
        MockMem.return_value = mock_mem

        from src.core.orchestrator import ZenicOrchestrator
        orch = ZenicOrchestrator()

    # Now manually set up all attributes that execute() needs
    import threading
    orch._request_count = 0
    orch._request_count_lock = threading.Lock()
    orch._memory = MagicMock()
    orch._memory.check_cache = MagicMock(return_value=None)
    orch._memory.add_working = MagicMock()
    orch._memory.save_to_cache = MagicMock()
    orch._memory.compute_importance = MagicMock(return_value=0.5)
    orch._analysis = MagicMock()
    orch._analysis.log_request = MagicMock()
    orch._agent_runner = MagicMock()
    orch._surgical_agent = MagicMock()
    orch._surgical_agent.classify_with_runner = MagicMock(return_value=MagicMock(
        operation="CREATE", goal="FEATURE_ADD", source="fallback", confidence=0.5))
    orch._surgical_agent.to_intent_payload = MagicMock(return_value=MagicMock(
        op="CREATE", target="test", goal="FEATURE_ADD",
        confidence=0.5, language="python", raw_code="", context="test"))
    orch.ast_engine = MagicMock()
    orch.cache = MagicMock()
    orch.cache.lookup = MagicMock(return_value=None)
    orch.router = MagicMock()
    orch.router.route = MagicMock(return_value=MagicMock(route="FAST_PATH_REGEX", criticality=1))
    orch.planner = MagicMock()
    orch.planner.generate_plan = MagicMock(return_value=MagicMock(
        solver_status="HEURISTIC_FALLBACK", solver_proof=None,
        mcts_simulations=0, mcts_depth_reached=0))
    orch._step_dispatcher = MagicMock()
    orch._step_dispatcher.execute_plan_steps = AsyncMock(
        return_value=("code", "code", []))
    orch._isolation_manager = MagicMock()
    orch._isolation_manager.create_workspace = MagicMock(
        return_value=MagicMock(sandbox_id="sb1"))
    orch._isolation_manager.release_workspace = MagicMock()
    orch.sandbox = MagicMock()
    orch.sandbox.validate_code = AsyncMock(return_value=MagicMock(
        status="PASS", error_message="", warnings=[], metrics={},
        paths_explored=0, paths_pruned=0))
    orch.sandbox.timeout_seconds = 30
    orch.ledger = MagicMock()
    orch.ledger.snapshot = MagicMock()
    orch.ledger.commit = MagicMock(return_value=MagicMock(hash_sha256="a" * 16))
    orch.ledger.rollback = MagicMock()
    orch._partial_reasoning = MagicMock()
    orch._abortive = MagicMock()
    orch._pending_resumptions = {}

    return orch


# ===========================================================================
#  Test: Inheritance
# ===========================================================================

class TestZenicOrchestratorInheritance:
    """Tests that ZenicOrchestrator properly inherits from BaseOrchestrator."""

    def test_is_subclass_of_base(self):
        """ZenicOrchestrator should be a subclass of BaseOrchestrator."""
        from src.core.orchestrator import ZenicOrchestrator
        assert issubclass(ZenicOrchestrator, BaseOrchestrator)

    def test_has_execute_method(self):
        """ZenicOrchestrator should have an async execute method."""
        from src.core.orchestrator import ZenicOrchestrator
        assert hasattr(ZenicOrchestrator, "execute")
        import inspect
        assert inspect.iscoroutinefunction(ZenicOrchestrator.execute)

    def test_has_request_count(self):
        """Instance should have _request_count from BaseOrchestrator._init_common_state."""
        orch = _make_mock_orchestrator()
        assert hasattr(orch, "_request_count")
        assert orch._request_count == 0


# ===========================================================================
#  Test: execute() - SmartMemory cache hit
# ===========================================================================

class TestExecuteCacheHit:
    """Tests for the SmartMemory cache hit path in execute()."""

    @pytest.mark.asyncio
    async def test_cache_hit_returns_cached_status(self):
        """When SmartMemory has a cache hit, execute should return CACHED."""
        orch = _make_mock_orchestrator()
        orch._memory.check_cache.return_value = {
            "source": "semantic",
            "response": "cached_response_code",
        }

        result = await orch.execute("test message")
        assert result["status"] == "CACHED"
        assert result["code"] == "cached_response_code"
        assert result["cache_source"] == "semantic"

    @pytest.mark.asyncio
    async def test_cache_hit_increments_request_count(self):
        """Cache hit should still increment request_count."""
        orch = _make_mock_orchestrator()
        orch._memory.check_cache.return_value = {"source": "test", "response": "x"}

        await orch.execute("test")
        assert orch._request_count == 1

    @pytest.mark.asyncio
    async def test_cache_hit_logs_request(self):
        """Cache hit should log the request as CACHED."""
        orch = _make_mock_orchestrator()
        orch._memory.check_cache.return_value = {"source": "test", "response": "x"}

        await orch.execute("test")
        orch._analysis.log_request.assert_called()
        call_args = orch._analysis.log_request.call_args
        assert call_args[0][1] == "CACHED"  # status = CACHED


# ===========================================================================
#  Test: execute() - Normal pipeline with sandbox PASS
# ===========================================================================

class TestExecuteSandboxPass:
    """Tests for the normal pipeline path when sandbox validates successfully."""

    @pytest.mark.asyncio
    async def test_sandbox_pass_returns_success(self):
        """When sandbox validates code, execute should return SUCCESS."""
        orch = _make_mock_orchestrator()
        # Default setup already has sandbox PASS

        with patch("src.core.orchestrator.SurgicalAgent") as MockSA:
            MockSA._extract_code_block.return_value = (None, None)
            result = await orch.execute("create a module")

        assert result["status"] == "SUCCESS"
        assert result["code"] == "code"

    @pytest.mark.asyncio
    async def test_sandbox_pass_increments_request_count(self):
        """Successful execution should increment request_count."""
        orch = _make_mock_orchestrator()

        with patch("src.core.orchestrator.SurgicalAgent") as MockSA:
            MockSA._extract_code_block.return_value = (None, None)
            await orch.execute("test")

        assert orch._request_count == 1

    @pytest.mark.asyncio
    async def test_success_includes_hash(self):
        """SUCCESS result should include a hash from the ledger commit."""
        orch = _make_mock_orchestrator()
        orch.ledger.commit.return_value = MagicMock(hash_sha256="a1b2c3d4e5f6")

        with patch("src.core.orchestrator.SurgicalAgent") as MockSA:
            MockSA._extract_code_block.return_value = (None, None)
            result = await orch.execute("test")

        assert "hash" in result
        assert result["hash"] == "a1b2c3d4e5f6"[:12]


# ===========================================================================
#  Test: execute() - Sandbox FAIL -> ROLLBACK
# ===========================================================================

class TestExecuteSandboxFail:
    """Tests for the sandbox FAIL -> ROLLBACK path."""

    @pytest.mark.asyncio
    async def test_sandbox_fail_returns_rollback(self):
        """When sandbox fails, execute should return ROLLBACK."""
        orch = _make_mock_orchestrator()
        orch.sandbox.validate_code = AsyncMock(return_value=MagicMock(
            status="FAIL_SYNTAX", error_message="Syntax error",
            warnings=["deprecated"], metrics={}, paths_explored=0, paths_pruned=0))

        with patch("src.core.orchestrator.SurgicalAgent") as MockSA:
            MockSA._extract_code_block.return_value = (None, None)
            result = await orch.execute("test")

        assert result["status"] == "ROLLBACK"
        assert result["error"] == "Syntax error"

    @pytest.mark.asyncio
    async def test_rollback_includes_warnings(self):
        """ROLLBACK result should include warnings from the sandbox."""
        orch = _make_mock_orchestrator()
        orch.sandbox.validate_code = AsyncMock(return_value=MagicMock(
            status="FAIL_SYNTAX", error_message="err",
            warnings=["deprecated usage"], metrics={}, paths_explored=0, paths_pruned=0))

        with patch("src.core.orchestrator.SurgicalAgent") as MockSA:
            MockSA._extract_code_block.return_value = (None, None)
            result = await orch.execute("test")

        assert result["warnings"] == ["deprecated usage"]


# ===========================================================================
#  Test: execute() - Theorem cache hit (Level 8)
# ===========================================================================

class TestExecuteTheoremCacheHit:
    """Tests for the Level 8 theorem cache hit path."""

    @pytest.mark.asyncio
    async def test_cache_lookup_hit_returns_cached(self):
        """When theorem cache hits, execute should return CACHED status."""
        orch = _make_mock_orchestrator()
        orch._memory.check_cache.return_value = None  # No memory cache
        orch.cache.lookup.return_value = {
            "source": "theorem",
            "data": {"code": "cached_code", "h": "abc"},
            "hits": 5,
        }

        with patch("src.core.orchestrator.SurgicalAgent") as MockSA:
            MockSA._extract_code_block.return_value = (None, None)
            result = await orch.execute("test")

        assert result["status"] == "CACHED"
        assert result["code"] == "cached_code"
        assert result["cache_hits"] == 5

    @pytest.mark.asyncio
    async def test_cache_hit_includes_hash(self):
        """Theorem cache hit should include the hash from cached data."""
        orch = _make_mock_orchestrator()
        orch._memory.check_cache.return_value = None
        orch.cache.lookup.return_value = {
            "source": "theorem",
            "data": {"code": "code", "h": "deadbeef"},
            "hits": 1,
        }

        with patch("src.core.orchestrator.SurgicalAgent") as MockSA:
            MockSA._extract_code_block.return_value = (None, None)
            result = await orch.execute("test")

        assert result["hash"] == "deadbeef"
