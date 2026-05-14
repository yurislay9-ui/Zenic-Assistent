//! Field Extraction Engine for Zenic-Agents (Phase 6.B).
//!
//! Implements pattern-based field extraction from text, matching
//! extracted data to template fields, confidence scoring, and
//! automatic template filling.
//!
//! # Architecture
//!
//! The extraction pipeline:
//!
//! 1. ExtractedText (from ingest.rs) → raw text content
//! 2. Key-value pair extraction from text
//! 3. Pattern matching against template field names and display names
//! 4. Confidence scoring for each match
//! 5. FieldMatch results → template auto-fill
//!
//! # Matching Strategy
//!
//! Field matching uses a multi-layer approach:
//!
//! 1. **Exact match**: key name == field name (confidence: 0.95)
//! 2. **Display match**: key contains field display_name (confidence: 0.85)
//! 3. **Stem match**: key stem matches field name stem (confidence: 0.70)
//! 4. **Keyword match**: key contains relevant keywords (confidence: 0.50)
//! 5. **Heuristic match**: value type matches field type (confidence: 0.30)
//!
//! # PyO3 Exposed Types
//!
//! - `FieldMatch` — a single matched field with confidence
//! - `ExtractionResult` — results from field extraction
//!
//! # PyO3 Exposed Functions
//!
//! - `extractor_match_fields(template_dict, extracted_texts)` — match fields to template
//! - `extractor_apply_matches(template_dict, matches)` — apply matches to template
//! - `extractor_confidence_score(field_name, field_type, candidate_value, text)` — score confidence
//! - `extractor_find_candidates(field_name, field_type, display_name, text)` — find candidates
//! - `extractor_stats(result)` — get extraction statistics

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};
use regex::Regex;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

use crate::ingest::ExtractedText;

// ═══════════════════════════════════════════════════════════════
//  Constants
// ═══════════════════════════════════════════════════════════════

/// Minimum confidence to consider a match valid.
const MIN_CONFIDENCE_THRESHOLD: f64 = 0.3;

/// Confidence level for exact name match.
const CONFIDENCE_EXACT: f64 = 0.95;

/// Confidence level for display name match.
const CONFIDENCE_DISPLAY: f64 = 0.85;

/// Confidence level for stem/substring match.
const CONFIDENCE_STEM: f64 = 0.70;

/// Confidence level for keyword match.
const CONFIDENCE_KEYWORD: f64 = 0.50;

/// Confidence level for heuristic/type match.
const CONFIDENCE_HEURISTIC: f64 = 0.30;

/// Maximum number of candidate values to extract per field.
const MAX_CANDIDATES_PER_FIELD: usize = 5;

/// Common field name aliases for fuzzy matching.
const FIELD_ALIASES: &[(&str, &[&str])] = &[
    ("business_name", &["company", "organization", "empresa", "negocio", "company_name", "business", "firm"]),
    ("business_type", &["company_type", "entity_type", "tipo_empresa", "organization_type"]),
    ("tax_id", &["ruc", "nit", "cif", "vat", "eIN", "tax_number", "rfc"]),
    ("country", &["pais", "nation", "region"]),
    ("industry", &["sector", "industria", "vertical", "domain"]),
    ("website", &["url", "sitio_web", "web", "homepage", "site"]),
    ("email", &["correo", "mail", "e-mail", "email_address"]),
    ("phone", &["telefono", "tel", "telephone", "phone_number", "contact_number"]),
    ("admin_email", &["admin_correo", "administrator_email", "admin_mail"]),
    ("admin_phone", &["admin_telefono", "administrator_phone"]),
    ("auth_method", &["authentication", "auth_type", "metodo_autenticacion"]),
    ("model_name", &["modelo", "model", "ai_model"]),
    ("model_provider", &["provider", "proveedor", "ai_provider"]),
    ("api_key_ref", &["api_key", "key_ref", "clave_api"]),
    ("base_currency", &["currency", "moneda", "moneda_base"]),
    ("payment_gateway", &["gateway", "pasarela", "payment_provider"]),
];

// ═══════════════════════════════════════════════════════════════
//  FieldMatch — a single matched field with confidence
// ═══════════════════════════════════════════════════════════════

