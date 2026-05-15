//! Document Ingestion Engine for Zenic-Agents (Phase 6.B).
//!
//! Handles document format detection, text extraction from simple
//! formats (TXT, CSV, JSON, Markdown), and provides a unified API
//! for the Python bridge to pass pre-extracted text from PDF/DOCX.
//!
//! # Architecture
//!
//! The ingestion pipeline:
//!
//! 1. User uploads documents (PDF, DOCX, TXT, CSV, JSON, etc.)
//! 2. Format detection from filename extension
//! 3. Text extraction:
//!    - TXT/CSV/JSON/MD: Rust-native extraction (no extra deps)
//!    - PDF/DOCX: Python parsers extract text, pass to Rust via PyO3
//! 4. ExtractedText → extractor.rs for field matching
//! 5. Matched fields → template auto-fill
//!
//! # Design Decisions
//!
//! - No heavy Rust crate dependencies for PDF/DOCX (Python handles those)
//! - Rust handles all core logic: format detection, text processing, validation
//! - Graceful fallback: if extraction fails, returns empty text with error info
//! - No `unwrap` or `panic` — all errors are handled explicitly
//!
//! # PyO3 Exposed Types
//!
//! - `DocumentFormat` — 8 supported document formats
//! - `ExtractedText` — text extracted from a single document
//! - `BatchExtractionResult` — results from batch extraction
//!
//! # PyO3 Exposed Functions
//!
//! - `ingest_detect_format(filename)` — detect format from extension
//! - `ingest_extract_text_simple(filename, data)` — extract from TXT/CSV/JSON bytes
//! - `ingest_process_extracted_text(filename, format_str, text)` — process pre-extracted text
//! - `ingest_extract_text_batch(documents)` — batch extraction
//! - `ingest_supported_formats()` — list supported format strings
//! - `ingest_validate_size(size_bytes)` — validate document size
//! - `ingest_combine_texts(texts)` — combine multiple ExtractedText into one
//! - `ingest_extract_key_value_pairs(text)` — extract key-value pairs from text

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

// ═══════════════════════════════════════════════════════════════
//  Constants
// ═══════════════════════════════════════════════════════════════

/// Maximum document size in bytes (50 MB).
const MAX_DOCUMENT_SIZE: usize = 50 * 1024 * 1024;

/// Maximum text length after extraction (5 MB chars).
const MAX_EXTRACTED_TEXT_LENGTH: usize = 5 * 1024 * 1024;

