"""
Zenic-Agents — Niche Rust Bridge (Phase 6.A + 6.B + 6.D)

Python wrapper for the Rust-compiled niche system exposed
via PyO3 in the ``_zenic_native`` extension module.

This package provides a clean Python API over the raw PyO3
bindings, with fallback to Python-only implementations when
the Rust extension is not available.

Public API (Phase 6.A):
    - NicheCatalog: query the compiled niche catalog
    - NicheTemplate: generate, validate, and fill YAML templates
    - NicheBridge: unified facade for catalog + template

Public API (Phase 6.B):
    - DocumentParser: Python-side document parsing (PDF, DOCX, HTML)
    - DocumentIngestor: full ingestion pipeline (parse → extract → match → fill)
    - IngestionResult: result of a full ingestion operation

Public API (Phase 6.D):
    - BlueprintCertifier: template → BlueprintConfig → CertifiedBlueprint
    - CertificationHelper: convenience workflow methods
    - CertificationResultPy: Python-side certification result

Public API (Phase D):
    - NichePipeline: step-by-step E2E niche onboarding pipeline
    - PipelineProgress: pipeline progress tracking
    - PipelineResult: final pipeline result
"""

from .bridge import NicheBridge, NicheCatalog, NicheTemplate
from .document_parser import DocumentParser
from .ingest_bridge import DocumentIngestor, IngestionResult
from .certifier_bridge import BlueprintCertifier, CertificationHelper, CertificationResultPy
from .e2e_bridge import NichePipeline, PipelineProgress, PipelineResult

__all__ = [
    "NicheBridge",
    "NicheCatalog",
    "NicheTemplate",
    "DocumentParser",
    "DocumentIngestor",
    "IngestionResult",
    "BlueprintCertifier",
    "CertificationHelper",
    "CertificationResultPy",
    "NichePipeline",
    "PipelineProgress",
    "PipelineResult",
]

__version__ = "3.1.0"
