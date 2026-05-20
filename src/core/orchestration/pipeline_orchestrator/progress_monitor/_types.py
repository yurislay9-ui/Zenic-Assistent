"""Types and constants for progress_monitor."""

from __future__ import annotations
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

class ProgressStatus(str, Enum):
    """Status of progress monitoring."""
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"



@dataclass
class ProgressSnapshot:
    """
    A point-in-time snapshot of pipeline progress.

    Attributes:
        pipeline_id: The pipeline being monitored.
        total_steps: Total number of steps.
        completed_steps: Number of completed steps.
        failed_steps: Number of failed steps.
        skipped_steps: Number of skipped steps.
        progress_pct: Progress as a percentage (0-100).
        elapsed_ms: Elapsed time in milliseconds.
        estimated_remaining_ms: Estimated remaining time in milliseconds.
        current_step: Currently executing step ID.
        status: Current monitoring status.
        step_details: Per-step progress details.
        timestamp: Snapshot timestamp.
    """
    pipeline_id: str = ""
    total_steps: int = 0
    completed_steps: int = 0
    failed_steps: int = 0
    skipped_steps: int = 0
    progress_pct: float = 0.0
    elapsed_ms: float = 0.0
    estimated_remaining_ms: Optional[float] = None
    current_step: str = ""
    status: ProgressStatus = ProgressStatus.IDLE
    step_details: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)



