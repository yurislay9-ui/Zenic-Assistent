"""Shared imports for partial_reason_parts."""

import gc
import json
import time
import uuid
import threading
import logging

from src.core.shared.db_initializer import get_projects_dir
from src.core.shared.contracts import OperationType, GoalType
from src.core.subtask_descriptor import SubtaskDescriptor

logger = logging.getLogger(__name__)
