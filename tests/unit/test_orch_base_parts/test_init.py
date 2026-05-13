"""Tests for _init_common_state, _init_pipeline_components, _init_extended_architecture."""

import pytest
from unittest.mock import MagicMock, patch

from src.core.orchestrator_base import BaseOrchestrator
from ._fixtures import mock_settings, base_orch, fully_mocked_orch


# ============================================================
#  _init_common_state Tests
# ============================================================

class TestInitCommonState:
    """Tests for _init_common_state method."""

    def test_request_count_initialized(self):
        """request_count should start at 0."""
        orch = BaseOrchestrator()
        with patch("src.core.orch_base_parts._imports.get_isolation_manager"):
            orch._init_common_state()
        assert orch._request_count == 0

    def test_pending_resumptions_empty(self):
        """_pending_resumptions should start as empty dict."""
        orch = BaseOrchestrator()
        with patch("src.core.orch_base_parts._imports.get_isolation_manager"):
            orch._init_common_state()
        assert orch._pending_resumptions == {}

    def test_current_client_id_default(self):
        """_current_client_id should default to 'default'."""
        orch = BaseOrchestrator()
        with patch("src.core.orch_base_parts._imports.get_isolation_manager"):
            orch._init_common_state()
        assert orch._current_client_id == "default"

    def test_isolation_manager_assigned(self):
        """_isolation_manager should be assigned from get_isolation_manager."""
        mock_mgr = MagicMock()
        orch = BaseOrchestrator()
        with patch("src.core.orch_base_parts._init_mixin.get_isolation_manager", return_value=mock_mgr):
            orch._init_common_state()
        assert orch._isolation_manager is mock_mgr


# ============================================================
#  _init_pipeline_components Tests
# ============================================================

class TestInitPipelineComponents:
    """Tests for _init_pipeline_components method."""

    def test_settings_stored(self, base_orch, mock_settings):
        """Settings should be stored on the instance."""
        assert base_orch.settings == mock_settings

    def test_project_dir_set(self, base_orch):
        """p_dir should be set from settings."""
        assert base_orch.p_dir == "/tmp/test_project"

    def test_parser_created(self, base_orch):
        """Parser component should be created."""
        assert base_orch.parser is not None

    def test_router_created(self, base_orch):
        """Router component should be created."""
        assert base_orch.router is not None

    def test_all_pipeline_components_created(self, base_orch):
        """All 8 pipeline components should be created."""
        assert base_orch.parser is not None
        assert base_orch.router is not None
        assert base_orch.ast_engine is not None
        assert base_orch.planner is not None
        assert base_orch.scrap is not None
        assert base_orch.surgeon is not None
        assert base_orch.sandbox is not None
        assert base_orch.ledger is not None
        assert base_orch.cache is not None

    def test_default_project_dir(self):
        """p_dir should default to '.' when not in settings."""
        with patch("src.core.orch_base_parts._imports.initialize_databases"), \
             patch("src.core.orch_base_parts._imports.SemanticParser"), \
             patch("src.core.orch_base_parts._imports.MacroRouter"), \
             patch("src.core.orch_base_parts._imports.GraphASTEngine"), \
             patch("src.core.orch_base_parts._imports.APAPlanner"), \
             patch("src.core.orch_base_parts._imports.GitHubScrapAgent"), \
             patch("src.core.orch_base_parts._imports.ASTSurgeon"), \
             patch("src.core.orch_base_parts._imports.ReflexionSandbox"), \
             patch("src.core.orch_base_parts._imports.MerkleLedger"), \
             patch("src.core.orch_base_parts._imports.TheoremCache"), \
             patch("src.core.orch_base_parts._imports.get_isolation_manager"):
            orch = BaseOrchestrator()
            orch._init_pipeline_components({})
            assert orch.p_dir == "."


# ============================================================
#  _init_extended_architecture Tests
# ============================================================

class TestInitExtendedArchitecture:
    """Tests for _init_extended_architecture method."""

    def test_assigns_thinking_engine(self):
        """Should store the thinking engine reference."""
        orch = BaseOrchestrator()
        mock_thinking = MagicMock()
        orch._init_extended_architecture(thinking_engine=mock_thinking)
        assert orch._thinking is mock_thinking

    def test_assigns_auth(self):
        """Should store the auth service reference."""
        orch = BaseOrchestrator()
        mock_auth = MagicMock()
        orch._init_extended_architecture(auth=mock_auth)
        assert orch._auth is mock_auth

    def test_defaults_to_none(self):
        """Unspecified components should default to None."""
        orch = BaseOrchestrator()
        orch._init_extended_architecture()
        assert orch._thinking is None
        assert orch._template_engine is None
        assert orch._auth is None
        assert orch._reasoning is None
