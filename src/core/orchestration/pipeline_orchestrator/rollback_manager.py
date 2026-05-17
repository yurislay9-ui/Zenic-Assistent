"""
Rollback Manager — Rollback/recovery management for pipeline steps.

Provides a mechanism for registering and executing compensating
actions when pipeline steps fail, enabling partial or full rollback
of pipeline state.

Designed for resource-constrained environments (Android/Termux, 500MB RAM).
No external dependencies beyond Python stdlib.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

__all__ = [
    "RollbackAction",
    "RollbackResult",
    "RollbackManager",
]


# ──────────────────────────────────────────────────────────────
#  DATA CONTRACTS
# ──────────────────────────────────────────────────────────────

class RollbackStatus(str, Enum):
    """Status of a rollback operation."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class RollbackAction:
    """
    A compensating action that can reverse a step's effects.

    Attributes:
        step_id: The step this action compensates.
        action_fn: Callable that performs the rollback.
        description: Human-readable description.
        priority: Execution priority (lower = executed first).
        status: Current status of this rollback action.
        error: Error message if the rollback failed.
        metadata: Additional metadata.
    """
    step_id: str
    action_fn: Callable[..., Any]
    description: str = ""
    priority: int = 0
    status: RollbackStatus = RollbackStatus.PENDING
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RollbackResult:
    """
    Result of a rollback operation.

    Attributes:
        success: Whether all rollback actions completed successfully.
        actions_total: Total number of rollback actions.
        actions_completed: Number of successfully completed actions.
        actions_failed: Number of failed rollback actions.
        actions_skipped: Number of skipped rollback actions.
        errors: List of error messages from failed rollbacks.
        duration_ms: Total rollback duration in milliseconds.
    """
    success: bool = True
    actions_total: int = 0
    actions_completed: int = 0
    actions_failed: int = 0
    actions_skipped: int = 0
    errors: List[str] = field(default_factory=list)
    duration_ms: float = 0.0


# ──────────────────────────────────────────────────────────────
#  ROLLBACK MANAGER
# ──────────────────────────────────────────────────────────────