/// A field matched from extracted text with confidence score.
///
/// Each match records:
/// - Which template field it corresponds to
/// - The extracted value
/// - Confidence score (0.0-1.0)
/// - The source document/section
/// - The matching method used
#[pyclass(name = "FieldMatch")]
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct FieldMatch {
    field_name: String,
    section_id: String,
    value: String,
    confidence: f64,
    source: String,
    match_method: String,
}

impl FieldMatch {
    /// Create a new FieldMatch with validation.
    pub fn new(
        field_name: String,
        section_id: String,
        value: String,
        confidence: f64,
        source: String,
        match_method: String,
    ) -> Self {
        let confidence_clamped = confidence.clamp(0.0, 1.0);
        FieldMatch {
            field_name,
            section_id,
            value,
            confidence: confidence_clamped,
            source,
            match_method,
        }
    }

    /// Get the field name.
    pub fn field_name(&self) -> &str {
        &self.field_name
    }

    /// Get the section ID.
    pub fn section_id(&self) -> &str {
        &self.section_id
    }

    /// Get the matched value.
    pub fn value(&self) -> &str {
        &self.value
    }

    /// Get the confidence score.
    pub fn confidence(&self) -> f64 {
        self.confidence
    }
}

#[pymethods]
impl FieldMatch {
    #[getter]
    fn field_name(&self) -> &str {
        &self.field_name
    }

    #[getter]
    fn section_id(&self) -> &str {
        &self.section_id
    }

    #[getter]
    fn value(&self) -> &str {
        &self.value
    }

    #[getter]
    fn confidence(&self) -> f64 {
        self.confidence
    }

    #[getter]
    fn source(&self) -> &str {
        &self.source
    }

    #[getter]
    fn match_method(&self) -> &str {
        &self.match_method
    }

    /// Check if this match meets the minimum confidence threshold.
    fn is_reliable(&self) -> bool {
        self.confidence >= MIN_CONFIDENCE_THRESHOLD
    }

    /// Get a summary dict.
    fn summary(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        let dict = PyDict::new_bound(py);
        dict.set_item("field_name", &self.field_name)?;
        dict.set_item("section_id", &self.section_id)?;
        dict.set_item("value", &self.value)?;
        dict.set_item("confidence", self.confidence)?;
        dict.set_item("source", &self.source)?;
        dict.set_item("match_method", &self.match_method)?;
        dict.set_item("is_reliable", self.is_reliable())?;
        Ok(dict.unbind())
    }

    fn __repr__(&self) -> String {
        format!(
            "FieldMatch(field={:?}, section={:?}, confidence={:.2}, method={:?})",
            self.field_name, self.section_id, self.confidence, self.match_method,
        )
    }
}

// ═══════════════════════════════════════════════════════════════
//  ExtractionResult — results from field extraction
// ═══════════════════════════════════════════════════════════════

/// Results from extracting field values from text.
///
/// Contains all matches, unmatched fields, and aggregate statistics.
#[pyclass(name = "ExtractionResult")]
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ExtractionResult {
    matches: Vec<FieldMatch>,
    unmatched_fields: Vec<String>,
    confidence_avg: f64,
    total_candidates: usize,
    matched_count: usize,
    reliable_count: usize,
}

#[pymethods]
impl ExtractionResult {
    #[getter]
    fn matches(&self) -> Vec<FieldMatch> {
        self.matches.clone()
    }

    #[getter]
    fn unmatched_fields(&self) -> Vec<String> {
        self.unmatched_fields.clone()
    }

    #[getter]
    fn confidence_avg(&self) -> f64 {
        self.confidence_avg
    }

    #[getter]
    fn total_candidates(&self) -> usize {
        self.total_candidates
    }

    #[getter]
    fn matched_count(&self) -> usize {
        self.matched_count
    }

    #[getter]
    fn reliable_count(&self) -> usize {
        self.reliable_count
    }

    /// Get a summary dict.
    fn summary(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        let dict = PyDict::new_bound(py);
        dict.set_item("matched_count", self.matched_count)?;
        dict.set_item("unmatched_count", self.unmatched_fields.len())?;
        dict.set_item("confidence_avg", self.confidence_avg)?;
        dict.set_item("reliable_count", self.reliable_count)?;
        dict.set_item("total_candidates", self.total_candidates)?;
        Ok(dict.unbind())
    }

