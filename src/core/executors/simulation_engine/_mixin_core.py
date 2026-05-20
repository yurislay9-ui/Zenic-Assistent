"""simulation_engine — Core mixin (init, lazy deps, simulate_dag)."""

from __future__ import annotations

import threading
import time
import uuid
from typing import Any, Dict, List, Optional

from ._types import *  # noqa: F403
from ._helpers import _ensure_db, _persist_result


class SimulationEngineCoreMixin:
    """Core initialization and DAG simulation for SimulationEngine."""

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

    def simulate_dag(self, ctx: Dict[str, Any]) -> SimulationResult:  # noqa: F821
        """Run through the DAG nodes in dry-run mode.

        Iterates over the nodes in *ctx* (key ``"dag_nodes"`` or
        ``"actions"``) and simulates each one via the DryRunExecutor.
        All operations are in-memory only.

        Transient errors are retried up to 2 times.

        Args:
            ctx: DAG context dictionary.

        Returns:
            A SimulationResult summarising the simulation.
        """
        with self._lock:
            self._simulation_count += 1
            dag_id = ctx.get("dag_id", uuid.uuid4().hex[:12])
            nodes = ctx.get("dag_nodes", ctx.get("actions", []))

            if not nodes:
                result = SimulationResult(  # noqa: F821
                    dag_id=dag_id,
                    nodes_simulated=0,
                    would_succeed=True,
                    node_results={"status": "NO_NODES"},
                )
                __import__("logging").getLogger("zenic_agents.executors.simulation_engine").debug(
                    "SimulationEngine: simulate_dag — no nodes in ctx"
                )
                return result

            start = time.monotonic()

            def _run_simulation() -> SimulationResult:  # noqa: F821
                simulated_actions: List[Any] = []
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
                        __import__("logging").getLogger("zenic_agents.executors.simulation_engine").debug(
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
                        __import__("logging").getLogger("zenic_agents.executors.simulation_engine").warning(
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
                result = _retry(  # noqa: F821
                    _run_simulation,
                    max_retries=2,
                    base_delay=0.1,
                    label=f"SimulationEngine.simulate_dag({dag_id})",
                )
            except Exception as exc:
                __import__("logging").getLogger("zenic_agents.executors.simulation_engine").error(
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

            __import__("logging").getLogger("zenic_agents.executors.simulation_engine").info(
                "SimulationEngine: simulate_dag %s — nodes=%d succeed=%s duration=%.1fms",
                dag_id, result.nodes_simulated, result.would_succeed,
                result.total_duration_ms,
            )

            return result
