"""
Shared imports and constants for abortive_parts.
"""

import gc
import logging

from src.config.loader import get_solver_timeout_ms
from src.core.shared.db_initializer import get_projects_dir
from src.core.shared.contracts import OperationType
from src.core.subtask_descriptor import SubtaskDescriptor
from src.core.step_dispatcher import StepDispatcher

logger = logging.getLogger(__name__)

# === Extracted Constants (previously hardcoded inline) ===
MAX_SUBTASKS = 5                   # Max subtasks for abortive protocol
MAX_DEEP_SUBTASKS = 3              # Max deep subtasks for recursive subdivision
MAX_ABORTIVE_DEPTH = 2             # Max recursion depth for abortive protocol
ABORTIVE_SANDBOX_TTL_MULTIPLIER = 5 # Abortive workspace TTL multiplier
ABORTIVE_SANDBOX_TTL_MIN = 300      # Minimum abortive workspace TTL
SUBTASK_SANDBOX_TTL_MULTIPLIER = 2  # Subtask workspace TTL multiplier
SUBTASK_SANDBOX_TTL_MIN = 60       # Minimum subtask workspace TTL
