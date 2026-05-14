"""DeterministicPipeline - Composition of task mixins."""

import logging
from ._tasks_1to4 import DeterministicTasks1To4Mixin
from ..evidence_collector import EvidenceCollector
from ._tasks_5to7 import DeterministicTasks5To7Mixin

logger = logging.getLogger(__name__)


class DeterministicPipeline(DeterministicTasks1To4Mixin, DeterministicTasks5To7Mixin):
    """
    Pipeline determinístico que reemplaza las 7 tareas de MiniAIEngine.

    Composed from DeterministicTasks1To4Mixin (tasks 1-4) and
    DeterministicTasks5To7Mixin (tasks 5-7).
    """

    def __init__(self):
        self._evidence_collector = EvidenceCollector()
