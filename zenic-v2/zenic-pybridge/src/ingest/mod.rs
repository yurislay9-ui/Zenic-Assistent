//! Document Ingestion Engine for Zenic-Agents (Phase 6.B).
//!
//! Handles document format detection, text extraction from simple
//! formats (TXT, CSV, JSON, Markdown), and provides a unified API
//! for the Python bridge to pass pre-extracted text from PDF/DOCX.

pub mod api;
pub mod extractors;
pub mod types;

// Re-export all public types and functions so that `use crate::ingest::DocumentFormat` still works
pub use api::{
    ingest_combine_texts, ingest_detect_format, ingest_extract_key_value_pairs,
    ingest_extract_text_batch, ingest_extract_text_simple, ingest_process_extracted_text,
    ingest_supported_formats, ingest_validate_size,
};
pub use extractors::{
    extract_csv, extract_json, extract_markdown, extract_txt, flatten_json_value,
    parse_csv_line, truncate_text,
};
pub use types::{
    BatchExtractionResult, DocumentFormat, ExtractedText, FORMAT_MAP, MAX_DOCUMENT_SIZE,
    MAX_EXTRACTED_TEXT_LENGTH,
};

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
        assert_eq!(combined.page_count, 2);
    }
}
