"""
E2E Pipeline Bridge — Python wrapper for the Rust-compiled E2E pipeline.

Provides a clean Python API over the 8-step niche onboarding pipeline:
    1. SELECT_NICHE → catalog lookup + template generation
    2. UPLOAD_DOCUMENTS → document ingestion + extraction
    3. GENERATE_QUESTIONS → identify missing required fields
    4. COLLECT_ANSWERS → interactive Q&A with validation
    5. VALIDATE_TEMPLATE → completeness check
    6. SAFETY_CHECK → domain safety + compliance gate
    7. CERTIFY_BLUEPRINT → ECDSA signature + certified blueprint
    8. EXPORT → final YAML + metadata export

All core logic is in Rust. This module provides:
    - NichePipeline: step-by-step pipeline API
    - PipelineProgress: progress tracking
    - PipelineResult: final pipeline result
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class PipelineProgress:
    """Progress information for an E2E pipeline."""

    __slots__ = (
        "pipeline_id",
        "niche_id",
        "current_step",
        "progress_pct",
        "documents_ingested",
        "fields_auto_filled",
        "fields_manual_filled",
        "total_fields",
        "required_fields",
        "template_completion_pct",
        "error_count",
        "warning_count",
    )

    def __init__(
        self,
        pipeline_id: str = "",
        niche_id: str = "",
        current_step: str = "not_started",
        progress_pct: float = 0.0,
        documents_ingested: int = 0,
        fields_auto_filled: int = 0,
        fields_manual_filled: int = 0,
        total_fields: int = 0,
        required_fields: int = 0,
        template_completion_pct: float = 0.0,
        error_count: int = 0,
        warning_count: int = 0,
    ) -> None:
        self.pipeline_id = pipeline_id
        self.niche_id = niche_id
        self.current_step = current_step
        self.progress_pct = progress_pct
        self.documents_ingested = documents_ingested
        self.fields_auto_filled = fields_auto_filled
        self.fields_manual_filled = fields_manual_filled
        self.total_fields = total_fields
        self.required_fields = required_fields
        self.template_completion_pct = template_completion_pct
        self.error_count = error_count
        self.warning_count = warning_count

    def __repr__(self) -> str:
        return (
            f"PipelineProgress(id={self.pipeline_id!r}, step={self.current_step}, "
            f"pct={self.progress_pct:.1f}%)"
        )


class PipelineResult:
    """Final result of the E2E pipeline."""

    __slots__ = (
        "success",
        "pipeline_id",
        "niche_id",
        "final_step",
        "progress_pct",
        "template_complete",
        "safety_passed",
        "blueprint_certified",
        "yaml_output",
        "errors",
        "warnings",
    )

    def __init__(
        self,
        success: bool = False,
        pipeline_id: str = "",
        niche_id: str = "",
        final_step: str = "",
        progress_pct: float = 0.0,
        template_complete: bool = False,
        safety_passed: bool = False,
        blueprint_certified: bool = False,
        yaml_output: str = "",
        errors: Optional[List[str]] = None,
        warnings: Optional[List[str]] = None,
    ) -> None:
        self.success = success
        self.pipeline_id = pipeline_id
        self.niche_id = niche_id
        self.final_step = final_step
        self.progress_pct = progress_pct
        self.template_complete = template_complete
        self.safety_passed = safety_passed
        self.blueprint_certified = blueprint_certified
        self.yaml_output = yaml_output
        self.errors = errors or []
        self.warnings = warnings or []

    def __repr__(self) -> str:
        return (
            f"PipelineResult(success={self.success}, niche={self.niche_id!r}, "
            f"safety={self.safety_passed}, certified={self.blueprint_certified})"
        )


class NichePipeline:
    """
    Step-by-step E2E niche onboarding pipeline.

    Provides a clean API for the 8-step pipeline:
        1. start(niche_id) → (state, template_dict)
        2. upload_documents(state, template_dict, extracted_texts) → state
        3. get_questions(state, template_dict) → questions
        4. submit_answer(state, template_dict, field_name, value) → (state, applied)
        5. submit_answers(state, template_dict, answers) → (state, count)
        6. validate(state, template_dict) → (state, validation_dict)
        7. safety_check(state, action_type, config) → (state, safety_result)
        8. certify(state, template_dict) → (state, cert_result)
        9. export(state, template_dict) → (state, yaml_string)

    Each step updates the pipeline state and returns it.
    The pipeline is resumable: steps can be called independently.
    """

    def __init__(self) -> None:
        self._native = None

    def _get_native(self):
        """Lazy-load the _zenic_native Rust extension."""
        if self._native is None:
            try:
                import _zenic_native as _native_mod  # type: ignore[import-not-found]
                self._native = _native_mod
            except ImportError:
                self._native = None
        return self._native

    def start(
        self, niche_id: str
    ) -> tuple:
        """
        Start a new pipeline by selecting a niche.

        Returns
        -------
        tuple[pipeline_state, template_dict_or_none]
            The pipeline state and initial template dict.
        """
        native = self._get_native()
        if native is not None:
            try:
                return native.e2e_start(niche_id)
            except Exception as e:
                logger.error(f"Rust e2e_start failed: {e}")

        # Python fallback
        return None, None

    def upload_documents(
        self,
        state: Any,
        template_dict: Dict[str, Any],
        extracted_texts: List[Any],
    ) -> Any:
        """
        Upload and ingest documents into the pipeline.

        Returns
        -------
        E2EPipelineState
            Updated pipeline state.
        """
        native = self._get_native()
        if native is not None and state is not None:
            try:
                return native.e2e_upload_documents(state, template_dict, extracted_texts)
            except Exception as e:
                logger.error(f"Rust e2e_upload_documents failed: {e}")

        return state

    def get_questions(
        self,
        state: Any,
        template_dict: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        Get questions for missing required fields.

        Returns
        -------
        list[dict]
            Structured questions for missing fields.
        """
        native = self._get_native()
        if native is not None and state is not None:
            try:
                questions = native.e2e_get_questions(state, template_dict)
                return [
                    {
                        "field_name": q.field_name,
                        "display_name": q.display_name,
                        "field_type": q.field_type,
                        "section_id": q.section_id,
                        "description": q.description,
                        "is_required": q.is_required,
                        "suggestions": q.suggestions,
                        "enum_variants": q.enum_variants,
                        "default_value": q.default_value,
                        "validation_hint": q.validation_hint,
                    }
                    for q in questions
                ]
            except Exception as e:
                logger.error(f"Rust e2e_get_questions failed: {e}")

        return []

    def submit_answer(
        self,
        state: Any,
        template_dict: Dict[str, Any],
        field_name: str,
        section_id: str = "",
        value: str = "",
    ) -> tuple:
        """
        Submit a single answer for a missing field.

        Returns
        -------
        tuple[updated_state, was_applied]
        """
        native = self._get_native()
        if native is not None and state is not None:
            try:
                return native.e2e_submit_answer(
                    state, template_dict, field_name, section_id, value
                )
            except Exception as e:
                logger.error(f"Rust e2e_submit_answer failed: {e}")

        return state, False

    def submit_answers(
        self,
        state: Any,
        template_dict: Dict[str, Any],
        answers: Dict[str, str],
    ) -> tuple:
        """
        Submit batch answers for missing fields.

        Returns
        -------
        tuple[updated_state, count_applied]
        """
        native = self._get_native()
        if native is not None and state is not None:
            try:
                return native.e2e_submit_answers(state, template_dict, answers)
            except Exception as e:
                logger.error(f"Rust e2e_submit_answers failed: {e}")

        return state, 0

    def validate(
        self,
        state: Any,
        template_dict: Dict[str, Any],
    ) -> tuple:
        """
        Validate template completeness.

        Returns
        -------
        tuple[updated_state, validation_dict]
        """
        native = self._get_native()
        if native is not None and state is not None:
            try:
                return native.e2e_validate(state, template_dict)
            except Exception as e:
                logger.error(f"Rust e2e_validate failed: {e}")

        return state, {}

    def safety_check(
        self,
        state: Any,
        action_type: str = "niche_onboarding",
        config: Optional[Dict[str, Any]] = None,
    ) -> tuple:
        """
        Run domain safety + compliance check.

        Returns
        -------
        tuple[updated_state, safety_result]
        """
        native = self._get_native()
        config = config or {}
        if native is not None and state is not None:
            try:
                return native.e2e_safety_check(state, action_type, config)
            except Exception as e:
                logger.error(f"Rust e2e_safety_check failed: {e}")

        return state, None

    def certify(
        self,
        state: Any,
        template_dict: Dict[str, Any],
    ) -> tuple:
        """
        Certify the blueprint.

        Returns
        -------
        tuple[updated_state, cert_result]
        """
        native = self._get_native()
        if native is not None and state is not None:
            try:
                return native.e2e_certify(state, template_dict)
            except Exception as e:
                logger.error(f"Rust e2e_certify failed: {e}")

        return state, None

    def export(
        self,
        state: Any,
        template_dict: Dict[str, Any],
    ) -> tuple:
        """
        Export the final YAML output.

        Returns
        -------
        tuple[updated_state, yaml_string]
        """
        native = self._get_native()
        if native is not None and state is not None:
            try:
                return native.e2e_export(state, template_dict)
            except Exception as e:
                logger.error(f"Rust e2e_export failed: {e}")

        return state, ""

    def get_progress(self, state: Any) -> PipelineProgress:
        """
        Get pipeline progress information.

        Returns
        -------
        PipelineProgress
            Current progress info.
        """
        native = self._get_native()
        if native is not None and state is not None:
            try:
                progress_dict = native.e2e_get_progress(state)
                return PipelineProgress(
                    pipeline_id=progress_dict.get("pipeline_id", ""),
                    niche_id=progress_dict.get("niche_id", ""),
                    current_step=progress_dict.get("current_step", ""),
                    progress_pct=progress_dict.get("progress_pct", 0.0),
                    documents_ingested=progress_dict.get("documents_ingested", 0),
                    fields_auto_filled=progress_dict.get("fields_auto_filled", 0),
                    fields_manual_filled=progress_dict.get("fields_manual_filled", 0),
                    total_fields=progress_dict.get("total_fields", 0),
                    required_fields=progress_dict.get("required_fields", 0),
                    template_completion_pct=progress_dict.get("template_completion_pct", 0.0),
                    error_count=progress_dict.get("error_count", 0),
                    warning_count=progress_dict.get("warning_count", 0),
                )
            except Exception as e:
                logger.error(f"Rust e2e_get_progress failed: {e}")

        return PipelineProgress()
