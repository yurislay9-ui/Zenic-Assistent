"""niche_onboarding_pipeline — Core implementation (composed from mixins)."""

from __future__ import annotations

from ._mixin_core import NicheOnboardingCoreMixin
from ._mixin_steps import NicheOnboardingStepsMixin


class NicheOnboardingPipeline(NicheOnboardingCoreMixin, NicheOnboardingStepsMixin):
    """
    Complete E2E pipeline for niche onboarding.

    Integrates all Phase 6 components into a single resumable pipeline:
        Phase A: NicheCatalog + NicheTemplate (niche selection + template generation)
        Phase B: DocumentIngestor (document parsing + field matching)
        Phase C: NicheTemplateGenerator (question generation)
        Phase D: InteractiveDataCollector + DomainSafetyGate (Q&A + safety)
    """


__all__ = ["NicheOnboardingPipeline"]
