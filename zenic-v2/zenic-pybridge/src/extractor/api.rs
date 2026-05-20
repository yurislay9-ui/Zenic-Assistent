//! Public API functions — extractor_confidence_score, extractor_find_candidates, extractor_stats.

use pyo3::prelude::*;
use pyo3::types::PyDict;
use std::collections::HashMap;

use super::matching::*;
use super::types::*;

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

    let total = result.matched_count() + result.unmatched_fields().len();
    let match_rate = if total > 0 {
        result.matched_count() as f64 / total as f64
    } else {
        0.0
    };

    dict.set_item("matched_count", result.matched_count())?;
    dict.set_item("unmatched_count", result.unmatched_fields().len())?;
    dict.set_item("confidence_avg", result.confidence_avg())?;
    dict.set_item("reliable_count", result.reliable_count())?;
    dict.set_item("total_candidates", result.total_candidates())?;
    dict.set_item("match_rate", match_rate)?;

    // Method distribution
    let method_dist = PyDict::new_bound(py);
    let mut method_counts: HashMap<String, usize> = HashMap::new();
    for m in result.matches() {
        *method_counts.entry(m.match_method.clone()).or_insert(0) += 1;
    }
    for (method, count) in &method_counts {
        method_dist.set_item(method, count)?;
    }
    dict.set_item("method_distribution", method_dist)?;

    Ok(dict.unbind())
}
