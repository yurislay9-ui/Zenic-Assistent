"""Mixin: Public API methods for ResourceGovernor."""

import gc
import time

from ._imports import logger
import logging


class APIMixin:
    """Mixin providing public API for resource control."""

    def cpu_throttle_sleep(self) -> None:
        """
        Duerme un poco entre operaciones pesadas para evitar
        que la CPU se pegue al 100%% y el telefono se caliente.

        El sleep es adaptativo: si la CPU esta alta, duerme mas.
        """
        cpu_usage = self._get_cpu_usage()
        if cpu_usage > 0.8:
            sleep_ms = self.DEFAULT_CPU_SLEEP_MS * 3  # 150ms
        elif cpu_usage > 0.6:
            sleep_ms = self.DEFAULT_CPU_SLEEP_MS * 2  # 100ms
        else:
            sleep_ms = self.DEFAULT_CPU_SLEEP_MS       # 50ms

        # Aplicar throttle termico
        sleep_ms = int(sleep_ms / self._thermal_throttle)

        time.sleep(sleep_ms / 1000.0)

    def _get_cpu_usage(self) -> float:
        """Thread-safe read of CPU usage."""
        cpu_lock = getattr(self, '_cpu_lock', None)
        if cpu_lock:
            with cpu_lock:
                return self._cpu_usage
        return self._cpu_usage

    def get_adaptive_mcts_simulations(self, base_simulations: int = 100) -> int:
        """
        Ajusta las simulaciones MCTS segun la carga del sistema.

        Si el telefono esta tranquilo: 100 simulaciones (max)
        Si la CPU esta alta: reduce proporcionalmente
        Si hay throttle termico: reduce aun mas
        """
        cpu_usage = self._get_cpu_usage()
        if cpu_usage > 0.8:
            scale = 0.3
        elif cpu_usage > 0.6:
            scale = 0.5
        elif cpu_usage > 0.4:
            scale = 0.7
        else:
            scale = 1.0

        # Aplicar throttle termico
        scale *= self._thermal_throttle

        # Nunca menos de 10 simulaciones
        adaptive = max(10, int(base_simulations * scale))

        if adaptive < base_simulations:
            logger.info(
                "MCTS adaptive: %d -> %d sims (CPU=%.0f%%, throttle=%.0f%%)",
                base_simulations, adaptive,
                cpu_usage * 100, self._thermal_throttle * 100
            )

        return adaptive

    def get_adaptive_solver_timeout(self, base_timeout_ms: int = 15000) -> int:
        """
        Ajusta el timeout del solver segun recursos disponibles.

        Si hay poca RAM: reduce timeout (evitar que Z3 consuma mas)
        Si hay throttle termico: reduce timeout
        Si el sistema esta tranquilo: timeout completo
        """
        scale = self._thermal_throttle

        if self._ram_usage_mb > self.ram_limit_mb * 0.8:
            scale *= 0.6  # Reducir mucho si RAM casi al limite
        elif self._ram_usage_mb > self.ram_limit_mb * 0.5:
            scale *= 0.8

        adaptive = max(3000, int(base_timeout_ms * scale))
        return adaptive

    def pre_request(self) -> None:
        """Llama antes de cada request para preparar el sistema."""
        with self._request_count_lock:
            self._request_count += 1
        self.stats["requests_served"] += 1

        # No GC before requests — let Python's automatic GC handle it.
        # Forced GC with llama-cpp-python loaded can trigger C extension
        # crashes (segfault) on ARM/Termux during object finalization.
        # The background monitor's _auto_gc() handles periodic cleanup.

    def post_request(self) -> None:
        """Llama despues de cada request para limpiar.

        FIX (v18.1): Removed aggressive gc.collect() calls here.
        Calling gc.collect() after every request was causing crashes
        in llama-cpp-python's C code on ARM/Termux. The C extension
        has internal state that can be corrupted when Python's GC
        finalizes objects while the model is loaded.

        The background monitor's _auto_gc() method handles periodic
        GC when RAM is high, which is sufficient for memory management.
        """
        # Update RAM measurement (non-destructive, no GC)
        self._update_ram_usage()

    def get_z3_memory_limit_mb(self) -> int:
        """
        Limite de memoria para Z3 solver.
        Z3 puede consumir muchisima RAM. Lo limitamos a 512MB
        en el telefono para dejar espacio al resto.
        """
        available = self.ram_limit_mb - self._ram_usage_mb
        # Max 512MB para Z3, o lo que quede menos 256MB
        return max(128, min(512, int(available - 256)))

    def is_ram_critical(self) -> bool:
        """Retorna True si la RAM esta al limite y hay que rechazar requests."""
        return self._ram_usage_mb > self.ram_limit_mb * 0.95
