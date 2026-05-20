"""Core logic for state_tracker."""

from __future__ import annotations
import copy
import logging
import time
import uuid
from typing import Any, Dict, List, Optional

from ._types import PipelineStatus, StepExecutionStatus, StepState, PipelineState

logger = logging.getLogger(__name__)


class StateTracker:
    """
    Pipeline state tracking and persistence.

    Supports:
    - Creating and managing pipeline state
    - Step-level state transitions
    - State snapshots for checkpointing
    - State queries and filtering

    Usage::

        tracker = StateTracker()
        pipeline = tracker.create_pipeline("my-pipeline")

        tracker.add_step(pipeline.pipeline_id, "extract", name="Extract Data")
        tracker.update_step_status(pipeline.pipeline_id, "extract", StepExecutionStatus.RUNNING)
        tracker.update_step_status(pipeline.pipeline_id, "extract", StepExecutionStatus.COMPLETED)

        snapshot = tracker.snapshot(pipeline.pipeline_id)

    Thread Safety:
        This class is NOT thread-safe. External synchronization is required.
    """

    def __init__(self, max_history: int = 100) -> None:
        """
        Initialize the StateTracker.

        Args:
            max_history: Maximum number of state snapshots to retain.
        """
        self._pipelines: Dict[str, PipelineState] = {}
        self._snapshots: Dict[str, List[PipelineState]] = {}
        self._max_history = max_history

    # ── Pipeline Management ──────────────────────────────────

    def create_pipeline(
        self,
        name: str = "",
        pipeline_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> PipelineState:
        """
        Create a new pipeline state.

        Args:
            name: Human-readable pipeline name.
            pipeline_id: Optional explicit ID (auto-generated if omitted).
            metadata: Additional metadata.

        Returns:
            The created PipelineState.
        """
        state = PipelineState(
            pipeline_id=pipeline_id or f"pipe-{uuid.uuid4().hex[:8]}",
            name=name,
            metadata=metadata or {},
        )
        self._pipelines[state.pipeline_id] = state
        self._snapshots[state.pipeline_id] = []
        logger.debug(
            "StateTracker: Created pipeline '%s' (id=%s)",
            name, state.pipeline_id,
        )
        return state

    def get_pipeline(self, pipeline_id: str) -> Optional[PipelineState]:
        """Retrieve a pipeline state by ID."""
        return self._pipelines.get(pipeline_id)

    def list_pipelines(self) -> List[PipelineState]:
        """List all tracked pipelines."""
        return list(self._pipelines.values())

    def remove_pipeline(self, pipeline_id: str) -> bool:
        """Remove a pipeline and its snapshots."""
        if pipeline_id in self._pipelines:
            del self._pipelines[pipeline_id]
        if pipeline_id in self._snapshots:
            del self._snapshots[pipeline_id]
            return True
        return pipeline_id not in self._pipelines

    # ── Step Management ──────────────────────────────────────

    def add_step(
        self,
        pipeline_id: str,
        step_id: str,
        name: str = "",
        input_data: Any = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> StepState:
        """
        Add a step to a pipeline.

        Args:
            pipeline_id: The pipeline to add the step to.
            step_id: Unique step identifier.
            name: Human-readable step name.
            input_data: Input data for the step.
            metadata: Additional metadata.

        Returns:
            The created StepState.

        Raises:
            KeyError: If pipeline_id does not exist.
        """
        pipeline = self._pipelines.get(pipeline_id)
        if pipeline is None:
            raise KeyError(f"Pipeline '{pipeline_id}' not found")

        step = StepState(
            step_id=step_id,
            name=name or step_id,
            input_data=input_data,
            metadata=metadata or {},
        )
        pipeline.steps[step_id] = step
        logger.debug(
            "StateTracker: Added step '%s' to pipeline '%s'",
            step_id, pipeline_id,
        )
        return step

    def get_step(self, pipeline_id: str, step_id: str) -> Optional[StepState]:
        """Retrieve a step's state."""
        pipeline = self._pipelines.get(pipeline_id)
        if pipeline is None:
            return None
        return pipeline.steps.get(step_id)

    def update_step_status(
        self,
        pipeline_id: str,
        step_id: str,
        status: StepExecutionStatus,
        output_data: Any = None,
        error: Optional[str] = None,
    ) -> None:
        """
        Update a step's execution status.

        Args:
            pipeline_id: The pipeline containing the step.
            step_id: The step to update.
            status: The new status.
            output_data: Output data (for COMPLETED status).
            error: Error message (for FAILED status).

        Raises:
            KeyError: If pipeline or step not found.
        """
        pipeline = self._pipelines.get(pipeline_id)
        if pipeline is None:
            raise KeyError(f"Pipeline '{pipeline_id}' not found")
        step = pipeline.steps.get(step_id)
        if step is None:
            raise KeyError(f"Step '{step_id}' not found in pipeline '{pipeline_id}'")

        step.status = status
        step.attempts += 1

        if status == StepExecutionStatus.RUNNING:
            step.started_at = time.time()
        elif status == StepExecutionStatus.COMPLETED:
            step.completed_at = time.time()
            if step.started_at is not None:
                step.duration_ms = (step.completed_at - step.started_at) * 1000
            step.output_data = output_data
        elif status == StepExecutionStatus.FAILED:
            step.completed_at = time.time()
            if step.started_at is not None:
                step.duration_ms = (step.completed_at - step.started_at) * 1000
            step.error = error

    def update_pipeline_status(
        self,
        pipeline_id: str,
        status: PipelineStatus,
    ) -> None:
        """
        Update the overall pipeline status.

        Args:
            pipeline_id: The pipeline to update.
            status: The new status.

        Raises:
            KeyError: If pipeline not found.
        """
        pipeline = self._pipelines.get(pipeline_id)
        if pipeline is None:
            raise KeyError(f"Pipeline '{pipeline_id}' not found")

        pipeline.status = status
        if status == PipelineStatus.RUNNING and pipeline.started_at is None:
            pipeline.started_at = time.time()
        elif status in (PipelineStatus.COMPLETED, PipelineStatus.FAILED, PipelineStatus.CANCELLED):
            pipeline.completed_at = time.time()

    # ── Snapshots ────────────────────────────────────────────

    def snapshot(self, pipeline_id: str) -> PipelineState:
        """
        Take a snapshot of the current pipeline state.

        Args:
            pipeline_id: The pipeline to snapshot.

        Returns:
            A deep copy of the pipeline state.

        Raises:
            KeyError: If pipeline not found.
        """
        pipeline = self._pipelines.get(pipeline_id)
        if pipeline is None:
            raise KeyError(f"Pipeline '{pipeline_id}' not found")

        snap = copy.deepcopy(pipeline)
        snapshots = self._snapshots.setdefault(pipeline_id, [])
        snapshots.append(snap)

        # Enforce max history
        while len(snapshots) > self._max_history:
            snapshots.pop(0)

        logger.debug(
            "StateTracker: Snapshot taken for pipeline '%s' (total: %d)",
            pipeline_id, len(snapshots),
        )
        return snap

    def get_snapshots(self, pipeline_id: str) -> List[PipelineState]:
        """Get all snapshots for a pipeline."""
        return list(self._snapshots.get(pipeline_id, []))

    def restore_snapshot(self, pipeline_id: str, snapshot_index: int = -1) -> PipelineState:
        """
        Restore a pipeline from a snapshot.

        Args:
            pipeline_id: The pipeline to restore.
            snapshot_index: Index of the snapshot (-1 = latest).

        Returns:
            The restored pipeline state.

        Raises:
            KeyError: If pipeline or snapshot not found.
            IndexError: If snapshot_index is out of range.
        """
        snapshots = self._snapshots.get(pipeline_id)
        if not snapshots:
            raise KeyError(f"No snapshots found for pipeline '{pipeline_id}'")

        restored = copy.deepcopy(snapshots[snapshot_index])
        self._pipelines[pipeline_id] = restored
        logger.info(
            "StateTracker: Restored pipeline '%s' from snapshot %d",
            pipeline_id, snapshot_index,
        )
        return restored

    # ── Queries ──────────────────────────────────────────────

    def get_failed_pipelines(self) -> List[PipelineState]:
        """Get all pipelines with FAILED status."""
        return [
            p for p in self._pipelines.values()
            if p.status == PipelineStatus.FAILED
        ]

    def get_running_pipelines(self) -> List[PipelineState]:
        """Get all pipelines with RUNNING status."""
        return [
            p for p in self._pipelines.values()
            if p.status == PipelineStatus.RUNNING
        ]

    @property
    def stats(self) -> Dict[str, Any]:
        """Runtime statistics."""
        status_counts: Dict[str, int] = {}
        for p in self._pipelines.values():
            key = p.status.value
            status_counts[key] = status_counts.get(key, 0) + 1
        return {
            "total_pipelines": len(self._pipelines),
            "total_snapshots": sum(len(s) for s in self._snapshots.values()),
            "status_counts": status_counts,
        }

    def clear(self) -> None:
        """Clear all tracked pipelines and snapshots."""
        self._pipelines.clear()
        self._snapshots.clear()
