"""simulation_engine — Execution mixin (dispatch, compare_scenarios, singleton)."""

from __future__ import annotations

import threading
import time
import uuid
from typing import Any, Dict, List, Optional

from ._types import *  # noqa: F403
from ._helpers import _ensure_db, _persist_result


class SimulationEngineExecutionMixin:
    """Dispatch, comparison, and singleton for SimulationEngine."""

    def simulate_dispatch(
        self,
        dispatch_request_dict: Dict[str, Any],
    ) -> SimulationResult:  # noqa: F821
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

            self._ensure_db()
            self._persist_result(result)

            __import__("logging").getLogger("zenic_agents.executors.simulation_engine").info(
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
    ) -> ScenarioComparison:  # noqa: F821
        """A/B comparison of two action scenarios.

        Args:
            scenario_a: First scenario dict.
            scenario_b: Second scenario dict.

        Returns:
            A ScenarioComparison with both results, differences,
            and a recommendation.
        """
        with self._lock:
            result_a = self.simulate_dispatch(scenario_a)
            result_b = self.simulate_dispatch(scenario_b)

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

            __import__("logging").getLogger("zenic_agents.executors.simulation_engine").info(
                "SimulationEngine: compare_scenarios — %d differences, recommendation: %s",
                len(differences), recommendation[:80],
            )

            return comparison

    # ── Recommendation helper ──────────────────────────────────

    @staticmethod
    def _generate_recommendation(
        result_a: SimulationResult,  # noqa: F821
        result_b: SimulationResult,  # noqa: F821
        differences: List[Dict[str, Any]],
    ) -> str:
        """Generate a human-readable recommendation from the comparison."""
        if not differences:
            return "Both scenarios are equivalent. Either can be chosen."

        if result_a.would_succeed and not result_b.would_succeed:
            return "Scenario A is recommended: it would succeed while scenario B would fail."

        if result_b.would_succeed and not result_a.would_succeed:
            return "Scenario B is recommended: it would succeed while scenario A would fail."

        # Both succeed or both fail — compare risk
        risk_a = _extract_risk_score(result_a)
        risk_b = _extract_risk_score(result_b)

        if risk_a < risk_b:
            return f"Scenario A is recommended: lower estimated risk ({risk_a:.2f} vs {risk_b:.2f})."
        elif risk_b < risk_a:
            return f"Scenario B is recommended: lower estimated risk ({risk_b:.2f} vs {risk_a:.2f})."

        if result_a.total_duration_ms < result_b.total_duration_ms:
            return (
                f"Scenario A is recommended: faster estimated execution "
                f"({result_a.total_duration_ms:.1f}ms vs {result_b.total_duration_ms:.1f}ms)."
            )
        elif result_b.total_duration_ms < result_a.total_duration_ms:
            return (
                f"Scenario B is recommended: faster estimated execution "
                f"({result_b.total_duration_ms:.1f}ms vs {result_a.total_duration_ms:.1f}ms)."
            )

        return "Both scenarios have similar risk and duration. Review differences for details."


def _extract_risk_score(result: SimulationResult) -> float:  # noqa: F821
    """Extract the maximum risk score from a SimulationResult."""
    max_score = 0.0
    for impact in result.estimated_impacts:
        if isinstance(impact, dict):
            score = impact.get("risk_score", 0.0)
            if isinstance(score, (int, float)):
                max_score = max(max_score, float(score))
    return max_score


# ──────────────────────────────────────────────────────────────
#  SINGLETON
# ──────────────────────────────────────────────────────────────

_instance: Optional[SimulationEngine] = None  # noqa: F821
_instance_lock = threading.Lock()


def get_simulation_engine() -> "SimulationEngine":  # noqa: F821
    """Return the singleton SimulationEngine instance."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                from ._core import SimulationEngine
                _instance = SimulationEngine()
    return _instance


def reset_simulation_engine() -> None:
    """Reset the singleton instance (mainly for testing)."""
    global _instance
    with _instance_lock:
        _instance = None
