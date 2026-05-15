"""
A12 TaskScheduler — SINGLE RESPONSIBILITY: Schedule and manage tasks with priority/deadlines.

Deterministic task scheduling: priority scoring, deadline weighting, round-robin assignment.
No AI. Pure sorting and assignment algorithms.
"""

from __future__ import annotations

from typing import Any

from ..resilience import BaseAgent
from ..schemas import TaskResult


# ──────────────────────────────────────────────────────────────
# CONSTANTS
# ──────────────────────────────────────────────────────────────

PRIORITY_WEIGHTS = {
    "critical": 4,
    "high": 3,
    "medium": 2,
    "low": 1,
}

DEADLINE_BONUS = 10          # Extra points for having a deadline
OVERDUE_BONUS = 15           # Extra points for overdue tasks
MAX_TASKS = 200              # Sanity cap
DEFAULT_PRIORITY = "medium"


class TaskScheduler(BaseAgent[TaskResult]):
    """
    A12: Schedule and manage tasks with priority/deadlines.

    Single Responsibility: Task scheduling and assignment ONLY.
    Method: Priority scoring + deadline weighting + round-robin assignment.
    Fallback: Empty TaskResult with no schedule.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(name="A12_TaskScheduler", **kwargs)

    def execute(self, input_data: Any) -> TaskResult:
        """
        Schedule tasks: score by priority + deadline, assign to resources.

        Input (BusinessData.data dict):
            - tasks: list of {name, priority, deadline/due_date, ...}
            - resources: list of {name, ...}

        Output: TaskResult with schedule, conflicts, priorities.
        """
        if not isinstance(input_data, dict):
            data = input_data.data if hasattr(input_data, "data") else {}
        else:
            data = input_data

        tasks = data.get("tasks", [])
        resources = data.get("resources", [])

        if not tasks:
            return TaskResult(
                schedule=[], conflicts=[], priorities={},
                source="deterministic",
            )

        # Cap tasks
        tasks = tasks[:MAX_TASKS]

        # ── Score each task ──
        import time as _time
        now = _time.time()
        scored = []

        for idx, task in enumerate(tasks):
            if not isinstance(task, dict):
                task = {"name": f"Task_{idx}"}

            priority = str(task.get("priority", DEFAULT_PRIORITY)).lower()
            base_score = PRIORITY_WEIGHTS.get(priority, 2) * 25

            # Deadline bonus
            deadline = task.get("deadline") or task.get("due_date")
            if deadline:
                base_score += DEADLINE_BONUS
                # Check if overdue (simple heuristic)
                if isinstance(deadline, (int, float)) and deadline < now:
                    base_score += OVERDUE_BONUS

            scored.append({
                **task,
                "score": base_score,
                "original_index": idx,
            })

        # Sort by score descending (highest priority first)
        scored.sort(key=lambda t: t["score"], reverse=True)

        # ── Build schedule ──
        schedule = []
        for order, task in enumerate(scored, 1):
            schedule.append({
                "order": order,
                "name": task.get("name", f"Task_{task.get('original_index', order)}"),
                "priority": task.get("priority", DEFAULT_PRIORITY),
                "score": task["score"],
                "has_deadline": bool(task.get("deadline") or task.get("due_date")),
            })

        # ── Round-robin assignment ──
        assignments = {}
        if resources:
            for idx, task in enumerate(scored):
                resource = resources[idx % len(resources)]
                resource_name = resource.get("name", f"Resource_{idx % len(resources)}")
                task_name = task.get("name", f"Task_{task.get('original_index', idx)}")
                assignments[task_name] = resource_name

        # ── Detect conflicts (tasks with same priority + same resource) ──
        conflicts: list[str] = []
        if resources:
            resource_tasks: dict[str, list[str]] = {}
            for task_name, resource_name in assignments.items():
                resource_tasks.setdefault(resource_name, []).append(task_name)
            for resource_name, task_names in resource_tasks.items():
                if len(task_names) > 3:
                    conflicts.append(
                        f"Resource overload: {resource_name} has {len(task_names)} tasks"
                    )

        # ── Priority summary ──
        priorities: dict[str, int] = {}
        for task in scored:
            p = task.get("priority", DEFAULT_PRIORITY)
            priorities[p] = priorities.get(p, 0) + 1

        return TaskResult(
            schedule=schedule,
            conflicts=conflicts,
            priorities=priorities,
            source="deterministic",
        )

    def fallback(self, input_data: Any) -> TaskResult:
        """Safe fallback: empty task result."""
        return TaskResult(
            schedule=[], conflicts=[], priorities={},
            source="fallback",
        )
