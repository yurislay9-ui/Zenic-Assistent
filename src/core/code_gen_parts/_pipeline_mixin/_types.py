"""
Pipeline-driven code generation for CodeGenerator.

M1 FIX: When generating feature modules, the _process() method now uses
CodeAssembler to produce REAL CRUD/analytics/notification logic instead
of the stub: return {"processed": True, "input": payload}
"""

import re
import logging
from src.core.shared.contracts import OperationType, GoalType


logger = logging.getLogger(__name__)


