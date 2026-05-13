"""
A11 CRMPipeline — SINGLE RESPONSIBILITY: Manage CRM pipeline stages and conversions.

Deterministic CRM logic: lead progression through 7 stages with conversion probabilities.
No AI. Lookup-table based stage management.
"""

from __future__ import annotations

from typing import Any

from ..resilience import BaseAgent
from ..schemas import CRMResult


# ──────────────────────────────────────────────────────────────
# CONSTANTS
# ──────────────────────────────────────────────────────────────

# 7-stage sales pipeline
PIPELINE_STAGES = [
    "new", "contacted", "qualified", "proposal",
    "negotiation", "closed_won", "closed_lost",
]

# Conversion probability per stage
STAGE_PROBABILITIES = {
    "new": 0.10,
    "contacted": 0.20,
    "qualified": 0.40,
    "proposal": 0.60,
    "negotiation": 0.80,
    "closed_won": 1.00,
    "closed_lost": 0.00,
}

# Next recommended action per stage
NEXT_ACTIONS = {
    "new": "Make initial contact",
    "contacted": "Qualify the lead",
    "qualified": "Send proposal",
    "proposal": "Begin negotiation",
    "negotiation": "Close the deal",
    "closed_won": "Send onboarding email",
    "closed_lost": "Archive lead, schedule follow-up in 30 days",
}

VALID_ACTIONS = frozenset({"advance", "regress", "close_won", "close_lost"})


class CRMPipeline(BaseAgent[CRMResult]):
    """
    A11: Manage CRM pipeline stages and conversions.

    Single Responsibility: Lead stage progression ONLY.
    Method: Deterministic stage machine with probability lookup.
    Fallback: Empty CRMResult with no stages.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(name="A11_CRMPipeline", **kwargs)

    def execute(self, input_data: Any) -> CRMResult:
        """
        Manage CRM pipeline: advance/regress leads through stages.

        Input (BusinessData.data dict):
            - lead_data / lead: dict with lead info
            - current_stage: str (default from lead)
            - action: "advance"|"regress"|"close_won"|"close_lost"

        Output: CRMResult with stages, conversions, forecasts.
        """
        if not isinstance(input_data, dict):
            data = input_data.data if hasattr(input_data, "data") else {}
        else:
            data = input_data

        lead = data.get("lead_data", data.get("lead", {}))
        current_stage = data.get("current_stage", lead.get("stage", "new"))
        action = data.get("action", "advance")

        # ── Validate current stage ──
        if current_stage not in PIPELINE_STAGES:
            current_stage = PIPELINE_STAGES[0]

        idx = PIPELINE_STAGES.index(current_stage)

        # ── Compute new stage ──
        new_stage = current_stage

        if action == "advance" and idx < len(PIPELINE_STAGES) - 1:
            new_stage = PIPELINE_STAGES[idx + 1]
        elif action == "regress" and idx > 0:
            new_stage = PIPELINE_STAGES[idx - 1]
        elif action == "close_won":
            new_stage = "closed_won"
        elif action == "close_lost":
            new_stage = "closed_lost"

        probability = STAGE_PROBABILITIES.get(new_stage, 0.0)
        next_action = NEXT_ACTIONS.get(new_stage, "Review lead status")

        # ── Build stages list ──
        stages = [
            {
                "name": stage,
                "probability": STAGE_PROBABILITIES.get(stage, 0.0),
                "is_current": stage == new_stage,
            }
            for stage in PIPELINE_STAGES
        ]

        # ── Conversion metrics ──
        conversions = {
            "previous_stage": current_stage,
            "new_stage": new_stage,
            "conversion_probability": probability,
            "pipeline_position": PIPELINE_STAGES.index(new_stage) + 1 if new_stage in PIPELINE_STAGES else 0,
        }

        # ── Simple forecast ──
        forecasts = {
            "deal_probability": probability,
            "next_action": next_action,
            "stage_progress": f"{current_stage} → {new_stage}",
            "estimated_close": "high" if probability >= 0.60 else "medium" if probability >= 0.30 else "low",
        }

        return CRMResult(
            stages=stages,
            conversions=conversions,
            forecasts=forecasts,
            source="deterministic",
        )

    def fallback(self, input_data: Any) -> CRMResult:
        """Safe fallback: empty CRM result."""
        return CRMResult(
            stages=[], conversions={}, forecasts={},
            source="fallback",
        )
