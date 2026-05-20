//! Field matching logic — normalization, comparison, scoring, aliases.

use std::collections::HashMap;

use super::types::*;

/// Normalize a string for comparison: lowercase, replace underscores/spaces with single form.
pub(crate) fn normalize_for_comparison(s: &str) -> String {
    s.to_lowercase()
        .replace('_', " ")
        .replace('-', " ")
        .split_whitespace()
        .collect::<Vec<&str>>()
        .join(" ")
}

/// Check if two strings match exactly (case-insensitive, normalized).
pub(crate) fn is_exact_match(a: &str, b: &str) -> bool {
    normalize_for_comparison(a) == normalize_for_comparison(b)
}

/// Check if string a contains string b (case-insensitive, normalized).
pub(crate) fn is_contains_match(haystack: &str, needle: &str) -> bool {
    let h = normalize_for_comparison(haystack);
    let n = normalize_for_comparison(needle);
    h.contains(&n) || n.contains(&h)
}

/// Get aliases for a field name.
pub(crate) fn get_field_aliases(field_name: &str) -> Vec<&'static str> {
    let name_lower = field_name.to_lowercase();
    for (key, aliases) in FIELD_ALIASES {
        if *key == name_lower {
            return aliases.to_vec();
        }
    }
    Vec::new()
}

/// Check if a candidate value looks valid for a given field type.
pub(crate) fn is_value_type_compatible(field_type: &str, value: &str) -> bool {
    match field_type {
        "email" => value.contains('@') && value.contains('.'),
        "url" => value.starts_with("http://") || value.starts_with("https://") || value.contains('.'),
        "phone" => {
            let digit_count = value.chars().filter(|c| c.is_ascii_digit()).count();
            digit_count >= 7
        }
        "number" | "currency" | "percentage" => {
            value.chars().any(|c| c.is_ascii_digit())
        }
        "boolean" => {
            let lower = value.to_lowercase();
            lower == "true" || lower == "false" || lower == "yes" || lower == "no"
                || lower == "1" || lower == "0" || lower == "si" || lower == "no"
        }
        "date" | "datetime" => {
            // Check for common date patterns
            value.chars().filter(|c| c.is_ascii_digit()).count() >= 4
                && (value.contains('-') || value.contains('/') || value.contains('.'))
        }
        "json" => value.starts_with('{') || value.starts_with('['),
        _ => true, // For text, enum, reference, file: always compatible
    }
}

/// Score the confidence of a potential field match.
///
/// Uses a multi-layer approach:
/// 1. Exact name match → CONFIDENCE_EXACT
/// 2. Display name match → CONFIDENCE_DISPLAY
/// 3. Alias match → CONFIDENCE_STEM
/// 4. Substring match → CONFIDENCE_KEYWORD
/// 5. Type compatibility → CONFIDENCE_HEURISTIC
pub(crate) fn score_field_match(
    field_name: &str,
    field_type: &str,
    display_name: &str,
    candidate_key: &str,
    candidate_value: &str,
) -> f64 {
    // Layer 1: Exact name match
    if is_exact_match(field_name, candidate_key) {
        return CONFIDENCE_EXACT;
    }

    // Layer 2: Display name match
    if !display_name.is_empty() && is_exact_match(display_name, candidate_key) {
        return CONFIDENCE_DISPLAY;
    }

    // Layer 3: Alias match
    let aliases = get_field_aliases(field_name);
    for alias in &aliases {
        if is_exact_match(alias, candidate_key) {
            return CONFIDENCE_STEM;
        }
    }

    // Layer 4: Substring / contains match
    if is_contains_match(field_name, candidate_key) {
        return CONFIDENCE_KEYWORD;
    }
    if !display_name.is_empty() && is_contains_match(display_name, candidate_key) {
        return CONFIDENCE_KEYWORD;
    }
    for alias in &aliases {
        if is_contains_match(alias, candidate_key) {
            return CONFIDENCE_KEYWORD;
        }
    }

    // Layer 5: Type compatibility
    if is_value_type_compatible(field_type, candidate_value) {
        return CONFIDENCE_HEURISTIC;
    }

    0.0
}

/// Extract key-value pairs from text using common delimiters.
pub(crate) fn extract_key_value_pairs_from_text(text: &str) -> HashMap<String, String> {
    let mut pairs: HashMap<String, String> = HashMap::new();

    let separators = [": ", " = ", " - ", ":  ", " : "];

    for line in text.lines() {
        let trimmed = line.trim();
        if trimmed.is_empty() || trimmed.starts_with('#') || trimmed.starts_with("//") {
            continue;
        }

        for separator in &separators {
            if let Some(pos) = trimmed.find(separator) {
                let key = trimmed[..pos].trim();
                let value = trimmed[pos + separator.len()..].trim();

                if !key.is_empty() && key.len() < 100 && !value.is_empty() && value.len() < 1000 {
                    let key_lower = key.to_lowercase();
                    pairs.entry(key_lower).or_insert_with(|| value.to_string());
                }
                break;
            }
        }
    }

    pairs
}
