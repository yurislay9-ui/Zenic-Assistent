from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DB_DIR = Path.home() / ".zenic_agents" / "db"
DB_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DB_DIR / "learning.sqlite"


class OutcomeStatus(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILURE = "failure"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


@dataclass
class ActionOutcome:
    id: str = ""
    action_id: str = ""
    action_type: str = ""
    expected_result: str = ""
    actual_result: str = ""
    status: OutcomeStatus = OutcomeStatus.SUCCESS
    duration_ms: int = 0
    error_message: Optional[str] = None
    feedback_score: float = 0.0
    timestamp: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


def _new_id(prefix: str = "out") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _now_iso() -> str:
    return datetime.utcnow().isoformat()


def _retry(func: Any, max_retries: int = 3, base_delay: float = 0.1) -> Any:
    last_exc: Optional[Exception] = None
    for attempt in range(max_retries):
        try:
            return func()
        except Exception as exc:
            last_exc = exc
            if attempt == max_retries - 1:
                raise
            time.sleep(base_delay * (2 ** attempt))
    raise last_exc  # type: ignore[misc]


class OutcomeTracker:
    """Thread-safe outcome tracking with SQLite persistence."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        self._lock = threading.RLock()
        self._db_path = db_path or str(DB_PATH)
        self._init_db()

    def _init_db(self) -> None:
        def _create() -> None:
            conn = sqlite3.connect(self._db_path)
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS learning_outcomes (
                    id TEXT PRIMARY KEY,
                    action_id TEXT NOT NULL,
                    action_type TEXT NOT NULL DEFAULT '',
                    expected_result TEXT NOT NULL DEFAULT '',
                    actual_result TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'success',
                    duration_ms INTEGER NOT NULL DEFAULT 0,
                    error_message TEXT,
                    feedback_score REAL NOT NULL DEFAULT 0.0,
                    timestamp TEXT NOT NULL DEFAULT '',
                    metadata TEXT NOT NULL DEFAULT '{}'
                );
                CREATE INDEX IF NOT EXISTS idx_outcomes_action_id ON learning_outcomes(action_id);
                CREATE INDEX IF NOT EXISTS idx_outcomes_action_type ON learning_outcomes(action_type);
                CREATE INDEX IF NOT EXISTS idx_outcomes_status ON learning_outcomes(status);
                CREATE INDEX IF NOT EXISTS idx_outcomes_timestamp ON learning_outcomes(timestamp);
            """)
            conn.commit()
            conn.close()

        _retry(_create)

    def record_outcome(
        self,
        action_id: str,
        action_type: str,
        expected: str,
        actual: str,
        status: OutcomeStatus,
        duration_ms: int = 0,
        error: Optional[str] = None,
        score: float = 0.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        outcome_id = _new_id("out")
        now = _now_iso()
        meta_json = json.dumps(metadata or {})

        with self._lock:
            def _insert() -> None:
                conn = sqlite3.connect(self._db_path)
                try:
                    conn.execute(
                        """INSERT INTO learning_outcomes
                           (id, action_id, action_type, expected_result, actual_result,
                            status, duration_ms, error_message, feedback_score, timestamp, metadata)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            outcome_id, action_id, action_type, expected, actual,
                            status.value, duration_ms, error, score, now, meta_json,
                        ),
                    )
                    conn.commit()
                finally:
                    conn.close()

            _retry(_insert)
        return outcome_id

    def get_outcome(self, outcome_id: str) -> Optional[ActionOutcome]:
        with self._lock:
            def _fetch() -> Optional[ActionOutcome]:
                conn = sqlite3.connect(self._db_path)
                try:
                    cursor = conn.execute(
                        "SELECT * FROM learning_outcomes WHERE id = ?", (outcome_id,)
                    )
                    row = cursor.fetchone()
                    if row is None:
                        return None
                    return self._outcome_from_row(row)
                finally:
                    conn.close()

            return _retry(_fetch)

    def get_action_history(
        self, action_type: str, limit: int = 100
    ) -> List[ActionOutcome]:
        with self._lock:
            def _fetch() -> List[ActionOutcome]:
                conn = sqlite3.connect(self._db_path)
                try:
                    cursor = conn.execute(
                        "SELECT * FROM learning_outcomes WHERE action_type = ? "
                        "ORDER BY timestamp DESC LIMIT ?",
                        (action_type, limit),
                    )
                    return [self._outcome_from_row(row) for row in cursor.fetchall()]
                finally:
                    conn.close()

            return _retry(_fetch)

    def get_success_rate(self, action_type: str, hours: int = 24) -> float:
        cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
        with self._lock:
            def _calc() -> float:
                conn = sqlite3.connect(self._db_path)
                try:
                    total = conn.execute(
                        "SELECT COUNT(*) FROM learning_outcomes "
                        "WHERE action_type = ? AND timestamp >= ?",
                        (action_type, cutoff),
                    ).fetchone()[0]
                    if total == 0:
                        return 0.0
                    success = conn.execute(
                        "SELECT COUNT(*) FROM learning_outcomes "
                        "WHERE action_type = ? AND status = 'success' AND timestamp >= ?",
                        (action_type, cutoff),
                    ).fetchone()[0]
                    return round(success / total, 4)
                finally:
                    conn.close()

            return _retry(_calc)

    def get_performance_trend(
        self, action_type: str, days: int = 7
    ) -> List[Dict[str, Any]]:
        with self._lock:
            def _calc() -> List[Dict[str, Any]]:
                conn = sqlite3.connect(self._db_path)
                try:
                    results: List[Dict[str, Any]] = []
                    for i in range(days):
                        day = datetime.utcnow() - timedelta(days=days - 1 - i)
                        day_start = day.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
                        day_end = day.replace(hour=23, minute=59, second=59, microsecond=999999).isoformat()

                        total = conn.execute(
                            "SELECT COUNT(*) FROM learning_outcomes "
                            "WHERE action_type = ? AND timestamp >= ? AND timestamp <= ?",
                            (action_type, day_start, day_end),
                        ).fetchone()[0]
                        success = conn.execute(
                            "SELECT COUNT(*) FROM learning_outcomes "
                            "WHERE action_type = ? AND status = 'success' AND timestamp >= ? AND timestamp <= ?",
                            (action_type, day_start, day_end),
                        ).fetchone()[0]
                        avg_duration = conn.execute(
                            "SELECT AVG(duration_ms) FROM learning_outcomes "
                            "WHERE action_type = ? AND timestamp >= ? AND timestamp <= ?",
                            (action_type, day_start, day_end),
                        ).fetchone()[0] or 0.0

                        results.append({
                            "date": day_start[:10],
                            "total": total,
                            "successes": success,
                            "success_rate": round(success / total, 4) if total > 0 else 0.0,
                            "avg_duration_ms": round(avg_duration, 2),
                        })
                    return results
                finally:
                    conn.close()

            return _retry(_calc)

    def analyze_failures(
        self, action_type: Optional[str] = None, hours: int = 24
    ) -> Dict[str, Any]:
        cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
        with self._lock:
            def _analyze() -> Dict[str, Any]:
                conn = sqlite3.connect(self._db_path)
                try:
                    conditions = ["status != 'success'", "timestamp >= ?"]
                    params: List[Any] = [cutoff]
                    if action_type:
                        conditions.append("action_type = ?")
                        params.append(action_type)

                    where = " AND ".join(conditions)

                    total_failures = conn.execute(
                        f"SELECT COUNT(*) FROM learning_outcomes WHERE {where}", params
                    ).fetchone()[0]

                    error_counts: Dict[str, int] = {}
                    cursor = conn.execute(
                        f"SELECT error_message, COUNT(*) FROM learning_outcomes "
                        f"WHERE {where} AND error_message IS NOT NULL "
                        f"GROUP BY error_message ORDER BY COUNT(*) DESC LIMIT 10",
                        params,
                    )
                    for msg, cnt in cursor.fetchall():
                        error_counts[msg or "unknown"] = cnt

                    type_counts: Dict[str, int] = {}
                    cursor = conn.execute(
                        f"SELECT action_type, COUNT(*) FROM learning_outcomes "
                        f"WHERE {where} GROUP BY action_type ORDER BY COUNT(*) DESC",
                        params,
                    )
                    for at, cnt in cursor.fetchall():
                        type_counts[at] = cnt

                    avg_duration = conn.execute(
                        f"SELECT AVG(duration_ms) FROM learning_outcomes WHERE {where}", params
                    ).fetchone()[0] or 0.0

                    return {
                        "total_failures": total_failures,
                        "top_errors": error_counts,
                        "failure_by_type": type_counts,
                        "avg_failure_duration_ms": round(avg_duration, 2),
                        "window_hours": hours,
                    }
                finally:
                    conn.close()

            return _retry(_analyze)

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            def _calc() -> Dict[str, Any]:
                conn = sqlite3.connect(self._db_path)
                try:
                    total = conn.execute("SELECT COUNT(*) FROM learning_outcomes").fetchone()[0]

                    status_counts: Dict[str, int] = {}
                    cursor = conn.execute(
                        "SELECT status, COUNT(*) FROM learning_outcomes GROUP BY status"
                    )
                    for status, cnt in cursor.fetchall():
                        status_counts[status] = cnt

                    type_counts: Dict[str, int] = {}
                    cursor = conn.execute(
                        "SELECT action_type, COUNT(*) FROM learning_outcomes GROUP BY action_type"
                    )
                    for at, cnt in cursor.fetchall():
                        type_counts[at] = cnt

                    avg_score = conn.execute(
                        "SELECT AVG(feedback_score) FROM learning_outcomes"
                    ).fetchone()[0] or 0.0

                    return {
                        "total_outcomes": total,
                        "status_counts": status_counts,
                        "type_counts": type_counts,
                        "avg_feedback_score": round(avg_score, 4),
                    }
                finally:
                    conn.close()

            return _retry(_calc)

    @staticmethod
    def _outcome_from_row(row: Any) -> ActionOutcome:
        return ActionOutcome(
            id=row[0],
            action_id=row[1],
            action_type=row[2],
            expected_result=row[3],
            actual_result=row[4],
            status=OutcomeStatus(row[5]),
            duration_ms=row[6],
            error_message=row[7],
            feedback_score=row[8],
            timestamp=row[9],
            metadata=json.loads(row[10]) if row[10] else {},
        )


# ── Singleton ──────────────────────────────────────────────────

_instance: Optional[OutcomeTracker] = None
_instance_lock = threading.Lock()


def get_outcome_tracker() -> OutcomeTracker:
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = OutcomeTracker()
    return _instance


def reset_outcome_tracker() -> None:
    global _instance
    with _instance_lock:
        _instance = None
