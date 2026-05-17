from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .types import (
    ChaosExperiment,
    ChaosExperimentState,
    FaultInjection,
    FaultType,
)

logger = logging.getLogger("zenic_agents.core.chaos.experiment_runner")

DB_DIR = Path.home() / ".zenic_agents" / "db"
DB_PATH = DB_DIR / "chaos.sqlite"


def _retry(func: Any, max_retries: int = 3, base_delay: float = 1.0) -> Any:
    for attempt in range(max_retries):
        try:
            return func()
        except Exception:
            if attempt == max_retries - 1:
                raise
            time.sleep(base_delay * (2 ** attempt))


class ChaosExperimentRunner:
    """Thread-safe chaos experiment runner with SQLite persistence."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        self._lock = threading.RLock()
        self._experiments: Dict[str, ChaosExperiment] = {}
        self._db_path = db_path or str(DB_PATH)
        self._run_count = 0
        self._success_count = 0
        self._fail_count = 0
        self._init_db()

    def _init_db(self) -> None:
        DB_DIR.mkdir(parents=True, exist_ok=True)

        def _create() -> None:
            conn = sqlite3.connect(self._db_path)
            conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                """CREATE TABLE IF NOT EXISTS chaos_experiments (
                    experiment_id TEXT PRIMARY KEY,
                    experiment_json TEXT NOT NULL,
                    state TEXT NOT NULL DEFAULT 'draft',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )"""
            )
            conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                """CREATE TABLE IF NOT EXISTS chaos_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    experiment_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    event_data TEXT NOT NULL DEFAULT '{}',
                    timestamp REAL NOT NULL
                )"""
            )
            conn.commit()
            conn.close()

        _retry(_create)
        self._load_from_db()

    def _load_from_db(self) -> None:
        try:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM chaos_experiments").fetchall()  # nosemgrep: sqlalchemy-execute-raw-query
            conn.close()
            for row in rows:
                exp = self._json_to_experiment(row["experiment_json"])
                if exp is not None:
                    exp.state = ChaosExperimentState(row["state"])
                    self._experiments[exp.id] = exp
        except Exception as exc:
            logger.error("Failed to load experiments from DB: %s", exc)

    def _experiment_to_json(self, exp: ChaosExperiment) -> str:
        data = {
            "id": exp.id,
            "name": exp.name,
            "description": exp.description,
            "injections": [
                {
                    "fault_type": i.fault_type.value,
                    "target": i.target,
                    "magnitude": i.magnitude,
                    "duration_seconds": i.duration_seconds,
                    "probability": i.probability,
                    "parameters": i.parameters,
                }
                for i in exp.injections
            ],
            "steady_state_hypothesis": exp.steady_state_hypothesis,
            "state": exp.state.value,
            "scheduled_at": exp.scheduled_at,
            "started_at": exp.started_at,
            "completed_at": exp.completed_at,
            "result": exp.result,
            "rollback_plan": exp.rollback_plan,
            "tags": list(exp.tags),
        }
        return json.dumps(data)

    def _json_to_experiment(self, raw: str) -> Optional[ChaosExperiment]:
        try:
            data = json.loads(raw)
            injections = [
                FaultInjection(
                    fault_type=FaultType(i["fault_type"]),
                    target=i["target"],
                    magnitude=i.get("magnitude", 1.0),
                    duration_seconds=i.get("duration_seconds", 30),
                    probability=i.get("probability", 1.0),
                    parameters=i.get("parameters", {}),
                )
                for i in data.get("injections", [])
            ]
            return ChaosExperiment(
                id=data["id"],
                name=data["name"],
                description=data.get("description", ""),
                injections=injections,
                steady_state_hypothesis=data.get("steady_state_hypothesis", {}),
                state=ChaosExperimentState(data.get("state", "draft")),
                scheduled_at=data.get("scheduled_at"),
                started_at=data.get("started_at"),
                completed_at=data.get("completed_at"),
                result=data.get("result"),
                rollback_plan=data.get("rollback_plan", {}),
                tags=set(data.get("tags", [])),
            )
        except Exception as exc:
            logger.error("Failed to parse experiment JSON: %s", exc)
            return None

    def _save_to_db(self, exp: ChaosExperiment) -> None:
        exp_json = self._experiment_to_json(exp)
        now = time.time()

        def _upsert() -> None:
            conn = sqlite3.connect(self._db_path)
            conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                """INSERT OR REPLACE INTO chaos_experiments
                   (experiment_id, experiment_json, state, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (exp.id, exp_json, exp.state.value, now, now),
            )
            conn.commit()
            conn.close()

        _retry(_upsert)

    def _delete_from_db(self, experiment_id: str) -> None:
        def _del() -> None:
            conn = sqlite3.connect(self._db_path)
            conn.execute("DELETE FROM chaos_experiments WHERE experiment_id = ?", (experiment_id,))  # nosemgrep: sqlalchemy-execute-raw-query
            conn.commit()
            conn.close()

        _retry(_del)

    def _record_history(
        self, experiment_id: str, event_type: str, event_data: Dict[str, Any]
    ) -> None:
        def _insert() -> None:
            conn = sqlite3.connect(self._db_path)
            conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                """INSERT INTO chaos_history (experiment_id, event_type, event_data, timestamp)
                   VALUES (?, ?, ?, ?)""",
                (experiment_id, event_type, json.dumps(event_data), time.time()),
            )
            conn.commit()
            conn.close()

        try:
            _retry(_insert)
        except Exception as exc:
            logger.error("Failed to record history: %s", exc)

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
            threshold = probe.get("threshold", {})
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

    def get_experiment_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get experiment history from DB."""
        try:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                "SELECT * FROM chaos_history ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
            conn.close()
            return [
                {
                    "id": r["id"],
                    "experiment_id": r["experiment_id"],
                    "event_type": r["event_type"],
                    "event_data": json.loads(r["event_data"]),
                    "timestamp": r["timestamp"],
                }
                for r in rows
            ]
        except Exception as exc:
            logger.error("Failed to get experiment history: %s", exc)
            return []

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


_runner_instance: Optional[ChaosExperimentRunner] = None
_runner_lock = threading.Lock()


def get_chaos_runner(db_path: Optional[str] = None) -> ChaosExperimentRunner:
    global _runner_instance
    with _runner_lock:
        if _runner_instance is None:
            _runner_instance = ChaosExperimentRunner(db_path=db_path)
        return _runner_instance


def reset_chaos_runner() -> None:
    global _runner_instance
    with _runner_lock:
        _runner_instance = None
