"""
Zenic-Agents — Document Ingestion Bridge (Phase 6.B)

Python bridge that coordinates the full document ingestion pipeline:
  1. DocumentParser → extract text from uploaded files
  2. Rust extractor → match fields against template
  3. NicheTemplate → auto-fill template with matched fields

Provides:
    - DocumentIngestor: main pipeline orchestrator
    - IngestionResult: result of a full ingestion operation

Fallback:
    If the Rust extension is not available, all methods return
    empty results with logged warnings. This ensures the codebase
    never crashes due to a missing native extension.
"""

from ._types import IngestionResult, NATIVE_AVAILABLE, os_path_exists
from ._mixin_core import DocumentIngestor

__all__ = [
    "IngestionResult",
    "DocumentIngestor",
    "NATIVE_AVAILABLE",
    "os_path_exists",
]
