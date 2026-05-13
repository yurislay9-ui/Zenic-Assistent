"""
BaseOrchestrator - Shared base class for ZenicOrchestrator and DAGOrchestrator.

Extracts all duplicated initialization, public API, backward-compat delegation,
and shared properties from both orchestrator implementations.

Both ZenicOrchestrator (sequential) and DAGOrchestrator (graph-based) share:
- 8-level pipeline component initialization
- 3-layer AI architecture wiring
- Extended architecture (thinking, template, app, automation, schema)
- Phase 7 engines (executor_registry, logic_builder, auth)
- Phase 8 intelligence (reasoning, chain_validator, chain_executor)
- Decomposed sub-modules (abortive, partial, code_gen, code_transform, analysis)
- Agent framework (F1-F5 agents)
- Common state (request_count, locks, pending_resumptions)
- Public API methods (resume_from_partial, generate_app, etc.)
- Backward-compat delegation methods
- Shared properties (model_manager, low_power_mode, etc.)
"""

from .orch_base_parts import *  # noqa: F401,F403
from .orch_base_parts import BaseOrchestrator  # explicit for clarity

__all__ = ["BaseOrchestrator"]
