"""Mixin: Hardware evaluation for LowPowerSequentialMode."""

import os
import time

from ._imports import logger, PowerMode, HardwareState
import logging


class EvaluateMixin:
    """Mixin providing hardware evaluation and mode determination."""

    def evaluate(self) -> PowerMode:
        """
        Evalua el estado actual del hardware y determina el modo optimo.

        Returns:
            PowerMode actual despues de la evaluacion
        """
        # If forced mode, use it
        if self._forced_mode:
            self._current_mode = self._forced_mode
            return self._current_mode

        # Read hardware state
        hw = self._read_hardware_state()

        # Calculate scores for each mode
        emergency_score = 0
        conservative_score = 0

        # CPU
        if hw.cpu_usage > self.CPU_EMERGENCY_THRESHOLD:
            emergency_score += 3
        elif hw.cpu_usage > self.CPU_CONSERVATIVE_THRESHOLD:
            conservative_score += 2

        # RAM
        if hw.ram_pct > self.RAM_EMERGENCY_THRESHOLD * 100:
            emergency_score += 3
        elif hw.ram_pct > self.RAM_CONSERVATIVE_THRESHOLD * 100:
            conservative_score += 2

        # Temperature
        if hw.temperature_c > self.TEMP_EMERGENCY_THRESHOLD:
            emergency_score += 3
        elif hw.temperature_c > self.TEMP_CONSERVATIVE_THRESHOLD:
            conservative_score += 2

        # Battery (only if not charging)
        if not hw.battery_charging:
            if hw.battery_level < self.BATTERY_EMERGENCY_THRESHOLD:
                emergency_score += 2
            elif hw.battery_level < self.BATTERY_CONSERVATIVE_THRESHOLD:
                conservative_score += 2

        # Thermal throttle
        if hw.thermal_throttle < 0.5:
            emergency_score += 2
        elif hw.thermal_throttle < 0.8:
            conservative_score += 1

        # Determine mode
        if emergency_score >= 4:
            new_mode = PowerMode.EMERGENCY
        elif emergency_score >= 2 or conservative_score >= 3:
            new_mode = PowerMode.CONSERVATIVE
        else:
            new_mode = PowerMode.NORMAL

        # Apply stickiness (don't change mode too quickly)
        time_in_mode = time.time() - self._mode_since
        if new_mode != self._current_mode:
            if time_in_mode < self.MODE_STICKINESS_SECONDS:
                # Block downgrade during stickiness, but always allow upgrade to more restrictive mode
                if self._mode_rank(new_mode) < self._mode_rank(self._current_mode):
                    new_mode = self._current_mode  # Stay in current (more restrictive) mode
            else:
                self._mode_since = time.time()

        # Log mode changes
        if new_mode != self._current_mode:
            logger.warning(
                f"LowPowerSequential: Mode change {self._current_mode.value} -> {new_mode.value} "
                f"(CPU={hw.cpu_usage:.0%}, RAM={hw.ram_pct:.0f}%, Temp={hw.temperature_c:.0f}C, "
                f"Battery={hw.battery_level:.0f}%)"
            )

        self._current_mode = new_mode

        # Record in history
        self._history.append({
            "timestamp": time.time(),
            "mode": new_mode.value,
            "cpu": hw.cpu_usage,
            "ram_pct": hw.ram_pct,
            "temp": hw.temperature_c,
            "battery": hw.battery_level,
        })

        return self._current_mode

    def _read_hardware_state(self) -> HardwareState:
        """Lee el estado actual del hardware."""
        hw = HardwareState()

        # From governor if available — use public API when possible
        if self._governor:
            # Use _get_cpu_usage() if available (thread-safe), fallback to direct attr
            if hasattr(self._governor, '_get_cpu_usage'):
                hw.cpu_usage = self._governor._get_cpu_usage()
            else:
                hw.cpu_usage = getattr(self._governor, '_cpu_usage', 0.0)
            hw.ram_usage_mb = getattr(self._governor, '_ram_usage_mb', 0.0)
            hw.ram_limit_mb = getattr(self._governor, 'ram_limit_mb', 4096)
            hw.thermal_throttle = getattr(self._governor, '_thermal_throttle', 1.0)

        # Read temperature from thermal zone (Android/Linux)
        hw.temperature_c = self._read_temperature()

        # Read battery level (Android)
        hw.battery_level, hw.battery_charging = self._read_battery()

        return hw

    def _read_temperature(self) -> float:
        """Lee la temperatura del CPU desde /sys/class/thermal/."""
        # Try common thermal zones
        thermal_paths = [
            "/sys/class/thermal/thermal_zone0/temp",  # Generic
            "/sys/class/thermal/thermal_zone1/temp",  # CPU
            "/sys/class/thermal/thermal_zone2/temp",  # GPU
            "/sys/class/hwmon/hwmon0/temp1_input",    # hwmon
        ]

        for path in thermal_paths:
            try:
                with open(path, "r") as f:
                    raw = int(f.read().strip())
                    # Some report in millidegrees, some in degrees
                    if raw > 1000:
                        return raw / 1000.0
                    return float(raw)
            except (FileNotFoundError, PermissionError, ValueError):
                continue

        # Fallback: estimate from CPU usage and thermal throttle
        if self._governor:
            cpu = getattr(self._governor, '_cpu_usage', 0.3)
            throttle = getattr(self._governor, '_thermal_throttle', 1.0)
            # Rough estimate: idle=38C, 100% CPU=70C, throttle reduces
            estimated = 38 + (cpu * 35) * throttle
            return estimated

        return 45.0  # Safe default

    def _read_battery(self) -> tuple:
        """Lee el nivel de bateria (Android/Termux)."""
        battery_path = "/sys/class/power_supply/battery"

        level = 100.0
        charging = True

        try:
            # Battery level
            cap_path = os.path.join(battery_path, "capacity")
            if os.path.isfile(cap_path):
                with open(cap_path, "r") as f:
                    level = float(f.read().strip())

            # Charging status
            status_path = os.path.join(battery_path, "status")
            if os.path.isfile(status_path):
                with open(status_path, "r") as f:
                    status = f.read().strip().lower()
                    charging = status in ("charging", "full")

        except (FileNotFoundError, PermissionError, ValueError):
            pass

        return level, charging

    @staticmethod
    def _mode_rank(mode: PowerMode) -> int:
        """Ranking de severidad de modos (mayor = mas restrictivo)."""
        return {
            PowerMode.NORMAL: 0,
            PowerMode.CONSERVATIVE: 1,
            PowerMode.EMERGENCY: 2,
        }.get(mode, 0)
