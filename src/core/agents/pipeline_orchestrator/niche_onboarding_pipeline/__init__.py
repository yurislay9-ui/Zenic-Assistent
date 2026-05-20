"""
NicheOnboardingPipeline — Complete E2E Pipeline for Niche Onboarding (Phase D).

Orchestrates the full 8-step niche onboarding flow:
    1. SELECT_NICHE    → catalog lookup + template generation
    2. UPLOAD_DOCUMENTS → document ingestion + field extraction
    3. GENERATE_QUESTIONS → identify missing required fields
    4. COLLECT_ANSWERS  → interactive Q&A with validation
    5. VALIDATE_TEMPLATE → completeness check
    6. SAFETY_CHECK     → domain safety + compliance gate
    7. CERTIFY_BLUEPRINT → ECDSA signature + certified blueprint
    8. EXPORT           → final YAML + metadata export

Integrates:
    - A49 DocumentIngestor (Phase B) — document parsing + field matching
    - A50 NicheTemplateGenerator (Phase C) — YAML template generation
    - A51 InteractiveDataCollector (Phase D) — interactive Q&A
    - DomainSafetyGate (Phase D) — domain rules + compliance + sensitivity

All core logic delegates to Rust via _zenic_native.
Python fallback provides deterministic working implementations.

INVARIANTS:
    1. Safety gate veto is ABSOLUTE — no override possible.
    2. Pipeline is resumable — steps can be retried independently.
    3. All operations are deterministic and auditable.
"""

from ._steps import PipelineStep, PipelineState
from ._pipeline import NicheOnboardingPipeline

__all__ = [
    "PipelineStep",
    "PipelineState",
    "NicheOnboardingPipeline",
]
