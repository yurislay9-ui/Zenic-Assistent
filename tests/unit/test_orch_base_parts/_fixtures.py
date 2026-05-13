"""Shared fixtures for orchestrator_base tests — imported into test files."""

import threading
import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from src.core.orchestrator_base import BaseOrchestrator


@pytest.fixture
def mock_settings():
    """Return mock settings dict."""
    return {"project_dir": "/tmp/test_project"}


@pytest.fixture
def base_orch(mock_settings):
    """Create a BaseOrchestrator with mocked pipeline components."""
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
        orch._init_pipeline_components(mock_settings)
        return orch


@pytest.fixture
def fully_mocked_orch(mock_settings):
    """Create a BaseOrchestrator with all sub-systems mocked."""
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
        orch._init_pipeline_components(mock_settings)

        orch._semantic = MagicMock()
        orch._semantic.is_loaded = True
        orch._ai = MagicMock()
        orch._ai.is_loaded = True
        orch._memory = MagicMock()
        orch._memory.enhanced_stats = {}
        orch._thinking = MagicMock()
        orch._thinking.stats = {}
        orch._thinking.reason.return_value = MagicMock(
            answer="test", confidence=0.9, source="test",
            context_used=[], thinking_time_s=0.1,
        )
        orch._template_engine = MagicMock()
        orch._executor_registry = MagicMock()
        orch._executor_registry._executors = {}
        orch._executor_registry.list_types.return_value = ["http_request", "file_write"]
        orch._logic_builder = MagicMock()
        orch._logic_builder.list_blocks.return_value = []
        orch._chain_validator = MagicMock()
        orch._chain_executor = MagicMock()
        orch._app_gen = MagicMock()
        orch._app_gen.list_templates.return_value = []
        orch._automation = MagicMock()
        orch._automation.stats = {}
        orch._automation.list_workflows.return_value = []
        orch._schema_designer = MagicMock()
        orch._auth = MagicMock()
        orch._reasoning = MagicMock()
        orch._reasoning.stats = {}
        orch._request_count = 0
        orch._request_count_lock = threading.Lock()
        orch._agent_runner = MagicMock()
        orch._agent_runner.stats = {}
        orch._agent_runner._cache = MagicMock()
        orch._agent_runner._cache.stats = {}
        orch._surgical_agent = MagicMock()
        orch._surgical_agent.stats = {}
        orch._reasoning_agent = MagicMock()
        orch._reasoning_agent.stats = {}
        orch._business_logic_agent = MagicMock()
        orch._business_logic_agent.stats = {}
        orch._code_agent = MagicMock()
        orch._code_agent.stats = {}
        orch._automation_agent = None
        orch._validation_agent = MagicMock()
        orch._validation_agent.stats = {}
        orch._context_agent = None
        orch._criticality_agent = None
        orch._zenic_meta_router = None
        orch._fractal_gen = None

        return orch
