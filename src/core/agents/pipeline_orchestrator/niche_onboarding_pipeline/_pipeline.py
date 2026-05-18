"""
NicheOnboardingPipeline — Main Pipeline Logic (Phase D).

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

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from ...executors.safety_gate.domain_gate import (
    get_default_domain_safety_gate,
)
from ...niche_rust.bridge import NicheBridge
from ...niche_rust.ingest_bridge import DocumentIngestor
from ...niche_rust.certifier_bridge import BlueprintCertifier
from ...niche_rust.e2e_bridge import PipelineProgress, PipelineResult
from ..business.interactive_data_collector import InteractiveDataCollector
from ._steps import PipelineStep, PipelineState

logger = logging.getLogger(__name__)


class NicheOnboardingPipeline:
    """
    Complete E2E pipeline for niche onboarding.

    Integrates all Phase 6 components into a single resumable pipeline:
        Phase A: NicheCatalog + NicheTemplate (niche selection + template generation)
        Phase B: DocumentIngestor (document parsing + field matching)
        Phase C: NicheTemplateGenerator (question generation)
        Phase D: InteractiveDataCollector + DomainSafetyGate (Q&A + safety)

    Usage::

        pipeline = NicheOnboardingPipeline()

        # Step-by-step execution
        state = pipeline.start("telemedicine")
        state = pipeline.upload_documents(state, files=[("doc.pdf", None)])
        questions = pipeline.get_questions(state)
        state = pipeline.submit_answer(state, "business_name", "My Clinic")
        state = pipeline.validate(state)
        state = pipeline.safety_check(state)
        result = pipeline.certify(state, private_key="...")

        # Or run full pipeline automatically
        result = pipeline.run_full(
            niche_id="telemedicine",
            files=[("doc.pdf", None)],
            answers={"business_name": "My Clinic", ...},
            private_key="...",
        )
    """

    def __init__(self) -> None:
        self._bridge = NicheBridge()
        self._ingestor = DocumentIngestor()
        self._collector = InteractiveDataCollector()
        self._domain_gate = get_default_domain_safety_gate()
        self._certifier = BlueprintCertifier()

    # ── Step 1: SELECT_NICHE ──────────────────────────────────

    def start(self, niche_id: str) -> PipelineState:
        """
        Start a new pipeline by selecting a niche.

        Generates a template from the niche catalog.
        """
        state = PipelineState(niche_id)

        # Get niche from catalog
        niche = self._bridge.get_niche(niche_id)
        if niche is None:
            state.add_error(f"Niche not found: {niche_id}")
            state.advance(PipelineStep.FAILED)
            return state

        # Determine category
        state.niche_category = getattr(niche, "category", "ai_data")
        if hasattr(niche, "niche_category"):
            state.niche_category = niche.niche_category

        # Generate template
        template_dict = self._bridge.create_template(niche_id)
        if template_dict is None:
            state.add_error(f"Template generation failed for niche: {niche_id}")
            state.advance(PipelineStep.FAILED)
            return state

        state.template_dict = template_dict
        state.advance(PipelineStep.SELECT_NICHE)

        # Calculate initial field counts
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
        state: PipelineState,
        files: Optional[List[Tuple[str, Optional[bytes]]]] = None,
        texts: Optional[List[str]] = None,
    ) -> PipelineState:
        """
        Upload and ingest documents. Auto-fills matched template fields.
        """
        if state.current_step == PipelineStep.FAILED:
            return state

        if state.template_dict is None:
            state.add_error("No template available for document ingestion")
            state.advance(PipelineStep.FAILED)
            return state

        result = self._ingestor.ingest_and_match(
            niche_id=state.niche_id,
            files=files,
            texts=texts,
        )

        state.documents_ingested = result.documents_processed

        if result.is_success:
            # Update template with matched fields
            if result.template_dict is not None:
                state.template_dict = result.template_dict
            state.fields_auto_filled = len(result.matched_fields)
            state.add_warning(f"Auto-filled {len(result.matched_fields)} fields from {result.documents_processed} documents")
        else:
            if result.errors:
                state.add_warning(f"Document ingestion had errors: {'; '.join(result.errors[:3])}")
            else:
                state.add_warning("No fields could be matched from uploaded documents")

        # Update field counts
        if state.template_dict is not None:
            validation = self._bridge.validate_template(state.template_dict)
            if isinstance(validation, dict):
                state.total_fields = validation.get("total_fields", 0)
                state.required_fields = validation.get("missing_required", 0)

        state.advance(PipelineStep.UPLOAD_DOCUMENTS)
        logger.info(
            "Pipeline %s: Ingested %d documents, auto-filled %d fields",
            state.pipeline_id, state.documents_ingested, state.fields_auto_filled,
        )
        return state

    # ── Step 3: GENERATE_QUESTIONS ────────────────────────────

    def get_questions(self, state: PipelineState) -> List[Dict[str, Any]]:
        """
        Get questions for missing required fields.
        """
        if state.template_dict is None:
            return []

        missing = self._bridge.all_missing_fields(state.template_dict)
        state.questions = missing
        state.advance(PipelineStep.GENERATE_QUESTIONS)
        return missing

    # ── Step 4: COLLECT_ANSWERS ───────────────────────────────

    def submit_answer(
        self,
        state: PipelineState,
        field_name: str,
        value: str,
        section_id: str = "",
    ) -> PipelineState:
        """Submit a single answer for a missing field."""
        if state.template_dict is None:
            state.add_error("No template available")
            return state

        # Apply directly via NicheTemplate
        if section_id:
            applied = self._bridge.fill_field(state.template_dict, section_id, field_name, value)
        else:
            # Try to find the section automatically
            applied = self._auto_fill_field(state.template_dict, field_name, value)

        if applied:
            state.fields_manual_filled += 1
        else:
            state.add_warning(f"Field '{field_name}' could not be set")

        state.advance(PipelineStep.COLLECT_ANSWERS)
        return state

    def submit_answers(
        self,
        state: PipelineState,
        answers: Dict[str, str],
    ) -> PipelineState:
        """Submit batch answers for missing fields."""
        for field_name, value in answers.items():
            self.submit_answer(state, field_name, value)

        return state

    # ── Step 5: VALIDATE_TEMPLATE ─────────────────────────────

    def validate(self, state: PipelineState) -> PipelineState:
        """
        Validate template completeness.
        """
        if state.template_dict is None:
            state.add_error("No template to validate")
            state.advance(PipelineStep.FAILED)
            return state

        validation = self._bridge.validate_template(state.template_dict)

        if isinstance(validation, dict):
            state.total_fields = validation.get("total_fields", 0)
            state.required_fields = validation.get("missing_required", 0)

            if validation.get("valid", False):
                logger.info(
                    "Pipeline %s: Template validation passed (%.1f%% complete)",
                    state.pipeline_id, validation.get("completion_pct", 0.0),
                )
            else:
                missing = validation.get("missing_field_names", [])
                state.add_warning(
                    f"Template incomplete: {len(missing)} missing required fields: "
                    f"{', '.join(missing[:5])}{'...' if len(missing) > 5 else ''}"
                )

        state.advance(PipelineStep.VALIDATE_TEMPLATE)
        return state

    # ── Step 6: SAFETY_CHECK ──────────────────────────────────

    def safety_check(
        self,
        state: PipelineState,
        action_type: str = "niche_onboarding",
        config: Optional[Dict[str, Any]] = None,
        data_sensitivity: str = "low",
    ) -> PipelineState:
        """
        Run domain safety + compliance check.

        INVARIANT: If safety gate returns DENY, the pipeline CANNOT proceed.
        """
        if state.current_step == PipelineStep.FAILED:
            return state

        config = config or {}

        # Add template metadata to config for compliance checking
        if state.template_dict is not None:
            config.setdefault("niche_id", state.niche_id)
            config.setdefault("niche_category", state.niche_category)

        safety_result = self._domain_gate.check(
            action_type=action_type,
            config=config,
            niche_category=state.niche_category,
            data_sensitivity=data_sensitivity,
        )

        state.safety_result = safety_result

        if not safety_result.can_proceed:
            state.add_error(
                f"Safety gate BLOCKED: {safety_result.reason}"
            )
            state.advance(PipelineStep.FAILED)
            logger.warning(
                "Pipeline %s: Safety check FAILED — %s",
                state.pipeline_id, safety_result.reason,
            )
            return state

        # Log compliance results
        for cr in safety_result.compliance_results:
            if not cr.compliant:
                state.add_warning(
                    f"Compliance ({cr.standard}): {len(cr.violations)} violation(s) — {cr.risk_level} risk"
                )

        if safety_result.escalation_applied:
            state.add_warning(
                f"Sensitivity escalation applied: {safety_result.base_verdict} → {safety_result.final_verdict}"
            )

        state.advance(PipelineStep.SAFETY_CHECK)
        logger.info(
            "Pipeline %s: Safety check PASSED (verdict=%s)",
            state.pipeline_id, safety_result.final_verdict,
        )
        return state

    # ── Step 7: CERTIFY_BLUEPRINT ─────────────────────────────

    def certify(
        self,
        state: PipelineState,
        private_key: str,
    ) -> PipelineState:
        """
        Certify the blueprint with ECDSA signing.
        """
        if state.current_step == PipelineStep.FAILED:
            return state

        if state.template_dict is None:
            state.add_error("No template to certify")
            state.advance(PipelineStep.FAILED)
            return state

        cert_result = self._certifier.certify_template(
            state.template_dict, private_key
        )

        state.cert_result = cert_result

        if not cert_result.success:
            state.add_error(f"Certification failed: {'; '.join(cert_result.errors)}")
            state.advance(PipelineStep.FAILED)
            return state

        state.add_warning(f"Blueprint certified: {cert_result.blueprint_id}")
        state.advance(PipelineStep.CERTIFY_BLUEPRINT)
        logger.info(
            "Pipeline %s: Blueprint certified (id=%s, hash=%s)",
            state.pipeline_id,
            cert_result.blueprint_id,
            cert_result.content_hash[:16],
        )
        return state

    # ── Step 8: EXPORT ────────────────────────────────────────

    def export(self, state: PipelineState) -> PipelineResult:
        """
        Export the final YAML output.
        """
        yaml_output = ""

        # Try to get YAML from certified blueprint
        if state.cert_result is not None and state.cert_result.yaml_string:
            yaml_output = state.cert_result.yaml_string
        elif state.template_dict is not None:
            yaml_output = self._bridge.template_to_yaml(state.template_dict) or ""

        state.advance(PipelineStep.COMPLETED)

        success = (
            state.current_step == PipelineStep.COMPLETED
            and len(state.errors) == 0
        )

        logger.info(
            "Pipeline %s: %s (niche=%s, safety=%s, certified=%s)",
            state.pipeline_id,
            "COMPLETED" if success else "COMPLETED_WITH_ISSUES",
            state.niche_id,
            "passed" if state.safety_result and state.safety_result.can_proceed else "N/A",
            "yes" if state.cert_result and state.cert_result.is_certified else "no",
        )

        return PipelineResult(
            success=success,
            pipeline_id=state.pipeline_id,
            niche_id=state.niche_id,
            final_step=state.current_step.value,
            progress_pct=state.progress_pct(),
            template_complete=state.required_fields == 0,
            safety_passed=state.safety_result.can_proceed if state.safety_result else False,
            blueprint_certified=state.cert_result.is_certified if state.cert_result else False,
            yaml_output=yaml_output,
            errors=state.errors,
            warnings=state.warnings,
        )

    # ── Full Pipeline Runner ──────────────────────────────────

    def run_full(
        self,
        niche_id: str,
        files: Optional[List[Tuple[str, Optional[bytes]]]] = None,
        texts: Optional[List[str]] = None,
        answers: Optional[Dict[str, str]] = None,
        private_key: str = "",
        data_sensitivity: str = "low",
    ) -> PipelineResult:
        """
        Run the full pipeline from start to finish.

        This is a convenience method that executes all 8 steps in sequence.
        For interactive workflows, use the step-by-step methods instead.
        """
        # Step 1: Select niche
        state = self.start(niche_id)
        if state.current_step == PipelineStep.FAILED:
            return self.export(state)

        # Step 2: Upload documents
        if files or texts:
            state = self.upload_documents(state, files=files, texts=texts)
            if state.current_step == PipelineStep.FAILED:
                return self.export(state)

        # Step 4: Submit answers (skip Step 3 if we have answers)
        if answers:
            state = self.submit_answers(state, answers)

        # Step 5: Validate
        state = self.validate(state)

        # Step 6: Safety check
        state = self.safety_check(state, data_sensitivity=data_sensitivity)
        if state.current_step == PipelineStep.FAILED:
            return self.export(state)

        # Step 7: Certify
        if private_key:
            state = self.certify(state, private_key)
            if state.current_step == PipelineStep.FAILED:
                return self.export(state)

        # Step 8: Export
        return self.export(state)

    # ── Progress ──────────────────────────────────────────────

    def get_progress(self, state: PipelineState) -> PipelineProgress:
        """Get pipeline progress information."""
        return PipelineProgress(
            pipeline_id=state.pipeline_id,
            niche_id=state.niche_id,
            current_step=state.current_step.value,
            progress_pct=state.progress_pct(),
            documents_ingested=state.documents_ingested,
            fields_auto_filled=state.fields_auto_filled,
            fields_manual_filled=state.fields_manual_filled,
            total_fields=state.total_fields,
            required_fields=state.required_fields,
            template_completion_pct=0.0,
            error_count=len(state.errors),
            warning_count=len(state.warnings),
        )

    # ── Helpers ───────────────────────────────────────────────

    def _auto_fill_field(
        self, template_dict: Dict[str, Any], field_name: str, value: str,
    ) -> bool:
        """Auto-fill a field by searching all sections."""
        template = template_dict.get("template", template_dict)
        sections = template.get("sections", {})

        for section_id, section in sections.items():
            if not isinstance(section, dict):
                continue
            fields = section.get("fields", {})
            if field_name in fields:
                return self._bridge.fill_field(template_dict, section_id, field_name, value)

        return False


__all__ = ["NicheOnboardingPipeline"]
