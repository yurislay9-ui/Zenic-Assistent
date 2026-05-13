"""
ZENIC-AGENTS - Model Manager v16 (Hybrid Lazy Loading + Auto-Unload)

Gestor de modelos que maximiza el rendimiento en el Redmi 12R Pro:
- Lazy Loading: Los modelos solo se cargan cuando se necesitan
- Auto-Unload: Los modelos se descargan tras N minutos de inactividad
- RAM Budget: Control estricto de memoria para no quemar el telefono
- Model Swap: Carga/descarga dinamica segun demanda
"""

from .manager import ModelManager
from .singleton import get_model_manager, init_model_manager
from ._imports import (
    IDLE_TIMEOUT_S, RAM_BUDGET_MB, ENABLE_AUTO_UNLOAD, ENABLE_LAZY_LOAD
)

__all__ = [
    "ModelManager",
    "get_model_manager",
    "init_model_manager",
    "IDLE_TIMEOUT_S",
    "RAM_BUDGET_MB",
    "ENABLE_AUTO_UNLOAD",
    "ENABLE_LAZY_LOAD",
]
