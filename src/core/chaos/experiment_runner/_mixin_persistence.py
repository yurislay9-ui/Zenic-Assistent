"""Persistence mixin for ChaosExperimentRunner."""

from __future__ import annotations
import json
import logging
import sqlite3
import time
from typing import Any, Dict, List, Optional

from ..types import ChaosExperiment, FaultInjection, FaultType, ChaosExperimentState
from ._types import DB_DIR, DB_PATH
from ._helpers import _retry

logger = logging.getLogger("zenic_agents.core.chaos.experiment_runner")


class ChaosPersistenceMixin:
    """Mixin providing SQLite persistence for ChaosExperimentRunner.

    Expects the host class to have ``_db_path``, ``_experiments``,
    and ``_lock`` attributes.
    """

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
