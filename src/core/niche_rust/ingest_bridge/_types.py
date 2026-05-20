"""
Ingest Bridge — Types and FFI imports.

Contains IngestionResult dataclass and the Rust extension
import block shared by ingest sub-modules.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
#  Rust Extension Import
# ──────────────────────────────────────────────────────────────

NATIVE_AVAILABLE: bool = False
_native = None

try:
    import _zenic_native as _native  # type: ignore[import-not-found]
    NATIVE_AVAILABLE = True
except ImportError:
    logger.warning(
        "IngestBridge: _zenic_native extension not available. "
        "Run 'maturin develop' to build the Rust extension. "
        "Falling back to Python-only mode."
    )


# ──────────────────────────────────────────────────────────────
#  IngestionResult — result of a full ingestion operation
# ──────────────────────────────────────────────────────────────

@dataclass
class IngestionResult:
    """Result of ingesting documents and matching to a template.

    Attributes:
        template_dict: The template dict (possibly modified with matches).
        extraction_result: The extraction result from Rust (or None).
        matched_fields: List of matched field names.
        unmatched_fields: List of unmatched field names.
        confidence_avg: Average confidence across matches.
        documents_processed: Number of documents processed.
        errors: List of error messages.
    """

    template_dict: Optional[Dict[str, Any]] = None
    extraction_result: Optional[Any] = None
    matched_fields: List[str] = field(default_factory=list)
    unmatched_fields: List[str] = field(default_factory=list)
    confidence_avg: float = 0.0
    documents_processed: int = 0
    errors: List[str] = field(default_factory=list)

    @property
    def is_success(self) -> bool:
        """Check if at least one field was matched."""
        return len(self.matched_fields) > 0

    @property
    def completion_rate(self) -> float:
        """Calculate the match completion rate (0.0-1.0)."""
        total = len(self.matched_fields) + len(self.unmatched_fields)
        if total == 0:
            return 0.0
        return len(self.matched_fields) / total

    def summary(self) -> Dict[str, Any]:
        """Get a summary dict for display purposes."""
        return {
            "matched_fields": len(self.matched_fields),
            "unmatched_fields": len(self.unmatched_fields),
            "confidence_avg": round(self.confidence_avg, 3),
            "documents_processed": self.documents_processed,
            "is_success": self.is_success,
            "completion_rate": round(self.completion_rate, 3),
            "errors": len(self.errors),
        }


# ──────────────────────────────────────────────────────────────
#  Utility
# ──────────────────────────────────────────────────────────────

def os_path_exists(path: str) -> bool:
    """Check if a file path exists, with error handling."""
    try:
        import os
        return os.path.exists(path)
    except Exception:
        return False
