"""
StepDispatcher - Unified step dispatch logic for pipeline execution.

Eliminates the duplicated step dispatch code that existed in:
- orchestrator.py (ZenicOrchestrator.execute step loop)
- MIGRATED: DAGOrchestrator now in zenic-core Rust crate
- abortive_protocol.py (AbortiveProtocol.execute_subtask step loop)

All three previously maintained identical if/elif chains for handling
step actions like ANALYZE_STRUCTURE, SCRAPE_PATTERNS, GENERATE_CODE, etc.

This module provides a single `execute_step()` method and a
`execute_plan_steps()` method that iterates plan steps.

Refactored to use the Strategy Registry pattern instead of if/elif chains,
with EventBus integration for step lifecycle events and Retry support.
"""

import logging
from typing import Dict, Any, List, Optional, Tuple

from src.core.patterns.behavioral import StrategyRegistry
from src.core.patterns.orchestration import EventBus
from src.core.patterns.resilience import RetryConfig, with_retry

logger = logging.getLogger("zenic_agents.step_dispatcher")


from ._core_mixin import StepDispatcherCoreMixin
from ._extra_mixin import StepDispatcherExtraMixin

__all__ = ["StepDispatcher"]


class StepDispatcher(StepDispatcherCoreMixin, StepDispatcherExtraMixin):
    """
    Unified step dispatch logic using Strategy Registry pattern.

    Takes a reference to the orchestrator (BaseOrchestrator) to access
    its components (ast_engine, scrap, surgeon, _code_gen, _code_transform,
    _analysis, _ai, _validation_agent, _agent_runner, _fractal_gen, etc.).

    Handles ALL step action types via individually registered handlers:
    - ANALYZE_STRUCTURE
    - SCRAPE_PATTERNS
    - GENERATE_CODE
    - REPLACE_AST_NODE
    - DELETE_AST_NODE
    - TRACE_EXECUTION
    - PATCH_FIX
    - QUALITY_REPORT
    - EXPLAIN_CODE
    - SEARCH_DEFINITION
    - SYMBOLIC_VALIDATION / SYNTAX_VALIDATION
    - ANALYZE_AND_RESPOND
    - QUICK_ANALYSIS
    - FULL_ANALYSIS
    - CHECK_DEPENDENCIES
    - SCAFFOLD_FRACTAL
    """

    def __init__(self, orchestrator):
        """
        Initialize with a reference to the orchestrator.

        Args:
            orchestrator: BaseOrchestrator (or subclass) instance for
                         accessing pipeline components.
        """
        self._orch = orchestrator
        self._registry = StrategyRegistry()
        self._event_bus = getattr(orchestrator, '_event_bus', None)
        self._retry_config = getattr(orchestrator, '_pipeline_retry', RetryConfig(max_attempts=2, base_delay=0.5))
        self._register_handlers()

