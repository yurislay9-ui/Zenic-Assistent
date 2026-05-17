"""
Zenic-Agents Asistente - Risk-Based Approval Routing (Phase C3)

Routes approval requests based on a contextual risk score computed from
multiple factors: action category, monetary amount, target environment,
time of day, and user history.

Scoring heuristics:
  - Action category:  financial=0.8, destructive=0.9, system=0.7, safe=0.1
  - Amount / size factor:  larger → higher risk
  - Target sensitivity:  production vs test
  - Time of day:  off-hours → higher risk
  - User history:  new users → higher risk

Role mapping (risk_score → recommended_role):
  < 0.3  → auto-approve
  0.3–0.5 → operador
  0.5–0.7 → gerente
  ≥ 0.7  → admin

Persistence: SQLite with retry logic.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3
_RETRY_DELAY = 0.1

# Category → base risk score
_ACTION_CATEGORY_SCORES: Dict[str, float] = {
    "financial": 0.8,
    "payment": 0.8,
    "destructive": 0.9,
    "delete": 0.9,
    "drop": 0.9,
    "system": 0.7,
    "config": 0.6,
    "write": 0.4,
    "create": 0.3,
    "read": 0.1,
    "safe": 0.1,
    "notification": 0.1,
}

# Role hierarchy level (mirrors auth_parts._imports.ROLE_HIERARCHY)
_ROLE_LEVELS: Dict[str, int] = {
    "viewer": 0,
    "operador": 1,
    "gerente": 2,
    "admin": 3,
}


class RiskLevel(str, Enum):
    """Qualitative risk level."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


def _score_to_risk_level(score: float) -> RiskLevel:
    """Map a numeric risk score to a RiskLevel."""
    if score < 0.3:
        return RiskLevel.LOW
    if score < 0.5:
        return RiskLevel.MEDIUM
    if score < 0.7:
        return RiskLevel.HIGH
    return RiskLevel.CRITICAL


def _score_to_role(score: float) -> str:
    """Map a numeric risk score to the minimum required approver role."""
    if score < 0.3:
        return "auto_approve"
    if score < 0.5:
        return "operador"
    if score < 0.7:
        return "gerente"
    return "admin"


@dataclass
class RiskAssessment:
    """Result of a risk assessment for an approval request."""

    risk_score: float = 0.0
    risk_level: RiskLevel = RiskLevel.LOW
    factors: List[str] = field(default_factory=list)
    recommended_role: str = "auto_approve"
    auto_approvable: bool = True
    explanation: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "risk_score": round(self.risk_score, 4),
            "risk_level": self.risk_level.value,
            "factors": self.factors,
            "recommended_role": self.recommended_role,
            "auto_approvable": self.auto_approvable,
            "explanation": self.explanation,
        }


