//! Internal validation and helper functions for the Template Completion Agent.

use pyo3::prelude::*;
use pyo3::types::PyDict;

use super::types::*;

// ═══════════════════════════════════════════════════════════════
//  Internal Helpers — Validation
// ═══════════════════════════════════════════════════════════════

/// Validate a value against a field type.
///
/// Returns (is_valid, error_message).
pub fn validate_value_for_type(field_type: &str, value: &str) -> (bool, Option<String>) {
    let trimmed = value.trim();
    if trimmed.is_empty() {
        return (false, Some("Value cannot be empty".to_string()));
    }

    match field_type {
        "email" => {
            let re = regex::Regex::new(EMAIL_PATTERN);
            match re {
                Ok(r) => {
                    if r.is_match(trimmed) {
                        (true, None)
                    } else {
                        (false, Some(format!("Invalid email format: {}", trimmed)))
                    }
                }
                Err(_) => {
                    // Fallback: basic check
                    if trimmed.contains('@') && trimmed.contains('.') {
                        (true, None)
                    } else {
                        (false, Some(format!("Invalid email format: {}", trimmed)))
                    }
                }
            }
        }
        "url" => {
            let re = regex::Regex::new(URL_PATTERN);
            match re {
                Ok(r) => {
                    if r.is_match(trimmed) {
                        (true, None)
                    } else if trimmed.contains('.') && !trimmed.contains(' ') {
                        (true, None)
                    } else {
                        (false, Some(format!("Invalid URL format: {}", trimmed)))
                    }
                }
                Err(_) => {
                    if trimmed.starts_with("http") || trimmed.contains('.') {
                        (true, None)
                    } else {
                        (false, Some(format!("Invalid URL format: {}", trimmed)))
                    }
                }
            }
        }
        "phone" => {
            let re = regex::Regex::new(PHONE_PATTERN);
            match re {
                Ok(r) => {
                    if r.is_match(trimmed) {
                        (true, None)
                    } else {
                        let digit_count = trimmed.chars().filter(|c| c.is_ascii_digit()).count();
                        if digit_count >= 7 {
                            (true, None)
                        } else {
                            (false, Some(format!("Invalid phone format: {}", trimmed)))
                        }
                    }
                }
                Err(_) => {
                    let digit_count = trimmed.chars().filter(|c| c.is_ascii_digit()).count();
                    if digit_count >= 7 {
                        (true, None)
                    } else {
                        (false, Some(format!("Invalid phone format: {}", trimmed)))
                    }
                }
            }
        }
        "number" => {
            if trimmed.parse::<f64>().is_ok() {
                (true, None)
            } else {
                (false, Some(format!("Invalid number: {}", trimmed)))
            }
        }
        "currency" => {
            let cleaned: String = trimmed
                .chars()
                .filter(|c| c.is_ascii_digit() || *c == '.' || *c == '-' || *c == ',')
                .collect();
            let normalized = cleaned.replace(',', "");
            if normalized.parse::<f64>().is_ok() {
                (true, None)
            } else {
                (false, Some(format!("Invalid currency value: {}", trimmed)))
            }
        }
        "percentage" => {
            let cleaned: String = trimmed.trim_end_matches('%').trim().to_string();
            if cleaned.parse::<f64>().is_ok() {
                (true, None)
            } else {
                (false, Some(format!("Invalid percentage: {}", trimmed)))
            }
        }
        "boolean" => {
            let lower = trimmed.to_lowercase();
            if matches!(lower.as_str(), "true" | "false" | "yes" | "no" | "1" | "0" | "si")
            {
                (true, None)
            } else {
                (false, Some(format!("Invalid boolean: {} (use true/false)", trimmed)))
            }
        }
        "date" => {
            let re = regex::Regex::new(DATE_PATTERN);
            match re {
                Ok(r) => {
                    if r.is_match(trimmed) {
                        (true, None)
                    } else {
                        (false, Some(format!("Invalid date format (use YYYY-MM-DD): {}", trimmed)))
                    }
                }
                Err(_) => {
                    let digit_count = trimmed.chars().filter(|c| c.is_ascii_digit()).count();
                    if digit_count >= 4 {
                        (true, None)
                    } else {
                        (false, Some(format!("Invalid date format: {}", trimmed)))
                    }
                }
            }
        }
        "datetime" => {
            let re = regex::Regex::new(DATETIME_PATTERN);
            match re {
                Ok(r) => {
                    if r.is_match(trimmed) {
                        (true, None)
                    } else {
                        (false, Some(format!("Invalid datetime format (use ISO 8601): {}", trimmed)))
                    }
                }
                Err(_) => {
                    let digit_count = trimmed.chars().filter(|c| c.is_ascii_digit()).count();
                    if digit_count >= 8 {
                        (true, None)
                    } else {
                        (false, Some(format!("Invalid datetime format: {}", trimmed)))
                    }
                }
            }
        }
        "json" => {
            if trimmed.starts_with('{') || trimmed.starts_with('[') {
                match serde_json::from_str::<serde_json::Value>(trimmed) {
                    Ok(_) => (true, None),
                    Err(e) => (false, Some(format!("Invalid JSON: {}", e))),
                }
            } else {
                (false, Some("JSON must start with { or [".to_string()))
            }
        }
        "enum" => {
            // Enum validation is context-dependent; accept any non-empty value
            (true, None)
        }
        "reference" => {
            // Reference validation is context-dependent; accept any non-empty value
            (true, None)
        }
        "file" => {
            // File validation is context-dependent; accept any non-empty value
            (true, None)
        }
        _ => {
            // "text" and unknown types: accept any non-empty value
            (true, None)
        }
    }
}

