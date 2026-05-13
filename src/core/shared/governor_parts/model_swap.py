"""Mixin: Model swap integration for ResourceGovernor."""

from typing import Dict, Any

from ._imports import logger


class ModelSwapMixin:
    """Mixin providing ModelManager integration for model swap decisions."""

    def set_model_manager(self, model_manager):
        """
        Conecta el ResourceGovernor con el ModelManager para model swap.

        Cuando el governor detecta presion de RAM, puede recomendar
        al ModelManager que descargue modelos para liberar memoria.
        """
        self._model_manager = model_manager
        logger.info("ResourceGovernor: Connected to ModelManager for model swap")

    def should_unload_models(self) -> str:
        """
        Recomienda al ModelManager descargar modelos segun presion de RAM.

        Returns:
            "none" - No se necesita descargar nada
            "semantic" - Descargar SemanticEngine (~150MB)
            "ai" - Descargar MiniAIEngine (~378MB)
            "all" - Descargar ambos (~530MB)
        """
        if self._ram_usage_mb > self.ram_limit_mb * 0.9:
            return "all"
        if self._ram_usage_mb > self.ram_limit_mb * 0.75:
            return "ai"
        if self._ram_usage_mb > self.ram_limit_mb * 0.6:
            return "semantic"
        return "none"

    def get_model_ram_status(self) -> Dict:
        """
        Retorna estado de RAM para que el ModelManager tome decisiones.

        El ModelManager consulta esto antes de cargar un modelo para
        decidir si hay presupuesto suficiente o si debe descargar otro.
        """
        return {
            "ram_usage_mb": round(self._ram_usage_mb, 1),
            "ram_limit_mb": self.ram_limit_mb,
            "ram_available_mb": round(self.ram_limit_mb - self._ram_usage_mb, 1),
            "ram_usage_pct": round(self._ram_usage_mb / self.ram_limit_mb * 100, 1),
            "thermal_throttle": round(self._thermal_throttle, 2),
            "recommendation": self.should_unload_models(),
        }

    def get_status(self) -> Dict[str, Any]:
        """Retorna el estado actual del governor para el endpoint /health."""
        return {
            "cpu_usage_pct": round(self._get_cpu_usage() * 100, 1),
            "ram_usage_mb": round(self._ram_usage_mb, 1),
            "ram_limit_mb": self.ram_limit_mb,
            "thermal_throttle": round(self._thermal_throttle, 2),
            "adaptive_mcts_sims": self.get_adaptive_mcts_simulations(),
            "adaptive_solver_timeout_ms": self.get_adaptive_solver_timeout(),
            "z3_memory_limit_mb": self.get_z3_memory_limit_mb(),
            "stats": self.stats,
        }

    @property
    def ram_usage_mb(self) -> float:
        """Public accessor for current RAM usage in MB."""
        return self._ram_usage_mb
