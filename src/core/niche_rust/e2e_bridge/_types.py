"""
E2E Bridge — Types.

Contains PipelineProgress and PipelineResult data classes.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


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