/// Supported file extensions mapped to DocumentFormat variants.
const FORMAT_MAP: &[(&str, DocumentFormat)] = &[
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
    text: String,
    page_count: usize,
    char_count: usize,
    word_count: usize,
    extraction_method: String,
    errors: Vec<String>,
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
    fn recalculate_counts(&mut self) {
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

// ═══════════════════════════════════════════════════════════════
//  Internal Helpers — Text Extraction
// ═══════════════════════════════════════════════════════════════

/// Extract text from a plain text file (UTF-8).
fn extract_txt(data: &[u8]) -> (String, Vec<String>) {
    let mut errors = Vec::new();
    match std::str::from_utf8(data) {
        Ok(text) => (text.to_string(), errors),
        Err(e) => {
            // Try lossy conversion as fallback
            errors.push(format!("UTF-8 decode error: {}, using lossy fallback", e));
            (String::from_utf8_lossy(data).into_owned(), errors)
        }
    }
}

/// Extract text from a CSV file.
///
/// Converts CSV rows to a structured text representation:
/// each row becomes a line with "column_name: value" pairs.
fn extract_csv(data: &[u8]) -> (String, Vec<String>) {
    let mut errors = Vec::new();
    let text = match std::str::from_utf8(data) {
        Ok(s) => s.to_string(),
        Err(e) => {
            errors.push(format!("UTF-8 decode error: {}, using lossy fallback", e));
            String::from_utf8_lossy(data).into_owned()
        }
    };

    let mut result_lines: Vec<String> = Vec::new();
    let mut lines = text.lines();
    let headers: Vec<String> = match lines.next() {
        Some(header_line) => parse_csv_line(header_line),
        None => return (String::new(), errors),
    };

    if headers.is_empty() {
        errors.push("CSV: empty header line".into());
        return (String::new(), errors);
    }

    for (row_idx, line) in lines.enumerate() {
        let values = parse_csv_line(line);
        let mut row_parts: Vec<String> = Vec::new();
        for (col_idx, value) in values.iter().enumerate() {
            let header = if col_idx < headers.len() {
                &headers[col_idx]
            } else {
                "unknown"
            };
            if !value.trim().is_empty() {
                row_parts.push(format!("{}: {}", header, value));
            }
        }
        if !row_parts.is_empty() {
            result_lines.push(format!("[Row {}] {}", row_idx + 1, row_parts.join(", ")));
        }
    }

    // Also add a header summary line
    result_lines.insert(0, format!("[Columns] {}", headers.join(", ")));

    (result_lines.join("\n"), errors)
}

/// Parse a single CSV line, handling quoted fields.
fn parse_csv_line(line: &str) -> Vec<String> {
    let mut fields = Vec::new();
    let mut current = String::new();
    let mut in_quotes = false;
    let trimmed = line.trim_end();

    for ch in trimmed.chars() {
        if ch == '"' {
            in_quotes = !in_quotes;
        } else if ch == ',' && !in_quotes {
            fields.push(current.trim().to_string());
            current = String::new();
        } else {
            current.push(ch);
        }
    }
    fields.push(current.trim().to_string());
    fields
}

/// Extract text from a JSON file.
///
/// Flattens JSON into key-value pairs with dot-notation paths.
fn extract_json(data: &[u8]) -> (String, Vec<String>) {
    let mut errors = Vec::new();
    let text = match std::str::from_utf8(data) {
        Ok(s) => s.to_string(),
        Err(e) => {
            errors.push(format!("UTF-8 decode error: {}", e));
            return (String::new(), errors);
        }
    };

    match serde_json::from_str::<serde_json::Value>(&text) {
        Ok(value) => {
            let mut pairs: Vec<String> = Vec::new();
            flatten_json_value(&value, "", &mut pairs);
            (pairs.join("\n"), errors)
        }
        Err(e) => {
            errors.push(format!("JSON parse error: {}", e));
            (String::new(), errors)
        }
    }
}

/// Recursively flatten a JSON value into dot-notation key-value pairs.
fn flatten_json_value(value: &serde_json::Value, prefix: &str, pairs: &mut Vec<String>) {
    match value {
        serde_json::Value::Object(map) => {
            for (key, val) in map {
                let new_prefix = if prefix.is_empty() {
                    key.clone()
                } else {
                    format!("{}.{}", prefix, key)
                };
                flatten_json_value(val, &new_prefix, pairs);
            }
        }
        serde_json::Value::Array(arr) => {
            for (idx, val) in arr.iter().enumerate() {
                let new_prefix = format!("{}[{}]", prefix, idx);
                flatten_json_value(val, &new_prefix, pairs);
            }
        }
        serde_json::Value::Null => {
            if !prefix.is_empty() {
                pairs.push(format!("{}: null", prefix));
            }
        }
        serde_json::Value::Bool(b) => {
            if !prefix.is_empty() {
                pairs.push(format!("{}: {}", prefix, b));
            }
        }
        serde_json::Value::Number(n) => {
            if !prefix.is_empty() {
                pairs.push(format!("{}: {}", prefix, n));
            }
        }
        serde_json::Value::String(s) => {
            if !prefix.is_empty() {
                pairs.push(format!("{}: {}", prefix, s));
            }
        }
    }
}

/// Extract text from a Markdown file.
///
/// Treats Markdown as plain text (the extractor will handle
/// pattern matching regardless of formatting).
fn extract_markdown(data: &[u8]) -> (String, Vec<String>) {
    extract_txt(data)
}

/// Truncate text to MAX_EXTRACTED_TEXT_LENGTH.
fn truncate_text(text: String) -> (String, Vec<String>) {
    let mut errors = Vec::new();
    if text.len() > MAX_EXTRACTED_TEXT_LENGTH {
        errors.push(format!(
            "Text truncated from {} to {} characters",
            text.len(),
            MAX_EXTRACTED_TEXT_LENGTH
        ));
        let truncated: String = text.chars().take(MAX_EXTRACTED_TEXT_LENGTH).collect();
        (truncated, errors)
    } else {
        (text, errors)
    }
}

// ═══════════════════════════════════════════════════════════════
//  PyO3 Functions — Public API
// ═══════════════════════════════════════════════════════════════

/// Detect document format from filename extension.
///
/// Parameters
/// ----------
/// filename : str
///     The filename (e.g., ``"report.pdf"``).
///
/// Returns
/// -------
/// DocumentFormat
///     The detected format, or ``DocumentFormat.Unknown`` if unrecognized.
#[pyfunction]
pub fn ingest_detect_format(filename: &str) -> DocumentFormat {
    let filename_trimmed = filename.trim();
    if filename_trimmed.is_empty() {
        return DocumentFormat::Unknown;
    }
    DocumentFormat::from_filename(filename_trimmed)
}

/// Extract text from a simple document (TXT, CSV, JSON, Markdown).
///
/// For PDF/DOCX/HTML, use ``ingest_process_extracted_text`` instead
/// with text pre-extracted by Python parsers.
///
/// Parameters
/// ----------
/// filename : str
///     The document filename.
/// data : bytes
///     The raw document bytes.
///
/// Returns
/// -------
/// ExtractedText
///     Extracted text with metadata and any errors.
#[pyfunction]
pub fn ingest_extract_text_simple(filename: &str, data: &[u8]) -> ExtractedText {
    let filename_clean = if filename.trim().is_empty() {
        "unknown".to_string()
    } else {
        filename.trim().to_string()
    };
    let format = DocumentFormat::from_filename(&filename_clean);

    let mut result = ExtractedText::new(filename_clean, format);

    if data.is_empty() {
        result.errors.push("Document data is empty".into());
        result.extraction_method = "none".into();
        return result;
    }

    if data.len() > MAX_DOCUMENT_SIZE {
        result.errors.push(format!(
            "Document size {} exceeds maximum {} bytes",
            data.len(),
            MAX_DOCUMENT_SIZE
        ));
        result.extraction_method = "none".into();
        return result;
    }

    let (text, errors) = match format {
        DocumentFormat::Txt => {
            result.extraction_method = "rust_txt".into();
            extract_txt(data)
        }
        DocumentFormat::Csv => {
            result.extraction_method = "rust_csv".into();
            extract_csv(data)
        }
        DocumentFormat::Json => {
            result.extraction_method = "rust_json".into();
            extract_json(data)
        }
        DocumentFormat::Markdown => {
            result.extraction_method = "rust_markdown".into();
            extract_markdown(data)
        }
        DocumentFormat::Pdf | DocumentFormat::Docx | DocumentFormat::Html => {
            result.extraction_method = "none".into();
            result.errors.push(format!(
                "Format '{}' requires Python-side extraction. Use ingest_process_extracted_text().",
                format.as_str()
            ));
            return result;
        }
        DocumentFormat::Unknown => {
            result.extraction_method = "none".into();
            result.errors.push("Unknown document format".into());
            return result;
        }
    };

    let (truncated_text, truncation_errors) = truncate_text(text);
    result.text = truncated_text;
    result.errors.extend(errors);
    result.errors.extend(truncation_errors);
    result.recalculate_counts();
    result.page_count = 1;

    result
}

/// Process pre-extracted text (from Python PDF/DOCX parsers).
///
/// This is the entry point for documents that were extracted by
/// Python libraries (PyPDF2, python-docx, etc.). The Rust side
/// normalizes and validates the text.
///
/// Parameters
/// ----------
/// filename : str
///     Original document filename.
/// format_str : str
///     Format string (e.g., ``"pdf"``, ``"docx"``).
/// text : str
///     The text content extracted by Python parsers.
///
/// Returns
/// -------
/// ExtractedText
///     Normalized extracted text with metadata.
#[pyfunction]
pub fn ingest_process_extracted_text(filename: &str, format_str: &str, text: &str) -> ExtractedText {
    let filename_clean = if filename.trim().is_empty() {
        "unknown".to_string()
    } else {
        filename.trim().to_string()
    };

    let format = if format_str.trim().is_empty() {
        DocumentFormat::from_filename(&filename_clean)
    } else {
        DocumentFormat::from_extension(format_str.trim())
    };

    let mut result = ExtractedText::new(filename_clean, format);
    result.extraction_method = format!("python_{}", format.as_str());

    if text.trim().is_empty() {
        result.errors.push("Pre-extracted text is empty".into());
        return result;
    }

    let (truncated_text, truncation_errors) = truncate_text(text.to_string());
    result.text = truncated_text;
    result.errors.extend(truncation_errors);
    result.recalculate_counts();

    // Estimate page count for PDF (rough heuristic: ~3000 chars per page)
    if format == DocumentFormat::Pdf {
        result.page_count = if result.char_count > 0 {
            (result.char_count / 3000).max(1)
        } else {
            0
        };
    } else {
        result.page_count = 1;
    }

    result
}

/// Batch extract text from multiple simple documents.
///
/// Each document is a tuple of (filename, bytes_data).
/// Only processes TXT/CSV/JSON/Markdown natively; PDF/DOCX
/// will be skipped with an error message.
///
/// Parameters
/// ----------
/// documents : list[tuple[str, bytes]]
///     List of (filename, data) tuples.
///
/// Returns
/// -------
/// BatchExtractionResult
///     Results for all documents.
#[pyfunction]
pub fn ingest_extract_text_batch(py: Python<'_>, documents: &Bound<'_, PyList>) -> PyResult<BatchExtractionResult> {
    let mut extracted: Vec<ExtractedText> = Vec::new();
    let mut successful: usize = 0;
    let mut failed: usize = 0;
    let mut total_chars: usize = 0;
    let mut total_words: usize = 0;
    let mut all_errors: Vec<String> = Vec::new();

    for item in documents.iter() {
        let tuple_res: Result<(String, Vec<u8>), _> = item.extract();
        match tuple_res {
            Ok((filename, data)) => {
                let result = ingest_extract_text_simple(&filename, &data);
                if result.is_empty() {
                    failed += 1;
                } else {
                    successful += 1;
                    total_chars += result.char_count;
                    total_words += result.word_count;
                }
                all_errors.extend(result.errors.clone());
                extracted.push(result);
            }
            Err(e) => {
                failed += 1;
                all_errors.push(format!("Invalid document tuple: {}", e));
            }
        }
    }

    Ok(BatchExtractionResult {
        total_documents: extracted.len(),
        successful,
        failed,
        total_chars,
        total_words,
        documents: extracted,
        errors: all_errors,
    })
}

/// Get list of supported document format strings.
///
/// Returns
/// -------
/// list[str]
///     All supported format strings (e.g., ``["pdf", "docx", "txt", ...]``).
#[pyfunction]
pub fn ingest_supported_formats() -> Vec<String> {
    DocumentFormat::supported()
        .iter()
        .map(|f| f.as_str().to_string())
        .collect()
}

/// Validate document size against the maximum limit.
///
/// Parameters
/// ----------
/// size_bytes : int
///     Document size in bytes.
///
/// Returns
/// -------
/// bool
///     True if size is within limits.
#[pyfunction]
pub fn ingest_validate_size(size_bytes: usize) -> bool {
    size_bytes <= MAX_DOCUMENT_SIZE
}

/// Combine multiple ExtractedText objects into one.
///
/// Concatenates all text content, merges errors, and
/// calculates aggregate statistics.
///
/// Parameters
/// ----------
/// texts : list[ExtractedText]
///     List of ExtractedText objects to combine.
///
/// Returns
/// -------
/// ExtractedText
///     Combined text with aggregated metadata.
#[pyfunction]
pub fn ingest_combine_texts(texts: Vec<ExtractedText>) -> ExtractedText {
    if texts.is_empty() {
        return ExtractedText::new("combined".into(), DocumentFormat::Txt);
    }

    let mut combined_text = String::new();
    let mut all_errors: Vec<String> = Vec::new();
    let mut total_pages: usize = 0;
    let mut methods: Vec<String> = Vec::new();
    let primary_format = texts[0].format;

    for (idx, ext) in texts.iter().enumerate() {
        if !combined_text.is_empty() {
            combined_text.push_str("\n\n--- Document: ");
            combined_text.push_str(&ext.filename);
            combined_text.push_str(" ---\n\n");
        } else {
            combined_text.push_str("--- Document: ");
            combined_text.push_str(&ext.filename);
            combined_text.push_str(" ---\n\n");
        }
        combined_text.push_str(&ext.text);
        total_pages += ext.page_count;
        all_errors.extend(ext.errors.clone());
        if !ext.extraction_method.is_empty() {
            methods.push(format!("{}:{}", ext.filename, ext.extraction_method));
        }
        let _ = idx; // suppress unused warning
    }

    let mut result = ExtractedText::new("combined".into(), primary_format);
    result.text = combined_text;
    result.page_count = total_pages;
    result.extraction_method = format!("combined({})", methods.len());
    result.errors = all_errors;
    result.recalculate_counts();

    result
}

/// Extract key-value pairs from text using common patterns.
///
/// Recognizes patterns like:
/// - ``Key: Value``
/// - ``Key = Value``
/// - ``Key - Value``
/// - Tabular data with headers
///
/// Parameters
/// ----------
/// text : str
///     The text to parse for key-value pairs.
///
/// Returns
/// -------
/// dict[str, str]
///     Extracted key-value pairs (keys lowercased, trimmed).
#[pyfunction]
pub fn ingest_extract_key_value_pairs(text: &str, py: Python<'_>) -> PyResult<Py<PyDict>> {
    let dict = PyDict::new_bound(py);

    if text.trim().is_empty() {
        return Ok(dict.unbind());
    }

    let patterns = [": ", " = ", " - ", ":  ", " : "];

    for line in text.lines() {
        let trimmed = line.trim();
        if trimmed.is_empty() || trimmed.starts_with('#') || trimmed.starts_with("//") {
            continue;
        }

        for separator in &patterns {
            if let Some(pos) = trimmed.find(separator) {
                let key = trimmed[..pos].trim();
                let value = trimmed[pos + separator.len()..].trim();

                // Validate key is not empty and looks like an identifier
                if !key.is_empty() && key.len() < 100 && !key.starts_with('[') {
                    // Skip if value is empty
                    if !value.is_empty() && value.len() < 1000 {
                        let key_lower = key.to_lowercase();
                        // Only set if not already present (first match wins)
                        if dict.get_item(&key_lower)?.is_none() {
                            dict.set_item(key_lower, value)?;
                        }
                    }
                }
                break; // Only try the first matching separator per line
            }
        }
    }

    Ok(dict.unbind())
}

// ═══════════════════════════════════════════════════════════════
//  Unit Tests
// ═══════════════════════════════════════════════════════════════

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_document_format_from_extension() {
        assert_eq!(DocumentFormat::from_extension("pdf"), DocumentFormat::Pdf);
        assert_eq!(DocumentFormat::from_extension("docx"), DocumentFormat::Docx);
        assert_eq!(DocumentFormat::from_extension("txt"), DocumentFormat::Txt);
        assert_eq!(DocumentFormat::from_extension("csv"), DocumentFormat::Csv);
        assert_eq!(DocumentFormat::from_extension("json"), DocumentFormat::Json);
        assert_eq!(DocumentFormat::from_extension("md"), DocumentFormat::Markdown);
        assert_eq!(DocumentFormat::from_extension("html"), DocumentFormat::Html);
        assert_eq!(DocumentFormat::from_extension("xyz"), DocumentFormat::Unknown);
    }

    #[test]
    fn test_document_format_from_filename() {
        assert_eq!(DocumentFormat::from_filename("report.pdf"), DocumentFormat::Pdf);
        assert_eq!(DocumentFormat::from_filename("data.csv"), DocumentFormat::Csv);
        assert_eq!(DocumentFormat::from_filename("config.JSON"), DocumentFormat::Json);
        assert_eq!(DocumentFormat::from_filename("noext"), DocumentFormat::Unknown);
        assert_eq!(DocumentFormat::from_filename(""), DocumentFormat::Unknown);
    }

    #[test]
    fn test_document_format_rust_native() {
        assert!(DocumentFormat::Txt.is_rust_native());
        assert!(DocumentFormat::Csv.is_rust_native());
        assert!(DocumentFormat::Json.is_rust_native());
        assert!(DocumentFormat::Markdown.is_rust_native());
        assert!(!DocumentFormat::Pdf.is_rust_native());
        assert!(!DocumentFormat::Docx.is_rust_native());
    }

    #[test]
    fn test_document_format_requires_python() {
        assert!(DocumentFormat::Pdf.requires_python());
        assert!(DocumentFormat::Docx.requires_python());
        assert!(DocumentFormat::Html.requires_python());
        assert!(!DocumentFormat::Txt.requires_python());
        assert!(!DocumentFormat::Csv.requires_python());
    }

    #[test]
    fn test_extracted_text_creation() {
        let ext = ExtractedText::new("test.txt".into(), DocumentFormat::Txt);
        assert_eq!(ext.filename(), "test.txt");
        assert_eq!(ext.format(), DocumentFormat::Txt);
        assert!(ext.is_empty());
        assert_eq!(ext.char_count, 0);
        assert_eq!(ext.word_count, 0);
    }

    #[test]
    fn test_extract_txt() {
        let data = b"Hello, World!";
        let (text, errors) = extract_txt(data);
        assert_eq!(text, "Hello, World!");
        assert!(errors.is_empty());
    }

    #[test]
    fn test_extract_txt_non_utf8() {
        let data: &[u8] = &[0xFF, 0xFE, 0x00, 0x01];
        let (text, errors) = extract_txt(data);
        assert!(!errors.is_empty()); // Should report UTF-8 error
        assert!(!text.is_empty()); // But should still produce some output
    }

    #[test]
    fn test_extract_csv() {
        let data = b"Name,Age,City\nAlice,30,NYC\nBob,25,LA";
        let (text, errors) = extract_csv(data);
        assert!(errors.is_empty());
        assert!(text.contains("Name"));
        assert!(text.contains("Alice"));
        assert!(text.contains("30"));
        assert!(text.contains("NYC"));
    }

    #[test]
    fn test_extract_csv_quoted() {
        let data = b"Name,Description\nAlice,\"Hello, World\"\nBob,Simple";
        let (text, errors) = extract_csv(data);
        assert!(errors.is_empty());
        assert!(text.contains("Hello, World"));
    }

    #[test]
    fn test_extract_json() {
        let data = br#"{"name": "Alice", "age": 30, "city": "NYC"}"#;
        let (text, errors) = extract_json(data);
        assert!(errors.is_empty());
        assert!(text.contains("name: Alice"));
        assert!(text.contains("age: 30"));
        assert!(text.contains("city: NYC"));
    }

    #[test]
    fn test_extract_json_nested() {
        let data = br#"{"user": {"name": "Bob", "contact": {"email": "bob@test.com"}}}"#;
        let (text, errors) = extract_json(data);
        assert!(errors.is_empty());
        assert!(text.contains("user.name: Bob"));
        assert!(text.contains("user.contact.email: bob@test.com"));
    }

    #[test]
    fn test_extract_json_invalid() {
        let data = b"not json at all";
        let (text, errors) = extract_json(data);
        assert!(!errors.is_empty());
        assert!(text.is_empty());
    }

    #[test]
    fn test_ingest_extract_text_simple_txt() {
        let data = b"Hello World\nLine 2\nLine 3";
        let result = ingest_extract_text_simple("test.txt", data);
        assert_eq!(result.format(), DocumentFormat::Txt);
        assert!(!result.is_empty());
        assert_eq!(result.extraction_method, "rust_txt");
        assert_eq!(result.word_count, 5);
    }

    #[test]
    fn test_ingest_extract_text_simple_csv() {
        let data = b"Name,Value\nKey1,Val1\nKey2,Val2";
        let result = ingest_extract_text_simple("data.csv", data);
        assert_eq!(result.format(), DocumentFormat::Csv);
        assert!(!result.is_empty());
    }

    #[test]
    fn test_ingest_extract_text_simple_json() {
        let data = br#"{"key": "value"}"#;
        let result = ingest_extract_text_simple("config.json", data);
        assert_eq!(result.format(), DocumentFormat::Json);
        assert!(!result.is_empty());
    }

    #[test]
    fn test_ingest_extract_text_simple_pdf_rejected() {
        let data = b"%PDF-1.4 fake content";
        let result = ingest_extract_text_simple("report.pdf", data);
        assert!(result.has_errors());
        assert!(result.is_empty());
    }

    #[test]
    fn test_ingest_extract_text_empty_data() {
        let result = ingest_extract_text_simple("empty.txt", b"");
        assert!(result.has_errors());
        assert!(result.is_empty());
    }

    #[test]
    fn test_ingest_process_extracted_text() {
        let result = ingest_process_extracted_text(
            "report.pdf",
            "pdf",
            "This is extracted PDF text content with some information.",
        );
        assert_eq!(result.format(), DocumentFormat::Pdf);
        assert!(!result.is_empty());
        assert_eq!(result.extraction_method, "python_pdf");
    }

    #[test]
    fn test_ingest_process_extracted_text_empty() {
        let result = ingest_process_extracted_text("empty.pdf", "pdf", "");
        assert!(result.has_errors());
        assert!(result.is_empty());
    }

    #[test]
    fn test_ingest_validate_size() {
        assert!(ingest_validate_size(1024));
        assert!(ingest_validate_size(MAX_DOCUMENT_SIZE));
        assert!(!ingest_validate_size(MAX_DOCUMENT_SIZE + 1));
    }

    #[test]
    fn test_ingest_supported_formats() {
        let formats = ingest_supported_formats();
        assert_eq!(formats.len(), 7);
        assert!(formats.contains(&"pdf".to_string()));
        assert!(formats.contains(&"txt".to_string()));
    }

    #[test]
    fn test_parse_csv_line() {
        let fields = parse_csv_line("a,b,c");
        assert_eq!(fields, vec!["a", "b", "c"]);

        let fields = parse_csv_line("\"hello, world\",test");
        assert_eq!(fields, vec!["hello, world", "test"]);

        let fields = parse_csv_line("single");
        assert_eq!(fields, vec!["single"]);
    }

    #[test]
    fn test_flatten_json_value() {
        let value: serde_json::Value = serde_json::json!({
            "name": "test",
            "nested": {"key": "value"},
            "arr": [1, 2]
        });
        let mut pairs: Vec<String> = Vec::new();
        flatten_json_value(&value, "", &mut pairs);
        assert!(pairs.iter().any(|p| p.contains("name: test")));
        assert!(pairs.iter().any(|p| p.contains("nested.key: value")));
        assert!(pairs.iter().any(|p| p.contains("arr[0]: 1")));
    }

    #[test]
    fn test_ingest_combine_texts() {
        let mut t1 = ExtractedText::new("a.txt".into(), DocumentFormat::Txt);
        t1.text = "Content A".into();
        t1.recalculate_counts();

        let mut t2 = ExtractedText::new("b.txt".into(), DocumentFormat::Txt);
        t2.text = "Content B".into();
        t2.recalculate_counts();

        let combined = ingest_combine_texts(vec![t1, t2]);
        assert!(combined.text.contains("Content A"));
        assert!(combined.text.contains("Content B"));
        assert_eq!(combined.word_count, 4); // "Content A" + "Content B"
    }

    #[test]
    fn test_ingest_combine_empty() {
        let combined = ingest_combine_texts(vec![]);
        assert!(combined.is_empty());
    }
}
