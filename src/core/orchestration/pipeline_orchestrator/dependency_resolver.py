"""
Dependency Resolver — Dependency resolution between pipeline steps.

Provides topological dependency resolution for pipeline steps,
detecting circular dependencies, computing execution layers,
and validating dependency graphs.

Designed for resource-constrained environments (Android/Termux, 500MB RAM).
No external dependencies beyond Python stdlib.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

__all__ = [
    "CircularDependencyError",
    "ResolutionResult",
    "DependencyResolver",
]


# ──────────────────────────────────────────────────────────────
#  EXCEPTIONS
# ──────────────────────────────────────────────────────────────

class CircularDependencyError(Exception):
    """
    Raised when a circular dependency is detected.

    Attributes:
        cycle: The list of step IDs forming the cycle.
    """

    def __init__(self, cycle: List[str]) -> None:
        self.cycle = cycle
        super().__init__(
            f"Circular dependency detected: {' -> '.join(cycle)}"
        )


# ──────────────────────────────────────────────────────────────
#  DATA CONTRACTS
# ──────────────────────────────────────────────────────────────

@dataclass
class ResolutionResult:
    """
    Result of dependency resolution.

    Attributes:
        is_valid: Whether the dependency graph is valid (no cycles).
        execution_order: Topologically sorted list of step IDs.
        execution_layers: Steps grouped by execution layer (parallelizable).
        cycles: Detected cycles (if any).
        unresolved: Step IDs with unresolved dependencies.
    """
    is_valid: bool = True
    execution_order: List[str] = field(default_factory=list)
    execution_layers: List[List[str]] = field(default_factory=list)
    cycles: List[List[str]] = field(default_factory=list)
    unresolved: List[str] = field(default_factory=list)


# ──────────────────────────────────────────────────────────────
#  DEPENDENCY RESOLVER
# ──────────────────────────────────────────────────────────────

class DependencyResolver:
    """
    Resolves dependencies between pipeline steps.

    Supports:
    - Declaring step dependencies
    - Topological sorting for execution order
    - Computing parallelizable execution layers
    - Circular dependency detection
    - Dependency validation

    Usage::

        resolver = DependencyResolver()
        resolver.add_step("extract")
        resolver.add_step("transform", depends_on=["extract"])
        resolver.add_step("load", depends_on=["transform"])

        result = resolver.resolve()
        # result.execution_order == ["extract", "transform", "load"]
        # result.execution_layers == [["extract"], ["transform"], ["load"]]

    Thread Safety:
        This class is NOT thread-safe. External synchronization is required.
    """

    def __init__(self) -> None:
        self._steps: Dict[str, Set[str]] = {}  # step_id -> set of dependency step_ids
        self._step_metadata: Dict[str, Dict[str, Any]] = {}

    # ── Step Registration ────────────────────────────────────

    def add_step(
        self,
        step_id: str,
        depends_on: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Register a step with its dependencies.

        Args:
            step_id: Unique step identifier.
            depends_on: List of step IDs this step depends on.
            metadata: Optional metadata for the step.

        Raises:
            ValueError: If step_id is empty.
        """
        if not step_id:
            raise ValueError("step_id must not be empty")

        self._steps[step_id] = set(depends_on or [])
        self._step_metadata[step_id] = metadata or {}
        logger.debug(
            "DependencyResolver: Added step '%s' (depends_on=%s)",
            step_id, depends_on or [],
        )

    def remove_step(self, step_id: str) -> bool:
        """
        Remove a step and clean up dependency references.

        Args:
            step_id: The step to remove.

        Returns:
            True if the step was found and removed.
        """
        if step_id not in self._steps:
            return False
        del self._steps[step_id]
        self._step_metadata.pop(step_id, None)
        # Remove from other steps' dependencies
        for deps in self._steps.values():
            deps.discard(step_id)
        return True

    def add_dependency(self, step_id: str, depends_on: str) -> None:
        """
        Add a single dependency to a step.

        Args:
            step_id: The step to add a dependency to.
            depends_on: The step it depends on.

        Raises:
            KeyError: If either step does not exist.
        """
        if step_id not in self._steps:
            raise KeyError(f"Step '{step_id}' not registered")
        if depends_on not in self._steps:
            raise KeyError(f"Dependency step '{depends_on}' not registered")
        self._steps[step_id].add(depends_on)

    def remove_dependency(self, step_id: str, depends_on: str) -> None:
        """
        Remove a single dependency from a step.

        Args:
            step_id: The step to remove a dependency from.
            depends_on: The dependency to remove.
        """
        if step_id in self._steps:
            self._steps[step_id].discard(depends_on)

    # ── Resolution ───────────────────────────────────────────

    def resolve(self) -> ResolutionResult:
        """
        Resolve all dependencies and compute execution order.

        Returns:
            ResolutionResult with execution order, layers, and any issues.
        """
        result = ResolutionResult()

        # Detect cycles first
        cycles = self._detect_cycles()
        if cycles:
            result.is_valid = False
            result.cycles = cycles
            return result

        # Compute topological order (Kahn's algorithm)
        in_degree: Dict[str, int] = {sid: 0 for sid in self._steps}
        for sid, deps in self._steps.items():
            for dep in deps:
                if dep in in_degree:
                    pass  # dep exists
            # in_degree = number of dependencies
            in_degree[sid] = len([d for d in deps if d in self._steps])

        # Check for unresolved dependencies
        unresolved = []
        for sid, deps in self._steps.items():
            for dep in deps:
                if dep not in self._steps:
                    unresolved.append(sid)
                    break
        if unresolved:
            result.unresolved = unresolved
            result.is_valid = False

        # Compute execution layers
        layers: List[List[str]] = []
        remaining = dict(in_degree)

        while remaining:
            # Find all steps with in_degree 0
            ready = sorted([sid for sid, deg in remaining.items() if deg == 0])
            if not ready:
                # This shouldn't happen if cycles are already detected,
                # but handle it gracefully
                break

            layers.append(ready)
            for sid in ready:
                del remaining[sid]
                # Reduce in_degree for dependents
                for other_sid, deps in self._steps.items():
                    if sid in deps and other_sid in remaining:
                        remaining[other_sid] -= 1

        result.execution_layers = layers
        result.execution_order = [sid for layer in layers for sid in layer]
        return result

    def _detect_cycles(self) -> List[List[str]]:
        """Detect cycles using DFS with coloring."""
        WHITE, GRAY, BLACK = 0, 1, 2
        color: Dict[str, int] = {sid: WHITE for sid in self._steps}
        cycles: List[List[str]] = []
        path: List[str] = []

        def dfs(node: str) -> None:
            color[node] = GRAY
            path.append(node)
            for dep in sorted(self._steps.get(node, set())):
                if dep not in color:
                    continue
                if color[dep] == GRAY:
                    cycle_start = path.index(dep)
                    cycles.append(path[cycle_start:] + [dep])
                elif color[dep] == WHITE:
                    dfs(dep)
            path.pop()
            color[node] = BLACK

        for sid in sorted(self._steps.keys()):
            if color[sid] == WHITE:
                dfs(sid)

        return cycles

    # ── Queries ──────────────────────────────────────────────

    def get_dependencies(self, step_id: str) -> Set[str]:
        """Get direct dependencies of a step."""
        return set(self._steps.get(step_id, set()))

    def get_dependents(self, step_id: str) -> Set[str]:
        """Get steps that depend on the given step."""
        dependents: Set[str] = set()
        for sid, deps in self._steps.items():
            if step_id in deps:
                dependents.add(sid)
        return dependents

    def get_all_ancestors(self, step_id: str) -> Set[str]:
        """Get all transitive dependencies of a step."""
        ancestors: Set[str] = set()
        stack = list(self._steps.get(step_id, set()))
        while stack:
            dep = stack.pop()
            if dep not in ancestors and dep in self._steps:
                ancestors.add(dep)
                stack.extend(self._steps[dep])
        return ancestors

    def get_all_descendants(self, step_id: str) -> Set[str]:
        """Get all transitive dependents of a step."""
        descendants: Set[str] = set()
        stack = list(self.get_dependents(step_id))
        while stack:
            dep = stack.pop()
            if dep not in descendants:
                descendants.add(dep)
                stack.extend(self.get_dependents(dep))
        return descendants

    def get_root_steps(self) -> List[str]:
        """Get steps with no dependencies (entry points)."""
        return sorted([
            sid for sid, deps in self._steps.items()
            if not deps or not any(d in self._steps for d in deps)
        ])

    def get_leaf_steps(self) -> List[str]:
        """Get steps that no other step depends on (exit points)."""
        all_deps: Set[str] = set()
        for deps in self._steps.values():
            all_deps.update(deps)
        return sorted([
            sid for sid in self._steps
            if sid not in all_deps
        ])

    # ── Accessors ────────────────────────────────────────────

    @property
    def steps(self) -> Dict[str, Set[str]]:
        """Read-only view of all steps and their dependencies."""
        return {sid: set(deps) for sid, deps in self._steps.items()}

    @property
    def step_count(self) -> int:
        """Number of registered steps."""
        return len(self._steps)

    def has_step(self, step_id: str) -> bool:
        """Check if a step is registered."""
        return step_id in self._steps

    def clear(self) -> None:
        """Clear all registered steps."""
        self._steps.clear()
        self._step_metadata.clear()

    def __repr__(self) -> str:
        return f"DependencyResolver(steps={self.step_count})"
