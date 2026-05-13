"""
ZENIC-AGENTS - Agent Framework Tests

Tests completos del framework de agentes:
  - BaseAgent (clase abstracta, utilidades)
  - AgentRunner (ejecución, fallback, retry, cache)
  - AgentCache (almacenamiento, expiración, evicción)
  - PromptBuilder (construcción de prompts)
  - Schemas (validación de datos)
  - Cableado con Orchestrator (integración)

Modularized into test_agent_fw_parts/ sub-directory.
"""

# Re-export all test classes from sub-modules for backward compatibility
from .test_agent_fw_parts import *
