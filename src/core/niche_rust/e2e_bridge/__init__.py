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

from ._types import PipelineProgress, PipelineResult
from ._mixin_core import NichePipeline

__all__ = [
    "PipelineProgress",
    "PipelineResult",
    "NichePipeline",
]
