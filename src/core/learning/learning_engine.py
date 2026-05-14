from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from .outcome_tracker import ActionOutcome, OutcomeStatus, get_outcome_tracker

logger = logging.getLogger(__name__)

DB_DIR = Path.home() / ".zenic_agents" / "db"
DB_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DB_DIR / "learning.sqlite"


class LearningStrategy(str, Enum):
    CONSERVATIVE = "conservative"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"


@dataclass
class LearningInsight:
    id: str = ""
    insight_type: str = ""
    pattern: str = ""
    recommendation: str = ""
    confidence: float = 0.0
    supporting_outcomes: List[str] = field(default_factory=list)
    created_at: str = ""
    applied: bool = False


def _new_id(prefix: str = "ins") -> str:
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


class LearningEngine:
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
                    cursor = conn.execute(
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
                    cursor = conn.execute(
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
                    total = conn.execute("SELECT COUNT(*) FROM learning_insights").fetchone()[0]
                    applied = conn.execute(
                        "SELECT COUNT(*) FROM learning_insights WHERE applied = 1"
                    ).fetchone()[0]

                    type_counts: Dict[str, int] = {}
                    cursor = conn.execute(
                        "SELECT insight_type, COUNT(*) FROM learning_insights GROUP BY insight_type"
                    )
                    for itype, cnt in cursor.fetchall():
                        type_counts[itype] = cnt

                    avg_conf = conn.execute(
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

    # ── Internal pattern detection ─────────────────────────────

    def _detect_failure_patterns(
        self, tracker: Any, action_type: Optional[str] = None
    ) -> List[LearningInsight]:
        insights: List[LearningInsight] = []
        analysis = tracker.analyze_failures(action_type, hours=168)

        for error_msg, count in analysis.get("top_errors", {}).items():
            if count >= 2:
                insights.append(LearningInsight(
                    id=_new_id("ins"),
                    insight_type="failure_pattern",
                    pattern=f"Recurring error: {error_msg[:100]}",
                    recommendation=f"Investigate and fix root cause of: {error_msg[:80]}",
                    confidence=0.0,
                    supporting_outcomes=[],
                    created_at=_now_iso(),
                ))

        for atype, count in analysis.get("failure_by_type", {}).items():
            if count >= 3:
                insights.append(LearningInsight(
                    id=_new_id("ins"),
                    insight_type="failure_pattern",
                    pattern=f"High failure count for {atype}: {count} failures",
                    recommendation=f"Review {atype} implementation for reliability issues",
                    confidence=0.0,
                    supporting_outcomes=[],
                    created_at=_now_iso(),
                ))

        if analysis.get("avg_failure_duration_ms", 0) > 5000:
            insights.append(LearningInsight(
                id=_new_id("ins"),
                insight_type="performance_degradation",
                pattern=f"Slow failures averaging {analysis['avg_failure_duration_ms']:.0f}ms",
                recommendation="Add timeout controls and circuit breakers",
                confidence=0.0,
                supporting_outcomes=[],
                created_at=_now_iso(),
            ))

        return insights

    def _detect_success_patterns(
        self, tracker: Any, action_type: Optional[str] = None
    ) -> List[LearningInsight]:
        insights: List[LearningInsight] = []

        stats = tracker.get_stats()
        for atype, count in stats.get("type_counts", {}).items():
            if action_type and atype != action_type:
                continue
            rate = tracker.get_success_rate(atype, hours=168)
            if rate >= 0.95 and count >= 10:
                insights.append(LearningInsight(
                    id=_new_id("ins"),
                    insight_type="success_pattern",
                    pattern=f"High success rate for {atype}: {rate*100:.1f}%",
                    recommendation=f"Use {atype} approach as template for similar operations",
                    confidence=0.0,
                    supporting_outcomes=[],
                    created_at=_now_iso(),
                ))

        return insights

    def _compute_confidence(
        self, insight: LearningInsight, tracker: Any
    ) -> float:
        base = 0.3

        if insight.insight_type == "failure_pattern":
            analysis = tracker.analyze_failures(hours=168)
            total = analysis.get("total_failures", 0)
            if total >= 5:
                base += 0.2
            if total >= 10:
                base += 0.15
        elif insight.insight_type == "success_pattern":
            base += 0.2
        elif insight.insight_type == "performance_degradation":
            base += 0.1

        if len(insight.supporting_outcomes) >= 3:
            base += 0.1

        return round(min(base, 1.0), 4)

    def _persist_insight(self, insight: LearningInsight) -> None:
        with self._lock:
            def _insert() -> None:
                conn = sqlite3.connect(self._db_path)
                try:
                    conn.execute(
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

_instance: Optional[LearningEngine] = None
_instance_lock = threading.Lock()


def get_learning_engine() -> LearningEngine:
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = LearningEngine()
    return _instance


def reset_learning_engine() -> None:
    global _instance
    with _instance_lock:
        _instance = None
