"""
A42 ConsensusResolver — SINGLE RESPONSIBILITY: Resolve evidence into consensus or flag for AI.

Deterministic. No AI.
Determines if the evidence is clear enough for a decision, or if AI arbitration is needed.

VETO RULES:
  - If SECURITY_CHECK evidence says NO with weight >= 0.7 → immediate NO
  - If SANDBOX_PASS evidence says NO with weight >= 0.7 → immediate NO
"""

from __future__ import annotations

from typing import Any

from ..resilience import BaseAgent
from ..schemas import Evidence, EvidenceType, ConsensusResult, Verdict

# ──────────────────────────────────────────────────────────────
# CONSENSUS THRESHOLDS
# ──────────────────────────────────────────────────────────────

CONSENSUS_CERTAIN_THRESHOLD = 0.85
CONSENSUS_HIGH_THRESHOLD = 0.60
CONSENSUS_MEDIUM_THRESHOLD = 0.30
# Below 0.30 → AI REQUIRED

# Evidence type weights
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

# Veto types — absolute NO if weight >= 0.7
VETO_TYPES = {EvidenceType.SECURITY_CHECK, EvidenceType.SANDBOX_PASS}


class ConsensusResolverV18(BaseAgent[ConsensusResult]):
    """
    A42: Resolve evidence into consensus or flag for AI.

    Single Responsibility: Consensus resolution ONLY.
    Method: Weighted scoring with veto rules.
    Fallback: Return NO with low confidence.
    Tie handling: Perfect ties produce provisional NO (precaution principle)
    with needs_llm=True, pending AI arbitration.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(name="A42_ConsensusResolver", **kwargs)

    def execute(self, input_data: Any) -> ConsensusResult:
        """
        Resolve evidence into a consensus result.

        input_data should be a list of Evidence objects,
        or a dict with 'evidence' key.
        """
        evidence: list[Evidence] = []

        if isinstance(input_data, list):
            evidence = input_data
        elif isinstance(input_data, dict):
            evidence = input_data.get("evidence", [])

        if not evidence:
            return ConsensusResult(
                verdict=Verdict.NO,
                confidence=0.0,
                needs_llm=True,
                source="deterministic",
            )

        # Step 1: Check for vetoes
        for e in evidence:
            if e.evidence_type in VETO_TYPES and e.favors == "NO" and e.weight >= 0.7:
                return ConsensusResult(
                    verdict=Verdict.NO,
                    confidence=0.95,
                    score=-1.0,
                    evidence_for=[e for e in evidence if e.favors == "YES"],
                    evidence_against=[e for e in evidence if e.favors == "NO"],
                    needs_llm=False,  # Veto is absolute — no AI needed
                    signals_count=len(evidence),
                    unanimous=False,
                    source="deterministic_veto",
                )

        # Step 2: Weighted scoring
        score_for = 0.0
        score_against = 0.0
        total_weight = 0.0

        for e in evidence:
            type_weight = EVIDENCE_WEIGHTS.get(e.evidence_type, 1.0)
            weighted = e.weight * type_weight
            total_weight += type_weight

            if e.favors == "YES":
                score_for += weighted
            else:
                score_against += weighted

        # Step 3: Normalize to -1.0 to 1.0
        if total_weight > 0:
            normalized = (score_for - score_against) / total_weight
        else:
            normalized = 0.0

        # Step 4: Determine confidence level
        abs_score = abs(normalized)
        if abs_score >= CONSENSUS_CERTAIN_THRESHOLD:
            confidence = 0.95
            needs_llm = False
        elif abs_score >= CONSENSUS_HIGH_THRESHOLD:
            confidence = 0.8
            needs_llm = False
        elif abs_score >= CONSENSUS_MEDIUM_THRESHOLD:
            confidence = 0.5
            needs_llm = True  # Borderline — ask AI
        else:
            confidence = 0.2
            needs_llm = True  # Tie — AI REQUIRED

        # Step 5: Determine verdict
        # Precaution principle: when in doubt, lean toward NO.
        # If needs_llm is True, this verdict is PROVISIONAL pending AI arbitration.
        if normalized > 0:
            verdict = Verdict.YES
        elif normalized < 0:
            verdict = Verdict.NO
        else:
            # Perfect tie: provisional NO (precaution) pending LLM arbitration
            verdict = Verdict.NO

        # Unanimous check
        all_same = all(e.favors == evidence[0].favors for e in evidence)

        return ConsensusResult(
            verdict=verdict,
            confidence=round(confidence, 2),
            score=round(normalized, 3),
            evidence_for=[e for e in evidence if e.favors == "YES"],
            evidence_against=[e for e in evidence if e.favors == "NO"],
            needs_llm=needs_llm,
            signals_count=len(evidence),
            unanimous=all_same,
            source="deterministic",
        )

    def fallback(self, input_data: Any) -> ConsensusResult:
        """
        Fallback: Return NO with low confidence.
        Precaution principle: in doubt, reject.
        """
        return ConsensusResult(
            verdict=Verdict.NO,
            confidence=0.1,
            needs_llm=False,
            source="fallback",
        )