/// Get the validation hint for a field type.
pub fn validation_hint_for_type(field_type: &str) -> String {
    match field_type {
        "email" => "Enter a valid email address (e.g., user@example.com)".to_string(),
        "url" => "Enter a valid URL (e.g., https://example.com)".to_string(),
        "phone" => "Enter a phone number with at least 7 digits".to_string(),
        "number" => "Enter a numeric value".to_string(),
        "currency" => "Enter a monetary value (e.g., 1000.00)".to_string(),
        "percentage" => "Enter a percentage (e.g., 15 or 15%)".to_string(),
        "boolean" => "Enter true or false (or yes/no)".to_string(),
        "date" => "Enter a date in YYYY-MM-DD format".to_string(),
        "datetime" => "Enter a datetime in ISO 8601 format".to_string(),
        "json" => "Enter a valid JSON object or array".to_string(),
        "enum" => "Select one of the available options".to_string(),
        "reference" => "Enter the identifier of the referenced entity".to_string(),
        "file" => "Provide a file path or upload a file".to_string(),
        _ => "Enter a text value".to_string(),
    }
}

/// Get suggestions for a field by name and type.
pub fn get_suggestions_for_field(field_name: &str, field_type: &str) -> Vec<String> {
    // Check field-specific suggestions
    let name_lower = field_name.to_lowercase();
    for (key, suggestions) in SUGGESTIONS_BY_TYPE {
        if *key == name_lower {
            return suggestions.iter().map(|s| s.to_string()).collect();
        }
    }

    // Fall back to type-based suggestions
    match field_type {
        "boolean" => vec!["true".to_string(), "false".to_string()],
        "enum" => vec![], // Enum variants are provided by the template
        _ => vec![],
    }
}

/// Generate a simple UUID-like session ID.
pub fn generate_session_id() -> String {
    use std::time::{SystemTime, UNIX_EPOCH};
    let timestamp = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_millis())
        .unwrap_or(0);
    format!("{:016x}-{:04x}", timestamp, (timestamp % 65536) as u16)
}

/// Sanitize a string value for template insertion.
pub fn sanitize_value(value: &str) -> String {
    let trimmed = value.trim();
    if trimmed.len() > MAX_ANSWER_LENGTH {
        trimmed.chars().take(MAX_ANSWER_LENGTH).collect()
    } else {
        trimmed.to_string()
    }
}

/// Get the field type for a field in the template.
pub fn get_field_type_from_template(
    template_dict: &Bound<'_, PyDict>,
    section_id: &str,
    field_name: &str,
) -> String {
    let template_obj = match template_dict.get_item("template") {
        Ok(Some(t)) => t,
        _ => return "text".to_string(),
    };

    let template_pydict: &Bound<'_, PyDict> = match template_obj.downcast() {
        Ok(d) => d,
        _ => return "text".to_string(),
    };

    let sections_obj = match template_pydict.get_item("sections") {
        Ok(Some(s)) => s,
        _ => return "text".to_string(),
    };

    let sections: &Bound<'_, PyDict> = match sections_obj.downcast() {
        Ok(d) => d,
        _ => return "text".to_string(),
    };

    let section_val = match sections.get_item(section_id) {
        Ok(Some(v)) => v,
        _ => return "text".to_string(),
    };

    let section_dict: &Bound<'_, PyDict> = match section_val.downcast() {
        Ok(d) => d,
        _ => return "text".to_string(),
    };

    let field_val = match section_dict.get_item(field_name) {
        Ok(Some(v)) => v,
        _ => return "text".to_string(),
    };

    let field_dict: &Bound<'_, PyDict> = match field_val.downcast() {
        Ok(d) => d,
        _ => return "text".to_string(),
    };

    field_dict
        .get_item("_type")
        .ok()
        .flatten()
        .and_then(|v| v.extract().ok())
        .unwrap_or_else(|| "text".to_string())
}
