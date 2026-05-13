"""
ZENIC-AGENTS - BusinessLogicAgent — Facade

Agente IA que reemplaza los 30+ LogicBlocks hardcoded con lógica de negocio
impulsada por IA.

This module is a thin facade; all logic lives in business_logic_agent_parts/.
"""

from .business_logic_agent_parts import *  # noqa: F401,F403
from .business_logic_agent_parts import BusinessLogicAgent, VALID_OPERATION_TYPES

__all__ = [
    "BusinessLogicAgent",
    "VALID_OPERATION_TYPES",
]
