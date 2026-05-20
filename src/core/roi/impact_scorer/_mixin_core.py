"""
Impact Scorer — ImpactScorer class.

Thread-safe economic impact scorer with SQLite persistence.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from typing import Any, Dict, List

from ._types import ImpactScore, _with_retry, _row_to_score

logger = logging.getLogger(__name__)


class ImpactScorer:
    """Thread-safe economic impact scorer with SQLite persistence.

    Scores alerts, exceptions, and actions based on estimated
    financial loss/gain and urgency.

    Usage::

        scorer = ImpactScorer()
        score = scorer.score_alert({
            "severity": "CRITICAL",
            "type": "stock_outage",
            "estimated_daily_revenue": 5000,
            "days_of_outage": 2,
        })
    """

    def __init__(self, db_path: str = "roi_impact.sqlite") -> None:
        self._db_path = db_path
        self._lock = threading.RLock()
        self._init_db()

    # ── Schema ──────────────────────────────────────────

    def _init_db(self) -> None:
        """Create the _zenic_impacts table if it does not exist."""
        try:
            def _create() -> None:
                conn = sqlite3.connect(self._db_path)
                conn.execute("""  # nosemgrep: sqlalchemy-execute-raw-query
                    CREATE TABLE IF NOT EXISTS _zenic_impacts (
                        score_id TEXT PRIMARY KEY,
                        source TEXT NOT NULL DEFAULT '',
                        source_id TEXT NOT NULL DEFAULT '',
                        impact_type TEXT NOT NULL DEFAULT '',
                        estimated_loss_if_no_action REAL NOT NULL DEFAULT 0,
                        estimated_gain_if_action REAL NOT NULL DEFAULT 0,
                        urgency_hours REAL NOT NULL DEFAULT 0,
                        impact_score REAL NOT NULL DEFAULT 0,
                        currency TEXT NOT NULL DEFAULT 'USD',
                        timestamp TEXT NOT NULL DEFAULT '',
                        metadata TEXT NOT NULL DEFAULT '{}'
                    )
                """)
                conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    "CREATE INDEX IF NOT EXISTS idx_impacts_source "
                    "ON _zenic_impacts(source)"
                )
                conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    "CREATE INDEX IF NOT EXISTS idx_impacts_timestamp "
                    "ON _zenic_impacts(timestamp)"
                )
                conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    "CREATE INDEX IF NOT EXISTS idx_impacts_urgency "
                    "ON _zenic_impacts(urgency_hours)"
                )
                conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                    "CREATE INDEX IF NOT EXISTS idx_impacts_score "
                    "ON _zenic_impacts(impact_score)"
                )
                conn.commit()
                conn.close()

            _with_retry(_create, label="ImpactScorer init_db")
        except Exception as exc:
            logger.error("ImpactScorer: DB init failed: %s", exc)

    # ── Scoring ─────────────────────────────────────────

    def score_alert(self, alert_data: Dict[str, Any]) -> ImpactScore:
        """Score a business alert based on severity and type."""
        severity = str(alert_data.get("severity", "INFO")).upper()
        alert_type = str(alert_data.get("type", "unknown"))
        source_id = str(alert_data.get("alert_id", alert_data.get("id", "")))

        loss: float = 0.0
        gain: float = 0.0
        urgency: float = 72.0
        impact_type: str = alert_type

        if severity == "CRITICAL" and alert_type == "stock_outage":
            daily_revenue = float(alert_data.get("estimated_daily_revenue", 0))
            days_of_outage = float(alert_data.get("days_of_outage", 1))
            loss = daily_revenue * days_of_outage
            gain = loss * 0.8
            urgency = 4.0
            impact_type = "critical_stock_outage"

        elif severity == "WARNING" and alert_type == "low_stock":
            potential_lost_sales = float(alert_data.get("potential_lost_sales", 0))
            loss = potential_lost_sales * 0.3
            gain = potential_lost_sales * 0.2
            urgency = 24.0
            impact_type = "low_stock_warning"

        elif alert_type == "overdue":
            invoice_amount = float(alert_data.get("invoice_amount", 0))
            default_prob = float(alert_data.get("probability_of_default", 0.15))
            loss = invoice_amount * default_prob
            gain = loss * 0.6
            urgency = 48.0
            impact_type = "financial_overdue"

        else:
            loss = float(alert_data.get("estimated_loss", 0))
            gain = float(alert_data.get("estimated_gain", loss * 0.5))
            urgency = float(alert_data.get("urgency_hours", 72.0))

        score = ImpactScore(
            source="alert",
            source_id=source_id,
            impact_type=impact_type,
            estimated_loss_if_no_action=round(loss, 2),
            estimated_gain_if_action=round(gain, 2),
            urgency_hours=urgency,
            metadata={"severity": severity, "alert_type": alert_type},
        )

        with self._lock:
            self._persist_score(score)

        logger.debug(
            "ImpactScorer: scored alert '%s' — loss=%.2f gain=%.2f urgency=%.1fh score=%.4f",
            source_id, loss, gain, urgency, score.impact_score,
        )
        return score

    def score_exception(self, exception_data: Dict[str, Any]) -> ImpactScore:
        """Score a system exception."""
        exc_type = str(exception_data.get("exception_type", "unknown"))
        source_id = str(exception_data.get("exception_id", exception_data.get("id", "")))
        loss: float = 0.0
        gain: float = 0.0
        urgency: float = 24.0
        impact_type: str = exc_type

        if exc_type in ("system_down", "service_outage", "downtime"):
            downtime_cost_per_hour = float(exception_data.get("cost_per_hour", 500))
            estimated_hours = float(exception_data.get("estimated_downtime_hours", 1))
            loss = downtime_cost_per_hour * estimated_hours
            gain = loss * 0.7
            urgency = 2.0
            impact_type = "system_downtime"

        elif exc_type in ("security_breach", "data_breach", "unauthorized_access"):
            breach_cost = float(exception_data.get("estimated_breach_cost", 50000))
            records_affected = int(exception_data.get("records_affected", 100))
            loss = breach_cost * (records_affected / 1000)
            gain = loss * 0.9
            urgency = 1.0
            impact_type = "security_violation"

        else:
            loss = float(exception_data.get("estimated_loss", 100))
            gain = float(exception_data.get("estimated_gain", 50))
            urgency = float(exception_data.get("urgency_hours", 24.0))

        score = ImpactScore(
            source="exception",
            source_id=source_id,
            impact_type=impact_type,
            estimated_loss_if_no_action=round(loss, 2),
            estimated_gain_if_action=round(gain, 2),
            urgency_hours=urgency,
            metadata={"exception_type": exc_type},
        )

        with self._lock:
            self._persist_score(score)

        logger.debug(
            "ImpactScorer: scored exception '%s' — loss=%.2f gain=%.2f urgency=%.1fh",
            source_id, loss, gain, urgency,
        )
        return score

    def score_action(
        self,
        action_type: str,
        action_config: Dict[str, Any],
    ) -> ImpactScore:
        """Score an action based on its type and configuration."""
        source_id = str(action_config.get("action_id", action_config.get("id", "")))
        loss: float = float(action_config.get("estimated_loss_if_skipped", 0))
        gain: float = float(action_config.get("estimated_gain_if_executed", 0))
        urgency: float = float(action_config.get("urgency_hours", 48.0))
        impact_type: str = action_type

        if action_type == "restock" and loss == 0:
            daily_revenue = float(action_config.get("daily_revenue_at_risk", 0))
            days_until_stockout = float(action_config.get("days_until_stockout", 3))
            loss = daily_revenue * max(days_until_stockout, 1)
            gain = loss * 0.85
            urgency = max(days_until_stockout * 8, 4)
            impact_type = "action_restock"

        elif action_type == "follow_up_invoice" and loss == 0:
            invoice_amount = float(action_config.get("invoice_amount", 0))
            overdue_days = float(action_config.get("overdue_days", 30))
            loss = invoice_amount * min(overdue_days / 90, 1.0)
            gain = invoice_amount * 0.7
            urgency = max(48 - overdue_days, 4)
            impact_type = "action_invoice_followup"

        elif action_type == "compliance_check" and loss == 0:
            loss = float(action_config.get("penalty_risk", 5000))
            gain = loss * 0.95
            urgency = float(action_config.get("deadline_hours", 168))
            impact_type = "action_compliance"

        score = ImpactScore(
            source="action",
            source_id=source_id,
            impact_type=impact_type,
            estimated_loss_if_no_action=round(loss, 2),
            estimated_gain_if_action=round(gain, 2),
            urgency_hours=urgency,
            metadata={"action_type": action_type},
        )

        with self._lock:
            self._persist_score(score)

        logger.debug(
            "ImpactScorer: scored action '%s' — loss=%.2f gain=%.2f urgency=%.1fh",
            action_type, loss, gain, urgency,
        )
        return score

    # ── Queries ─────────────────────────────────────────

    def get_top_impacts(self, limit: int = 10) -> List[ImpactScore]:
        """Return the top *limit* impact scores ordered by impact_score descending."""
        with self._lock:
            try:
                def _query() -> List[ImpactScore]:
                    conn = sqlite3.connect(self._db_path)
                    rows = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                        "SELECT score_id, source, source_id, impact_type, "
                        "estimated_loss_if_no_action, estimated_gain_if_action, "
                        "urgency_hours, impact_score, currency, timestamp, metadata "
                        "FROM _zenic_impacts "
                        "ORDER BY impact_score DESC LIMIT ?",
                        (limit,),
                    ).fetchall()
                    conn.close()
                    return [_row_to_score(row) for row in rows]

                return _with_retry(_query, label="ImpactScorer get_top_impacts")
            except Exception as exc:
                logger.error("ImpactScorer: get_top_impacts failed: %s", exc)
                return []

    def get_impact_summary(
        self,
        from_time: str = "",
        to_time: str = "",
    ) -> Dict[str, Any]:
        """Return aggregate impact summary: total potential loss/gain, average urgency."""
        with self._lock:
            try:
                def _query() -> Dict[str, Any]:
                    conn = sqlite3.connect(self._db_path)
                    sql = (
                        "SELECT COALESCE(SUM(estimated_loss_if_no_action), 0), "
                        "COALESCE(SUM(estimated_gain_if_action), 0), "
                        "COALESCE(AVG(urgency_hours), 0), "
                        "COUNT(*) "
                        "FROM _zenic_impacts WHERE 1=1"
                    )
                    params: list = []
                    if from_time:
                        sql += " AND timestamp >= ?"
                        params.append(from_time)
                    if to_time:
                        sql += " AND timestamp <= ?"
                        params.append(to_time)
                    row = conn.execute(sql, params).fetchone()  # nosemgrep: sqlalchemy-execute-raw-query
                    conn.close()
                    return {
                        "total_potential_loss": float(row[0]),
                        "total_potential_gain": float(row[1]),
                        "average_urgency_hours": round(float(row[2]), 2),
                        "impact_count": int(row[3]),
                    }

                return _with_retry(_query, label="ImpactScorer get_impact_summary")
            except Exception as exc:
                logger.error("ImpactScorer: get_impact_summary failed: %s", exc)
                return {
                    "total_potential_loss": 0.0,
                    "total_potential_gain": 0.0,
                    "average_urgency_hours": 0.0,
                    "impact_count": 0,
                }

    def get_urgent_actions(
        self,
        max_urgency_hours: float = 24,
    ) -> List[ImpactScore]:
        """Return impacts with urgency ≤ *max_urgency_hours*, ordered by urgency ascending."""
        with self._lock:
            try:
                def _query() -> List[ImpactScore]:
                    conn = sqlite3.connect(self._db_path)
                    rows = conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                        "SELECT score_id, source, source_id, impact_type, "
                        "estimated_loss_if_no_action, estimated_gain_if_action, "
                        "urgency_hours, impact_score, currency, timestamp, metadata "
                        "FROM _zenic_impacts "
                        "WHERE urgency_hours <= ? "
                        "ORDER BY urgency_hours ASC, impact_score DESC",
                        (max_urgency_hours,),
                    ).fetchall()
                    conn.close()
                    return [_row_to_score(row) for row in rows]

                return _with_retry(_query, label="ImpactScorer get_urgent_actions")
            except Exception as exc:
                logger.error("ImpactScorer: get_urgent_actions failed: %s", exc)
                return []

    # ── Persistence ─────────────────────────────────────

    def _persist_score(self, score: ImpactScore) -> None:
        """Insert an ImpactScore row with retry."""

        def _insert() -> None:
            conn = sqlite3.connect(self._db_path)
            conn.execute(  # nosemgrep: sqlalchemy-execute-raw-query
                """INSERT INTO _zenic_impacts
                   (score_id, source, source_id, impact_type,
                    estimated_loss_if_no_action, estimated_gain_if_action,
                    urgency_hours, impact_score, currency, timestamp, metadata)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    score.score_id,
                    score.source,
                    score.source_id,
                    score.impact_type,
                    score.estimated_loss_if_no_action,
                    score.estimated_gain_if_action,
                    score.urgency_hours,
                    score.impact_score,
                    score.currency,
                    score.timestamp,
                    json.dumps(score.metadata),
                ),
            )
            conn.commit()
            conn.close()

        try:
            _with_retry(_insert, label="ImpactScorer persist_score")
        except Exception as exc:
            logger.error("ImpactScorer: persist failed: %s", exc)
