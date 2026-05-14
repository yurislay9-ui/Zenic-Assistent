"""
Zenic-Agents Asistente - SNA Scheduler

Priority-based async scheduler for SNA monitors.
Supports configurable intervals, priority queues, and
AlarmManager integration for Android/Termux wake-up.
"""

from __future__ import annotations

import asyncio
import heapq
import logging
import os
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from .types import (
    MonitorConfig, MonitorWeight, SchedulerState,
    DEFAULT_INTERVALS, SNAStats,
)

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
#  SCHEDULER ENTRY (for priority queue)
# ──────────────────────────────────────────────────────────────

class _ScheduleEntry:
    """Internal priority queue entry for a scheduled monitor check."""

    __slots__ = ("next_run", "priority", "monitor_id", "entry_id")

    def __init__(self, next_run: float, priority: int,
                 monitor_id: str, entry_id: int = 0) -> None:
        self.next_run = next_run
        self.priority = priority
        self.monitor_id = monitor_id
        self.entry_id = entry_id  # Tiebreaker for heap

    def __lt__(self, other: "_ScheduleEntry") -> bool:
        if self.next_run != other.next_run:
            return self.next_run < other.next_run
        if self.priority != other.priority:
            return self.priority < other.priority
        return self.entry_id < other.entry_id


# ──────────────────────────────────────────────────────────────
#  ALARM MANAGER (Android/Termux)
# ──────────────────────────────────────────────────────────────

