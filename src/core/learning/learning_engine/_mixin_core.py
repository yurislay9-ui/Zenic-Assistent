"""Core logic for learning_engine."""

from __future__ import annotations
import json
import logging
import sqlite3
import threading
import time
import uuid
from collections import Counter
from typing import Any, Dict, List, Optional, Set
from .outcome_tracker import ActionOutcome, OutcomeStatus, get_outcome_tracker
from ._types import *
from ._helpers import *
from ._mixin_patterns import PatternDetectionMixin

logger = logging.getLogger(__name__)

class LearningEngine(PatternDetectionMixin):
    """Self-learning engine that analyzes outcomes and generates insights."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        self._lock = threading.RLock()
        self._db_path = db_path or str(DB_PATH)
        self._init_db()

    def _init_db(self) -> None:
        def _create() -> None:
            conn = sqlite3.connect(self._db_path)
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS learning_insights (
                    id TEXT PRIMARY KEY,
                    insight_type TEXT NOT NULL DEFAULT '',
                    pattern TEXT NOT NULL DEFAULT '',
                    recommendation TEXT NOT NULL DEFAULT '',
                    confidence REAL NOT NULL DEFAULT 0.0,
                    supporting_outcomes TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL DEFAULT '',
                    applied INTEGER NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS idx_insights_type ON learning_insights(insight_type);
                CREATE INDEX IF NOT EXISTS idx_insights_confidence ON learning_insights(confidence);
                CREATE INDEX IF NOT EXISTS idx_insights_applied ON learning_insights(applied);
            """)
            conn.commit()
            conn.close()

        _retry(_create)

    def analyze_patterns(
        self, action_type: Optional[str] = None
    ) -> List[LearningInsight]:
        tracker = get_outcome_tracker()
        insights: List[LearningInsight] = []

        failure_insights = self._detect_failure_patterns(tracker, action_type)
        insights.extend(failure_insights)

        success_insights = self._detect_success_patterns(tracker, action_type)
        insights.extend(success_insights)

        for insight in insights:
            insight.confidence = self._compute_confidence(insight, tracker)
            self._persist_insight(insight)

        return insights

    def generate_recommendation(self, insight: LearningInsight) -> Dict[str, Any]:
        if insight.insight_type == "failure_pattern":
            return {
                "action": "investigate_and_fix",
                "pattern": insight.pattern,
                "recommendation": insight.recommendation,
                "confidence": insight.confidence,
                "steps": [
                    f"Review failures matching: {insight.pattern}",
                    "Identify root cause from error messages",
                    "Apply fix and monitor",
                ],
            }
        elif insight.insight_type == "success_pattern":
            return {
                "action": "reinforce",
                "pattern": insight.pattern,
                "recommendation": insight.recommendation,
                "confidence": insight.confidence,
                "steps": [
                    f"Document successful pattern: {insight.pattern}",
                    "Apply pattern to similar action types",
                    "Monitor for consistency",
                ],
            }
        elif insight.insight_type == "performance_degradation":
            return {
                "action": "optimize",
                "pattern": insight.pattern,
                "recommendation": insight.recommendation,
                "confidence": insight.confidence,
                "steps": [
                    "Profile slow operations",
                    "Identify bottlenecks",
                    "Apply optimizations",
                ],
            }
        return {
            "action": "review",
            "pattern": insight.pattern,
            "recommendation": insight.recommendation,
            "confidence": insight.confidence,
        }

    def apply_insight(self, insight_id: str) -> bool:
        with self._lock:
            def _apply() -> bool:
                conn = sqlite3.connect(self._db_path)
                try:
                    cursor = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                        "UPDATE learning_insights SET applied = 1 WHERE id = ?",
                        (insight_id,),
                    )
                    conn.commit()
                    return cursor.rowcount > 0
                finally:
                    conn.close()

            return _retry(_apply)

    def get_insights(
        self,
        min_confidence: float = 0.0,
        applied: Optional[bool] = None,
    ) -> List[LearningInsight]:
        with self._lock:
            def _fetch() -> List[LearningInsight]:
                conn = sqlite3.connect(self._db_path)
                try:
                    conditions: List[str] = ["confidence >= ?"]
                    params: List[Any] = [min_confidence]
                    if applied is not None:
                        conditions.append("applied = ?")
                        params.append(1 if applied else 0)

                    where = " AND ".join(conditions)
                    cursor = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                        f"SELECT * FROM learning_insights WHERE {where} "
                        f"ORDER BY confidence DESC",
                        params,
                    )
                    return [self._insight_from_row(row) for row in cursor.fetchall()]
                finally:
                    conn.close()

            return _retry(_fetch)

    def auto_learn(
        self, strategy: LearningStrategy = LearningStrategy.MODERATE
    ) -> Dict[str, Any]:
        tracker = get_outcome_tracker()
        insights = self.analyze_patterns()
        result: Dict[str, Any] = {
            "insights_found": len(insights),
            "applied": 0,
            "skipped": 0,
            "recommendations": [],
        }

        thresholds = {
            LearningStrategy.CONSERVATIVE: 0.8,
            LearningStrategy.MODERATE: 0.6,
            LearningStrategy.AGGRESSIVE: 0.4,
        }
        threshold = thresholds.get(strategy, 0.6)

        for insight in insights:
            if insight.confidence >= threshold:
                rec = self.generate_recommendation(insight)
                result["recommendations"].append(rec)
                if strategy == LearningStrategy.AGGRESSIVE:
                    self.apply_insight(insight.id)
                result["applied"] += 1
            else:
                result["skipped"] += 1

        return result

    def get_failure_prediction(
        self, action_type: str, context: Dict[str, Any]
    ) -> float:
        tracker = get_outcome_tracker()
        recent_rate = tracker.get_success_rate(action_type, hours=24)
        failure_rate = 1.0 - recent_rate

        failure_analysis = tracker.analyze_failures(action_type, hours=24)
        error_diversity = len(failure_analysis.get("top_errors", {}))

        context_risk = 0.0
        if context.get("retry_count", 0) > 2:
            context_risk += 0.2
        if context.get("complexity", "low") == "high":
            context_risk += 0.15
        if context.get("dependency_count", 0) > 5:
            context_risk += 0.1

        error_factor = min(error_diversity * 0.05, 0.2)
        prediction = min(failure_rate + error_factor + context_risk, 1.0)
        return round(max(prediction, 0.0), 4)

    def get_optimization_hints(self, action_type: str) -> List[Dict[str, Any]]:
        tracker = get_outcome_tracker()
        hints: List[Dict[str, Any]] = []

        history = tracker.get_action_history(action_type, limit=50)
        if not history:
            return hints

        durations = [h.duration_ms for h in history if h.duration_ms > 0]
        if durations:
            avg = sum(durations) / len(durations)
            slow = [h for h in history if h.duration_ms > avg * 2]
            if slow:
                hints.append({
                    "type": "slow_execution",
                    "message": f"{len(slow)} actions took >2x average ({avg:.0f}ms)",
                    "avg_duration_ms": round(avg, 2),
                    "slow_count": len(slow),
                })

        failures = [h for h in history if h.status != OutcomeStatus.SUCCESS]
        if len(failures) > len(history) * 0.3:
            hints.append({
                "type": "high_failure_rate",
                "message": f"Failure rate is {len(failures)/len(history)*100:.1f}%",
                "failure_count": len(failures),
                "total_count": len(history),
            })

        errors: Counter = Counter()
        for f in failures:
            if f.error_message:
                errors[f.error_message] += 1
        for msg, count in errors.most_common(3):
            hints.append({
                "type": "recurring_error",
                "message": f"Error '{msg[:80]}' occurred {count} times",
                "error": msg,
                "count": count,
            })

        return hints

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            def _calc() -> Dict[str, Any]:
                conn = sqlite3.connect(self._db_path)
                try:
                    total = conn.execute("SELECT COUNT(*) FROM learning_insights").fetchone()[0]  # nosemgrep: sqlalchemy-execute-raw-query
                    applied = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                        "SELECT COUNT(*) FROM learning_insights WHERE applied = 1"
                    ).fetchone()[0]

                    type_counts: Dict[str, int] = {}
                    cursor = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                        "SELECT insight_type, COUNT(*) FROM learning_insights GROUP BY insight_type"
                    )
                    for itype, cnt in cursor.fetchall():
                        type_counts[itype] = cnt

                    avg_conf = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                        "SELECT AVG(confidence) FROM learning_insights"
                    ).fetchone()[0] or 0.0

                    return {
                        "total_insights": total,
                        "applied_insights": applied,
                        "pending_insights": total - applied,
                        "type_counts": type_counts,
                        "avg_confidence": round(avg_conf, 4),
                    }
                finally:
                    conn.close()

            return _retry(_calc)

    def _persist_insight(self, insight: LearningInsight) -> None:
        with self._lock:
            def _insert() -> None:
                conn = sqlite3.connect(self._db_path)
                try:
                    conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                        """INSERT OR REPLACE INTO learning_insights
                           (id, insight_type, pattern, recommendation, confidence,
                            supporting_outcomes, created_at, applied)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            insight.id, insight.insight_type, insight.pattern,
                            insight.recommendation, insight.confidence,
                            json.dumps(insight.supporting_outcomes),
                            insight.created_at, 1 if insight.applied else 0,
                        ),
                    )
                    conn.commit()
                finally:
                    conn.close()

            _retry(_insert)

    @staticmethod
    def _insight_from_row(row: Any) -> LearningInsight:
        return LearningInsight(
            id=row[0],
            insight_type=row[1],
            pattern=row[2],
            recommendation=row[3],
            confidence=row[4],
            supporting_outcomes=json.loads(row[5]) if row[5] else [],
            created_at=row[6],
            applied=bool(row[7]),
        )


# ── Singleton ──────────────────────────────────────────────────