    fn __repr__(&self) -> String {
        format!(
            "ExtractionResult(matched={}, unmatched={}, avg_confidence={:.2})",
            self.matched_count,
            self.unmatched_fields.len(),
            self.confidence_avg,
        )
    }
}

// ═══════════════════════════════════════════════════════════════
//  Internal Helpers — Pattern Matching
// ═══════════════════════════════════════════════════════════════

/// Normalize a string for comparison: lowercase, replace underscores/spaces with single form.
fn normalize_for_comparison(s: &str) -> String {
    s.to_lowercase()
        .replace('_', " ")
        .replace('-', " ")
        .split_whitespace()
        .collect::<Vec<&str>>()
        .join(" ")
}

/// Check if two strings match exactly (case-insensitive, normalized).
fn is_exact_match(a: &str, b: &str) -> bool {
    normalize_for_comparison(a) == normalize_for_comparison(b)
}

/// Check if string a contains string b (case-insensitive, normalized).
fn is_contains_match(haystack: &str, needle: &str) -> bool {
    let h = normalize_for_comparison(haystack);
    let n = normalize_for_comparison(needle);
    h.contains(&n) || n.contains(&h)
}

/// Get aliases for a field name.
fn get_field_aliases(field_name: &str) -> Vec<&'static str> {
    let name_lower = field_name.to_lowercase();
    for (key, aliases) in FIELD_ALIASES {
        if *key == name_lower {
            return aliases.to_vec();
        }
    }
    Vec::new()
}

/// Check if a candidate value looks valid for a given field type.
fn is_value_type_compatible(field_type: &str, value: &str) -> bool {
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

/// Extract key-value pairs from text using common delimiters.
fn extract_key_value_pairs_from_text(text: &str) -> HashMap<String, String> {
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

/// Score the confidence of a potential field match.
///
/// Uses a multi-layer approach:
/// 1. Exact name match → CONFIDENCE_EXACT
/// 2. Display name match → CONFIDENCE_DISPLAY
/// 3. Alias match → CONFIDENCE_STEM
/// 4. Substring match → CONFIDENCE_KEYWORD
/// 5. Type compatibility → CONFIDENCE_HEURISTIC
fn score_field_match(
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

// ═══════════════════════════════════════════════════════════════
//  PyO3 Functions — Public API
// ═══════════════════════════════════════════════════════════════

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
            return Ok(ExtractionResult {
                matches: Vec::new(),
                unmatched_fields: Vec::new(),
                confidence_avg: 0.0,
                total_candidates: 0,
                matched_count: 0,
                reliable_count: 0,
            });
        }
    };

    let template_pydict: &Bound<'_, PyDict> = match template_obj.downcast() {
        Ok(d) => d,
        _ => {
            return Ok(ExtractionResult {
                matches: Vec::new(),
                unmatched_fields: Vec::new(),
                confidence_avg: 0.0,
                total_candidates: 0,
                matched_count: 0,
                reliable_count: 0,
            });
        }
    };

    let sections_obj = match template_pydict.get_item("sections") {
        Ok(Some(s)) => s,
        _ => {
            return Ok(ExtractionResult {
                matches: Vec::new(),
                unmatched_fields: Vec::new(),
                confidence_avg: 0.0,
                total_candidates: 0,
                matched_count: 0,
                reliable_count: 0,
            });
        }
    };

    let sections: &Bound<'_, PyDict> = match sections_obj.downcast() {
        Ok(d) => d,
        _ => {
            return Ok(ExtractionResult {
                matches: Vec::new(),
                unmatched_fields: Vec::new(),
                confidence_avg: 0.0,
                total_candidates: 0,
                matched_count: 0,
                reliable_count: 0,
            });
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

    Ok(ExtractionResult {
        matches,
        unmatched_fields,
        confidence_avg,
        total_candidates,
        matched_count: matched_field_names.len(),
        reliable_count,
    })
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

/// Apply extraction matches to a template dict.
///
/// Sets field values in the template for each match that meets
/// the minimum confidence threshold. Also recalculates completeness.
///
/// Parameters
/// ----------
/// template_dict : dict
///     The template dict (will be modified in-place).
/// matches : list[FieldMatch]
///     The field matches to apply.
///
/// Returns
/// -------
/// bool
///     True if at least one field was successfully set.
#[pyfunction]
pub fn extractor_apply_matches(
    template_dict: &Bound<'_, PyDict>,
    matches: &Bound<'_, PyList>,
) -> PyResult<bool> {
    let match_list: Vec<FieldMatch> = matches.extract()?;
    if match_list.is_empty() {
        return Ok(false);
    }

    let mut any_applied = false;

    // Use template_set_field from the template module for each match
    for field_match in &match_list {
        if field_match.confidence() < MIN_CONFIDENCE_THRESHOLD {
            continue;
        }

        let section_id = field_match.section_id();
        let field_name = field_match.field_name();
        let value = field_match.value();

        // Try to set the field using the existing template API
        let result = crate::template::template_set_field(
            template_dict,
            section_id,
            field_name,
            value.into(),
        );

        match result {
            Ok(true) => any_applied = true,
            Ok(false) => {
                // Field not found in the specified section; try to find it
                // This can happen when section_id is empty
                if section_id.is_empty() {
                    if let Ok(found) = try_set_field_any_section(template_dict, field_name, value) {
                        if found {
                            any_applied = true;
                        }
                    }
                }
            }
            Err(_) => continue,
        }
    }

    Ok(any_applied)
}

/// Try to set a field value by searching all sections.
fn try_set_field_any_section(
    template_dict: &Bound<'_, PyDict>,
    field_name: &str,
    value: &str,
) -> PyResult<bool> {
    let template_obj = match template_dict.get_item("template") {
        Ok(Some(t)) => t,
        _ => return Ok(false),
    };

    let template_pydict: &Bound<'_, PyDict> = match template_obj.downcast() {
        Ok(d) => d,
        _ => return Ok(false),
    };

    let sections_obj = match template_pydict.get_item("sections") {
        Ok(Some(s)) => s,
        _ => return Ok(false),
    };

    let sections: &Bound<'_, PyDict> = match sections_obj.downcast() {
        Ok(d) => d,
        _ => return Ok(false),
    };

    for (section_key, section_val) in sections.iter() {
        let section_dict: &Bound<'_, PyDict> = match section_val.downcast() {
            Ok(d) => d,
            _ => continue,
        };

        if let Ok(Some(_)) = section_dict.get_item(field_name) {
            let section_id: String = section_key.extract().unwrap_or_default();
            return crate::template::template_set_field(
                template_dict,
                &section_id,
                field_name,
                value.into(),
            );
        }
    }

    Ok(false)
}

