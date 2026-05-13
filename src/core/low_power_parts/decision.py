"""Mixin: Decision API for LowPowerSequentialMode."""

from ._imports import PowerMode


class DecisionMixin:
    """Mixin providing decision API for DAGOrchestrator."""

    def should_run_parallel_layer4(self) -> bool:
        """
        Deberia la Capa 4 (Architect, Planner, Risk) ejecutarse en paralelo?

        Returns:
            True si paralelo, False si secuencial
        """
        mode = self._evaluate_cached()
        return self._should_run_parallel_layer4(mode)

    def _should_run_parallel_layer4(self, mode: PowerMode) -> bool:
        """Internal: decision based on pre-evaluated mode."""
        return mode == PowerMode.NORMAL

    def should_run_parallel_agents(self) -> bool:
        """
        Deberian los agentes ejecutarse en paralelo?

        Returns:
            True si paralelo, False si secuencial
        """
        mode = self._evaluate_cached()
        return self._should_run_parallel_agents(mode)

    def _should_run_parallel_agents(self, mode: PowerMode) -> bool:
        """Internal: decision based on pre-evaluated mode."""
        return mode != PowerMode.EMERGENCY

    def get_mcts_scale(self) -> float:
        """
        Factor de escala para simulaciones MCTS segun el modo.

        Returns:
            1.0 (normal), 0.5 (conservative), 0.25 (emergency)
        """
        mode = self._evaluate_cached()
        return self._get_mcts_scale(mode)

    def _get_mcts_scale(self, mode: PowerMode) -> float:
        """Internal: scale based on pre-evaluated mode."""
        scales = {
            PowerMode.NORMAL: 1.0,
            PowerMode.CONSERVATIVE: 0.5,
            PowerMode.EMERGENCY: 0.25,
        }
        return scales.get(mode, 1.0)

    def get_solver_timeout_scale(self) -> float:
        """
        Factor de escala para solver timeout segun el modo.

        Returns:
            1.0 (normal), 0.7 (conservative), 0.4 (emergency)
        """
        mode = self._evaluate_cached()
        return self._get_solver_timeout_scale(mode)

    def _get_solver_timeout_scale(self, mode: PowerMode) -> float:
        """Internal: scale based on pre-evaluated mode."""
        scales = {
            PowerMode.NORMAL: 1.0,
            PowerMode.CONSERVATIVE: 0.7,
            PowerMode.EMERGENCY: 0.4,
        }
        return scales.get(mode, 1.0)

    def should_postpone_non_critical(self) -> bool:
        """
        Deberian postponerse tareas no criticas (auto-scraping, indexing)?

        Returns:
            True si se debe postponer
        """
        mode = self._evaluate_cached()
        return self._should_postpone_non_critical(mode)

    def _should_postpone_non_critical(self, mode: PowerMode) -> bool:
        """Internal: decision based on pre-evaluated mode."""
        return mode != PowerMode.NORMAL

    def get_active_agents(self) -> list:
        """
        Lista de agentes que deberian estar activos segun el modo.

        En EMERGENCY, solo los agentes criticos del pipeline principal.
        """
        mode = self._evaluate_cached()
        return self._get_active_agents(mode)

    def _get_active_agents(self, mode: PowerMode) -> list:
        """Internal: agents based on pre-evaluated mode."""
        # All agents (normal mode)
        all_agents = [
            "INTENT", "DECOMPOSER", "EXTRACTOR",
            "ARCHITECT", "PLANNER", "RISK",
            "WRITER", "ASSEMBLER", "FORMATTER",
        ]

        # Critical agents only (emergency mode)
        critical_agents = [
            "INTENT", "EXTRACTOR", "WRITER", "FORMATTER",
        ]

        if mode == PowerMode.EMERGENCY:
            return critical_agents
        elif mode == PowerMode.CONSERVATIVE:
            # Skip RISK in conservative (it's optional)
            return [a for a in all_agents if a != "RISK"]
        else:
            return all_agents

    def get_execution_order(self, layer: int = 4) -> list:
        """
        Orden de ejecucion para una capa del DAG segun el modo.

        En NORMAL: todos en paralelo
        En CONSERVATIVE/EMERGENCY: uno a uno, ordenados por prioridad
        """
        mode = self._evaluate_cached()

        if mode == PowerMode.NORMAL:
            return ["parallel"]

        if layer == 4:
            # Capa 4: Architect -> Planner -> Risk (prioridad de seguridad)
            if mode == PowerMode.CONSERVATIVE:
                return ["ARCHITECT", "PLANNER"]  # Skip RISK
            else:  # EMERGENCY
                return ["ARCHITECT"]  # Solo lo esencial

        return ["sequential"]
