"""
ZENIC-AGENTS - LowPowerSequentialMode (Dinamico Basado en Hardware)

Modo "Low-Power Sequential" dinamico que hace que el DAG evalue
la temperatura y bateria del dispositivo, y fuerce la ejecucion
secuencial de la Capa 4 cuando el hardware esta bajo estres.
"""

from .mode import LowPowerSequentialMode
from ._imports import PowerMode, HardwareState

__all__ = [
    "LowPowerSequentialMode",
    "PowerMode",
    "HardwareState",
]
