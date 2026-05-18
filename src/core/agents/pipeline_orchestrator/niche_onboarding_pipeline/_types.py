"""niche_onboarding_pipeline — Type definitions."""

from __future__ import annotations

import logging
import time
import uuid
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from ...executors.safety_gate.domain_gate import (
    DomainSafetyGate,
    DomainSafetyCheckResult,
    ComplianceResult,
    get_default_domain_safety_gate,
)
from ...executors.safety_gate._types import SafetyVerdict
from ...niche_rust.bridge import NicheBridge, NicheCatalog, NicheTemplate
from ...niche_rust.ingest_bridge import DocumentIngestor, IngestionResult
from ...niche_rust.certifier_bridge import BlueprintCertifier, CertificationResultPy, CertificationHelper
from ...niche_rust.e2e_bridge import PipelineProgress, PipelineResult
from ..business.interactive_data_collector import (
    InteractiveDataCollector,
    InteractiveCollectionResult,
)

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
# PIPELINE STEPS
# ──────────────────────────────────────────────────────────────

class PipelineStep(str, Enum):
    """Pipeline step identifiers."""
    NOT_STARTED = "not_started"
    SELECT_NICHE = "select_niche"
    UPLOAD_DOCUMENTS = "upload_documents"
    GENERATE_QUESTIONS = "generate_questions"
    COLLECT_ANSWERS = "collect_answers"
    VALIDATE_TEMPLATE = "validate_template"
    SAFETY_CHECK = "safety_check"
    CERTIFY_BLUEPRINT = "certify_blueprint"
    EXPORT = "export"
    COMPLETED = "completed"
    FAILED = "failed"


# ──────────────────────────────────────────────────────────────
# PIPELINE STATE
# ──────────────────────────────────────────────────────────────

class PipelineState:
    """Mutable state for an ongoing pipeline execution."""

    __slots__ = (
        "pipeline_id",
        "niche_id",
        "niche_category",
        "current_step",
        "template_dict",
        "session_id",
        "documents_ingested",
        "fields_auto_filled",
        "fields_manual_filled",
        "total_fields",
        "required_fields",
        "questions",
        "safety_result",
        "cert_result",
        "errors",
        "warnings",
        "created_at",
        "updated_at",
    )

    def __init__(self, niche_id: str = "") -> None:
        self.pipeline_id = f"pipe-{uuid.uuid4().hex[:8]}"
        self.niche_id = niche_id
        self.niche_category = ""
        self.current_step = PipelineStep.NOT_STARTED
        self.template_dict: Optional[Dict[str, Any]] = None
        self.session_id = ""
        self.documents_ingested = 0
        self.fields_auto_filled = 0
        self.fields_manual_filled = 0
        self.total_fields = 0
        self.required_fields = 0
        self.questions: List[Dict[str, Any]] = []
        self.safety_result: Optional[DomainSafetyCheckResult] = None
        self.cert_result: Optional[CertificationResultPy] = None
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.created_at = time.time()
        self.updated_at = time.time()

    def advance(self, step: PipelineStep) -> None:
        self.current_step = step
        self.updated_at = time.time()

    def add_error(self, msg: str) -> None:
        self.errors.append(msg)
        self.updated_at = time.time()

    def add_warning(self, msg: str) -> None:
        self.warnings.append(msg)
        self.updated_at = time.time()

    def progress_pct(self) -> float:
        """Calculate overall pipeline progress (0-100)."""
        step_values = {
            PipelineStep.NOT_STARTED: 0,
            PipelineStep.SELECT_NICHE: 12.5,
            PipelineStep.UPLOAD_DOCUMENTS: 25.0,
            PipelineStep.GENERATE_QUESTIONS: 37.5,
            PipelineStep.COLLECT_ANSWERS: 50.0,
            PipelineStep.VALIDATE_TEMPLATE: 62.5,
            PipelineStep.SAFETY_CHECK: 75.0,
            PipelineStep.CERTIFY_BLUEPRINT: 87.5,
            PipelineStep.EXPORT: 100.0,
            PipelineStep.COMPLETED: 100.0,
            PipelineStep.FAILED: self._last_progress,
        }
        return step_values.get(self.current_step, 0.0)

    @property
    def _last_progress(self) -> float:
        return 0.0


# ──────────────────────────────────────────────────────────────
# NICHE ONBOARDING PIPELINE
# ──────────────────────────────────────────────────────────────
