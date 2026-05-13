"""
Abortive Protocol - Auto-subdivision when solver timeout.

Si el solver hace timeout (15s), el sistema:
1. Hace rollback al estado pristino anterior
2. Subdivide automaticamente la tarea en unidades logicas
3. EJECUTA cada subtask a traves del pipeline completo (no solo plan)
4. Combina los resultados de cada subtask
5. Valida el resultado combinado en sandbox
6. Si pasa -> commit SUCCESS; si subtask timeout -> subdividir recursivamente (max depth 2)
7. Si la combinacion falla -> devolver Razonamiento Parcial con token de resumption
"""

from .abortive_parts import *  # noqa: F401,F403
from .abortive_parts import AbortiveProtocol  # noqa: F401

__all__ = [
    "AbortiveProtocol",
    "MAX_SUBTASKS", "MAX_DEEP_SUBTASKS", "MAX_ABORTIVE_DEPTH",
    "ABORTIVE_SANDBOX_TTL_MULTIPLIER", "ABORTIVE_SANDBOX_TTL_MIN",
    "SUBTASK_SANDBOX_TTL_MULTIPLIER", "SUBTASK_SANDBOX_TTL_MIN",
]
