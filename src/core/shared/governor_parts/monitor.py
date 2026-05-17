"""Mixin: Background monitoring for ResourceGovernor."""

import time
import threading
import gc

from ._imports import logger, resource
import logging


class MonitorMixin:
    """Mixin providing background monitoring thread for CPU/RAM/thermal."""

    def start_monitoring(self):
        """Inicia el thread de monitoreo en background."""
        if self._monitor_thread and self._monitor_thread.is_alive():
            return
        self._stop_event.clear()
        self._cpu_lock = threading.Lock()
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop, daemon=True
        )
        self._monitor_thread.start()
        logger.info("ResourceGovernor: monitoring started")

    def stop_monitoring(self):
        """Detiene el thread de monitoreo."""
        self._stop_event.set()
        if self._monitor_thread:
            self._monitor_thread.join(timeout=2)
        logger.info("ResourceGovernor: monitoring stopped")

    def _monitor_loop(self):
        """Loop principal del monitor que corre en background."""
        while not self._stop_event.is_set():
            try:
                self._update_cpu_usage()
                self._update_ram_usage()
                self._check_thermal()
                self._auto_gc()
            except Exception as e:
                logger.debug("Monitor error: %s", e)

            self._stop_event.wait(timeout=self.DEFAULT_CPU_SAMPLE_INTERVAL)

    def _update_cpu_usage(self):
        """Estima el uso de CPU leyendo /proc/stat (Linux/proot).

        Uses self._stop_event.wait() instead of time.sleep() so the
        monitor thread can respond to stop_monitoring() immediately.
        """
        try:
            # Metodo 1: Leer /proc/stat (disponible en proot-distro Debian)
            with open('/proc/stat', 'r') as f:
                line = f.readline()
            values = [int(x) for x in line.split()[1:]]
            idle = values[3]
            total = sum(values)

            # Use stop_event.wait() instead of time.sleep() so we can
            # respond to stop_monitoring() without a 100ms delay.
            self._stop_event.wait(timeout=0.1)
            if self._stop_event.is_set():
                return  # Early exit if monitoring was stopped

            with open('/proc/stat', 'r') as f:
                line = f.readline()
            values2 = [int(x) for x in line.split()[1:]]
            idle2 = values2[3]
            total2 = sum(values2)

            delta_idle = idle2 - idle
            delta_total = total2 - total
            if delta_total > 0:
                with self._cpu_lock:
                    self._cpu_usage = 1.0 - (delta_idle / delta_total)
        except (FileNotFoundError, PermissionError, ValueError):
            # Fallback: estimar basado en tiempo de proceso
            if resource is not None:
                try:
                    usage = resource.getrusage(resource.RUSAGE_SELF)
                    user_time = usage.ru_utime
                    wall_time = time.time() - self._last_cpu_check
                    if wall_time > 0:
                        with self._cpu_lock:
                            self._cpu_usage = min(user_time / wall_time, 1.0)
                    self._last_cpu_check = time.time()
                except Exception as e:
                    with self._cpu_lock:
                        self._cpu_usage = 0.3  # Asumir uso moderado
                    logger.debug("ResourceGovernor: CPU usage estimation failed: %s", e)
            else:
                with self._cpu_lock:
                    self._cpu_usage = 0.3  # resource module unavailable

    def _update_ram_usage(self):
        """Mide el uso de RAM del proceso actual."""
        try:
            # Metodo 1: /proc/self/status (mas preciso en Linux)
            with open('/proc/self/status', 'r') as f:
                for line in f:
                    if line.startswith('VmRSS:'):
                        self._ram_usage_mb = int(line.split()[1]) / 1024
                        break
        except (FileNotFoundError, PermissionError):
            # Fallback: resource module
            if resource is not None:
                try:
                    usage = resource.getrusage(resource.RUSAGE_SELF)
                    # ru_maxrss es en KB en Linux
                    self._ram_usage_mb = usage.ru_maxrss / 1024
                except Exception:
                    self._ram_usage_mb = 0
            else:
                self._ram_usage_mb = 0  # resource module unavailable

    def _check_thermal(self):
        """Verifica si hay riesgo de throttling termico y reduce agresividad."""
        if self._cpu_usage > 0.7:
            if self._high_cpu_start is None:
                self._high_cpu_start = time.time()
            else:
                elapsed = time.time() - self._high_cpu_start
                if elapsed > self.THERMAL_SCALE_BACK_THRESHOLD:
                    # Reducir agresividad al 60%
                    self._thermal_throttle = max(0.4, self._thermal_throttle * 0.8)
                    self.stats["thermal_throttles"] += 1
                    logger.warning(
                        "Thermal throttle: CPU >70%% por %.0fs, "
                        "reduciendo agresividad a %.0f%%",
                        elapsed, self._thermal_throttle * 100
                    )
        else:
            # CPU normal: restaurar gradualmente
            if self._high_cpu_start is not None:
                self._high_cpu_start = None
            self._thermal_throttle = min(1.0, self._thermal_throttle * 1.05)

    def _auto_gc(self):
        """Fuerza garbage collection si la RAM se acerca al limite.

        FIX (v18.1): Only run gc.collect(0) (gen-0, lightweight) in the
        background monitor. Full gc.collect(2) can crash llama-cpp-python's
        C extension on ARM/Termux when it finalizes Python wrappers around
        native model state. We only do gen-0 collection which is safe and
        fast. Full GC is reserved for explicit unload_model() scenarios
        where the model is already freed.
        """
        if self._ram_usage_mb > self.gc_threshold_mb:
            try:
                collected = gc.collect(0)  # Gen-0 only (safe with C extensions)
                self._gc_count += 1
                self.stats["gc_forced"] += 1
                logger.info(
                    "Auto-GC: RAM=%.0fMB > threshold=%.0fMB, gen-0 collected %d objects",
                    self._ram_usage_mb, self.gc_threshold_mb, collected
                )
            except Exception as e:
                logger.debug("Auto-GC error (non-critical): %s", e)