/// Score the confidence of a potential field match.
///
/// Parameters
/// ----------
/// field_name : str
///     The template field name.
/// field_type : str
///     The template field type (e.g., ``"email"``, ``"text"``).
/// candidate_key : str
///     The key from extracted text.
/// candidate_value : str
///     The value from extracted text.
///
/// Returns
/// -------
/// float
///     Confidence score between 0.0 and 1.0.
#[pyfunction]
pub fn extractor_confidence_score(
    field_name: &str,
    field_type: &str,
    candidate_key: &str,
    candidate_value: &str,
) -> f64 {
    score_field_match(field_name, field_type, "", candidate_key, candidate_value)
}

/// Find candidate matches for a specific field in text.
///
/// Parameters
/// ----------
/// field_name : str
///     The template field name.
/// field_type : str
///     The template field type.
/// display_name : str
///     The human-readable field display name.
/// text : str
///     The text to search in.
///
/// Returns
/// -------
/// list[FieldMatch]
///     Up to MAX_CANDIDATES_PER_FIELD candidate matches.
#[pyfunction]
pub fn extractor_find_candidates(
    field_name: &str,
    field_type: &str,
    display_name: &str,
    text: &str,
) -> Vec<FieldMatch> {
    let mut candidates: Vec<FieldMatch> = Vec::new();

    if text.trim().is_empty() {
        return candidates;
    }

    let kv_pairs = extract_key_value_pairs_from_text(text);

    for (key, value) in &kv_pairs {
        let confidence = score_field_match(field_name, field_type, display_name, key, value);
        if confidence >= MIN_CONFIDENCE_THRESHOLD {
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

            candidates.push(FieldMatch::new(
                field_name.to_string(),
                String::new(),
                value.clone(),
                confidence,
                "text_search".to_string(),
                method.to_string(),
            ));

            if candidates.len() >= MAX_CANDIDATES_PER_FIELD {
                break;
            }
        }
    }

    // Sort by confidence descending
    candidates.sort_by(|a, b| b.confidence().partial_cmp(&a.confidence()).unwrap_or(std::cmp::Ordering::Equal));

    candidates
}

