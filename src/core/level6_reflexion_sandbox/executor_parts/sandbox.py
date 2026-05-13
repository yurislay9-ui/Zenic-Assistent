"""ReflexionSandbox main class combining all mixins."""

from ._imports import (
    logger, load_settings, get_sandbox_timeout_s, get_k_path_limit,
    TimeoutEnforcer, SymbolicExecutor, KPathAnalyzer, get_isolation_manager
)
from .python_validation import PythonValidationMixin
from .other_validation import OtherValidationMixin
from .analysis import AnalysisMixin
from .isolated_exec import IsolatedExecMixin


class ReflexionSandbox(
    PythonValidationMixin,
    OtherValidationMixin,
    AnalysisMixin,
    IsolatedExecMixin,
):
    """
    Sandbox con ejecucion simbolica real, timeout real y K-Path limiting.
    TODO el codigo se ejecuta en un workspace AISLADO separado del proyecto.

    Implementa el Nivel 6 del documento de arquitectura:
    - AISLAMIENTO: Workspace separado, sin acceso al filesystem del proyecto
    - Ejecucion Simbolica Acotada (estados simbolicos + path conditions)
    - K-Paths de radio configurable (default 10) desde el grafo AST
    - Path Pruning de side effects (I/O -> Mock)
    - Timeout enforcement real via threading
    - Ejecucion segura con builtins restringidos y open() sandboxed
    """

    def __init__(self, timeout_seconds=None, k_path_limit=None):
        self.settings = load_settings()
        self.timeout_seconds = timeout_seconds or get_sandbox_timeout_s(self.settings)
        self.k_path_limit = k_path_limit or get_k_path_limit(self.settings)
        self._enforcer = TimeoutEnforcer(timeout_ms=self.timeout_seconds * 1000)
        self._symbolic_executor = SymbolicExecutor(
            k_path_limit=self.k_path_limit,
            max_depth=20
        )
        self._kpath_analyzer = KPathAnalyzer(k_limit=self.k_path_limit)

        # Sistema de aislamiento
        self._isolation_manager = get_isolation_manager()

        logger.info("ReflexionSandbox: timeout=%ds, k_path_limit=%d, ISOLATED=True",
                     self.timeout_seconds, self.k_path_limit)

    async def validate_code(self, code, language, target_name):
        """Valida codigo con ejecucion simbolica real y analisis de caminos."""
        if language == "python":
            return self._validate_python(code, target_name)
        return self._validate_other(code, language, target_name)
