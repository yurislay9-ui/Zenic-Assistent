"""
MiniAIEngine main class — v17.1 Verdict Architecture with Resilience.

CAMBIO FUNDAMENTAL (v16 → v17):
  ANTES: La IA hacía 7 tareas bounded (clasificar, extraer, generar, etc.)
  AHORA: La IA SOLO emite veredictos binarios (SÍ/NO) como árbitro final.

CAMBIO v17 → v17.1:
  - Las 7 tareas bounded son ahora 100% determinísticas (NUNCA llaman al LLM)
  - El veredicto tiene Circuit Breaker, Retry con backoff, Health Monitor
  - Multi-attempt consensus: Pregunta 3 veces, mayoría gana
  - Auditoría completa de todas las decisiones

Las 7 tareas originales ahora las hace código determinístico.
MiniAIEngine conserva los métodos legacy para compatibilidad,
pero internamente NUNCA llaman al LLM.

El ÚNICO método que usa la IA es verdict(), que solo acepta YES/NO.
Con resiliencia:
  - Circuit Breaker protege contra LLM caído
  - Retry con exponential backoff (3 intentos)
  - Multi-attempt consensus (3 preguntas, mayoría gana)
  - Health Monitor en tiempo real
  - Auditoría de todas las decisiones
"""

from ._imports import IntentResult
from ._lifecycle import ModelLifecycleMixin
from ._tasks import BoundedTasksMixin
from ._fallbacks import FallbackMethodsMixin
from ._verdict_mixin import VerdictMixin
from typing import Optional


class MiniAIEngine(ModelLifecycleMixin, BoundedTasksMixin, FallbackMethodsMixin, VerdictMixin):
    """
    Motor de IA para ZENIC-AGENTS v1.1 - Arquitectura de Veredicto con Resiliencia.

    Filosofía (v17.1): La IA NO hace tareas. Solo arbitra.
    - Todas las tareas las hace código determinístico (sin IA)
    - La IA solo responde SÍ/NO cuando hay empate en el consenso
    - Es imposible que la IA dé una "mala respuesta" porque
      solo puede decir SÍ o NO, y si dice algo ambiguo = NO

    Resiliencia (v17.1):
    - Circuit Breaker: Si el LLM falla 3 veces, se abre
    - Retry con backoff: Reintento inteligente con delays crecientes
    - Multi-attempt consensus: 3 preguntas, mayoría gana
    - Health Monitor: Tracking de salud en tiempo real
    - Auditoría: Registro de todas las decisiones

    Compatibilidad:
    - Los 7 métodos bounded siguen funcionando (determinísticos, sin IA)
    - El método verdict() es el punto de entrada recomendado
    - Los agentes que usaban _call_llm() siguen funcionando
    """

    def __init__(self, model_path: Optional[str] = None, auto_load: bool = True):
        self._init_lifecycle(model_path=model_path, auto_load=auto_load)
        self._init_verdict()