/// Get extraction statistics from an ExtractionResult.
///
/// Parameters
/// ----------
/// result : ExtractionResult
///     The extraction result to analyze.
///
/// Returns
/// -------
/// dict
///     Statistics dict with keys:
///     - ``matched_count`` (int): Number of matched fields
///     - ``unmatched_count`` (int): Number of unmatched fields
///     - ``confidence_avg`` (float): Average confidence
///     - ``reliable_count`` (int): Matches above threshold
///     - ``match_rate`` (float): matched / total ratio
///     - ``method_distribution`` (dict): Count by match method
#[pyfunction]
pub fn extractor_stats(result: &ExtractionResult, py: Python<'_>) -> PyResult<Py<PyDict>> {
    let dict = PyDict::new_bound(py);

    let total = result.matched_count + result.unmatched_fields.len();
    let match_rate = if total > 0 {
        result.matched_count as f64 / total as f64
    } else {
        0.0
    };

    dict.set_item("matched_count", result.matched_count)?;
    dict.set_item("unmatched_count", result.unmatched_fields.len())?;
    dict.set_item("confidence_avg", result.confidence_avg)?;
    dict.set_item("reliable_count", result.reliable_count)?;
    dict.set_item("total_candidates", result.total_candidates)?;
    dict.set_item("match_rate", match_rate)?;

    // Method distribution
    let method_dist = PyDict::new_bound(py);
    let mut method_counts: HashMap<String, usize> = HashMap::new();
    for m in &result.matches {
        *method_counts.entry(m.match_method.clone()).or_insert(0) += 1;
    }
    for (method, count) in &method_counts {
        method_dist.set_item(method, count)?;
    }
    dict.set_item("method_distribution", method_dist)?;

    Ok(dict.unbind())
}

