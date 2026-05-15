"""
A41 EvidenceCollector — SINGLE RESPONSIBILITY: Collect evidence for/against a decision.

Deterministic. No AI.
Collects evidence from all agent results to build a case for the ConsensusResolver.
"""

from __future__ import annotations

from typing import Any

from ..resilience import BaseAgent
from ..schemas import (
    Evidence, EvidenceType, SecurityResult, SyntaxResult,
    CriticalityResult, IntentResult, CodeResult,
)


class EvidenceCollectorV18(BaseAgent[list[Evidence]]):
    """
    A41: Collect evidence for/against a decision.

    Single Responsibility: Evidence collection ONLY.
    Method: Analyze agent results and create typed evidence items.
    Fallback: Return empty evidence list.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(name="A41_EvidenceCollector", **kwargs)

    # Evidence type weights (higher = more trusted)
    EVIDENCE_WEIGHTS = {
        EvidenceType.SECURITY_CHECK: 1.5,
        EvidenceType.SANDBOX_PASS: 1.5,
        EvidenceType.SYNTAX_VALID: 1.2,
        EvidenceType.AST_VALIDATION: 1.2,
        EvidenceType.CACHE_HIT: 1.3,
        EvidenceType.TYPE_SAFETY: 1.1,
        EvidenceType.RULE_ENGINE: 1.0,
        EvidenceType.PATTERN_MATCH: 0.8,
        EvidenceType.STRUCTURAL_MATCH: 0.7,
        EvidenceType.REGEX_MATCH: 0.6,
        EvidenceType.KEYWORD_CLASSIFY: 0.5,
        EvidenceType.SEMANTIC_SIMILARITY: 0.4,
    }

    def execute(self, input_data: Any) -> list[Evidence]:
        """
        Collect evidence from agent results.

        input_data should be a dict with agent results:
          - 'security_result': SecurityResult
          - 'syntax_result': SyntaxResult
          - 'criticality_result': CriticalityResult
          - 'intent_result': IntentResult
          - 'code_result': CodeResult (optional)
        """
        if not isinstance(input_data, dict):
            # Try to handle list of results or object attributes
            if isinstance(input_data, list):
                # Might be a raw list of results — try to build evidence from items
                return self.fallback(input_data)
            elif hasattr(input_data, '__dict__'):
                input_data = {k: v for k, v in input_data.__dict__.items() 
                             if not k.startswith('_')}
            else:
                return self.fallback(input_data)

        evidence: list[Evidence] = []

        # Security evidence (has VETO power)
        security = input_data.get("security_result")
        if security and isinstance(security, SecurityResult):
            if security.safe:
                evidence.append(Evidence(
                    evidence_type=EvidenceType.SECURITY_CHECK,
                    favors="YES",
                    weight=0.9,
                    source="A23_SecurityScanner",
                    detail="No dangerous patterns detected",
                ))
            else:
                evidence.append(Evidence(
                    evidence_type=EvidenceType.SECURITY_CHECK,
                    favors="NO",
                    weight=0.9,
                    source="A23_SecurityScanner",
                    detail=f"Security threats: {[t.code for t in security.threats]}",
                ))

        # Syntax evidence
        syntax = input_data.get("syntax_result")
        if syntax and isinstance(syntax, SyntaxResult):
            if syntax.valid:
                evidence.append(Evidence(
                    evidence_type=EvidenceType.SYNTAX_VALID,
                    favors="YES",
                    weight=0.8,
                    source="A24_SyntaxValidator",
                    detail="Syntax is valid",
                ))
            else:
                evidence.append(Evidence(
                    evidence_type=EvidenceType.SYNTAX_VALID,
                    favors="NO",
                    weight=0.9,
                    source="A24_SyntaxValidator",
                    detail=f"Syntax errors: {len(syntax.errors)}",
                ))

        # Criticality evidence
        criticality = input_data.get("criticality_result")
        if criticality and isinstance(criticality, CriticalityResult):
            if criticality.level <= 2:
                evidence.append(Evidence(
                    evidence_type=EvidenceType.RULE_ENGINE,
                    favors="YES",
                    weight=0.7 * criticality.confidence,
                    source="A04_CriticalityScorer",
                    detail=f"Criticality level {criticality.level}, confidence {criticality.confidence}",
                ))
            else:
                # High criticality = more scrutiny needed
                evidence.append(Evidence(
                    evidence_type=EvidenceType.RULE_ENGINE,
                    favors="NO",
                    weight=0.5,
                    source="A04_CriticalityScorer",
                    detail=f"High criticality (level {criticality.level}) requires extra scrutiny",
                ))

        # Intent evidence
        intent = input_data.get("intent_result")
        if intent and isinstance(intent, IntentResult):
            if intent.confidence >= 0.5:
                evidence.append(Evidence(
                    evidence_type=EvidenceType.KEYWORD_CLASSIFY,
                    favors="YES",
                    weight=0.5 * intent.confidence,
                    source="A01_IntentClassifier",
                    detail=f"Intent: {intent.operation}/{intent.goal} (conf: {intent.confidence})",
                ))
            else:
                evidence.append(Evidence(
                    evidence_type=EvidenceType.KEYWORD_CLASSIFY,
                    favors="NO",
                    weight=0.3,
                    source="A01_IntentClassifier",
                    detail=f"Low intent confidence: {intent.confidence}",
                ))

        # Code result evidence
        code_result = input_data.get("code_result")
        if code_result and isinstance(code_result, CodeResult):
            if code_result.code and not code_result.fixes:
                evidence.append(Evidence(
                    evidence_type=EvidenceType.PATTERN_MATCH,
                    favors="YES",
                    weight=0.6,
                    source="CodeOperation",
                    detail=f"Code generated successfully ({len(code_result.code)} chars)",
                ))
            elif code_result.fixes:
                evidence.append(Evidence(
                    evidence_type=EvidenceType.PATTERN_MATCH,
                    favors="NO",
                    weight=0.5,
                    source="CodeOperation",
                    detail=f"Code has {len(code_result.fixes)} fixes applied",
                ))

        return evidence

    def fallback(self, input_data: Any) -> list[Evidence]:
        return []
