//! Internal text extraction helpers — TXT, CSV, JSON, Markdown, truncate.

use super::types::*;

/// Extract text from a plain text file (UTF-8).
pub(crate) fn extract_txt(data: &[u8]) -> (String, Vec<String>) {
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
pub(crate) fn extract_csv(data: &[u8]) -> (String, Vec<String>) {
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
pub(crate) fn parse_csv_line(line: &str) -> Vec<String> {
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
pub(crate) fn extract_json(data: &[u8]) -> (String, Vec<String>) {
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
pub(crate) fn flatten_json_value(value: &serde_json::Value, prefix: &str, pairs: &mut Vec<String>) {
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
pub(crate) fn extract_markdown(data: &[u8]) -> (String, Vec<String>) {
    extract_txt(data)
}

/// Truncate text to MAX_EXTRACTED_TEXT_LENGTH.
pub(crate) fn truncate_text(text: String) -> (String, Vec<String>) {
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
