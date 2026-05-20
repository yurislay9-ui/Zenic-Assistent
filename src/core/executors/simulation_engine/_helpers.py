"""
Simulation Engine — Retry helper and SQLite history persistence utilities.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
import uuid
from typing import Any, Optional

from ._types import SimulationResult

logger = logging.getLogger(__name__)


def retry(
    fn: Any,
    max_retries: int = 2,
    base_delay: float = 0.1,
    label: str = "simulation",
) -> Any:
    """Execute *fn* with exponential-backoff retry.

    Default is 2 retries with 0.1s base delay.
    """
    last_exc: Optional[Exception] = None
    for attempt in range(max_retries):
        try:
            return fn()
        except Exception as exc:
            last_exc = exc
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                logger.debug(
                    "%s: retry %d/%d after %.2fs — %s",
                    label, attempt + 1, max_retries, delay, exc,
                )
                time.sleep(delay)
            else:
                logger.warning(
                    "%s: failed after %d attempts — %s",
                    label, max_retries, exc,
                )
    raise last_exc  # type: ignore[misc]


def ensure_db(db_path: Optional[str], history_db_name: str) -> str:
    """Ensure the SQLite history database exists and return its path.

    Args:
        db_path: Existing path or None to create a new one.
        history_db_name: Filename for the SQLite database.

    Returns:
        The database file path.
    """
    if db_path is not None:
        return db_path

    try:
        from src.core.shared.db_initializer import get_data_dir
        data_dir = get_data_dir()
    except Exception:
        import tempfile
        data_dir = tempfile.mkdtemp(prefix="zenic_sim_")

    resolved_path = str(data_dir / history_db_name)

    def _init_schema() -> None:
        conn = sqlite3.connect(resolved_path)
        try:
            conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                """
                CREATE TABLE IF NOT EXISTS _simulation_history (
                    simulation_id TEXT PRIMARY KEY,
                    dag_id        TEXT NOT NULL,
                    nodes_simulated INTEGER NOT NULL DEFAULT 0,
                    would_succeed  INTEGER NOT NULL DEFAULT 1,
                    total_duration_ms REAL NOT NULL DEFAULT 0.0,
                    result_json   TEXT NOT NULL DEFAULT '{}',
                    created_at    REAL NOT NULL
                )
                """
            )
            conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                "CREATE INDEX IF NOT EXISTS idx_sim_created "
                "ON _simulation_history(created_at)"
            )
            conn.commit()
        finally:
            conn.close()

    try:
        retry(_init_schema, max_retries=3, base_delay=0.1, label="SimulationEngine._ensure_db")
    except Exception as exc:
        logger.warning("SimulationEngine: could not init history DB: %s", exc)

    return resolved_path


def persist_result(db_path: str, result: SimulationResult, max_history: int = 50) -> None:
    """Persist a simulation result (keeping only the last *max_history*)."""
    simulation_id = uuid.uuid4().hex
    created_at = time.time()

    def _do_persist() -> None:
        conn = sqlite3.connect(db_path)
        try:
            conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                """
                INSERT INTO _simulation_history
                    (simulation_id, dag_id, nodes_simulated,
                     would_succeed, total_duration_ms,
                     result_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    simulation_id,
                    result.dag_id,
                    result.nodes_simulated,
                    1 if result.would_succeed else 0,
                    result.total_duration_ms,
                    json.dumps(result.to_dict(), default=str),
                    created_at,
                ),
            )

            # Prune to keep only the last max_history
            conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                """
                DELETE FROM _simulation_history
                WHERE simulation_id NOT IN (
                    SELECT simulation_id FROM _simulation_history
                    ORDER BY created_at DESC
                    LIMIT ?
                )
                """,
                (max_history,),
            )

            conn.commit()
        finally:
            conn.close()

    try:
        retry(_do_persist, max_retries=2, base_delay=0.1, label="SimulationEngine._persist_result")
    except Exception as exc:
        logger.debug("SimulationEngine: persist failed: %s", exc)
