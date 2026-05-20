"""
Ingest Bridge — DocumentIngestor class.

Main pipeline orchestrator for document ingestion and field matching.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from .bridge import NicheBridge, NicheCatalog, NicheTemplate
from .document_parser import DocumentParser
from ._types import IngestionResult, NATIVE_AVAILABLE, _native, os_path_exists

logger = logging.getLogger(__name__)


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
        """Full ingestion pipeline: parse → extract → match → fill."""
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
            if NATIVE_AVAILABLE and hasattr(extraction_result, "matches"):
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
                filled = validation.get("filled_fields", 0)
                missing_names = validation.get("missing_field_names", [])
                result.unmatched_fields = missing_names

        return result

    def ingest_files_only(
        self,
        files: List[Tuple[str, Optional[bytes]]],
    ) -> List[Any]:
        """Extract text from files without matching to a template."""
        return self._extract_all_texts(files, [])

    def match_text_to_template(
        self,
        niche_id: str,
        text: str,
        source_name: str = "user_text",
    ) -> IngestionResult:
        """Match a single text string against a niche template."""
        return self.ingest_and_match(
            niche_id=niche_id,
            texts=[text] if text else None,
        )

    # ── Field Detection ───────────────────────────────────

    def detect_format(self, filename: str) -> str:
        """Detect document format from filename."""
        if NATIVE_AVAILABLE:
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
        """Get list of all supported document format strings."""
        if NATIVE_AVAILABLE:
            try:
                return _native.ingest_supported_formats()
            except Exception:
                pass
        return ["pdf", "docx", "txt", "csv", "json", "markdown", "html"]

    def validate_document_size(self, size_bytes: int) -> bool:
        """Validate document size against maximum limit."""
        if NATIVE_AVAILABLE:
            try:
                return _native.ingest_validate_size(size_bytes)
            except Exception:
                pass
        return 0 < size_bytes <= 50 * 1024 * 1024

    def available_parsers(self) -> Dict[str, bool]:
        """Check which parsers (Rust and Python) are available."""
        parsers: Dict[str, bool] = {}
        parsers["rust_native"] = NATIVE_AVAILABLE
        parsers.update(self._parser.available_parsers())
        return parsers

    # ── Internal Helpers ──────────────────────────────────

    def _extract_all_texts(
        self,
        files: Optional[List[Tuple[str, Optional[bytes]]]],
        texts: Optional[List[str]],
    ) -> List[Any]:
        """Extract text from all sources (files + raw texts)."""
        extracted: List[Any] = []

        if files:
            for file_info in files:
                if not isinstance(file_info, (tuple, list)) or len(file_info) < 1:
                    continue
                filename = file_info[0]
                data = file_info[1] if len(file_info) > 1 else None
                ext_text = self._extract_single_file(filename, data)
                if ext_text is not None:
                    extracted.append(ext_text)

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
        """Extract text from a single file."""
        fmt_str = self.detect_format(filename)

        if NATIVE_AVAILABLE and fmt_str in ("txt", "csv", "json", "markdown"):
            try:
                if data is not None:
                    return _native.ingest_extract_text_simple(filename, data)
                elif os_path_exists(filename):
                    with open(filename, "rb") as f:
                        data = f.read()
                    return _native.ingest_extract_text_simple(filename, data)
            except Exception as e:
                logger.error("Rust extraction failed for %s: %s", filename, e)

        if fmt_str in ("pdf", "docx", "html"):
            text_content: str = ""
            errors: List[str] = []

            if data is not None:
                text_content, errors = self._parser.parse_bytes(filename, data)
            elif os_path_exists(filename):
                text_content, errors = self._parser.parse_file(filename)

            if text_content and NATIVE_AVAILABLE:
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

        if text_content and NATIVE_AVAILABLE:
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
        """Process a raw text string through the Rust pipeline."""
        if not text.strip():
            return None

        if NATIVE_AVAILABLE:
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
        """Match extracted text fields against template using Rust extractor."""
        if not NATIVE_AVAILABLE:
            logger.warning("DocumentIngestor._match_fields: Rust extension not available")
            return None

        try:
            native_texts = []
            for ext in extracted_texts:
                if isinstance(ext, dict):
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
