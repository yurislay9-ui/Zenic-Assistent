"""
AbortiveProtocol main class — inherits from all mixins.
"""

from ._imports import StepDispatcher
from ._protocol import ProtocolMixin
from ._subtasks import SubtaskGenerationMixin
from ._execution import ExecutionMixin
from ._merge import MergeMixin


class AbortiveProtocol(ProtocolMixin, SubtaskGenerationMixin, ExecutionMixin, MergeMixin):
    """Handles the Abortive Protocol for auto-subdivision when solver timeout."""

    def __init__(self, orchestrator):
        """
        Initialize with a reference to the orchestrator.

        Args:
            orchestrator: BaseOrchestrator (or subclass) instance for accessing pipeline components.
        """
        self._orchestrator = orchestrator
        self._step_dispatcher = StepDispatcher(orchestrator)
