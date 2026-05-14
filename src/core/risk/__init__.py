from __future__ import annotations

try:
    from .types import (
        RiskLevel, BlastRadiusReport, RiskPropagationReport,
        CriticalPathReport, CompositeRiskReport,
    )
except ImportError:
    RiskLevel = None  # type: ignore[assignment,misc]
    BlastRadiusReport = None  # type: ignore[assignment,misc]
    RiskPropagationReport = None  # type: ignore[assignment,misc]
    CriticalPathReport = None  # type: ignore[assignment,misc]
    CompositeRiskReport = None  # type: ignore[assignment,misc]

try:
    from .engine import (
        RiskPredictionEngine,
        get_risk_prediction_engine,
        reset_risk_prediction_engine,
    )
except ImportError:
    RiskPredictionEngine = None  # type: ignore[assignment,misc]
    get_risk_prediction_engine = None  # type: ignore[assignment,misc]
    reset_risk_prediction_engine = None  # type: ignore[assignment,misc]

__all__ = [
    "RiskLevel", "BlastRadiusReport", "RiskPropagationReport",
    "CriticalPathReport", "CompositeRiskReport",
    "RiskPredictionEngine", "get_risk_prediction_engine",
    "reset_risk_prediction_engine",
]
