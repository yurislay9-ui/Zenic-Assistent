//! Core extraction logic — regex extractors, find_best_match, extractor_match_fields.

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};
use regex::Regex;
use std::collections::HashMap;

use crate::ingest::ExtractedText;

use super::matching::*;
use super::types::*;

/// Try to extract an email-like value from text near a keyword.
fn extract_email_near_keyword(text: &str, keyword: &str) -> Option<String> {
    let email_re = Regex::new(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}").ok()?;
    let keyword_lower = keyword.to_lowercase();

    for line in text.lines() {
        if line.to_lowercase().contains(&keyword_lower) {
            if let Some(mat) = email_re.find(line) {
                return Some(mat.as_str().to_string());
            }
        }
    }
    None
}

/// Try to extract a URL-like value from text near a keyword.
fn extract_url_near_keyword(text: &str, keyword: &str) -> Option<String> {
    let url_re = Regex::new(r"https?://[a-zA-Z0-9.\-_/]+").ok()?;
    let keyword_lower = keyword.to_lowercase();

    for line in text.lines() {
        if line.to_lowercase().contains(&keyword_lower) {
            if let Some(mat) = url_re.find(line) {
                return Some(mat.as_str().to_string());
            }
        }
    }
    None
}

/// Try to extract a phone-like value from text near a keyword.
fn extract_phone_near_keyword(text: &str, keyword: &str) -> Option<String> {
    let phone_re = Regex::new(r"[\+]?[\d\s\-\(\)]{7,20}").ok()?;
    let keyword_lower = keyword.to_lowercase();

    for line in text.lines() {
        if line.to_lowercase().contains(&keyword_lower) {
            if let Some(mat) = phone_re.find(line) {
                let cleaned = mat.as_str().trim().to_string();
                if cleaned.chars().filter(|c| c.is_ascii_digit()).count() >= 7 {
                    return Some(cleaned);
                }
            }
        }
    }
    None
}

/// Find the best match for a single field from key-value pairs.
fn find_best_match(
    field_name: &str,
    field_type: &str,
    display_name: &str,
    kv_pairs: &HashMap<String, String>,
    full_text: &str,
) -> Option<FieldMatch> {
    let mut best_match: Option<FieldMatch> = None;
    let mut best_confidence: f64 = 0.0;

    // Try key-value pair matching
    for (key, value) in kv_pairs {
        let confidence = score_field_match(field_name, field_type, display_name, key, value);
        if confidence > best_confidence && confidence >= MIN_CONFIDENCE_THRESHOLD {
            best_confidence = confidence;
            let method = if confidence >= CONFIDENCE_EXACT {
                "exact"
            } else if confidence >= CONFIDENCE_DISPLAY {
                "display"
            } else if confidence >= CONFIDENCE_STEM {
                "alias"
            } else if confidence >= CONFIDENCE_KEYWORD {
                "keyword"
            } else {
                "heuristic"
            };
            best_match = Some(FieldMatch::new(
                field_name.to_string(),
                String::new(), // section_id set later
                value.clone(),
                confidence,
                "kv_pairs".to_string(),
                method.to_string(),
            ));
        }
    }

    // Try regex-based extraction for specific types
    if best_match.is_none() || best_match.as_ref().map_or(true, |m| m.confidence < CONFIDENCE_STEM) {
        match field_type {
            "email" => {
                if let Some(email) = extract_email_near_keyword(full_text, display_name) {
                    if best_match.as_ref().map_or(true, |m| m.confidence < CONFIDENCE_DISPLAY) {
                        best_match = Some(FieldMatch::new(
                            field_name.to_string(),
                            String::new(),
                            email,
                            CONFIDENCE_DISPLAY,
                            "regex_email".to_string(),
                            "regex".to_string(),
                        ));
                    }
                }
                // Also try with field name as keyword
                if best_match.is_none() {
                    if let Some(email) = extract_email_near_keyword(full_text, field_name) {
                        best_match = Some(FieldMatch::new(
                            field_name.to_string(),
                            String::new(),
                            email,
                            CONFIDENCE_KEYWORD,
                            "regex_email".to_string(),
                            "regex".to_string(),
                        ));
                    }
                }
            }
            "url" => {
                if let Some(url) = extract_url_near_keyword(full_text, display_name) {
                    if best_match.as_ref().map_or(true, |m| m.confidence < CONFIDENCE_DISPLAY) {
                        best_match = Some(FieldMatch::new(
                            field_name.to_string(),
                            String::new(),
                            url,
                            CONFIDENCE_DISPLAY,
                            "regex_url".to_string(),
                            "regex".to_string(),
                        ));
                    }
                }
            }
            "phone" => {
                if let Some(phone) = extract_phone_near_keyword(full_text, display_name) {
                    if best_match.as_ref().map_or(true, |m| m.confidence < CONFIDENCE_DISPLAY) {
                        best_match = Some(FieldMatch::new(
                            field_name.to_string(),
                            String::new(),
                            phone,
                            CONFIDENCE_DISPLAY,
                            "regex_phone".to_string(),
                            "regex".to_string(),
                        ));
                    }
                }
            }
            _ => {}
        }
    }

    best_match
}

