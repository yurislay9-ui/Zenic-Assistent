"""
Shared imports and constants for business_logic_agent_parts.
"""

import re
import json
import time
import logging
from typing import Any, Dict, List, Optional, Tuple

from src.core.agents.base import BaseAgent, AgentResult
from src.core.agents.schemas import BusinessInput, BusinessOutput
from src.core.agents.prompts import AgentPrompts, PromptBuilder

logger = logging.getLogger(__name__)

# Valid operation types
VALID_OPERATION_TYPES = frozenset({
    "invoice", "inventory", "crm", "task", "report",
    "notification", "analytics", "custom",
})
