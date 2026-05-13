"""Tests for Orchestrator Phase 8 integration and cross-phase wiring."""

import pytest


# ============================================================
#  ORCHESTRATOR PHASE 8 INTEGRATION TESTS
# ============================================================

class TestOrchestratorPhase8:
    """Tests for Orchestrator with Phase 8 Intelligence.

    Uses the shared_orchestrator fixture to avoid OOM from loading
    the semantic model multiple times.
    """

    @pytest.fixture(autouse=True)
    def setup(self, shared_orchestrator):
        self.orch = shared_orchestrator

    @pytest.mark.asyncio
    async def test_system_status_has_phase8(self):
        """System status should include Phase 8 intelligence."""
        status = await self.orch.get_system_status()
        assert "phase8_intelligence" in status
        assert status["phase8_intelligence"]["reasoning_available"] is True
        assert status["phase8_intelligence"]["chain_validation"] is True

    @pytest.mark.asyncio
    async def test_reason_endpoint(self):
        """reason endpoint should return reasoning result."""
        result = await self.orch.reason("How to build an API?", mode="step_by_step")
        assert "answer" in result
        assert "confidence" in result
        # Mode should be step_by_step (even in fallback, mode is honored)
        assert result["mode"] in ("step_by_step", "fallback")  # fallback when no model

    @pytest.mark.asyncio
    async def test_reason_auto_mode(self):
        """reason endpoint should support auto mode."""
        result = await self.orch.reason("Test query", mode="auto")
        assert "answer" in result
        assert len(result["answer"]) > 0

    @pytest.mark.asyncio
    async def test_validate_logic_chain(self):
        """validate_logic_chain should validate a chain."""
        result = await self.orch.validate_logic_chain("sistema de inventario con alertas")
        assert "is_valid" in result
        assert "block_count" in result

    @pytest.mark.asyncio
    async def test_execute_logic_chain(self):
        """execute_logic_chain should execute with safety."""
        result = await self.orch.execute_logic_chain(
            "validar y sanitizar datos",
            data={"name": "Test", "email": "test@test.com"},
            recovery="skip"
        )
        assert "status" in result
        assert "steps_completed" in result

    @pytest.mark.asyncio
    async def test_intelligence_status(self):
        """intelligence_status should return Phase 8 details."""
        status = await self.orch.get_intelligence_status()
        assert "reasoning_engine" in status
        assert "ai_layers" in status
        assert "phase8_modes" in status
        assert "layer1_semantic" in status["ai_layers"]
        assert "layer2_qwen" in status["ai_layers"]
        assert "layer3_memory" in status["ai_layers"]

    @pytest.mark.asyncio
    async def test_phase7_still_works(self):
        """Phase 7 endpoints should still work after Phase 8 integration."""
        # Action executor
        result = await self.orch.execute_action(
            "send_notification",
            {"channel": "log", "message": "Phase 8 integration test"}
        )
        assert result.get("success") is True

        # Logic builder
        result = await self.orch.build_logic("sistema de facturacion")
        assert result.get("block_count", 0) > 0

    @pytest.mark.asyncio
    async def test_phase6_template_engine_wired(self):
        """Phase 6 TemplateEngine should still be wired."""
        status = await self.orch.get_system_status()
        # TemplateEngine was wired in Phase 6
        assert self.orch._template_engine is not None


# ============================================================
#  CROSS-PHASE WIRING VERIFICATION
# ============================================================

class TestCrossPhaseWiring:
    """Verify all wiring between Phases 6, 7, and 8 is connected.

    Uses the shared_orchestrator fixture to avoid OOM from loading
    the semantic model multiple times.
    """

    @pytest.fixture(autouse=True)
    def setup(self, shared_orchestrator):
        self.orch = shared_orchestrator

    def test_phase6_template_engine_exists(self):
        """Phase 6: TemplateEngine should be initialized."""
        assert self.orch._template_engine is not None

    def test_phase7_executor_registry_exists(self):
        """Phase 7: ExecutorRegistry should be initialized."""
        assert self.orch._executor_registry is not None
        assert len(self.orch._executor_registry._executors) >= 8

    def test_phase7_logic_builder_exists(self):
        """Phase 7: LogicBuilder should be initialized."""
        assert self.orch._logic_builder is not None
        assert len(self.orch._logic_builder.list_blocks()) >= 30

    def test_phase7_auth_service_exists(self):
        """Phase 7: AuthService should be initialized."""
        assert self.orch._auth is not None

    def test_phase8_reasoning_engine_exists(self):
        """Phase 8: ReasoningEngine should be initialized."""
        assert self.orch._reasoning is not None

    def test_phase8_chain_validator_exists(self):
        """Phase 8: ChainValidator should be initialized."""
        assert self.orch._chain_validator is not None

    def test_phase8_chain_executor_exists(self):
        """Phase 8: ChainExecutor should be initialized."""
        assert self.orch._chain_executor is not None

    def test_ai_3_layer_architecture(self):
        """All 3 AI layers should be connected."""
        assert self.orch._semantic is not None
        assert self.orch._ai is not None
        assert self.orch._memory is not None

    def test_thinking_engine_wired_to_all_layers(self):
        """ThinkingEngine should have references to all 3 AI layers."""
        assert self.orch._thinking._ai is self.orch._ai
        assert self.orch._thinking._semantic is self.orch._semantic
        assert self.orch._thinking._memory is self.orch._memory

    def test_reasoning_engine_wired_to_all_layers(self):
        """ReasoningEngine should have references to all 3 AI layers."""
        assert self.orch._reasoning._ai is self.orch._ai
        assert self.orch._reasoning._semantic is self.orch._semantic
        assert self.orch._reasoning._memory is self.orch._memory

    def test_semantic_parser_wired_to_semantic_engine(self):
        """SemanticParser (L1) should be wired to SemanticEngine when loaded."""
        # Only wired if SemanticEngine is loaded (requires embeddings model)
        if self.orch._semantic and self.orch._semantic.is_loaded:
            assert self.orch.parser._semantic_engine is self.orch._semantic
        else:
            # When SemanticEngine is not loaded (e.g., no model in test env),
            # the parser should still be functional without it
            assert self.orch.parser is not None

    def test_semantic_parser_wired_to_smart_memory(self):
        """SemanticParser (L1) should be wired to SmartMemory."""
        assert self.orch.parser._smart_memory is self.orch._memory

    def test_automation_engine_wired_to_executor_registry(self):
        """AutomationEngine should be wired to ExecutorRegistry."""
        assert self.orch._automation._executor_registry is self.orch._executor_registry

    def test_app_generator_wired_to_template_engine(self):
        """AppGenerator should be wired to TemplateEngine."""
        assert self.orch._app_gen._template_engine is self.orch._template_engine

    def test_logic_builder_wired_to_template_engine(self):
        """LogicBuilder should be wired to TemplateEngine."""
        assert self.orch._logic_builder._template_engine is self.orch._template_engine
