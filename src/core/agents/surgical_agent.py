"""
ZENIC-AGENTS - SurgicalAgent (F2)

Agente quirúrgico de clasificación de intención que UNIFICA y REEMPLAZA
la lógica dispersa en 3 subsistemas redundantes:

  1. SemanticParser (TF-IDF + keyword maps) — level1_semantic_engine/parser.py
  2. SemanticEngine._fallback_classify() — semantic_engine.py
  3. MiniAIEngine.classify_intent() — mini_ai_engine.py

Arquitectura SurgicalAgent:
  ┌─────────────────────────────────────────────────┐
  │  CABLE 1: SmartMemory cache ──► hit? → return   │
  │  CABLE 2: SemanticEngine embed ──► high conf? →  │
  │  CABLE 3: LLM (AgentRunner) ──► valid JSON? →   │
  │  CABLE 4: TF-IDF determinista ──► always works   │
  └─────────────────────────────────────────────────┘

Fusión multi-señal:
  - Si LLM + SemanticEngine coinciden → confianza ALTA (0.7-1.0)
  - Si solo LLM o solo Semantic → confianza MEDIA (0.4-0.7)
  - Si solo TF-IDF → confianza BAJA (0.0-0.4)
  - Calibración: Ajusta confianza según historial de aciertos

Restricciones de diseño:
  - ≤600 tokens por llamada LLM (Qwen3-0.6B)
  - Fallback determinista siempre disponible
  - Compatible con Android/Termux, 500MB RAM
"""

from .surgical_agent_parts import *  # noqa: F401,F403
from .surgical_agent_parts import SurgicalAgent  # noqa: F401

__all__ = [
    "SurgicalAgent",
]
