"""PartialReasoningManager main class combining all mixins."""

from .partial import PartialMixin
from .resume import ResumeMixin


class PartialReasoningManager(
    PartialMixin,
    ResumeMixin,
):
    """Manages partial reasoning responses and resumption tokens."""

    def __init__(self, orchestrator):
        """
        Initialize with a reference to the orchestrator.

        Args:
            orchestrator: ZenicOrchestrator instance for accessing pipeline components.
        """
        self._orchestrator = orchestrator
