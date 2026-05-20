"""
Zenic-Agents — Document Parser (Phase 6.B)

Python-side document parsing for formats that require Python
libraries (PDF, DOCX, HTML). The Rust ingestion engine handles
TXT, CSV, JSON, and Markdown natively; this module fills the
gap for binary formats.

Supported Formats:
    - PDF: PyPDF2 / pdfminer.six (fallback)
    - DOCX: python-docx
    - HTML: built-in html.parser
    - TXT/CSV/JSON: delegated to Rust (ingest_extract_text_simple)

Fallback:
    If a Python library is not installed, the parser returns an
    empty string with an error message. It never raises exceptions.
"""

from ._mixin_core import DocumentParser, MAX_FILE_SIZE, PYTHON_FORMATS, FORMAT_UNKNOWN

__all__ = [
    "DocumentParser",
    "MAX_FILE_SIZE",
    "PYTHON_FORMATS",
    "FORMAT_UNKNOWN",
]