/// Match fields from extracted text against a template dict.
///
/// This is the primary function for the document ingestion pipeline.
/// It takes a template dict (from template_generate) and a list of
/// ExtractedText objects, and returns an ExtractionResult with
/// all matches found.
///
/// Parameters
/// ----------
/// template_dict : dict
///     The template dict (as returned by ``template_generate``).
/// extracted_texts : list[ExtractedText]
///     List of ExtractedText objects from document ingestion.
///
/// Returns
/// -------
/// ExtractionResult
///     Results with all matches, unmatched fields, and statistics.
#[pyfunction]
pub fn extractor_match_fields(
    template_dict: &Bound<'_, PyDict>,
    extracted_texts: &Bound<'_, PyList>,
    py: Python<'_>,
) -> PyResult<ExtractionResult> {
    // Extract template sections
    let template_obj = match template_dict.get_item("template") {
        Ok(Some(t)) => t,
        _ => {
            return Ok(ExtractionResult::new(
                Vec::new(), Vec::new(), 0.0, 0, 0, 0,
            ));
        }
    };

    let template_pydict: &Bound<'_, PyDict> = match template_obj.downcast() {
        Ok(d) => d,
        _ => {
            return Ok(ExtractionResult::new(
                Vec::new(), Vec::new(), 0.0, 0, 0, 0,
            ));
        }
    };

    let sections_obj = match template_pydict.get_item("sections") {
        Ok(Some(s)) => s,
        _ => {
            return Ok(ExtractionResult::new(
                Vec::new(), Vec::new(), 0.0, 0, 0, 0,
            ));
        }
    };

    let sections: &Bound<'_, PyDict> = match sections_obj.downcast() {
        Ok(d) => d,
        _ => {
            return Ok(ExtractionResult::new(
                Vec::new(), Vec::new(), 0.0, 0, 0, 0,
            ));
        }
    };

    // Combine all extracted text into one
    let mut combined_text = String::new();
    let texts: Vec<ExtractedText> = extracted_texts.extract()?;
    for ext in &texts {
        if !combined_text.is_empty() {
            combined_text.push('\n');
        }
        combined_text.push_str(&ext.text);
    }

    // Extract key-value pairs from combined text
    let kv_pairs = extract_key_value_pairs_from_text(&combined_text);
    let total_candidates = kv_pairs.len();

    // Match each template field against extracted data
    let mut matches: Vec<FieldMatch> = Vec::new();
    let mut matched_field_names: HashMap<String, bool> = HashMap::new();
    let mut all_field_names: Vec<(String, String, String, String)> = Vec::new(); // (name, section_id, type, display_name)

    for (section_key, section_val) in sections.iter() {
        let section_id: String = match section_key.extract() {
            Ok(s) => s,
            _ => continue,
        };

        let section_dict: &Bound<'_, PyDict> = match section_val.downcast() {
            Ok(d) => d,
            _ => continue,
        };

        for (field_key, field_val) in section_dict.iter() {
            let field_name: String = match field_key.extract() {
                Ok(s) => s,
                _ => continue,
            };

            if field_name.starts_with('_') {
                continue;
            }

            let field_dict: &Bound<'_, PyDict> = match field_val.downcast() {
                Ok(d) => d,
                _ => continue,
            };

            let field_type: String = field_dict
                .get_item("_type")
                .ok()
                .flatten()
                .and_then(|v| v.extract().ok())
                .unwrap_or_else(|| "text".into());

            let display_name: String = field_dict
                .get_item("_display")
                .ok()
                .flatten()
                .and_then(|v| v.extract().ok())
                .unwrap_or_else(|| field_name.clone());

            all_field_names.push((field_name.clone(), section_id.clone(), field_type.clone(), display_name.clone()));

            // Check if field already has a value
            let existing_value = field_dict.get_item("value").ok().flatten();
            let has_value = existing_value.as_ref().map_or(false, |v| !v.is_none());
            if has_value {
                matched_field_names.insert(field_name, true);
                continue;
            }

            // Try to match this field against extracted key-value pairs
            let best_match = find_best_match(
                &field_name,
                &field_type,
                &display_name,
                &kv_pairs,
                &combined_text,
            );

            if let Some(field_match) = best_match {
                if field_match.confidence() >= MIN_CONFIDENCE_THRESHOLD {
                    matched_field_names.insert(field_name, true);
                    matches.push(field_match);
                }
            }
        }
    }

    // Build unmatched list
    let unmatched_fields: Vec<String> = all_field_names
        .iter()
        .filter(|(name, _, _, _)| !matched_field_names.contains_key(name))
        .map(|(name, _, _, _)| name.clone())
        .collect();

    // Calculate average confidence
    let confidence_avg = if matches.is_empty() {
        0.0
    } else {
        matches.iter().map(|m| m.confidence()).sum::<f64>() / matches.len() as f64
    };

    let reliable_count = matches.iter().filter(|m| m.is_reliable()).count();

    Ok(ExtractionResult::new(
        matches,
        unmatched_fields,
        confidence_avg,
        total_candidates,
        matched_field_names.len(),
        reliable_count,
    ))
}
