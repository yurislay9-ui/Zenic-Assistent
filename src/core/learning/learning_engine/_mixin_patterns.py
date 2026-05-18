"""Pattern detection mixin for LearningEngine."""

from __future__ import annotations
import json
import logging
import sqlite3
from typing import Any, Dict, List, Optional
from ._types import *
from ._helpers import *

logger = logging.getLogger(__name__)


class PatternDetectionMixin:
    """Mixin providing pattern detection methods for LearningEngine."""

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
