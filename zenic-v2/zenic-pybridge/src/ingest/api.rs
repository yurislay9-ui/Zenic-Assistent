//! Public API — all ingest_* PyO3-exposed functions.

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};

use super::extractors::*;
use super::types::*;

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

    for ext in &texts {
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
