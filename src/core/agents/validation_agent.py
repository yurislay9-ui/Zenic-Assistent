"""
ZENIC-AGENTS - ValidationAgent

Agente IA que UNIFICA la validación de código y cadenas lógicas.
Reemplaza la lógica de validación dispersa en 2 módulos:

  1. ChainValidator (250 líneas, pre-execution validation)
  2. CodeTransformer bug detection (partial, within fix_python)

Arquitectura del ValidationAgent:
  - LLM path: AgentRunner → Qwen3-0.6B → parse_response → ValidationOutput
  - Rule path: Reglas deterministas de validación por tipo de target
  - Fallback path: Validación determinista por reglas estáticas (sin LLM)

Tipos de validación soportados:
  - code: Validación de código (seguridad, calidad, bugs)
  - chain: Validación de cadenas lógicas (compatibilidad, completitud)
  - config: Validación de configuración (schemas, valores)

Produce un ValidationOutput compatible con ChainValidator.ValidationResult.
"""

from .validation_agent_parts import *  # noqa: F401,F403
from .validation_agent_parts import ValidationAgent  # noqa: F401

__all__ = [
    "ValidationAgent",
    "SECURITY_PATTERNS", "QUALITY_PATTERNS", "CHAIN_COMPATIBILITY_RULES",
    "ValidationInput", "ValidationOutput", "ValidationIssue",
]
