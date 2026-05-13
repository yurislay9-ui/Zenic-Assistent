"""
A27 RiskCalculator — SINGLE RESPONSIBILITY: Calculate aggregate risk score.

Deterministic. No AI.
"""

from __future__ import annotations

from typing import Any

from ..resilience import BaseAgent
from ..schemas import RiskResult, SecurityResult, SyntaxResult


class RiskCalculator(BaseAgent[RiskResult]):
    """
    A27: Calculate aggregate risk score from all validations.

    Single Responsibility: Risk calculation ONLY.
    Method: Weighted aggregation of security + syntax results.
    Fallback: Return moderate risk (fail-safe).
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(name="A27_RiskCalculator", **kwargs)

    # Severity weights
    SEVERITY_WEIGHTS = {
        "error": 0.3,
        "warning": 0.1,
        "info": 0.02,
    }

    def execute(self, input_data: Any) -> RiskResult:
        """
        Calculate risk from validation results.

        input_data should be a dict with:
          - 'security_result': SecurityResult
          - 'syntax_result': SyntaxResult
          - (optional) 'chain_result', 'config_result'
        """
        if not isinstance(input_data, dict):
            return self.fallback(input_data)

        security: SecurityResult = input_data.get("security_result", SecurityResult())
        syntax: SyntaxResult = input_data.get("syntax_result", SyntaxResult())

        # Calculate security risk
        # Use the pre-computed risk_score from SecurityScanner directly.
        # It already accounts for threat weights and safe pattern reductions.
        security_risk = 0.0
        if security and isinstance(security, SecurityResult):
            security_risk = security.risk_score

        # Calculate syntax risk
        syntax_risk = 0.0
        if syntax and isinstance(syntax, SyntaxResult):
            if not syntax.valid:
                syntax_risk += 0.3
            for error in syntax.errors:
                syntax_risk += self.SEVERITY_WEIGHTS.get(error.severity, 0.1)

        # Aggregate
        total_risk = min(security_risk + syntax_risk, 1.0)

        # Classify level
        if total_risk >= 0.7:
            level = "critical"
        elif total_risk >= 0.4:
            level = "high"
        elif total_risk >= 0.2:
            level = "medium"
        else:
            level = "low"

        # Generate recommendations
        recommendations = []
        if security_risk > 0.3:
            recommendations.append("Address security vulnerabilities before deployment")
        if syntax_risk > 0.3:
            recommendations.append("Fix syntax errors before proceeding")
        if total_risk > 0.7:
            recommendations.append("DO NOT deploy — critical risk level")

        return RiskResult(
            score=round(total_risk, 2),
            level=level,
            recommendations=recommendations,
            source="deterministic",
        )

    def fallback(self, input_data: Any) -> RiskResult:
        """Fallback: Return moderate risk when calculator is unavailable."""
        return RiskResult(
            score=0.4,
            level="medium",
            recommendations=["Risk calculation unavailable — assuming moderate risk"],
            source="fallback",
        )
