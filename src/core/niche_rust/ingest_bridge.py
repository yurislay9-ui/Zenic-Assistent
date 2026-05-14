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

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .bridge import NicheBridge, NicheCatalog, NicheTemplate
from .document_parser import DocumentParser

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
#  Rust Extension Import
# ──────────────────────────────────────────────────────────────

_NATIVE_AVAILABLE: bool = False
_native = None

try:
    import _zenic_native as _native  # type: ignore[import-not-found]
    _NATIVE_AVAILABLE = True
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
#  DocumentIngestor — Main pipeline orchestrator
# ──────────────────────────────────────────────────────────────

class DocumentIngestor:
    """Full document ingestion pipeline for Zenic-Agents.

    Coordinates:
        1. Document parsing (Python: PDF/DOCX, Rust: TXT/CSV/JSON)
        2. Text extraction and normalization
        3. Field matching against template (Rust: pattern matching)
        4. Template auto-fill with matched fields

    Usage::

        ingestor = DocumentIngestor()

        # Ingest documents and match to a niche template
        result = ingestor.ingest_and_match(
            niche_id="telemedicine",
            files=[("/path/to/clinic_info.pdf", None)],
        )

        # Get the auto-filled template
        if result.is_success:
            template = result.template_dict

        # Check what still needs to be filled
        bridge = NicheBridge()
        missing = bridge.all_missing_fields(result.template_dict)
    """

    def __init__(self) -> None:
        self._parser = DocumentParser()
        self._catalog = NicheCatalog()
        self._template = NicheTemplate()

    # ── Core Pipeline ─────────────────────────────────────

    def ingest_and_match(
        self,
        niche_id: str,
        files: Optional[List[Tuple[str, Optional[bytes]]]] = None,
        texts: Optional[List[str]] = None,
    ) -> IngestionResult:
        """Full ingestion pipeline: parse → extract → match → fill.

        This is the primary entry point for document ingestion.
        It takes a niche_id and a list of files/texts, generates
        a template, extracts data, matches fields, and fills the
        template.

        Args:
            niche_id: The niche identifier from the catalog.
            files: Optional list of (file_path, bytes_data) tuples.
                If bytes_data is None, reads from file_path.
            texts: Optional list of raw text strings to include.

        Returns:
            IngestionResult with the auto-filled template and stats.
        """
        result = IngestionResult()

        if not niche_id or not isinstance(niche_id, str):
            result.errors.append("niche_id must be a non-empty string")
            return result

        # Step 1: Generate template from niche
        template_dict = self._template.generate(niche_id)
        if template_dict is None:
            result.errors.append(f"Niche not found: {niche_id}")
            return result
        result.template_dict = template_dict

        # Step 2: Extract text from all documents
        extracted_texts = self._extract_all_texts(files, texts)
        result.documents_processed = len(extracted_texts)

        if not extracted_texts:
            result.errors.append("No text could be extracted from the provided documents")
            return result

        # Step 3: Match fields using Rust extractor
        extraction_result = self._match_fields(template_dict, extracted_texts)
        if extraction_result is not None:
            result.extraction_result = extraction_result
            result.matched_fields = getattr(extraction_result, "matched_fields", [])
            result.unmatched_fields = getattr(extraction_result, "unmatched_fields", [])
            result.confidence_avg = getattr(extraction_result, "confidence_avg", 0.0)

            # Step 4: Apply matches to template
            if _NATIVE_AVAILABLE and hasattr(extraction_result, "matches"):
                try:
                    _native.extractor_apply_matches(
                        template_dict, extraction_result.matches
                    )
                except Exception as e:
                    result.errors.append(f"Apply matches error: {e}")

        # Recalculate matched/unmatched from template validation
        if template_dict is not None:
            validation = self._template.validate(template_dict)
            if isinstance(validation, dict):
                result.matched_fields = [
                    f for f in validation.get("missing_field_names", [])
                    if f not in validation.get("missing_field_names", [])
                ]
                # Actually: filled = total - missing
                filled = validation.get("filled_fields", 0)
                missing_names = validation.get("missing_field_names", [])
                result.unmatched_fields = missing_names

        return result

    def ingest_files_only(
        self,
        files: List[Tuple[str, Optional[bytes]]],
    ) -> List[Any]:
        """Extract text from files without matching to a template.

        Useful for previewing extracted text before selecting a niche.

        Args:
            files: List of (file_path, bytes_data) tuples.

        Returns:
            List of ExtractedText objects (PyO3) or empty dicts.
        """
        return self._extract_all_texts(files, [])

    def match_text_to_template(
        self,
        niche_id: str,
        text: str,
        source_name: str = "user_text",
    ) -> IngestionResult:
        """Match a single text string against a niche template.

        Convenience method for matching raw text (e.g., from
        a user input field) without file upload.

        Args:
            niche_id: The niche identifier.
            text: The text content to match.
            source_name: Label for the text source.

        Returns:
            IngestionResult with the auto-filled template.
        """
        return self.ingest_and_match(
            niche_id=niche_id,
            texts=[text] if text else None,
        )

    # ── Field Detection ───────────────────────────────────

    def detect_format(self, filename: str) -> str:
        """Detect document format from filename.

        Args:
            filename: The document filename.

        Returns:
            Format string (e.g., "pdf", "txt", "unknown").
        """
        if _NATIVE_AVAILABLE:
            try:
                fmt = _native.ingest_detect_format(filename)
                return str(fmt)
            except Exception:
                pass

        # Python fallback
        ext = DocumentParser._get_extension(filename)
        format_map = {
            "pdf": "pdf",
            "docx": "docx",
            "doc": "docx",
            "txt": "txt",
            "csv": "csv",
            "tsv": "csv",
            "json": "json",
            "md": "markdown",
            "markdown": "markdown",
            "html": "html",
            "htm": "html",
        }
        return format_map.get(ext, "unknown")

    def supported_formats(self) -> List[str]:
        """Get list of all supported document format strings.

        Returns:
            List of format strings (e.g., ["pdf", "docx", "txt", ...]).
        """
        if _NATIVE_AVAILABLE:
            try:
                return _native.ingest_supported_formats()
            except Exception:
                pass
        return ["pdf", "docx", "txt", "csv", "json", "markdown", "html"]

    def validate_document_size(self, size_bytes: int) -> bool:
        """Validate document size against maximum limit.

        Args:
            size_bytes: Document size in bytes.

        Returns:
            True if size is within limits.
        """
        if _NATIVE_AVAILABLE:
            try:
                return _native.ingest_validate_size(size_bytes)
            except Exception:
                pass
        return 0 < size_bytes <= 50 * 1024 * 1024

    def available_parsers(self) -> Dict[str, bool]:
        """Check which parsers (Rust and Python) are available.

        Returns:
            Dict mapping parser name to availability.
        """
        parsers: Dict[str, bool] = {}
        parsers["rust_native"] = _NATIVE_AVAILABLE
        parsers.update(self._parser.available_parsers())
        return parsers

    # ── Internal Helpers ──────────────────────────────────

    def _extract_all_texts(
        self,
        files: Optional[List[Tuple[str, Optional[bytes]]]],
        texts: Optional[List[str]],
    ) -> List[Any]:
        """Extract text from all sources (files + raw texts).

        Args:
            files: Optional list of (filename, bytes_or_none) tuples.
            texts: Optional list of raw text strings.

        Returns:
            List of ExtractedText objects or plain dicts.
        """
        extracted: List[Any] = []

        # Process files
        if files:
            for file_info in files:
                if not isinstance(file_info, (tuple, list)) or len(file_info) < 1:
                    continue

                filename = file_info[0]
                data = file_info[1] if len(file_info) > 1 else None

                ext_text = self._extract_single_file(filename, data)
                if ext_text is not None:
                    extracted.append(ext_text)

        # Process raw texts
        if texts:
            for text in texts:
                if not text or not isinstance(text, str):
                    continue
                ext_text = self._process_raw_text(text)
                if ext_text is not None:
                    extracted.append(ext_text)

        return extracted

    def _extract_single_file(
        self, filename: str, data: Optional[bytes]
    ) -> Optional[Any]:
        """Extract text from a single file.

        Uses Rust for simple formats (TXT/CSV/JSON/MD) and Python
        for binary formats (PDF/DOCX/HTML).

        Args:
            filename: The document filename.
            data: Raw bytes, or None to read from filename path.

        Returns:
            ExtractedText object, or dict with text data, or None.
        """
        fmt_str = self.detect_format(filename)

        # Rust-native formats
        if _NATIVE_AVAILABLE and fmt_str in ("txt", "csv", "json", "markdown"):
            try:
                if data is not None:
                    return _native.ingest_extract_text_simple(filename, data)
                elif os_path_exists(filename):
                    with open(filename, "rb") as f:
                        data = f.read()
                    return _native.ingest_extract_text_simple(filename, data)
            except Exception as e:
                logger.error("Rust extraction failed for %s: %s", filename, e)

        # Python-side parsing (PDF, DOCX, HTML)
        if fmt_str in ("pdf", "docx", "html"):
            text_content: str = ""
            errors: List[str] = []

            if data is not None:
                text_content, errors = self._parser.parse_bytes(filename, data)
            elif os_path_exists(filename):
                text_content, errors = self._parser.parse_file(filename)

            if text_content and _NATIVE_AVAILABLE:
                try:
                    return _native.ingest_process_extracted_text(
                        filename, fmt_str, text_content
                    )
                except Exception as e:
                    logger.error("Rust processing failed for %s: %s", filename, e)
                    return {"filename": filename, "text": text_content, "errors": errors}

            if text_content:
                return {"filename": filename, "text": text_content, "errors": errors}

        # Fallback: try Python parser for any format
        if data is not None:
            text_content, errors = self._parser.parse_bytes(filename, data)
        elif os_path_exists(filename):
            text_content, errors = self._parser.parse_file(filename)
        else:
            return None

        if text_content and _NATIVE_AVAILABLE:
            try:
                return _native.ingest_process_extracted_text(
                    filename, fmt_str, text_content
                )
            except Exception:
                return {"filename": filename, "text": text_content, "errors": errors}

        if text_content:
            return {"filename": filename, "text": text_content, "errors": errors}

        return None

    def _process_raw_text(self, text: str) -> Optional[Any]:
        """Process a raw text string through the Rust pipeline.

        Args:
            text: The text content.

        Returns:
            ExtractedText object, or dict with text data, or None.
        """
        if not text.strip():
            return None

        if _NATIVE_AVAILABLE:
            try:
                return _native.ingest_process_extracted_text(
                    "user_text", "txt", text
                )
            except Exception as e:
                logger.error("Rust text processing failed: %s", e)

        return {"filename": "user_text", "text": text, "errors": []}

    def _match_fields(
        self,
        template_dict: Dict[str, Any],
        extracted_texts: List[Any],
    ) -> Optional[Any]:
        """Match extracted text fields against template using Rust extractor.

        Args:
            template_dict: The template dict.
            extracted_texts: List of ExtractedText objects or dicts.

        Returns:
            ExtractionResult from Rust, or None.
        """
        if not _NATIVE_AVAILABLE:
            logger.warning("DocumentIngestor._match_fields: Rust extension not available")
            return None

        try:
            # Convert dict-based texts to ExtractedText if needed
            native_texts = []
            for ext in extracted_texts:
                if isinstance(ext, dict):
                    # Convert dict to ExtractedText via Rust
                    text_content = ext.get("text", "")
                    filename = ext.get("filename", "unknown")
                    if text_content:
                        native_text = _native.ingest_process_extracted_text(
                            filename, "txt", text_content
                        )
                        native_texts.append(native_text)
                else:
                    native_texts.append(ext)

            if not native_texts:
                return None

            return _native.extractor_match_fields(template_dict, native_texts)

        except Exception as e:
            logger.error("Field matching failed: %s", e)
            return None


# ──────────────────────────────────────────────────────────────
#  Utility Functions
# ──────────────────────────────────────────────────────────────

def os_path_exists(path: str) -> bool:
    """Check if a file path exists, with error handling.

    Args:
        path: File path to check.

    Returns:
        True if the file exists, False otherwise.
    """
    try:
        import os
        return os.path.exists(path)
    except Exception:
        return False
