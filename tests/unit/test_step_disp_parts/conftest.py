"""
Shared fixtures for test_step_disp_parts sub-modules.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock

from src.core.step_dispatcher import StepDispatcher


def make_step(action, constraints=None, target_node_name=""):
    """Create a mock step object with given action and constraints."""
    step = MagicMock()
    step.action = action
    step.constraints = constraints or {}
    step.target_node_name = target_node_name
    return step


def make_intent(op="CREATE", target="test_func", scrap_query="test query"):
    """Create a mock intent payload."""
    intent = MagicMock()
    intent.op = op
    intent.target = target
    intent.scrap_query = scrap_query
    intent.raw_code = ""
    return intent


def make_plan(solver_proof=None):
    """Create a mock plan with optional solver proof."""
    plan = MagicMock()
    plan.solver_proof = solver_proof
    plan.steps = []
    return plan


@pytest.fixture
def mock_orchestrator():
    """Create a fully mocked orchestrator for StepDispatcher."""
    orch = MagicMock()

    # AST Engine
    orch.ast_engine.analyze_structure.return_value = {
        "functions": 3, "classes": 1, "max_complexity": 5,
        "function_names": ["func_a", "func_b", "func_c"],
    }
    orch.ast_engine.get_node_info.return_value = [
        {"node_type": "function", "name": "test_func", "complexity": 3},
    ]

    # Scrap agent (async methods)
    orch.scrap.smart_fetch = AsyncMock(return_value={
        "success": True, "content": "sample code", "source": "github",
    })
    orch.scrap.fetch_all_sources = AsyncMock(return_value={
        "github": "gh_code", "devdocs": "",
    })

    # Code generator
    orch._code_gen.generate_contextual_code.return_value = "def new_func(): pass"
    orch._code_gen.extract_solver_insights.return_value = {}

    # Code transformer
    orch._code_transform.optimize_function.return_value = "def optimized(): pass"

    # Surgeon
    orch.surgeon.mutate_node.return_value = "def replaced(): pass"
    orch.surgeon.delete_function.return_value = "# deleted"

    # Analysis utils
    orch._analysis.apply_fix.return_value = "def fixed(): pass"
    orch._analysis.generate_quality_report.return_value = "Quality: 85/100"
    orch._analysis.explain_code.return_value = "This code does X"
    orch._analysis.explain_concept.return_value = "Concept explanation"
    orch._analysis.analyze_and_respond.return_value = "Analysis result"
    orch._analysis.general_response.return_value = "General response"
    orch._analysis.full_analysis.return_value = "Full analysis result"
    orch._analysis.check_dependencies.return_value = ["dep1", "dep2"]

    # MiniAI
    orch._ai.is_loaded = False
    orch._ai.suggest_pattern.return_value = "validator_pattern"

    # Validation agent
    orch._validation_agent = None
    orch._agent_runner = None

    # Fractal generator
    orch._fractal_gen = None

    return orch


@pytest.fixture
def dispatcher(mock_orchestrator):
    """Create a StepDispatcher with mocked orchestrator."""
    return StepDispatcher(mock_orchestrator)
