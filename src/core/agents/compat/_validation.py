"""
compat._validation — ValidationAgentCompat v1→v2 wrapper.
"""

from __future__ import annotations

import logging
from typing import Any

from src.core.agents.validation import SecurityScanner, SyntaxValidator, RiskCalculator
from src.core.agents.schemas import SecurityResult, SyntaxResult, RiskResult
from src.core.agents.schemas._v1_compat_schemas import ValidationOutput
from src.core.shared.agent_schemas import ValidationIssue as SharedValidationIssue

logger = logging.getLogger(__name__)


class ValidationAgentCompat:
    """v1-compatible ValidationAgent wrapper around v2 validation agents."""

    def __init__(self, semantic_engine=None, smart_memory=None, **kwargs) -> None:
        self._semantic = semantic_engine
        self._memory = smart_memory
        self._security_scanner = SecurityScanner(**kwargs)
        self._syntax_validator = SyntaxValidator(**kwargs)
        self._risk_calculator = RiskCalculator(**kwargs)
        self._call_count = 0

    def validate_with_runner(self, runner: Any, target: str, content: str,
                             rules: list[str] = None,
                             language: str = "python") -> ValidationOutput:
        """Validate using v2 agents."""
        self._call_count += 1
        rules = rules or ["security", "quality"]

        all_issues: list[SharedValidationIssue] = []

        # Security scan
        if "security" in rules and content:
            sec_result = self._security_scanner.run({"code": content, "language": language})
            sec_data = sec_result.get("data")
            if isinstance(sec_data, SecurityResult):
                all_issues.extend([
                    SharedValidationIssue(
                        severity=t.severity, code=t.code,
                        message=t.message, line=t.line,
                        suggestion=t.suggestion,
                    )
                    for t in sec_data.threats
                ])

        # Syntax validation
        if "quality" in rules and content:
            syn_result = self._syntax_validator.run({"code": content, "language": language})
            syn_data = syn_result.get("data")
            if isinstance(syn_data, SyntaxResult):
                all_issues.extend([
                    SharedValidationIssue(
                        severity=e.severity, code=e.code,
                        message=e.message, line=e.line,
                        suggestion=e.suggestion,
                    )
                    for e in syn_data.errors
                ])

        # Chain validation
        if target == "chain" and content:
            from .validation import ChainValidator
            chain_val = ChainValidator()
            chain_result = chain_val.run({"description": content})
            chain_data = chain_result.get("data")
            if isinstance(chain_data, dict):
                incompat = chain_data.get("incompatibilities", [])
                for inc in incompat:
                    all_issues.append(SharedValidationIssue(
                        severity="warning", code="chain_incompatibility",
                        message=str(inc),
                    ))

        # Risk calculation
        risk_score = 0.0
        if content:
            risk_result = self._risk_calculator.run({"issues": all_issues, "code": content})
            risk_data = risk_result.get("data")
            if isinstance(risk_data, RiskResult):
                risk_score = risk_data.score

        suggestions = [i.suggestion for i in all_issues if i.suggestion]
        is_valid = not any(i.severity == "error" for i in all_issues)

        return ValidationOutput(
            is_valid=is_valid, issues=all_issues,
            suggestions=suggestions, risk_score=risk_score,
            source="deterministic",
        )

    @property
    def stats(self) -> dict[str, Any]:
        return {
            "name": "ValidationAgentCompat",
            "call_count": self._call_count,
            "security_scanner": self._security_scanner.stats,
        }