class RollbackManager:
    """
    Manages rollback/recovery for pipeline step failures.

    Supports:
    - Registering compensating actions for each step
    - Ordered rollback execution (reverse completion order)
    - Partial rollback (up to a specific step)
    - Best-effort rollback (continues even if some actions fail)
    - Rollback history for audit

    Usage::

        manager = RollbackManager()

        # Register compensating actions as steps complete
        manager.register("step_1", lambda: cleanup_temp_files(),
                        description="Clean temp files")
        manager.register("step_2", lambda: revert_db_changes(),
                        description="Revert DB changes")

        # If step_3 fails, rollback steps 2 and 1
        result = manager.rollback_to("step_1")

    Thread Safety:
        This class is NOT thread-safe. External synchronization is required.
    """

    def __init__(self, continue_on_failure: bool = True) -> None:
        """
        Initialize the RollbackManager.

        Args:
            continue_on_failure: If True, continue executing remaining
                rollback actions even if one fails.
        """
        self._actions: Dict[str, RollbackAction] = {}
        self._completion_order: List[str] = []
        self._continue_on_failure = continue_on_failure
        self._rollback_history: List[RollbackResult] = []

    # ── Registration ─────────────────────────────────────────

    def register(
        self,
        step_id: str,
        action_fn: Callable[..., Any],
        description: str = "",
        priority: int = 0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Register a compensating action for a step.

        Args:
            step_id: The step this action compensates.
            action_fn: Callable to execute during rollback.
            description: Human-readable description.
            priority: Execution priority (lower = executed first).
            metadata: Additional metadata.
        """
        action = RollbackAction(
            step_id=step_id,
            action_fn=action_fn,
            description=description or f"Rollback for {step_id}",
            priority=priority,
            metadata=metadata or {},
        )
        self._actions[step_id] = action
        if step_id not in self._completion_order:
            self._completion_order.append(step_id)
        logger.debug(
            "RollbackManager: Registered rollback for step '%s' (priority=%d)",
            step_id, priority,
        )

    def unregister(self, step_id: str) -> bool:
        """
        Remove a registered rollback action.

        Args:
            step_id: The step whose rollback to remove.

        Returns:
            True if found and removed, False otherwise.
        """
        if step_id in self._actions:
            del self._actions[step_id]
        if step_id in self._completion_order:
            self._completion_order.remove(step_id)
            return True
        return False

    def mark_completed(self, step_id: str) -> None:
        """
        Mark a step as completed, updating the completion order.

        Args:
            step_id: The step that completed.
        """
        if step_id in self._completion_order:
            self._completion_order.remove(step_id)
        self._completion_order.append(step_id)

    # ── Rollback Execution ───────────────────────────────────

    def rollback_all(self) -> RollbackResult:
        """
        Rollback all registered steps in reverse completion order.

        Returns:
            RollbackResult with the outcome.
        """
        if not self._completion_order:
            return RollbackResult(success=True)

        # Rollback in reverse order
        reversed_steps = list(reversed(self._completion_order))
        return self._execute_rollback(reversed_steps)

    def rollback_to(self, target_step_id: str) -> RollbackResult:
        """
        Rollback steps from the most recent down to (and including)
        the specified step.

        Args:
            target_step_id: The step to rollback to (inclusive).

        Returns:
            RollbackResult with the outcome.

        Raises:
            KeyError: If target_step_id is not registered.
        """
        if target_step_id not in self._actions:
            raise KeyError(f"Step '{target_step_id}' has no registered rollback action")

        # Find steps after target in completion order
        try:
            target_idx = self._completion_order.index(target_step_id)
        except ValueError:
            raise KeyError(f"Step '{target_step_id}' not found in completion order")

        steps_to_rollback = list(reversed(self._completion_order[target_idx:]))
        return self._execute_rollback(steps_to_rollback)

    def rollback_step(self, step_id: str) -> RollbackResult:
        """
        Rollback a single step.

        Args:
            step_id: The step to rollback.

        Returns:
            RollbackResult with the outcome.
        """
        if step_id not in self._actions:
            return RollbackResult(
                success=False,
                actions_total=1,
                actions_failed=1,
                errors=[f"No rollback action registered for step '{step_id}'"],
            )
        return self._execute_rollback([step_id])

    def _execute_rollback(self, step_ids: List[str]) -> RollbackResult:
        """Execute rollback for the given step IDs."""
        start_time = time.monotonic()
        result = RollbackResult(actions_total=len(step_ids))

        # Sort by priority (lower = first) within the given order
        ordered_actions: List[RollbackAction] = []
        for sid in step_ids:
            if sid in self._actions:
                ordered_actions.append(self._actions[sid])
            else:
                result.actions_skipped += 1
                logger.warning(
                    "RollbackManager: No action for step '%s', skipping", sid,
                )

        ordered_actions.sort(key=lambda a: a.priority)

        for action in ordered_actions:
            action.status = RollbackStatus.RUNNING
            try:
                action.action_fn()
                action.status = RollbackStatus.COMPLETED
                result.actions_completed += 1
                logger.info(
                    "RollbackManager: Rolled back step '%s' — %s",
                    action.step_id, action.description,
                )
            except Exception as exc:
                action.status = RollbackStatus.FAILED
                action.error = str(exc)
                result.actions_failed += 1
                result.errors.append(
                    f"Step '{action.step_id}' rollback failed: {exc}"
                )
                result.success = False
                logger.error(
                    "RollbackManager: Rollback FAILED for step '%s': %s",
                    action.step_id, exc,
                )
                if not self._continue_on_failure:
                    break

        result.duration_ms = (time.monotonic() - start_time) * 1000
        self._rollback_history.append(result)
        return result

    # ── Accessors ────────────────────────────────────────────

    @property
    def registered_steps(self) -> List[str]:
        """List of step IDs with registered rollback actions."""
        return list(self._actions.keys())

    @property
    def completion_order(self) -> List[str]:
        """List of step IDs in completion order."""
        return list(self._completion_order)

    @property
    def history(self) -> List[RollbackResult]:
        """History of all rollback operations."""
        return list(self._rollback_history)

    def has_action(self, step_id: str) -> bool:
        """Check if a rollback action is registered for a step."""
        return step_id in self._actions

    def clear(self) -> None:
        """Clear all registered actions and history."""
        self._actions.clear()
        self._completion_order.clear()
        self._rollback_history.clear()

    def __repr__(self) -> str:
        return (
            f"RollbackManager(registered={len(self._actions)}, "
            f"history={len(self._rollback_history)})"
        )
