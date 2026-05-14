"""
ZENIC-AGENTS - Agent Framework

Sistema de agentes IA que reemplaza la lógica de negocio hardcodeada.
Cada agente = Prompt Estructurado + Esquema Pydantic + Wrapper Delgado.

Agentes:
  - IntentAgent: Comprensión semántica (reemplaza keyword matching)
  - SurgicalAgent (F2): Clasificación quirúrgica multi-señal
  - ContextAgent (F3): Gestión de ventana de contexto con compresión adaptativa
  - ReasoningAgent: Razonamiento avanzado (reemplaza reasoning_engine)
  - BusinessLogicAgent: Lógica de negocio IA (reemplaza 30+ LogicBlocks)
  - CodeAgent: Generación + transformación (reemplaza templates/f-strings)
  - AutomationAgent: Automatización inteligente (reemplaza keyword inference)
  - ValidationAgent: Validación inteligente (reemplaza regex patterns)
  - YamilAgent: Agente creador de plantillas (nichos → Blueprints certificados)

Principios:
  - INFRAESTRUCTURA PERMANECE, LÓGICA DE NEGOCIO → AGENTES IA
  - Cada agente tiene fallback determinista
  - Compatible con API OpenAI existente
  - Tests como contrato de comportamiento

.. deprecated::
    This module (agents v1) is the legacy pipeline. It will be replaced by
    ``agents_v2`` which uses the Business Operations model (PROCESS, FORECAST,
    RESOLVE) instead of the Code Automation model (CREATE, REFACTOR, DEBUG).
    Import from ``src.core.agents_v2`` for new code.
    Removal target: post v2.0 stable release.
"""

import warnings

warnings.warn(
    "agents v1 (src.core.agents) is deprecated. "
    "Use agents_v2 (src.core.agents_v2) for new code. "
    "The v1 pipeline uses the Code Automation model (CREATE, REFACTOR, DEBUG) "
    "which has been replaced by Business Operations (PROCESS, FORECAST, RESOLVE) "
    "in v2. Removal target: post v2.0 stable release.",
    DeprecationWarning,
    stacklevel=2,
)

from src.core.agents.base import BaseAgent, AgentResult
from src.core.agents.runner import AgentRunner
from src.core.agents.schemas import (
    IntentInput, IntentOutput,
    ReasoningInput, ReasoningOutput,
    BusinessInput, BusinessOutput,
    CodeInput, CodeOutput,
    AutomationInput, AutomationOutput,
    ValidationInput, ValidationOutput,
    ContextInput, ContextOutput,
    CriticalityInput, CriticalityOutput,
)
from src.core.agents.prompts import PromptBuilder, AgentPrompts
from src.core.agents.cache import AgentCache
from src.core.agents.intent_agent import IntentAgent
from src.core.agents.surgical_agent import SurgicalAgent
from src.core.agents.context_agent import ContextAgent
from src.core.agents.reasoning_agent import ReasoningAgent
from src.core.agents.business_logic_agent import BusinessLogicAgent
# CodeAgent removed — module deleted
from src.core.agents.automation_agent import AutomationAgent
from src.core.agents.validation_agent import ValidationAgent
from src.core.agents.criticality_agent import CriticalityAgent
from src.core.agents.yamil import YamilAgent

__all__ = [
    "BaseAgent", "AgentResult",
    "AgentRunner",
    "IntentInput", "IntentOutput",
    "ReasoningInput", "ReasoningOutput",
    "BusinessInput", "BusinessOutput",
    "CodeInput", "CodeOutput",
    "AutomationInput", "AutomationOutput",
    "ValidationInput", "ValidationOutput",
    "ContextInput", "ContextOutput",
    "CriticalityInput", "CriticalityOutput",
    "PromptBuilder", "AgentPrompts",
    "AgentCache",
    "IntentAgent",
    "SurgicalAgent",
    "ContextAgent",
    "ReasoningAgent",
    "BusinessLogicAgent",
    # "CodeAgent" removed — module deleted
    "AutomationAgent",
    "ValidationAgent",
    "CriticalityAgent",
    "YamilAgent",
]
