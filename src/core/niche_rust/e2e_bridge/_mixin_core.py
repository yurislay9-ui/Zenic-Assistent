"""
E2E Bridge — NichePipeline class.

Step-by-step E2E niche onboarding pipeline.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from ._types import PipelineProgress

logger = logging.getLogger(__name__)


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
        """Start a new pipeline by selecting a niche."""
        native = self._get_native()
        if native is not None:
            try:
                return native.e2e_start(niche_id)
            except Exception as e:
                logger.error(f"Rust e2e_start failed: {e}")

        return None, None

    def upload_documents(
        self,
        state: Any,
        template_dict: Dict[str, Any],
        extracted_texts: List[Any],
    ) -> Any:
        """Upload and ingest documents into the pipeline."""
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
        """Get questions for missing required fields."""
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
        """Submit a single answer for a missing field."""
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
        """Submit batch answers for missing fields."""
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
        """Validate template completeness."""
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
        """Run domain safety + compliance check."""
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
        """Certify the blueprint."""
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
        """Export the final YAML output."""
        native = self._get_native()
        if native is not None and state is not None:
            try:
                return native.e2e_export(state, template_dict)
            except Exception as e:
                logger.error(f"Rust e2e_export failed: {e}")

        return state, ""

    def get_progress(self, state: Any) -> PipelineProgress:
        """Get pipeline progress information."""
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
