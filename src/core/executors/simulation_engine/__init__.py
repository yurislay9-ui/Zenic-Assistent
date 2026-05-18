"""
ZENIC-AGENTS - Simulation Engine (C1: Simulation Engine)

Runs the entire DAG pipeline (or a single action dispatch) in
simulation/dry-run mode.  All results are strictly in-memory — no
real I/O is performed.  A rolling SQLite table (``_simulation_history``)
persists the last 50 simulation results for debugging / audit.

Features:
  - ``simulate_dag``  – dry-run every node in a DAG context.
  - ``simulate_dispatch`` – dry-run a single action dispatch.
  - ``compare_scenarios`` – A/B comparison of two action configs.
  - Thread-safe via RLock.
  - Retry logic: ``simulate_dag`` retries up to 2 times on
    transient errors.
  - Singleton: get_simulation_engine() / reset_simulation_engine().
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

from src.core.native import (
    topological_sort as _native_topological_sort,
    detect_cycles as _native_detect_cycles,
    aggregate_impact as _native_aggregate_impact,
    simulate_dag as _native_simulate_dag,
    calculate_blast_radius as _native_calculate_blast_radius,
    propagate_risks as _native_propagate_risks,
    find_critical_path as _native_find_critical_path,
    HAS_NATIVE as _HAS_NATIVE,
)

from ._helpers import ensure_db, persist_result, retry
from ._types import ScenarioComparison, SimulationResult, extract_risk_score

logger = logging.getLogger(__name__)

__all__ = [
    "SimulationResult",
    "ScenarioComparison",
    "SimulationEngine",
    "get_simulation_engine",
    "reset_simulation_engine",
]


class SimulationEngine:
    """Runs the entire DAG pipeline in simulation/dry-run mode.

    All results are in-memory only — no persistence of simulation
    results beyond the optional ``_simulation_history`` SQLite table
    (last 50 entries).

    Thread-safe: All public methods guarded by RLock.
    """

    _HISTORY_DB_NAME = "simulation_history.sqlite"
    _MAX_HISTORY = 50

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._dry_run_executor: Optional[Any] = None  # lazy
        self._impact_preview_engine: Optional[Any] = None  # lazy
        self._db_path: Optional[str] = None  # initialised lazily
        self._simulation_count: int = 0

    # ── Lazy dependencies ──────────────────────────────────────

    @property
    def dry_run_executor(self) -> Any:
        """Lazy-load the DryRunExecutor singleton."""
        if self._dry_run_executor is None:
            from .dry_run_executor import DryRunExecutor, get_dry_run_executor
            self._dry_run_executor = get_dry_run_executor()
        return self._dry_run_executor

    @property
    def impact_preview_engine(self) -> Any:
        """Lazy-load the ImpactPreviewEngine singleton."""
        if self._impact_preview_engine is None:
            from .impact_preview import ImpactPreviewEngine, get_impact_preview_engine
            self._impact_preview_engine = get_impact_preview_engine()
        return self._impact_preview_engine

    # ── SQLite history persistence ─────────────────────────────

    def _ensure_db(self) -> str:
        """Ensure the SQLite history database exists and return its path."""
        self._db_path = ensure_db(self._db_path, self._HISTORY_DB_NAME)
        return self._db_path

    def _persist_result(self, result: SimulationResult) -> None:
        """Persist a simulation result (keeping only the last 50)."""
        if self._db_path is None:
            return  # DB not yet initialised; skip silently
        persist_result(self._db_path, result, self._MAX_HISTORY)

    # ── Core API ───────────────────────────────────────────────

    def simulate_dag(self, ctx: Dict[str, Any]) -> SimulationResult:
        """Run through the DAG nodes in dry-run mode.

        Iterates over the nodes in *ctx* (key ``"dag_nodes"`` or
        ``"actions"``) and simulates each one via the DryRunExecutor.
        All operations are in-memory only.

        Transient errors are retried up to 2 times.

        Args:
            ctx: DAG context dictionary. Expected keys:

                * ``dag_id`` – optional DAG identifier.
                * ``dag_nodes`` / ``actions`` – list of node dicts,
                  each with ``action_type``, ``config``, and optional
                  ``context``.

        Returns:
            A SimulationResult summarising the simulation.
        """
        with self._lock:
            self._simulation_count += 1
            dag_id = ctx.get("dag_id", uuid.uuid4().hex[:12])
            nodes = ctx.get("dag_nodes", ctx.get("actions", []))

            if not nodes:
                result = SimulationResult(
                    dag_id=dag_id,
                    nodes_simulated=0,
                    would_succeed=True,
                    node_results={"status": "NO_NODES"},
                )
                logger.debug("SimulationEngine: simulate_dag — no nodes in ctx")
                return result

            start = time.monotonic()

            def _run_simulation() -> SimulationResult:
                estimated_impacts: List[Dict[str, Any]] = []
                node_results: Dict[str, Any] = {}
                all_succeed = True

                for idx, node in enumerate(nodes):
                    node_id = node.get("id", node.get("node_id", f"node_{idx}"))
                    action_type = node.get("action_type", "unknown")
                    config = node.get("config", {})
                    node_ctx = node.get("context", {})

                    # Get impact preview
                    impact_dict: Dict[str, Any] = {}
                    try:
                        impact_dict = self.dry_run_executor.preview_action(
                            action_type, config, node_ctx,
                        )
                    except Exception as exc:
                        logger.debug(
                            "SimulationEngine: preview failed for node %s: %s",
                            node_id, exc,
                        )
                        impact_dict = {"error": str(exc)}

                    estimated_impacts.append(impact_dict)

                    # Record operation via DryRunExecutor
                    try:
                        action_lower = action_type.lower()
                        if action_lower in ("email", "send_email"):
                            self.dry_run_executor._intercept_smtp(config)
                        elif action_lower in ("http", "http_request"):
                            self.dry_run_executor._intercept_http(config)
                        elif action_lower in ("database", "db", "database_operation"):
                            self.dry_run_executor._intercept_db(config)
                        elif action_lower in ("file", "file_operation"):
                            self.dry_run_executor._intercept_file(config)
                        else:
                            self.dry_run_executor._record_operation(
                                operation_type=action_lower,
                                target=config.get("operation", action_type),
                                would_affect={"simulated": True},
                            )
                    except Exception as exc:
                        logger.warning(
                            "SimulationEngine: intercept failed for node %s: %s",
                            node_id, exc,
                        )
                        all_succeed = False

                    # Determine if the node would succeed
                    risk_level = impact_dict.get("risk_level", "none")
                    node_would_succeed = risk_level not in ("critical", "high")
                    if not node_would_succeed:
                        all_succeed = False

                    node_results[node_id] = {
                        "action_type": action_type,
                        "would_succeed": node_would_succeed,
                        "risk_level": risk_level,
                    }

                # Collect all operations from the DryRunExecutor
                simulated_actions = list(self.dry_run_executor.operations)

                duration_ms = (time.monotonic() - start) * 1000

                result = SimulationResult(
                    dag_id=dag_id,
                    nodes_simulated=len(nodes),
                    total_duration_ms=round(duration_ms, 2),
                    simulated_actions=simulated_actions,
                    estimated_impacts=estimated_impacts,
                    would_succeed=all_succeed,
                    node_results=node_results,
                )
                return result

            # Retry up to 2 times on transient errors
            try:
                result = retry(
                    _run_simulation,
                    max_retries=2,
                    base_delay=0.1,
                    label=f"SimulationEngine.simulate_dag({dag_id})",
                )
            except Exception as exc:
                logger.error(
                    "SimulationEngine: simulate_dag failed for %s: %s",
                    dag_id, exc,
                )
                result = SimulationResult(
                    dag_id=dag_id,
                    nodes_simulated=len(nodes),
                    would_succeed=False,
                    node_results={"error": str(exc)},
                )

            # Persist to history
            self._ensure_db()
            self._persist_result(result)

            logger.info(
                "SimulationEngine: simulate_dag %s — nodes=%d succeed=%s duration=%.1fms",
                dag_id, result.nodes_simulated, result.would_succeed,
                result.total_duration_ms,
            )

            return result

    def simulate_dispatch(
        self,
        dispatch_request_dict: Dict[str, Any],
    ) -> SimulationResult:
        """Simulate a single action dispatch.

        Args:
            dispatch_request_dict: Dictionary with keys ``action_type``,
                ``config``, and optional ``context``.

        Returns:
            A SimulationResult for the single dispatch.
        """
        with self._lock:
            from .dry_run_executor import dry_run_dispatch

            start = time.monotonic()

            # Build a minimal dispatcher-like object
            # dry_run_dispatch will handle the interception
            dry_result = dry_run_dispatch(dispatcher=None, request=dispatch_request_dict)

            duration_ms = (time.monotonic() - start) * 1000

            result = SimulationResult(
                dag_id=dispatch_request_dict.get("action_id", uuid.uuid4().hex[:12]),
                nodes_simulated=1,
                total_duration_ms=round(duration_ms, 2),
                simulated_actions=dry_result.simulated_operations,
                estimated_impacts=[dry_result.impact_preview],
                would_succeed=dry_result.would_succeed,
                node_results={
                    dispatch_request_dict.get("action_type", "dispatch"): {
                        "would_succeed": dry_result.would_succeed,
                        "safety_verdict": dry_result.safety_verdict_would_be,
                    },
                },
            )

            # Persist to history
            self._ensure_db()
            self._persist_result(result)

            logger.info(
                "SimulationEngine: simulate_dispatch %s — succeed=%s verdict=%s",
                dispatch_request_dict.get("action_type", "?"),
                result.would_succeed,
                dry_result.safety_verdict_would_be,
            )

            return result

    def compare_scenarios(
        self,
        scenario_a: Dict[str, Any],
        scenario_b: Dict[str, Any],
    ) -> ScenarioComparison:
        """A/B comparison of two action scenarios.

        Simulates both scenarios and produces a detailed comparison
        of their results.

        Args:
            scenario_a: First scenario dict (same shape as
                ``dispatch_request_dict``).
            scenario_b: Second scenario dict.

        Returns:
            A ScenarioComparison with both results, differences,
            and a recommendation.
        """
        with self._lock:
            # Simulate both scenarios
            result_a = self.simulate_dispatch(scenario_a)
            result_b = self.simulate_dispatch(scenario_b)

            # Compute differences
            differences: List[Dict[str, Any]] = []

            if result_a.nodes_simulated != result_b.nodes_simulated:
                differences.append({
                    "field": "nodes_simulated",
                    "scenario_a": result_a.nodes_simulated,
                    "scenario_b": result_b.nodes_simulated,
                })

            if result_a.would_succeed != result_b.would_succeed:
                differences.append({
                    "field": "would_succeed",
                    "scenario_a": result_a.would_succeed,
                    "scenario_b": result_b.would_succeed,
                })

            if abs(result_a.total_duration_ms - result_b.total_duration_ms) > 1.0:
                differences.append({
                    "field": "total_duration_ms",
                    "scenario_a": result_a.total_duration_ms,
                    "scenario_b": result_b.total_duration_ms,
                })

            # Compare estimated impacts
            impacts_a = result_a.estimated_impacts
            impacts_b = result_b.estimated_impacts
            if impacts_a and impacts_b:
                risk_a = impacts_a[0].get("risk_level", "none") if impacts_a else "none"
                risk_b = impacts_b[0].get("risk_level", "none") if impacts_b else "none"
                if risk_a != risk_b:
                    differences.append({
                        "field": "risk_level",
                        "scenario_a": risk_a,
                        "scenario_b": risk_b,
                    })

                score_a = impacts_a[0].get("risk_score", 0.0) if impacts_a else 0.0
                score_b = impacts_b[0].get("risk_score", 0.0) if impacts_b else 0.0
                if abs(score_a - score_b) > 0.1:
                    differences.append({
                        "field": "risk_score",
                        "scenario_a": score_a,
                        "scenario_b": score_b,
                    })

            # Generate recommendation
            recommendation = self._generate_recommendation(
                result_a, result_b, differences,
            )

            comparison = ScenarioComparison(
                scenario_a_result=result_a,
                scenario_b_result=result_b,
                differences=differences,
                recommendation=recommendation,
            )

            logger.info(
                "SimulationEngine: compare_scenarios — %d differences, recommendation: %s",
                len(differences), recommendation[:80],
            )

            return comparison

    # ── Recommendation helper ──────────────────────────────────

    @staticmethod
    def _generate_recommendation(
        result_a: SimulationResult,
        result_b: SimulationResult,
        differences: List[Dict[str, Any]],
    ) -> str:
        """Generate a human-readable recommendation from the comparison.

        Prefers the scenario that would succeed.  If both succeed,
        prefers the one with lower risk.  If both fail, recommends
        reviewing both.
        """
        if not differences:
            return "Both scenarios are equivalent. Either can be chosen."

        if result_a.would_succeed and not result_b.would_succeed:
            return "Scenario A is recommended: it would succeed while scenario B would fail."

        if result_b.would_succeed and not result_a.would_succeed:
            return "Scenario B is recommended: it would succeed while scenario A would fail."

        # Both succeed or both fail — compare risk
        risk_a = extract_risk_score(result_a)
        risk_b = extract_risk_score(result_b)

        if risk_a < risk_b:
            return (
                f"Scenario A is recommended: lower estimated risk "
                f"({risk_a:.2f} vs {risk_b:.2f})."
            )
        elif risk_b < risk_a:
            return (
                f"Scenario B is recommended: lower estimated risk "
                f"({risk_b:.2f} vs {risk_a:.2f})."
            )

        if result_a.total_duration_ms < result_b.total_duration_ms:
            return (
                f"Scenario A is recommended: faster estimated execution "
                f"({result_a.total_duration_ms:.1f}ms vs "
                f"{result_b.total_duration_ms:.1f}ms)."
            )
        elif result_b.total_duration_ms < result_a.total_duration_ms:
            return (
                f"Scenario B is recommended: faster estimated execution "
                f"({result_b.total_duration_ms:.1f}ms vs "
                f"{result_a.total_duration_ms:.1f}ms)."
            )

        return "Both scenarios have similar risk and duration. Review differences for details."


# ──────────────────────────────────────────────────────────────
#  SINGLETON
# ──────────────────────────────────────────────────────────────

_instance: Optional[SimulationEngine] = None
_instance_lock = threading.Lock()


def get_simulation_engine() -> SimulationEngine:
    """Return the singleton SimulationEngine instance."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = SimulationEngine()
    return _instance


def reset_simulation_engine() -> None:
    """Reset the singleton instance (mainly for testing)."""
    global _instance
    with _instance_lock:
        _instance = None
