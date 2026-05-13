"""
ZENIC-AGENTS - ContextAgent (F3) Tests

Test suite completa para el agente de gestión de contexto.
Cubre: 4 cables, scoring, compresión, presupuesto, deduplicación.
"""

from .test_context_parts import *  # noqa: F401,F403
from .test_context_parts import __all__  # noqa: F401
from .test_context_parts.conftest import *  # noqa: F401,F403