// ═══════════════════════════════════════════════════════════════
//  Unit Tests
// ═══════════════════════════════════════════════════════════════

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_normalize_for_comparison() {
        assert_eq!(normalize_for_comparison("Business_Name"), "business name");
        assert_eq!(normalize_for_comparison("business-name"), "business name");
        assert_eq!(normalize_for_comparison("BusinessName"), "businessname");
    }

    #[test]
    fn test_exact_match() {
        assert!(is_exact_match("Business_Name", "business name"));
        assert!(is_exact_match("tax_id", "Tax ID"));
        assert!(!is_exact_match("tax_id", "tax_number"));
    }

    #[test]
    fn test_contains_match() {
        assert!(is_contains_match("business_name", "business"));
        assert!(is_contains_match("Business Name", "name"));
        assert!(!is_contains_match("email", "phone"));
    }

    #[test]
    fn test_get_field_aliases() {
        let aliases = get_field_aliases("business_name");
        assert!(!aliases.is_empty());
        assert!(aliases.contains(&"company"));
        assert!(aliases.contains(&"empresa"));

        let no_aliases = get_field_aliases("nonexistent_field_xyz");
        assert!(no_aliases.is_empty());
    }

    #[test]
    fn test_is_value_type_compatible() {
        assert!(is_value_type_compatible("email", "user@example.com"));
        assert!(!is_value_type_compatible("email", "not an email"));

        assert!(is_value_type_compatible("url", "https://example.com"));
        assert!(is_value_type_compatible("url", "example.com"));

        assert!(is_value_type_compatible("phone", "+1 555-123-4567"));
        assert!(!is_value_type_compatible("phone", "abc"));

        assert!(is_value_type_compatible("boolean", "true"));
        assert!(is_value_type_compatible("boolean", "yes"));
        assert!(!is_value_type_compatible("boolean", "maybe"));

        assert!(is_value_type_compatible("json", "{\"key\": \"value\"}"));
    }

    #[test]
    fn test_score_field_match_exact() {
        let score = score_field_match("business_name", "text", "Business Name", "business_name", "Acme Corp");
        assert_eq!(score, CONFIDENCE_EXACT);
    }

    #[test]
    fn test_score_field_match_display() {
        let score = score_field_match("business_name", "text", "Business Name", "business name", "Acme Corp");
        assert_eq!(score, CONFIDENCE_DISPLAY);
    }

    #[test]
    fn test_score_field_match_alias() {
        let score = score_field_match("business_name", "text", "Business Name", "company", "Acme Corp");
        assert_eq!(score, CONFIDENCE_STEM);
    }

    #[test]
    fn test_score_field_match_keyword() {
        let score = score_field_match("business_name", "text", "Business Name", "business type", "LLC");
        assert!(score >= CONFIDENCE_KEYWORD);
    }

    #[test]
    fn test_score_field_match_no_match() {
        let score = score_field_match("auth_method", "enum", "Authentication Method", "color", "red");
        assert!(score < MIN_CONFIDENCE_THRESHOLD);
    }

    #[test]
    fn test_extract_key_value_pairs() {
        let text = "Name: Alice\nAge: 30\nCity = NYC\nIndustry - Tech";
        let pairs = extract_key_value_pairs_from_text(text);
        assert_eq!(pairs.get("name").map(|s| s.as_str()), Some("Alice"));
        assert_eq!(pairs.get("age").map(|s| s.as_str()), Some("30"));
        assert_eq!(pairs.get("city").map(|s| s.as_str()), Some("NYC"));
        assert_eq!(pairs.get("industry").map(|s| s.as_str()), Some("Tech"));
    }

    #[test]
    fn test_extract_key_value_pairs_first_wins() {
        let text = "Name: Alice\nName: Bob";
        let pairs = extract_key_value_pairs_from_text(text);
        assert_eq!(pairs.get("name").map(|s| s.as_str()), Some("Alice"));
    }

    #[test]
    fn test_field_match_creation() {
        let fm = FieldMatch::new(
            "business_name".into(),
            "business_identity".into(),
            "Acme Corp".into(),
            0.95,
            "kv_pairs".into(),
            "exact".into(),
        );
        assert_eq!(fm.field_name(), "business_name");
        assert_eq!(fm.value(), "Acme Corp");
        assert!((fm.confidence() - 0.95).abs() < 0.001);
        assert!(fm.is_reliable());
    }

    #[test]
    fn test_field_match_confidence_clamped() {
        let fm = FieldMatch::new(
            "test".into(),
            "section".into(),
            "value".into(),
            1.5, // Over 1.0
            "source".into(),
            "method".into(),
        );
        assert!((fm.confidence() - 1.0).abs() < 0.001);
    }

    #[test]
    fn test_find_candidates() {
        let text = "Business Name: Acme Corp\nTax ID: 123456789\nCountry: USA\nEmail: admin@acme.com";
        let candidates = extractor_find_candidates("business_name", "text", "Business Name", text);
        assert!(!candidates.is_empty());
        assert_eq!(candidates[0].value(), "Acme Corp");
        assert!(candidates[0].confidence() >= CONFIDENCE_EXACT);
    }

    #[test]
    fn test_find_candidates_email_regex() {
        let text = "Contact us at support@company.com for more info";
        let candidates = extractor_find_candidates("admin_email", "email", "Admin Email", text);
        assert!(!candidates.is_empty());
    }

    #[test]
    fn test_find_candidates_empty_text() {
        let candidates = extractor_find_candidates("test", "text", "Test", "");
        assert!(candidates.is_empty());
    }

    #[test]
    fn test_extract_email_near_keyword() {
        let text = "Admin Email: boss@company.com\nOther: info@company.com";
        let result = extract_email_near_keyword(text, "admin email");
        assert!(result.is_some());
        assert_eq!(result.unwrap(), "boss@company.com");
    }

    #[test]
    fn test_extract_url_near_keyword() {
        let text = "Website: https://example.com\nOther text";
        let result = extract_url_near_keyword(text, "website");
        assert!(result.is_some());
        assert_eq!(result.unwrap(), "https://example.com");
    }

    #[test]
    fn test_confidence_thresholds() {
        assert!(CONFIDENCE_EXACT > CONFIDENCE_DISPLAY);
        assert!(CONFIDENCE_DISPLAY > CONFIDENCE_STEM);
        assert!(CONFIDENCE_STEM > CONFIDENCE_KEYWORD);
        assert!(CONFIDENCE_KEYWORD > CONFIDENCE_HEURISTIC);
        assert!(CONFIDENCE_HEURISTIC >= MIN_CONFIDENCE_THRESHOLD);
    }
}
