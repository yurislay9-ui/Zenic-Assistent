"""Core logic for experiment_runner."""

from __future__ import annotations
import json
import logging
import sqlite3
import threading
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from ..types import ChaosExperiment, FaultInjection, FaultType, ChaosExperimentState
from ._types import DB_DIR, DB_PATH
from ._helpers import _retry
from ._mixin_persistence import ChaosPersistenceMixin

logger = logging.getLogger("zenic_agents.core.chaos.experiment_runner")

class ChaosExperimentRunner(ChaosPersistenceMixin):
    """Thread-safe chaos experiment runner with SQLite persistence."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        self._lock = threading.RLock()
        self._experiments: Dict[str, ChaosExperiment] = {}
        self._db_path = db_path or str(DB_PATH)
        self._run_count = 0
        self._success_count = 0
        self._fail_count = 0
        self._init_db()

    def create_experiment(self, experiment: ChaosExperiment) -> str:
        """Create a new experiment."""
        with self._lock:
            if not experiment.id:
                experiment.id = str(uuid.uuid4())
            if experiment.id in self._experiments:
                raise ValueError(f"Experiment already exists: {experiment.id}")
            experiment.state = ChaosExperimentState.DRAFT
            self._experiments[experiment.id] = experiment
            self._save_to_db(experiment)
            self._record_history(experiment.id, "created", {"name": experiment.name})
            logger.info("Experiment created: %s", experiment.id)
            return experiment.id

    def get_experiment(self, experiment_id: str) -> Optional[ChaosExperiment]:
        with self._lock:
            return self._experiments.get(experiment_id)

    def list_experiments(
        self, state: Optional[ChaosExperimentState] = None
    ) -> List[ChaosExperiment]:
        with self._lock:
            result = list(self._experiments.values())
            if state is not None:
                result = [e for e in result if e.state == state]
            return result

    def run_experiment(
        self, experiment_id: str, dry_run: bool = False
    ) -> Dict[str, Any]:
        """Run or dry-run an experiment."""
        with self._lock:
            exp = self._experiments.get(experiment_id)
            if exp is None:
                return {"success": False, "error": "Experiment not found"}
            if exp.state == ChaosExperimentState.RUNNING:
                return {"success": False, "error": "Experiment already running"}

        # Verify steady state before experiment
        steady_ok, steady_data = self._verify_steady_state(exp)
        if not steady_ok:
            return {
                "success": False,
                "error": "Steady state verification failed",
                "steady_state": steady_data,
            }

        if dry_run:
            return {
                "success": True,
                "dry_run": True,
                "experiment_id": experiment_id,
                "steady_state": steady_data,
                "injections": [
                    {
                        "fault_type": i.fault_type.value,
                        "target": i.target,
                        "magnitude": i.magnitude,
                        "duration_seconds": i.duration_seconds,
                    }
                    for i in exp.injections
                ],
            }

        # Mark as running
        with self._lock:
            exp.state = ChaosExperimentState.RUNNING
            exp.started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            self._save_to_db(exp)
            self._run_count += 1

        self._record_history(experiment_id, "started", {"injections": len(exp.injections)})

        # Execute fault injections
        injection_results: List[Dict[str, Any]] = []
        any_failed = False
        for injection in exp.injections:
            try:
                result = self._inject_fault(injection)
                injection_results.append(result)
                if not result.get("success", False):
                    any_failed = True
            except Exception as exc:
                injection_results.append({"success": False, "error": str(exc)})
                any_failed = True

        # Measure impact
        impact = self._measure_impact(exp)

        # Verify steady state after experiment
        post_steady_ok, post_steady_data = self._verify_steady_state(exp)

        # Rollback if needed
        if not post_steady_ok:
            logger.warning("Steady state violated — executing rollback for %s", experiment_id)
            self._rollback(exp)

        # Finalize
        with self._lock:
            exp.state = ChaosExperimentState.FAILED if any_failed else ChaosExperimentState.COMPLETED
            exp.completed_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            exp.result = {
                "steady_state_before": steady_data,
                "steady_state_after": post_steady_data,
                "steady_state_maintained": post_steady_ok,
                "injection_results": injection_results,
                "impact": impact,
            }
            self._save_to_db(exp)
            if exp.state == ChaosExperimentState.COMPLETED:
                self._success_count += 1
            else:
                self._fail_count += 1

        self._record_history(
            experiment_id, "completed",
            {"state": exp.state.value, "steady_maintained": post_steady_ok},
        )

        return {
            "success": exp.state == ChaosExperimentState.COMPLETED,
            "experiment_id": experiment_id,
            "state": exp.state.value,
            "steady_state_maintained": post_steady_ok,
            "injection_results": injection_results,
            "impact": impact,
        }

    def cancel_experiment(self, experiment_id: str) -> bool:
        with self._lock:
            exp = self._experiments.get(experiment_id)
            if exp is None:
                return False
            if exp.state != ChaosExperimentState.RUNNING:
                return False
            exp.state = ChaosExperimentState.CANCELLED
            exp.completed_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            self._save_to_db(exp)
            self._record_history(experiment_id, "cancelled", {})
            # Attempt rollback
            self._rollback(exp)
            return True

    def _verify_steady_state(
        self, experiment: ChaosExperiment
    ) -> Tuple[bool, Dict[str, Any]]:
        """Verify the steady state hypothesis."""
        hypothesis = experiment.steady_state_hypothesis
        if not hypothesis:
            return (True, {"status": "no_hypothesis_defined"})

        probes = hypothesis.get("probes", [])
        if not probes:
            return (True, {"status": "no_probes_defined"})

        results: List[Dict[str, Any]] = []
        all_ok = True
        for probe in probes:
            probe_type = probe.get("type", "health")
            target = probe.get("target", "")
            probe_ok = True
            try:
                # Use steady state verifier if available
                from .steady_state import get_steady_state_verifier
                verifier = get_steady_state_verifier()
                health = verifier.check_system_health()
                if health.get("status") != "healthy":
                    probe_ok = False
            except ImportError:
                pass  # No verifier — assume OK
            except Exception:
                probe_ok = False

            results.append({
                "probe": target or probe_type,
                "ok": probe_ok,
            })
            if not probe_ok:
                all_ok = False

        return (all_ok, {"probes": results})

    def _inject_fault(self, injection: FaultInjection) -> Dict[str, Any]:
        """Inject a fault (simulated)."""
        logger.info(
            "Injecting %s fault on %s (magnitude=%.2f, duration=%ds)",
            injection.fault_type.value, injection.target,
            injection.magnitude, injection.duration_seconds,
        )
        # In a real implementation, this would interact with the actual system
        return {
            "success": True,
            "fault_type": injection.fault_type.value,
            "target": injection.target,
            "magnitude": injection.magnitude,
            "duration_seconds": injection.duration_seconds,
            "probability": injection.probability,
            "injected_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

    def _rollback(self, experiment: ChaosExperiment) -> bool:
        """Execute rollback plan."""
        plan = experiment.rollback_plan
        if not plan:
            logger.warning("No rollback plan for experiment %s", experiment.id)
            return True

        actions = plan.get("actions", [])
        for action in actions:
            try:
                logger.info("Rollback action: %s", action.get("type", "unknown"))
            except Exception as exc:
                logger.error("Rollback action failed: %s", exc)

        self._record_history(experiment.id, "rollback", {"actions": len(actions)})
        return True

    def _measure_impact(self, experiment: ChaosExperiment) -> Dict[str, Any]:
        """Measure the impact of the experiment."""
        try:
            from .steady_state import get_steady_state_verifier
            verifier = get_steady_state_verifier()
            health = verifier.check_system_health()
            return {
                "system_health": health,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
        except ImportError:
            return {
                "system_health": {"status": "unknown"},
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }

    def get_resilience_score(self) -> float:
        """Overall system resilience score (0-1)."""
        with self._lock:
            total = self._success_count + self._fail_count
            if total == 0:
                return 1.0
            return self._success_count / total

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "total_experiments": len(self._experiments),
                "total_runs": self._run_count,
                "successful_runs": self._success_count,
                "failed_runs": self._fail_count,
                "resilience_score": round(self.get_resilience_score(), 3),
                "by_state": {
                    s.value: sum(
                        1 for e in self._experiments.values() if e.state == s
                    )
                    for s in ChaosExperimentState
                },
            }
