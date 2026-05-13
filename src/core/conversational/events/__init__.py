"""
Sistema de eventos del Asistente.

Event bus desacoplado para comunicacion entre componentes.
Los componentes emiten eventos despues de actuar,
y otros componentes se suscriben para reaccionar.
"""

from .event_bus import EventBus
from .event_types import EventTypes

__all__ = [
    "EventBus",
    "EventTypes",
]
