//! Document ingestion types — DocumentFormat, ExtractedText, BatchExtractionResult, constants.

use pyo3::prelude::*;
use pyo3::types::PyDict;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

// ═══════════════════════════════════════════════════════════════
//  Constants
// ═══════════════════════════════════════════════════════════════

/// Maximum document size in bytes (50 MB).
pub(crate) const MAX_DOCUMENT_SIZE: usize = 50 * 1024 * 1024;

/// Maximum text length after extraction (5 MB chars).
pub(crate) const MAX_EXTRACTED_TEXT_LENGTH: usize = 5 * 1024 * 1024;

/// Supported file extensions mapped to DocumentFormat variants.
pub(crate) const FORMAT_MAP: &[(&str, DocumentFormat)] = &[
    ("pdf", DocumentFormat::Pdf),
    ("docx", DocumentFormat::Docx),
    ("doc", DocumentFormat::Docx),
    ("txt", DocumentFormat::Txt),
    ("csv", DocumentFormat::Csv),
    ("tsv", DocumentFormat::Csv),
    ("json", DocumentFormat::Json),
    ("md", DocumentFormat::Markdown),
    ("markdown", DocumentFormat::Markdown),
    ("html", DocumentFormat::Html),
    ("htm", DocumentFormat::Html),
];

// ═══════════════════════════════════════════════════════════════
//  DocumentFormat — 8 supported document formats
// ═══════════════════════════════════════════════════════════════

/// Supported document format for ingestion.
///
/// Each variant maps to a specific extraction strategy:
///
/// ========= ============ ===================================
/// Variant   Python value Extraction Strategy
/// ========= ============ ===================================
/// Pdf       ``"pdf"``    Python parsers (PyPDF2/pdfminer)
/// Docx      ``"docx"``   Python parsers (python-docx)
/// Txt       ``"txt"``    Rust-native UTF-8 decode
/// Csv       ``"csv"``    Rust-native CSV parsing
/// Json      ``"json"``   Rust-native serde_json parse
/// Markdown  ``"markdown"`` Rust-native text extraction
/// Html      ``"html"``   Python/Rust tag stripping
/// Unknown   ``"unknown"`` No extraction (error)
/// ========= ============ ===================================
#[pyclass(name = "DocumentFormat", eq, eq_int, frozen, hash)]
#[derive(Clone, Debug, PartialEq, Eq, Hash, Copy, Serialize, Deserialize)]
pub enum DocumentFormat {
    Pdf,
    Docx,
    Txt,
    Csv,
    Json,
    Markdown,
    Html,
    Unknown,
}

impl DocumentFormat {
    /// Return the Python-enum string value.
    pub fn as_str(&self) -> &'static str {
        match self {
            DocumentFormat::Pdf => "pdf",
            DocumentFormat::Docx => "docx",
            DocumentFormat::Txt => "txt",
            DocumentFormat::Csv => "csv",
            DocumentFormat::Json => "json",
            DocumentFormat::Markdown => "markdown",
            DocumentFormat::Html => "html",
            DocumentFormat::Unknown => "unknown",
        }
    }

    /// Detect format from a file extension.
    ///
    /// The extension is extracted from the filename (last `.` segment),
    /// converted to lowercase, and matched against known formats.
    pub fn from_extension(ext: &str) -> DocumentFormat {
        let ext_lower = ext.trim_start_matches('.').to_lowercase();
        for (known_ext, fmt) in FORMAT_MAP {
            if *known_ext == ext_lower {
                return *fmt;
            }
        }
        DocumentFormat::Unknown
    }

    /// Detect format from a full filename.
    pub fn from_filename(filename: &str) -> DocumentFormat {
        let ext = filename
            .rfind('.')
            .map(|pos| &filename[pos + 1..])
            .unwrap_or("");
        Self::from_extension(ext)
    }

    /// Check if this format can be extracted natively in Rust.
    pub fn is_rust_native(&self) -> bool {
        matches!(
            self,
            DocumentFormat::Txt
                | DocumentFormat::Csv
                | DocumentFormat::Json
                | DocumentFormat::Markdown
        )
    }

    /// Check if this format requires Python-side extraction.
    pub fn requires_python(&self) -> bool {
        matches!(
            self,
            DocumentFormat::Pdf | DocumentFormat::Docx | DocumentFormat::Html
        )
    }

    /// All supported variants in catalog order.
    pub fn supported() -> &'static [DocumentFormat] {
        &[
            DocumentFormat::Pdf,
            DocumentFormat::Docx,
            DocumentFormat::Txt,
            DocumentFormat::Csv,
            DocumentFormat::Json,
            DocumentFormat::Markdown,
            DocumentFormat::Html,
        ]
    }
}

#[pymethods]
impl DocumentFormat {
    fn __str__(&self) -> &'static str {
        self.as_str()
    }

    fn __repr__(&self) -> String {
        format!("DocumentFormat.{}", self.as_str().to_uppercase())
    }
}

// ═══════════════════════════════════════════════════════════════
//  ExtractedText — text extracted from a single document
// ═══════════════════════════════════════════════════════════════

