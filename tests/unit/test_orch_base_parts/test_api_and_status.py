"""Tests for public API, properties, and system status."""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from src.core.orchestrator_base import BaseOrchestrator
from ._fixtures import mock_settings, base_orch, fully_mocked_orch


# ============================================================
#  Public API Tests
# ============================================================

class TestPublicAPI:
    """Tests for shared public API methods."""

    @pytest.mark.asyncio
    async def test_register_user_no_auth(self):
        """register_user should return error when auth not available."""
        orch = BaseOrchestrator()
        orch._auth = None
        result = await orch.register_user("user", "e@e.com", "pass")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_register_user_with_auth(self):
        """register_user should delegate to auth service."""
        orch = BaseOrchestrator()
        orch._auth = MagicMock()
        orch._auth.register_user.return_value = {"username": "test"}
        result = await orch.register_user("user", "e@e.com", "pass")
        orch._auth.register_user.assert_called_once_with("user", "e@e.com", "pass", "user")
        assert result["username"] == "test"

    @pytest.mark.asyncio
    async def test_login_user_no_auth(self):
        """login_user should return error when auth not available."""
        orch = BaseOrchestrator()
        orch._auth = None
        result = await orch.login_user("user", "pass")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_login_user_with_auth(self):
        """login_user should delegate to auth service."""
        orch = BaseOrchestrator()
        orch._auth = MagicMock()
        orch._auth.login_user.return_value = {"access_token": "tok"}
        result = await orch.login_user("user", "pass")
        assert "access_token" in result

    @pytest.mark.asyncio
    async def test_verify_token_no_auth(self):
        """verify_token should return error when auth not available."""
        orch = BaseOrchestrator()
        orch._auth = None
        result = await orch.verify_token("token")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_verify_token_with_auth(self):
        """verify_token should delegate to auth service."""
        orch = BaseOrchestrator()
        orch._auth = MagicMock()
        orch._auth.verify_token.return_value = {"sub": "1"}
        result = await orch.verify_token("token")
        assert "sub" in result

    @pytest.mark.asyncio
    async def test_verify_token_exception(self):
        """verify_token should handle exceptions from auth."""
        orch = BaseOrchestrator()
        orch._auth = MagicMock()
        orch._auth.verify_token.side_effect = Exception("bad token")
        result = await orch.verify_token("bad")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_execute_action_no_registry(self):
        """execute_action should return error when registry not available."""
        orch = BaseOrchestrator()
        orch._executor_registry = None
        result = await orch.execute_action("http_request", {})
        assert "error" in result

    @pytest.mark.asyncio
    async def test_execute_action_with_registry(self):
        """execute_action should delegate to executor registry."""
        orch = BaseOrchestrator()
        orch._executor_registry = MagicMock()
        mock_result = MagicMock(success=True, data={"key": "val"}, error=None, duration_ms=10)
        orch._executor_registry.execute_action = AsyncMock(return_value=mock_result)
        result = await orch.execute_action("http_request", {"url": "http://test.com"})
        assert result["success"] is True
        assert result["data"] == {"key": "val"}

    @pytest.mark.asyncio
    async def test_list_projects_with_memory(self, fully_mocked_orch):
        """list_projects should delegate to memory when available."""
        fully_mocked_orch._memory.list_projects.return_value = [{"name": "proj1"}]
        result = await fully_mocked_orch.list_projects()
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_list_projects_no_memory(self):
        """list_projects should return empty list when memory not available."""
        orch = BaseOrchestrator()
        orch._memory = None
        result = await orch.list_projects()
        assert result == []

    @pytest.mark.asyncio
    async def test_build_logic_no_agents(self):
        """build_logic should return error when no builder or agent."""
        orch = BaseOrchestrator()
        orch._business_logic_agent = None
        orch._logic_builder = None
        result = await orch.build_logic("create user auth")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_list_logic_blocks_no_builder(self):
        """list_logic_blocks should return empty list when no builder."""
        orch = BaseOrchestrator()
        orch._logic_builder = None
        result = await orch.list_logic_blocks()
        assert result == []


# ============================================================
#  Properties Tests
# ============================================================

class TestProperties:
    """Tests for shared properties."""

    def test_low_power_mode_none(self):
        """low_power_mode should be None when not initialized."""
        orch = BaseOrchestrator()
        orch._low_power_mode = None
        assert orch.low_power_mode is None

    def test_low_power_mode_set(self):
        """low_power_mode should return the mode object."""
        orch = BaseOrchestrator()
        mock_mode = MagicMock()
        orch._low_power_mode = mock_mode
        assert orch.low_power_mode is mock_mode

    def test_model_manager_none(self):
        """model_manager should be None when not initialized."""
        orch = BaseOrchestrator()
        orch._model_mgr = None
        assert orch.model_manager is None

    def test_model_manager_set(self):
        """model_manager should return the manager object."""
        orch = BaseOrchestrator()
        mock_mgr = MagicMock()
        orch._model_mgr = mock_mgr
        assert orch.model_manager is mock_mgr

    def test_project_dir_property(self, base_orch, mock_settings):
        """project_dir property should return p_dir."""
        assert base_orch.project_dir == "/tmp/test_project"


# ============================================================
#  System Status Tests
# ============================================================

class TestSystemStatus:
    """Tests for get_system_status and get_intelligence_status."""

    @pytest.mark.asyncio
    async def test_get_system_status_structure(self, fully_mocked_orch):
        """get_system_status should return all expected keys."""
        status = await fully_mocked_orch.get_system_status()
        assert "pipeline" in status
        assert "ai" in status
        assert "phase7_engines" in status
        assert "phase8_intelligence" in status
        assert "agent_framework" in status
        assert "request_count" in status

    @pytest.mark.asyncio
    async def test_get_intelligence_status_structure(self, fully_mocked_orch):
        """get_intelligence_status should return intelligence info."""
        status = await fully_mocked_orch.get_intelligence_status()
        assert "reasoning_engine" in status
        assert "ai_layers" in status
        assert "thinking_engine" in status
        assert "phase8_modes" in status

    @pytest.mark.asyncio
    async def test_get_intelligence_status_ai_layers(self, fully_mocked_orch):
        """get_intelligence_status should report AI layer availability."""
        status = await fully_mocked_orch.get_intelligence_status()
        layers = status["ai_layers"]
        assert "layer1_semantic" in layers
        assert "layer2_qwen" in layers
        assert "layer3_memory" in layers