class RiskBasedApprovalRouter:
    """Routes approval requests based on contextual risk scores.

    Each assessment is persisted so that historical data can be queried
    for auditing and analytics.
    """

    def __init__(self, db_path: str = "risk_routing.sqlite") -> None:
        self._db_path = db_path
        self._lock = threading.RLock()
        self._init_db()

    # ── DB Initialisation ──────────────────────────────────

    def _init_db(self) -> None:
        """Create the risk_assessments table if it does not exist."""
        def _do_init() -> None:
            conn = sqlite3.connect(self._db_path)
            conn.execute("""  # nosemgrep: sqlalchemy-execute-raw-query
                CREATE TABLE IF NOT EXISTS risk_assessments (
                    assessment_id TEXT PRIMARY KEY,
                    action_type TEXT NOT NULL,
                    risk_score REAL NOT NULL,
                    risk_level TEXT NOT NULL,
                    recommended_role TEXT NOT NULL,
                    auto_approvable INTEGER NOT NULL DEFAULT 1,
                    factors TEXT NOT NULL DEFAULT '[]',
                    explanation TEXT NOT NULL DEFAULT '',
                    context TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute("""  # nosemgrep: sqlalchemy-execute-raw-query
                CREATE INDEX IF NOT EXISTS idx_risk_action_type
                ON risk_assessments(action_type, created_at DESC)
            """)
            conn.commit()
            conn.close()

        self._with_retry(_do_init)

    # ── Core Operations ────────────────────────────────────

    def assess_risk(
        self,
        action_type: str,
        action_config: Dict[str, Any],
        context: Dict[str, Any],
    ) -> RiskAssessment:
        """Compute a risk assessment for the given action + context.

        Factors considered:
          1. Action category base score
          2. Amount / size factor
          3. Target environment sensitivity
          4. Time-of-day factor (off-hours = higher risk)
          5. User history factor
        """
        factors: List[str] = []
        scores: List[float] = []

        # 1. Action category base score
        base = self._action_category_score(action_type)
        scores.append(base)
        factors.append(f"action_category={base:.2f}")

        # 2. Amount / size factor
        amount_score = self._amount_score(action_config)
        if amount_score > 0.0:
            scores.append(amount_score)
            factors.append(f"amount_factor={amount_score:.2f}")

        # 3. Target sensitivity
        target_score = self._target_score(action_config, context)
        if target_score > 0.0:
            scores.append(target_score)
            factors.append(f"target_sensitivity={target_score:.2f}")

        # 4. Time-of-day factor
        time_score = self._time_of_day_score()
        if time_score > 0.0:
            scores.append(time_score)
            factors.append(f"off_hours={time_score:.2f}")

        # 5. User history factor
        user_score = self._user_history_score(context)
        if user_score > 0.0:
            scores.append(user_score)
            factors.append(f"user_history={user_score:.2f}")

        # Weighted combination — base score weighted highest
        if scores:
            risk_score = min(1.0, scores[0] * 0.5 + sum(scores[1:]) * 0.5 / max(len(scores) - 1, 1))
        else:
            risk_score = 0.1

        risk_level = _score_to_risk_level(risk_score)
        recommended_role = _score_to_role(risk_score)

        # Determine auto-approvability
        auto_approvable = risk_score < 0.3 and not self._is_financial_or_destructive(action_type)

        explanation = (
            f"Risk score {risk_score:.2f} ({risk_level.value}) for action "
            f"'{action_type}'. Factors: {', '.join(factors)}. "
            f"Recommended approver: {recommended_role}."
        )

        assessment = RiskAssessment(
            risk_score=risk_score,
            risk_level=risk_level,
            factors=factors,
            recommended_role=recommended_role,
            auto_approvable=auto_approvable,
            explanation=explanation,
        )

        # Persist the assessment
        with self._lock:
            self._persist_assessment(action_type, assessment, context)

        logger.info(
            "RiskRouter: action='%s' score=%.2f level=%s role=%s auto=%s",
            action_type, risk_score, risk_level.value, recommended_role, auto_approvable,
        )
        return assessment

    def get_recommended_approver(self, risk_assessment: RiskAssessment) -> str:
        """Map risk_level to the required approver role.

        Returns the *recommended_role* from the assessment, which is
        derived from the numeric risk score.
        """
        return risk_assessment.recommended_role

    def should_escalate(
        self, current_role: str, risk_assessment: RiskAssessment,
    ) -> bool:
        """Check if the current approver role is sufficient for the risk level.

        Returns True if the current_role is below the recommended_role
        in the hierarchy, meaning escalation is needed.
        """
        recommended = risk_assessment.recommended_role
        if recommended == "auto_approve":
            return False
        current_level = _ROLE_LEVELS.get(current_role, -1)
        recommended_level = _ROLE_LEVELS.get(recommended, -1)
        return current_level < recommended_level

    # ── Query Methods ──────────────────────────────────────

    def get_history(
        self, action_type: str = "", limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Return recent risk assessments, optionally filtered by action_type."""
        def _do_query() -> List[Dict[str, Any]]:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            if action_type:
                rows = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    """SELECT * FROM risk_assessments
                       WHERE action_type = ?
                       ORDER BY created_at DESC LIMIT ?""",
                    (action_type, limit),
                ).fetchall()
            else:
                rows = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    """SELECT * FROM risk_assessments
                       ORDER BY created_at DESC LIMIT ?""",
                    (limit,),
                ).fetchall()
            conn.close()
            results: List[Dict[str, Any]] = []
            for row in rows:
                results.append({
                    "assessment_id": row["assessment_id"],
                    "action_type": row["action_type"],
                    "risk_score": row["risk_score"],
                    "risk_level": row["risk_level"],
                    "recommended_role": row["recommended_role"],
                    "auto_approvable": bool(row["auto_approvable"]),
                    "factors": json.loads(row["factors"] or "[]"),
                    "explanation": row["explanation"],
                    "created_at": row["created_at"],
                })
            return results

        return self._with_retry(_do_query, fallback=[])

    def get_stats(self) -> Dict[str, Any]:
        """Return aggregate risk-routing statistics."""
        def _do_query() -> Dict[str, Any]:
            conn = sqlite3.connect(self._db_path)
            try:
                total = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    "SELECT COUNT(*) FROM risk_assessments"
                ).fetchone()[0]
                avg_score_row = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    "SELECT AVG(risk_score) FROM risk_assessments"
                ).fetchone()[0]
                avg_score = round(avg_score_row, 4) if avg_score_row is not None else 0.0
                auto_count = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    "SELECT COUNT(*) FROM risk_assessments WHERE auto_approvable = 1"
                ).fetchone()[0]
                by_level: Dict[str, int] = {}
                for level in RiskLevel:
                    cnt = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                        "SELECT COUNT(*) FROM risk_assessments WHERE risk_level = ?",
                        (level.value,),
                    ).fetchone()[0]
                    by_level[level.value] = cnt
            finally:
                conn.close()
            return {
                "total_assessments": total,
                "avg_risk_score": avg_score,
                "auto_approvable_count": auto_count,
                "by_risk_level": by_level,
            }

        return self._with_retry(_do_query, fallback={})

    # ── Private Scoring Helpers ────────────────────────────

    @staticmethod
    def _action_category_score(action_type: str) -> float:
        """Return the base risk score for the action category."""
        action_lower = action_type.lower()
        for keyword, score in _ACTION_CATEGORY_SCORES.items():
            if keyword in action_lower:
                return score
        # Default: moderate risk for unknown actions
        return 0.4

    @staticmethod
    def _amount_score(action_config: Dict[str, Any]) -> float:
        """Higher monetary amounts / larger sizes increase risk."""
        amount = action_config.get("amount", 0)
        if isinstance(amount, (int, float)) and amount > 0:
            # Logarithmic scaling: $100→0.05, $10k→0.35, $1M→0.65
            import math
            try:
                return min(0.7, max(0.0, math.log10(max(amount, 1)) / 10))
            except (ValueError, OverflowError):
                return 0.3
        size = action_config.get("size", 0)
        if isinstance(size, (int, float)) and size > 0:
            return min(0.5, size / 10000)
        return 0.0

    @staticmethod
    def _target_score(
        action_config: Dict[str, Any], context: Dict[str, Any],
    ) -> float:
        """Production targets are higher risk than test/dev."""
        target = (
            action_config.get("target", "")
            or action_config.get("environment", "")
            or context.get("target", "")
            or context.get("environment", "")
        ).lower()
        if "production" in target or "prod" in target:
            return 0.3
        if "staging" in target:
            return 0.15
        if "test" in target or "dev" in target:
            return 0.0
        # Unknown target: moderate risk
        return 0.1

    @staticmethod
    def _time_of_day_score() -> float:
        """Off-hours (22:00–06:00 UTC) increase risk."""
        hour = datetime.now(timezone.utc).hour
        if hour >= 22 or hour < 6:
            return 0.15
        return 0.0

    @staticmethod
    def _user_history_score(context: Dict[str, Any]) -> float:
        """New or low-reputation users add risk."""
        approval_count = context.get("user_approval_count", 0)
        rejection_count = context.get("user_rejection_count", 0)
        total = approval_count + rejection_count
        if total == 0:
            return 0.2  # New user
        if total < 5:
            return 0.1  # Limited history
        rejection_rate = rejection_count / total
        if rejection_rate > 0.3:
            return 0.3  # High rejection rate
        return 0.0

    @staticmethod
    def _is_financial_or_destructive(action_type: str) -> bool:
        """Return True for financial or destructive action types."""
        action_lower = action_type.lower()
        financial_kws = ("payment", "financial", "refund", "invoice_pay")
        destructive_kws = ("delete", "drop", "destructive", "remove", "truncate")
        for kw in financial_kws + destructive_kws:
            if kw in action_lower:
                return True
        return False

    # ── Persistence ────────────────────────────────────────

    def _persist_assessment(
        self,
        action_type: str,
        assessment: RiskAssessment,
        context: Dict[str, Any],
    ) -> None:
        """Write a risk assessment to the database."""
        assessment_id = f"ra-{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()

        def _do_persist() -> None:
            conn = sqlite3.connect(self._db_path)
            conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                """INSERT INTO risk_assessments
                   (assessment_id, action_type, risk_score, risk_level,
                    recommended_role, auto_approvable, factors,
                    explanation, context, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    assessment_id, action_type, assessment.risk_score,
                    assessment.risk_level.value, assessment.recommended_role,
                    int(assessment.auto_approvable),
                    json.dumps(assessment.factors),
                    assessment.explanation,
                    json.dumps(context), now,
                ),
            )
            conn.commit()
            conn.close()

        self._with_retry(_do_persist)

    # ── Retry Helper ───────────────────────────────────────

    @staticmethod
    def _with_retry(
        fn: Any,
        fallback: Any = None,
        max_retries: int = _MAX_RETRIES,
    ) -> Any:
        """Execute *fn* with retry logic on database errors."""
        last_exc: Optional[Exception] = None
        for attempt in range(1, max_retries + 1):
            try:
                return fn()
            except sqlite3.OperationalError as exc:
                last_exc = exc
                logger.warning(
                    "RiskRouter: DB retry %d/%d — %s", attempt, max_retries, exc,
                )
                if attempt < max_retries:
                    time.sleep(_RETRY_DELAY * attempt)
            except Exception as exc:
                last_exc = exc
                logger.error("RiskRouter: DB error — %s", exc)
                break
        logger.error("RiskRouter: All retries exhausted — %s", last_exc)
        return fallback


# ── Singleton ─────────────────────────────────────────────

_risk_router_instance: Optional[RiskBasedApprovalRouter] = None
_risk_router_lock = threading.Lock()


def get_risk_router(db_path: str = "risk_routing.sqlite") -> RiskBasedApprovalRouter:
    """Get or create the global RiskBasedApprovalRouter instance."""
    global _risk_router_instance
    with _risk_router_lock:
        if _risk_router_instance is None:
            _risk_router_instance = RiskBasedApprovalRouter(db_path=db_path)
        return _risk_router_instance


def reset_risk_router() -> None:
    """Reset the global RiskBasedApprovalRouter (for testing)."""
    global _risk_router_instance
    _risk_router_instance = None


__all__ = [
    "RiskLevel",
    "RiskAssessment",
    "RiskBasedApprovalRouter",
    "get_risk_router",
    "reset_risk_router",
]
