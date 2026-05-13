"""LowPowerSequentialMode main class combining all mixins."""

import time
from collections import deque
from typing import Optional, Dict, Any

from ._imports import logger, PowerMode, HardwareState
from .evaluate import EvaluateMixin
from .decision import DecisionMixin


class LowPowerSequentialMode(
    EvaluateMixin,
    DecisionMixin,
):
    """
    Evaluador de modo de energia que decide si la ejecucion
    debe ser paralela o secuencial basandose en el estado del hardware.

    Integrado con el DAGOrchestrator y el ResourceGovernor para
    tomar decisiones dinamicas durante la ejecucion del pipeline.
    """

    # Umbrales para cambiar de modo
    CPU_CONSERVATIVE_THRESHOLD = 0.65     # 65% CPU -> conservativo
    CPU_EMERGENCY_THRESHOLD = 0.85        # 85% CPU -> emergencia
    RAM_CONSERVATIVE_THRESHOLD = 0.70     # 70% RAM -> conservativo
    RAM_EMERGENCY_THRESHOLD = 0.90        # 90% RAM -> emergencia
    TEMP_CONSERVATIVE_THRESHOLD = 55.0    # 55C -> conservativo
    TEMP_EMERGENCY_THRESHOLD = 65.0       # 65C -> emergencia
    BATTERY_CONSERVATIVE_THRESHOLD = 30.0 # 30% bateria -> conservativo
    BATTERY_EMERGENCY_THRESHOLD = 15.0    # 15% bateria -> emergencia

    # Duracion minima en un modo antes de poder cambiar (evita flapping)
    MODE_STICKINESS_SECONDS = 30.0

    # Cache duration for evaluate() result (prevents 6x redundant calls in stats)
    _EVAL_CACHE_TTL = 5.0  # seconds

    def __init__(self, governor=None):
        self._governor = governor
        self._current_mode = PowerMode.NORMAL
        self._mode_since = time.time()
        self._history: deque = deque(maxlen=100)
        self._forced_mode: Optional[PowerMode] = None
        self._eval_cache_time = 0.0
        self._eval_cache_mode = PowerMode.NORMAL

    def set_governor(self, governor):
        """Conecta con el ResourceGovernor existente."""
        self._governor = governor

    def force_mode(self, mode: Optional[PowerMode]):
        """Fuerza un modo especifico (para testing o configuracion manual)."""
        self._forced_mode = mode
        if mode:
            self._current_mode = mode
            self._mode_since = time.time()
            self._eval_cache_time = 0.0  # Invalidate cache
            logger.info(f"LowPowerSequential: Forced mode to {mode.value}")

    @property
    def current_mode(self) -> PowerMode:
        """Modo actual sin re-evaluar."""
        return self._current_mode

    @property
    def hardware_state(self) -> HardwareState:
        """Estado actual del hardware."""
        return self._read_hardware_state()

    def _evaluate_cached(self) -> PowerMode:
        """Evaluate with short-lived cache to prevent redundant hardware reads."""
        now = time.time()
        if now - self._eval_cache_time < self._EVAL_CACHE_TTL:
            return self._eval_cache_mode
        mode = self.evaluate()
        self._eval_cache_time = now
        self._eval_cache_mode = mode
        return mode

    @property
    def stats(self) -> Dict[str, Any]:
        """Estadisticas del modo de energia."""
        hw = self._read_hardware_state()
        mode = self._evaluate_cached()
        return {
            "current_mode": mode.value,
            "cpu_usage": round(hw.cpu_usage * 100, 1),
            "ram_pct": round(hw.ram_pct, 1),
            "temperature_c": round(hw.temperature_c, 1),
            "battery_level": round(hw.battery_level, 1),
            "battery_charging": hw.battery_charging,
            "thermal_throttle": round(hw.thermal_throttle, 2),
            "parallel_layer4": self._should_run_parallel_layer4(mode),
            "parallel_agents": self._should_run_parallel_agents(mode),
            "mcts_scale": self._get_mcts_scale(mode),
            "solver_timeout_scale": self._get_solver_timeout_scale(mode),
            "active_agents": self._get_active_agents(mode),
            "postpone_non_critical": self._should_postpone_non_critical(mode),
            "history_entries": len(self._history),
            "forced_mode": self._forced_mode.value if self._forced_mode else None,
        }
