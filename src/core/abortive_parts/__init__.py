"""
AbortiveProtocol sub-package — Auto-subdivision when solver timeout.
"""

from ._imports import (
    MAX_SUBTASKS, MAX_DEEP_SUBTASKS, MAX_ABORTIVE_DEPTH,
    ABORTIVE_SANDBOX_TTL_MULTIPLIER, ABORTIVE_SANDBOX_TTL_MIN,
    SUBTASK_SANDBOX_TTL_MULTIPLIER, SUBTASK_SANDBOX_TTL_MIN,
    SubtaskDescriptor, StepDispatcher, OperationType,
    get_solver_timeout_ms, get_projects_dir,
)
from ._protocol import ProtocolMixin
from ._subtasks import SubtaskGenerationMixin
from ._execution import ExecutionMixin
from ._merge import MergeMixin
from ._protocol_main import AbortiveProtocol

__all__ = [
    "MAX_SUBTASKS", "MAX_DEEP_SUBTASKS", "MAX_ABORTIVE_DEPTH",
    "ABORTIVE_SANDBOX_TTL_MULTIPLIER", "ABORTIVE_SANDBOX_TTL_MIN",
    "SUBTASK_SANDBOX_TTL_MULTIPLIER", "SUBTASK_SANDBOX_TTL_MIN",
    "SubtaskDescriptor", "StepDispatcher", "OperationType",
    "get_solver_timeout_ms", "get_projects_dir",
    "ProtocolMixin", "SubtaskGenerationMixin",
    "ExecutionMixin", "MergeMixin",
    "AbortiveProtocol",
]
