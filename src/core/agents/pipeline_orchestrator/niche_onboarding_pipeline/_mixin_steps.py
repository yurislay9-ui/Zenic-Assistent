"""niche_onboarding_pipeline — Steps mixin (questions, validate, safety, certify, export)."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from ._types import *  # noqa: F403

logger = logging.getLogger("zenic_agents.agents.niche_onboarding_pipeline")


class NicheOnboardingStepsMixin:
    """Pipeline step methods for NicheOnboardingPipeline."""

    # ── Step 3: GENERATE_QUESTIONS ────────────────────────────

    def get_questions(self, state: PipelineState) -> List[Dict[str, Any]]:  # noqa: F821
        """Get questions for missing required fields."""
        if state.template_dict is None:
            return []
        missing = self._bridge.all_missing_fields(state.template_dict)
        state.questions = missing
        state.advance(PipelineStep.GENERATE_QUESTIONS)  # noqa: F821
        return missing

    # ── Step 4: COLLECT_ANSWERS ───────────────────────────────

    def submit_answer(
        self,
        state: PipelineState,  # noqa: F821
        field_name: str,
        value: str,
        section_id: str = "",
    ) -> PipelineState:  # noqa: F821
        """Submit a single answer for a missing field."""
        if state.template_dict is None:
            state.add_error("No template available")
            return state

        if section_id:
            applied = self._bridge.fill_field(state.template_dict, section_id, field_name, value)
        else:
            applied = self._auto_fill_field(state.template_dict, field_name, value)

        if applied:
            state.fields_manual_filled += 1
        else:
            state.add_warning(f"Field '{field_name}' could not be set")

        state.advance(PipelineStep.COLLECT_ANSWERS)  # noqa: F821
        return state

    def submit_answers(
        self,
        state: PipelineState,  # noqa: F821
        answers: Dict[str, str],
    ) -> PipelineState:  # noqa: F821
        """Submit batch answers for missing fields."""
        for field_name, value in answers.items():
            self.submit_answer(state, field_name, value)
        return state

    # ── Step 5: VALIDATE_TEMPLATE ─────────────────────────────

    def validate(self, state: PipelineState) -> PipelineState:  # noqa: F821
        """Validate template completeness."""
        if state.template_dict is None:
            state.add_error("No template to validate")
            state.advance(PipelineStep.FAILED)  # noqa: F821
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

        state.advance(PipelineStep.VALIDATE_TEMPLATE)  # noqa: F821
        return state

    # ── Step 6: SAFETY_CHECK ──────────────────────────────────

    def safety_check(
        self,
        state: PipelineState,  # noqa: F821
        action_type: str = "niche_onboarding",
        config: Optional[Dict[str, Any]] = None,
        data_sensitivity: str = "low",
    ) -> PipelineState:  # noqa: F821
        """Run domain safety + compliance check."""
        if state.current_step == PipelineStep.FAILED:  # noqa: F821
            return state

        config = config or {}
        if state.template_dict is not None:
            config.setdefault("niche_id", state.niche_id)
            config.setdefault("niche_category", state.niche_category)

        safety_result = self._domain_gate.check(
            action_type=action_type, config=config,
            niche_category=state.niche_category,
            data_sensitivity=data_sensitivity,
        )

        state.safety_result = safety_result

        if not safety_result.can_proceed:
            state.add_error(f"Safety gate BLOCKED: {safety_result.reason}")
            state.advance(PipelineStep.FAILED)  # noqa: F821
            logger.warning("Pipeline %s: Safety check FAILED — %s", state.pipeline_id, safety_result.reason)
            return state

        for cr in safety_result.compliance_results:
            if not cr.compliant:
                state.add_warning(
                    f"Compliance ({cr.standard}): {len(cr.violations)} violation(s) — {cr.risk_level} risk"
                )

        if safety_result.escalation_applied:
            state.add_warning(
                f"Sensitivity escalation applied: {safety_result.base_verdict} → {safety_result.final_verdict}"
            )

        state.advance(PipelineStep.SAFETY_CHECK)  # noqa: F821
        logger.info("Pipeline %s: Safety check PASSED (verdict=%s)", state.pipeline_id, safety_result.final_verdict)
        return state

    # ── Step 7: CERTIFY_BLUEPRINT ─────────────────────────────

    def certify(self, state: PipelineState, private_key: str) -> PipelineState:  # noqa: F821
        """Certify the blueprint with ECDSA signing."""
        if state.current_step == PipelineStep.FAILED:  # noqa: F821
            return state
        if state.template_dict is None:
            state.add_error("No template to certify")
            state.advance(PipelineStep.FAILED)  # noqa: F821
            return state

        cert_result = self._certifier.certify_template(state.template_dict, private_key)
        state.cert_result = cert_result

        if not cert_result.success:
            state.add_error(f"Certification failed: {'; '.join(cert_result.errors)}")
            state.advance(PipelineStep.FAILED)  # noqa: F821
            return state

        state.add_warning(f"Blueprint certified: {cert_result.blueprint_id}")
        state.advance(PipelineStep.CERTIFY_BLUEPRINT)  # noqa: F821
        logger.info(
            "Pipeline %s: Blueprint certified (id=%s, hash=%s)",
            state.pipeline_id, cert_result.blueprint_id, cert_result.content_hash[:16],
        )
        return state

    # ── Step 8: EXPORT ────────────────────────────────────────

    def export(self, state: PipelineState) -> PipelineResult:  # noqa: F821
        """Export the final YAML output."""
        yaml_output = ""

        if state.cert_result is not None and state.cert_result.yaml_string:
            yaml_output = state.cert_result.yaml_string
        elif state.template_dict is not None:
            yaml_output = self._bridge.template_to_yaml(state.template_dict) or ""

        state.advance(PipelineStep.COMPLETED)  # noqa: F821

        success = (
            state.current_step == PipelineStep.COMPLETED  # noqa: F821
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
    ) -> PipelineResult:  # noqa: F821
        """Run the full pipeline from start to finish."""
        state = self.start(niche_id)
        if state.current_step == PipelineStep.FAILED:  # noqa: F821
            return self.export(state)

        if files or texts:
            state = self.upload_documents(state, files=files, texts=texts)
            if state.current_step == PipelineStep.FAILED:  # noqa: F821
                return self.export(state)

        if answers:
            state = self.submit_answers(state, answers)

        state = self.validate(state)

        state = self.safety_check(state, data_sensitivity=data_sensitivity)
        if state.current_step == PipelineStep.FAILED:  # noqa: F821
            return self.export(state)

        if private_key:
            state = self.certify(state, private_key)
            if state.current_step == PipelineStep.FAILED:  # noqa: F821
                return self.export(state)

        return self.export(state)

    # ── Progress ──────────────────────────────────────────────

    def get_progress(self, state: PipelineState) -> PipelineProgress:  # noqa: F821
        """Get pipeline progress information."""
        return PipelineProgress(  # noqa: F821
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
