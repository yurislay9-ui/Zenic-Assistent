"""MiniAIEngine bounded tasks — composition of task mixins."""

import logging
from ._tasks_1to4_mixin import BoundedTasks1To4Mixin
from ._tasks_5to7_mixin import BoundedTasks5To7Mixin

logger = logging.getLogger(__name__)


class BoundedTasksMixin(BoundedTasks1To4Mixin, BoundedTasks5To7Mixin):
    """7 Bounded Task methods — 100% deterministic, NO LLM calls.

    Composed from BoundedTasks1To4Mixin (tasks 1-4) and
    BoundedTasks5To7Mixin (tasks 5-7).
    """
    pass