class ProgressMonitor:
    """
    Pipeline progress monitoring and reporting.

    Supports:
    - Real-time step-level progress tracking
    - ETA estimation based on average step duration
    - Progress callbacks for UI updates
    - Progress history for analytics
    - Step weight-based progress (vs simple count-based)

    Usage::

        monitor = ProgressMonitor()
        monitor.start_pipeline("pipe-1", total_steps=3)

        monitor.start_step("pipe-1", "extract")
        monitor.complete_step("pipe-1", "extract")

        snapshot = monitor.get_progress("pipe-1")
        # snapshot.progress_pct == 33.3

    Thread Safety:
        This class is NOT thread-safe. External synchronization is required.
    """

    def __init__(
        self,
        history_limit: int = 100,
        callback: Optional[Callable[[ProgressSnapshot], None]] = None,
    ) -> None:
        """
        Initialize the ProgressMonitor.

        Args:
            history_limit: Maximum number of progress snapshots to retain.
            callback: Optional callback invoked on every progress update.
        """
        self._pipelines: Dict[str, _PipelineProgress] = {}
        self._history: Dict[str, List[ProgressSnapshot]] = {}
        self._history_limit = history_limit
        self._callback = callback

    # ── Pipeline Lifecycle ───────────────────────────────────

    def start_pipeline(
        self,
        pipeline_id: str,
        total_steps: int = 0,
        step_weights: Optional[Dict[str, float]] = None,
    ) -> None:
        """
        Start monitoring a pipeline.

        Args:
            pipeline_id: The pipeline to monitor.
            total_steps: Expected total number of steps.
            step_weights: Optional weight per step (for weighted progress).
        """
        self._pipelines[pipeline_id] = _PipelineProgress(
            pipeline_id=pipeline_id,
            total_steps=total_steps,
            step_weights=step_weights or {},
            started_at=time.monotonic(),
        )
        self._history[pipeline_id] = []
        logger.debug(
            "ProgressMonitor: Started monitoring pipeline '%s' (%d steps)",
            pipeline_id, total_steps,
        )
        self._notify(pipeline_id)

    def finish_pipeline(
        self,
        pipeline_id: str,
        status: ProgressStatus = ProgressStatus.COMPLETED,
    ) -> None:
        """
        Mark a pipeline as finished.

        Args:
            pipeline_id: The pipeline to finish.
            status: The final status.
        """
        pp = self._pipelines.get(pipeline_id)
        if pp is not None:
            pp.status = status
            pp.finished_at = time.monotonic()
            logger.debug(
                "ProgressMonitor: Pipeline '%s' finished with status '%s'",
                pipeline_id, status.value,
            )
            self._notify(pipeline_id)

    def remove_pipeline(self, pipeline_id: str) -> None:
        """Remove a pipeline from monitoring."""
        self._pipelines.pop(pipeline_id, None)
        self._history.pop(pipeline_id, None)

    # ── Step Progress ────────────────────────────────────────

    def start_step(self, pipeline_id: str, step_id: str) -> None:
        """
        Mark a step as started.

        Args:
            pipeline_id: The pipeline containing the step.
            step_id: The step that started.
        """
        pp = self._pipelines.get(pipeline_id)
        if pp is None:
            logger.warning("ProgressMonitor: Unknown pipeline '%s'", pipeline_id)
            return
        pp.current_step = step_id
        pp.step_states[step_id] = _StepProgress(
            step_id=step_id,
            status="running",
            started_at=time.monotonic(),
        )
        self._notify(pipeline_id)

    def complete_step(self, pipeline_id: str, step_id: str) -> None:
        """
        Mark a step as completed.

        Args:
            pipeline_id: The pipeline containing the step.
            step_id: The step that completed.
        """
        pp = self._pipelines.get(pipeline_id)
        if pp is None:
            return
        sp = pp.step_states.get(step_id)
        if sp is not None:
            sp.status = "completed"
            sp.finished_at = time.monotonic()
            if sp.started_at is not None:
                sp.duration_ms = (sp.finished_at - sp.started_at) * 1000
        pp.completed_steps += 1
        if pp.current_step == step_id:
            pp.current_step = ""
        self._notify(pipeline_id)

    def fail_step(self, pipeline_id: str, step_id: str, error: str = "") -> None:
        """
        Mark a step as failed.

        Args:
            pipeline_id: The pipeline containing the step.
            step_id: The step that failed.
            error: Optional error description.
        """
        pp = self._pipelines.get(pipeline_id)
        if pp is None:
            return
        sp = pp.step_states.get(step_id)
        if sp is not None:
            sp.status = "failed"
            sp.finished_at = time.monotonic()
            sp.error = error
            if sp.started_at is not None:
                sp.duration_ms = (sp.finished_at - sp.started_at) * 1000
        pp.failed_steps += 1
        if pp.current_step == step_id:
            pp.current_step = ""
        self._notify(pipeline_id)

    def skip_step(self, pipeline_id: str, step_id: str) -> None:
        """
        Mark a step as skipped.

        Args:
            pipeline_id: The pipeline containing the step.
            step_id: The step that was skipped.
        """
        pp = self._pipelines.get(pipeline_id)
        if pp is None:
            return
        sp = pp.step_states.get(step_id)
        if sp is not None:
            sp.status = "skipped"
        pp.skipped_steps += 1
        if pp.current_step == step_id:
            pp.current_step = ""
        self._notify(pipeline_id)

    # ── Progress Queries ─────────────────────────────────────

    def get_progress(self, pipeline_id: str) -> ProgressSnapshot:
        """
        Get a progress snapshot for a pipeline.

        Args:
            pipeline_id: The pipeline to query.

        Returns:
            ProgressSnapshot with current state.
        """
        pp = self._pipelines.get(pipeline_id)
        if pp is None:
            return ProgressSnapshot(pipeline_id=pipeline_id)

        elapsed = (time.monotonic() - pp.started_at) * 1000 if pp.started_at else 0.0
        progress_pct = self._compute_progress(pp)
        eta = self._estimate_remaining(pp, elapsed, progress_pct)

        step_details: Dict[str, Dict[str, Any]] = {}
        for sid, sp in pp.step_states.items():
            step_details[sid] = {
                "status": sp.status,
                "duration_ms": sp.duration_ms,
                "error": sp.error,
            }

        return ProgressSnapshot(
            pipeline_id=pipeline_id,
            total_steps=pp.total_steps,
            completed_steps=pp.completed_steps,
            failed_steps=pp.failed_steps,
            skipped_steps=pp.skipped_steps,
            progress_pct=progress_pct,
            elapsed_ms=elapsed,
            estimated_remaining_ms=eta,
            current_step=pp.current_step,
            status=pp.status,
            step_details=step_details,
        )

    def get_history(self, pipeline_id: str) -> List[ProgressSnapshot]:
        """Get progress history for a pipeline."""
        return list(self._history.get(pipeline_id, []))

    # ── Internal ─────────────────────────────────────────────

    def _compute_progress(self, pp: _PipelineProgress) -> float:
        """Compute progress percentage (0-100)."""
        if pp.total_steps <= 0:
            return 0.0

        if pp.step_weights:
            total_weight = sum(pp.step_weights.values())
            if total_weight <= 0:
                return 0.0
            completed_weight = sum(
                pp.step_weights.get(sid, 0.0)
                for sid, sp in pp.step_states.items()
                if sp.status in ("completed", "skipped")
            )
            return min((completed_weight / total_weight) * 100, 100.0)
        else:
            done = pp.completed_steps + pp.skipped_steps
            return min((done / pp.total_steps) * 100, 100.0)

    def _estimate_remaining(
        self,
        pp: _PipelineProgress,
        elapsed_ms: float,
        progress_pct: float,
    ) -> Optional[float]:
        """Estimate remaining time based on progress rate."""
        if progress_pct <= 0 or progress_pct >= 100:
            return None
        rate = progress_pct / elapsed_ms if elapsed_ms > 0 else 0
        if rate <= 0:
            return None
        remaining_pct = 100.0 - progress_pct
        return remaining_pct / rate

    def _notify(self, pipeline_id: str) -> None:
        """Invoke callback and record history."""
        snapshot = self.get_progress(pipeline_id)

        # Record history
        history = self._history.setdefault(pipeline_id, [])
        history.append(snapshot)
        while len(history) > self._history_limit:
            history.pop(0)

        # Invoke callback
        if self._callback is not None:
            try:
                self._callback(snapshot)
            except Exception as exc:
                logger.error("ProgressMonitor: Callback error: %s", exc)

    # ── Accessors ────────────────────────────────────────────

    @property
    def monitored_pipelines(self) -> List[str]:
        """List of pipeline IDs being monitored."""
        return list(self._pipelines.keys())

    @property
    def stats(self) -> Dict[str, Any]:
        """Runtime statistics."""
        return {
            "monitored_count": len(self._pipelines),
            "history_entries": sum(len(h) for h in self._history.values()),
        }

    def clear(self) -> None:
        """Clear all monitoring state."""
        self._pipelines.clear()
        self._history.clear()


# ──────────────────────────────────────────────────────────────
#  INTERNAL: Pipeline & Step Progress
# ──────────────────────────────────────────────────────────────


class _StepProgress:
    """Internal step progress tracker."""

    __slots__ = ("step_id", "status", "started_at", "finished_at", "duration_ms", "error")

    def __init__(
        self,
        step_id: str,
        status: str = "pending",
        started_at: Optional[float] = None,
        finished_at: Optional[float] = None,
        duration_ms: float = 0.0,
        error: str = "",
    ) -> None:
        self.step_id = step_id
        self.status = status
        self.started_at = started_at
        self.finished_at = finished_at
        self.duration_ms = duration_ms
        self.error = error


