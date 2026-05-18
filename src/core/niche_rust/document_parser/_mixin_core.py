"""
Document Parser — Main DocumentParser class and constants.

Python-side document parsing for formats that require Python
libraries (PDF, DOCX, HTML).
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional, Tuple

from ._parsers import _parse_pdf, _parse_pdf_bytes, _parse_docx, _parse_docx_bytes, _parse_html

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
#  Constants
# ──────────────────────────────────────────────────────────────

#: Maximum file size for Python-side parsing (50 MB).
MAX_FILE_SIZE: int = 50 * 1024 * 1024

#: Supported format strings for Python parsing.
PYTHON_FORMATS: Tuple[str, ...] = ("pdf", "docx", "html")

#: Format string for unknown/unparseable documents.
FORMAT_UNKNOWN: str = "unknown"


# ──────────────────────────────────────────────────────────────
#  DocumentParser — Main public class
# ──────────────────────────────────────────────────────────────

class DocumentParser:
    """Python document parser for PDF, DOCX, and HTML files.

    Handles binary format parsing that the Rust ingestion engine
    cannot process natively. For TXT/CSV/JSON/Markdown, delegates
    to the Rust ``ingest_extract_text_simple`` function.

    Usage::

        parser = DocumentParser()

        # Parse a file by path
        text, errors = parser.parse_file("/path/to/document.pdf")

        # Parse bytes (e.g., from upload)
        text, errors = parser.parse_bytes("report.docx", docx_bytes)

        # Check if a format is supported
        if parser.supports("pdf"):
            ...
    """

    def parse_file(self, file_path: str) -> Tuple[str, List[str]]:
        """Parse a document file and extract its text content."""
        if not file_path or not isinstance(file_path, str):
            return ("", ["file_path must be a non-empty string"])

        if not os.path.exists(file_path):
            return ("", [f"File not found: {file_path}"])

        file_size = os.path.getsize(file_path)
        if file_size == 0:
            return ("", ["File is empty"])
        if file_size > MAX_FILE_SIZE:
            return ("", [f"File too large: {file_size} bytes (max {MAX_FILE_SIZE})"])

        ext = self._get_extension(file_path)

        if ext == "pdf":
            return _parse_pdf(file_path)
        elif ext in ("docx", "doc"):
            return _parse_docx(file_path)
        elif ext in ("html", "htm"):
            try:
                with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                    html_content = f.read()
                return _parse_html(html_content)
            except Exception as e:
                return ("", [f"HTML file read error: {e}"])
        elif ext in ("txt", "csv", "tsv", "json", "md", "markdown"):
            try:
                with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                    return (f.read(), [])
            except Exception as e:
                return ("", [f"Text file read error: {e}"])
        else:
            return ("", [f"Unsupported format: .{ext}"])

    def parse_bytes(
        self, filename: str, data: bytes
    ) -> Tuple[str, List[str]]:
        """Parse document bytes and extract text content."""
        if not filename or not isinstance(filename, str):
            return ("", ["filename must be a non-empty string"])
        if not data:
            return ("", ["Document data is empty"])
        if len(data) > MAX_FILE_SIZE:
            return ("", [f"Data too large: {len(data)} bytes (max {MAX_FILE_SIZE})"])

        ext = self._get_extension(filename)

        if ext == "pdf":
            return _parse_pdf_bytes(data)
        elif ext in ("docx", "doc"):
            return _parse_docx_bytes(data)
        elif ext in ("html", "htm"):
            try:
                html_content = data.decode("utf-8", errors="replace")
                return _parse_html(html_content)
            except Exception as e:
                return ("", [f"HTML decode error: {e}"])
        elif ext in ("txt", "csv", "tsv", "json", "md", "markdown"):
            try:
                text = data.decode("utf-8", errors="replace")
                return (text, [])
            except Exception as e:
                return ("", [f"Text decode error: {e}"])
        else:
            return ("", [f"Unsupported format: .{ext}"])

    def supports(self, format_str: str) -> bool:
        """Check if a format is supported for Python-side parsing."""
        return format_str.lower() in PYTHON_FORMATS or format_str.lower() in (
            "txt", "csv", "tsv", "json", "md", "markdown", "html", "htm", "doc",
        )

    def available_parsers(self) -> Dict[str, bool]:
        """Check which Python parsers are actually available."""
        available: Dict[str, bool] = {}
        try:
            import PyPDF2  # noqa: F401
            available["pdf_pypdf2"] = True
        except ImportError:
            available["pdf_pypdf2"] = False

        try:
            import pdfminer  # noqa: F401
            available["pdf_pdfminer"] = True
        except ImportError:
            available["pdf_pdfminer"] = False

        try:
            import docx  # noqa: F401
            available["docx_python_docx"] = True
        except ImportError:
            available["docx_python_docx"] = False

        # HTML parser is always available (built-in)
        available["html_builtin"] = True

        return available

    @staticmethod
    def _get_extension(filename: str) -> str:
        """Extract and normalize file extension."""
        if not filename:
            return ""
        parts = filename.rsplit(".", 1)
        if len(parts) < 2:
            return ""
        return parts[1].lower()
