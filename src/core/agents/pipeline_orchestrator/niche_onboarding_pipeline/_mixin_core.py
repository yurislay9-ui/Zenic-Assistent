"""niche_onboarding_pipeline — Core mixin (init, start, upload_documents)."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from ._types import *  # noqa: F403

logger = logging.getLogger("zenic_agents.agents.niche_onboarding_pipeline")


class NicheOnboardingCoreMixin:
    """Core initialization and first pipeline steps."""

    def __init__(self) -> None:
        self._bridge = NicheBridge()  # noqa: F821
        self._ingestor = DocumentIngestor()  # noqa: F821
        self._collector = InteractiveDataCollector()  # noqa: F821
        self._domain_gate = get_default_domain_safety_gate()  # noqa: F821
        self._certifier = BlueprintCertifier()  # noqa: F821

    # ── Step 1: SELECT_NICHE ──────────────────────────────────

    def start(self, niche_id: str) -> PipelineState:  # noqa: F821
        """Start a new pipeline by selecting a niche."""
        state = PipelineState(niche_id)  # noqa: F821

        niche = self._bridge.get_niche(niche_id)
        if niche is None:
            state.add_error(f"Niche not found: {niche_id}")
            state.advance(PipelineStep.FAILED)  # noqa: F821
            return state

        state.niche_category = getattr(niche, "category", "ai_data")
        if hasattr(niche, "niche_category"):
            state.niche_category = niche.niche_category

        template_dict = self._bridge.create_template(niche_id)
        if template_dict is None:
            state.add_error(f"Template generation failed for niche: {niche_id}")
            state.advance(PipelineStep.FAILED)  # noqa: F821
            return state

        state.template_dict = template_dict
        state.advance(PipelineStep.SELECT_NICHE)  # noqa: F821

        validation = self._bridge.validate_template(template_dict)
        if isinstance(validation, dict):
            state.total_fields = validation.get("total_fields", 0)
            state.required_fields = validation.get("missing_required", 0)

        logger.info(
            "Pipeline %s: Started for niche=%s category=%s",
            state.pipeline_id, niche_id, state.niche_category,
        )
        return state

    # ── Step 2: UPLOAD_DOCUMENTS ──────────────────────────────

    def upload_documents(
        self,
        state: PipelineState,  # noqa: F821
        files: Optional[List[Tuple[str, Optional[bytes]]]] = None,
        texts: Optional[List[str]] = None,
    ) -> PipelineState:  # noqa: F821
        """Upload and ingest documents. Auto-fills matched template fields."""
        if state.current_step == PipelineStep.FAILED:  # noqa: F821
            return state

        if state.template_dict is None:
            state.add_error("No template available for document ingestion")
            state.advance(PipelineStep.FAILED)  # noqa: F821
            return state

        result = self._ingestor.ingest_and_match(
            niche_id=state.niche_id, files=files, texts=texts,
        )

        state.documents_ingested = result.documents_processed

        if result.is_success:
            if result.template_dict is not None:
                state.template_dict = result.template_dict
            state.fields_auto_filled = len(result.matched_fields)
            state.add_warning(
                f"Auto-filled {len(result.matched_fields)} fields from "
                f"{result.documents_processed} documents"
            )
        else:
            if result.errors:
                state.add_warning(f"Document ingestion had errors: {'; '.join(result.errors[:3])}")
            else:
                state.add_warning("No fields could be matched from uploaded documents")

        if state.template_dict is not None:
            validation = self._bridge.validate_template(state.template_dict)
            if isinstance(validation, dict):
                state.total_fields = validation.get("total_fields", 0)
                state.required_fields = validation.get("missing_required", 0)

        state.advance(PipelineStep.UPLOAD_DOCUMENTS)  # noqa: F821
        logger.info(
            "Pipeline %s: Ingested %d documents, auto-filled %d fields",
            state.pipeline_id, state.documents_ingested, state.fields_auto_filled,
        )
        return state
