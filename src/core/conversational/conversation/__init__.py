"""
Modulo de gestion de conversacion del Asistente.

Gestiona conversaciones multi-turno con:
  - ConversationManager: Orquesta sesiones de conversacion
  - TurnTracker: Trackea turnos y detecta topic shifts
  - ContextSummarizer: Resume contexto para ventanas largas
  - ConversationState: Estado inmutable de la conversacion
"""

from .manager import ConversationManager
from .turn_tracker import TurnTracker
from .summarizer import ContextSummarizer
from .state import ConversationState, ConversationPhase

__all__ = [
    "ConversationManager",
    "TurnTracker",
    "ContextSummarizer",
    "ConversationState",
    "ConversationPhase",
]