class AlarmManager:
    """Manages Android/Termux alarm wake-ups for the SNA scheduler.

    When running on Termux, the system can suspend the process to
    save battery. This uses Termux:Boot's alarm mechanism to wake
    the system for critical monitor checks.

    Falls back to a no-op when not on Android/Termux.
    """

    def __init__(self) -> None:
        self._is_termux = self._detect_termux()
        self._alarms_set: Dict[str, float] = {}

    def _detect_termux(self) -> bool:
        """Detect if running on Termux/Android."""
        return (
            "TERMUX_VERSION" in os.environ
            or "ANDROID_ARGUMENT" in os.environ
            or os.path.exists("/data/data/com.termux")
        )

    def set_alarm(self, monitor_id: str, delay_seconds: float) -> None:
        """Schedule a wake-up alarm via Termux API.

        Uses `termux-notification --alarm` if available.
        """
        if not self._is_termux:
            return

        wake_time = time.time() + delay_seconds
        self._alarms_set[monitor_id] = wake_time

        try:
            import subprocess
            alarm_time_str = time.strftime(
                "%H:%M", time.localtime(wake_time),
            )
            subprocess.Popen(
                [
                    "termux-notification",
                    "--title", f"SNA: {monitor_id}",
                    "--content", f"Monitor check at {alarm_time_str}",
                    "--alarm",
                    "--time", str(int(delay_seconds)),
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            logger.debug(
                "AlarmManager: Set alarm for %s in %ds",
                monitor_id, delay_seconds,
            )
        except FileNotFoundError:
            logger.debug("AlarmManager: termux-api not available")
        except Exception as e:
            logger.debug("AlarmManager: Alarm set failed: %s", e)

    def cancel_alarm(self, monitor_id: str) -> None:
        """Cancel a scheduled alarm."""
        self._alarms_set.pop(monitor_id, None)

    @property
    def active_alarms(self) -> int:
        """Number of currently scheduled alarms."""
        now = time.time()
        return sum(1 for t in self._alarms_set.values() if t > now)


# ──────────────────────────────────────────────────────────────
#  SNA SCHEDULER
# ──────────────────────────────────────────────────────────────

class SNAScheduler:
    """Priority-based async scheduler for SNA monitors.

    Features:
      - Priority queue: critical monitors run first
      - Configurable intervals per monitor weight
      - AlarmManager integration for Android/Termux
      - Dynamic add/remove of monitors
      - Graceful start/stop with cleanup
      - Statistics tracking
    """

    def __init__(self) -> None:
        self._monitors: Dict[str, MonitorConfig] = {}
        self._queue: List[_ScheduleEntry] = []
        self._entry_counter: int = 0
        self._state: SchedulerState = SchedulerState.STOPPED
        self._alarm_mgr = AlarmManager()
        self._task: Optional[asyncio.Task] = None
        self._check_callback: Optional[Callable] = None
        self._start_time: float = 0.0
        self._stats = {
            "checks_scheduled": 0,
            "checks_completed": 0,
            "checks_failed": 0,
        }

    # ── Configuration ──────────────────────────────────────

    def set_check_callback(self, callback: Callable) -> None:
        """Set the callback invoked for each monitor check.

        Callback signature: async callback(monitor_config: MonitorConfig) -> None
        """
        self._check_callback = callback

    def add_monitor(self, config: MonitorConfig) -> None:
        """Add or update a monitor in the schedule."""
        if not config.enabled:
            return
        self._monitors[config.monitor_id] = config
        self._schedule_next(config)
        logger.info(
            "SNAScheduler: Added monitor %s (interval=%0.0fs, priority=%d)",
            config.monitor_id, config.effective_interval, config.priority,
        )

    def remove_monitor(self, monitor_id: str) -> None:
        """Remove a monitor from the schedule."""
        self._monitors.pop(monitor_id, None)
        self._alarm_mgr.cancel_alarm(monitor_id)
        # Rebuild queue without this monitor
        self._rebuild_queue()
        logger.info("SNAScheduler: Removed monitor %s", monitor_id)

    def enable_monitor(self, monitor_id: str) -> None:
        """Enable a previously disabled monitor."""
        config = self._monitors.get(monitor_id)
        if config:
            config.enabled = True
            self._schedule_next(config)

    def disable_monitor(self, monitor_id: str) -> None:
        """Disable a monitor without removing it."""
        config = self._monitors.get(monitor_id)
        if config:
            config.enabled = False
            self._alarm_mgr.cancel_alarm(monitor_id)
            self._rebuild_queue()

    def get_monitors(self) -> Dict[str, MonitorConfig]:
        """Get all registered monitor configurations."""
        return dict(self._monitors)

    # ── Lifecycle ──────────────────────────────────────────

    async def start(self) -> None:
        """Start the scheduler loop."""
        if self._state == SchedulerState.RUNNING:
            return
        self._state = SchedulerState.RUNNING
        self._start_time = time.time()
        self._task = asyncio.create_task(self._run_loop())
        logger.info(
            "SNAScheduler: Started with %d monitors", len(self._monitors),
        )

    async def stop(self) -> None:
        """Stop the scheduler gracefully."""
        self._state = SchedulerState.STOPPED
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        logger.info("SNAScheduler: Stopped")

    async def pause(self) -> None:
        """Pause the scheduler (keeps monitors, stops checks)."""
        self._state = SchedulerState.PAUSED
        logger.info("SNAScheduler: Paused")

    async def resume(self) -> None:
        """Resume the scheduler from paused state."""
        if self._state == SchedulerState.PAUSED:
            self._state = SchedulerState.RUNNING
            self._task = asyncio.create_task(self._run_loop())
            logger.info("SNAScheduler: Resumed")

    # ── Scheduler Loop ─────────────────────────────────────

    async def _run_loop(self) -> None:
        """Main scheduler loop that dispatches monitor checks."""
        while self._state == SchedulerState.RUNNING:
            try:
                if not self._queue:
                    await asyncio.sleep(1.0)
                    continue

                # Peek at the next entry
                entry = self._queue[0]
                now = time.time()
                delay = entry.next_run - now

                if delay > 0:
                    # Wait until next check (max 1s to allow new entries)
                    await asyncio.sleep(min(delay, 1.0))
                    continue

                # Pop the entry
                heapq.heappop(self._queue)

                config = self._monitors.get(entry.monitor_id)
                if config is None or not config.enabled:
                    continue

                # Execute the check via callback
                self._stats["checks_scheduled"] += 1
                if self._check_callback:
                    try:
                        await self._check_callback(config)
                        self._stats["checks_completed"] += 1
                    except Exception as e:
                        self._stats["checks_failed"] += 1
                        logger.error(
                            "SNAScheduler: Check callback failed for %s: %s",
                            entry.monitor_id, e,
                        )

                # Schedule next check
                self._schedule_next(config)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("SNAScheduler: Loop error: %s", e)
                await asyncio.sleep(5.0)

    # ── Queue Management ───────────────────────────────────

    def _schedule_next(self, config: MonitorConfig) -> None:
        """Schedule the next check for a monitor."""
        interval = config.effective_interval
        next_run = time.time() + interval
        self._entry_counter += 1
        entry = _ScheduleEntry(
            next_run=next_run,
            priority=config.priority,
            monitor_id=config.monitor_id,
            entry_id=self._entry_counter,
        )
        heapq.heappush(self._queue, entry)

        # Set Android alarm for critical monitors
        if config.priority <= 1:
            self._alarm_mgr.set_alarm(config.monitor_id, interval)

    def _rebuild_queue(self) -> None:
        """Rebuild the priority queue (after monitor removal)."""
        active_ids = set(self._monitors.keys())
        self._queue = [
            e for e in self._queue if e.monitor_id in active_ids
        ]
        heapq.heapify(self._queue)

    # ── Statistics ─────────────────────────────────────────

    @property
    def state(self) -> SchedulerState:
        """Get current scheduler state."""
        return self._state

    @property
    def stats(self) -> Dict[str, Any]:
        """Get scheduler statistics."""
        uptime = (time.time() - self._start_time) if self._start_time else 0
        return {
            **self._stats,
            "state": self._state.value,
            "active_monitors": len(self._monitors),
            "queue_size": len(self._queue),
            "uptime_seconds": round(uptime, 1),
            "alarm_manager_alarms": self._alarm_mgr.active_alarms,
        }