/// Text extracted from a single document.
///
/// Contains the extracted text content along with metadata
/// about the extraction process (format, method, errors).
///
/// All fields are read-only from Python via getters.
#[pyclass(name = "ExtractedText")]
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ExtractedText {
    filename: String,
    format: DocumentFormat,
    pub(crate) text: String,
    page_count: usize,
    char_count: usize,
    word_count: usize,
    extraction_method: String,
    pub(crate) errors: Vec<String>,
    metadata: HashMap<String, String>,
}

impl ExtractedText {
    /// Create a new ExtractedText with the given filename and format.
    pub fn new(filename: String, format: DocumentFormat) -> Self {
        ExtractedText {
            filename,
            format,
            text: String::new(),
            page_count: 0,
            char_count: 0,
            word_count: 0,
            extraction_method: String::new(),
            errors: Vec::new(),
            metadata: HashMap::new(),
        }
    }

    /// Get the extracted text content.
    pub fn text(&self) -> &str {
        &self.text
    }

    /// Get the filename.
    pub fn filename(&self) -> &str {
        &self.filename
    }

    /// Get the format.
    pub fn format(&self) -> DocumentFormat {
        self.format
    }

    /// Recalculate derived counts from the current text.
    pub(crate) fn recalculate_counts(&mut self) {
        self.char_count = self.text.len();
        self.word_count = if self.text.is_empty() {
            0
        } else {
            self.text.split_whitespace().count()
        };
    }
}

#[pymethods]
impl ExtractedText {
    #[getter]
    fn filename(&self) -> &str {
        &self.filename
    }

    #[getter]
    fn format(&self) -> DocumentFormat {
        self.format
    }

    #[getter]
    fn text(&self) -> &str {
        &self.text
    }

    #[getter]
    fn page_count(&self) -> usize {
        self.page_count
    }

    #[getter]
    fn char_count(&self) -> usize {
        self.char_count
    }

    #[getter]
    fn word_count(&self) -> usize {
        self.word_count
    }

    #[getter]
    fn extraction_method(&self) -> &str {
        &self.extraction_method
    }

    #[getter]
    fn errors(&self) -> Vec<String> {
        self.errors.clone()
    }

    #[getter]
    fn has_errors(&self) -> bool {
        !self.errors.is_empty()
    }

    #[getter]
    fn is_empty(&self) -> bool {
        self.text.trim().is_empty()
    }

    /// Get a summary dict for display purposes.
    fn summary(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        let dict = PyDict::new_bound(py);
        dict.set_item("filename", &self.filename)?;
        dict.set_item("format", self.format.as_str())?;
        dict.set_item("char_count", self.char_count)?;
        dict.set_item("word_count", self.word_count)?;
        dict.set_item("page_count", self.page_count)?;
        dict.set_item("extraction_method", &self.extraction_method)?;
        dict.set_item("has_errors", self.has_errors())?;
        dict.set_item("is_empty", self.is_empty())?;
        Ok(dict.unbind())
    }

    fn __repr__(&self) -> String {
        format!(
            "ExtractedText(filename={:?}, format={}, chars={}, words={})",
            self.filename,
            self.format.as_str(),
            self.char_count,
            self.word_count,
        )
    }
}

// ═══════════════════════════════════════════════════════════════
//  BatchExtractionResult — results from batch extraction
// ═══════════════════════════════════════════════════════════════

/// Results from extracting text from multiple documents.
///
/// Tracks success/failure counts and aggregates all errors.
#[pyclass(name = "BatchExtractionResult")]
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct BatchExtractionResult {
    documents: Vec<ExtractedText>,
    total_documents: usize,
    successful: usize,
    failed: usize,
    total_chars: usize,
    total_words: usize,
    errors: Vec<String>,
}

#[pymethods]
impl BatchExtractionResult {
    #[getter]
    fn documents(&self) -> Vec<ExtractedText> {
        self.documents.clone()
    }

    #[getter]
    fn total_documents(&self) -> usize {
        self.total_documents
    }

    #[getter]
    fn successful(&self) -> usize {
        self.successful
    }

    #[getter]
    fn failed(&self) -> usize {
        self.failed
    }

    #[getter]
    fn total_chars(&self) -> usize {
        self.total_chars
    }

    #[getter]
    fn total_words(&self) -> usize {
        self.total_words
    }

    #[getter]
    fn errors(&self) -> Vec<String> {
        self.errors.clone()
    }

    /// Get a summary dict for display purposes.
    fn summary(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        let dict = PyDict::new_bound(py);
        dict.set_item("total_documents", self.total_documents)?;
        dict.set_item("successful", self.successful)?;
        dict.set_item("failed", self.failed)?;
        dict.set_item("total_chars", self.total_chars)?;
        dict.set_item("total_words", self.total_words)?;
        dict.set_item("error_count", self.errors.len())?;
        Ok(dict.unbind())
    }

    fn __repr__(&self) -> String {
        format!(
            "BatchExtractionResult(total={}, successful={}, failed={})",
            self.total_documents, self.successful, self.failed,
        )
    }
}
