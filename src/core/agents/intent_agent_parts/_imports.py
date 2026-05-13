"""
Shared imports and constants for intent_agent_parts.
"""

import re
import logging
from typing import Any, Dict, List, Optional, Tuple

from src.core.agents.base import BaseAgent, AgentResult
from src.core.agents.schemas import IntentInput, IntentOutput
from src.core.agents.prompts import AgentPrompts, PromptBuilder
from src.core.agents.intent_shared import (
    VALID_OPERATIONS, VALID_GOALS, VALID_LANGUAGES,
    OP_KEYWORDS, GOAL_KEYWORDS,
    EXT_LANG_MAP, FENCE_LANG_MAP,
    extract_target_and_language, extract_code_block,
    extract_entities, infer_criticality, infer_template_type,
)

logger = logging.getLogger(__name__)

# Criticality keywords (local to IntentAgent)
CRITICALITY_KEYWORDS = {
    "critical": ["auth", "login", "password", "token", "jwt", "secret", "crypto",
                 "ssl", "tls", "certificate", "permission", "privilege",
                 "autenticacion", "contrasena", "secreto", "permiso"],
    "moderate": ["database", "db", "migration", "config", "setting",
                 "base de datos", "migracion", "configuracion"],
}
