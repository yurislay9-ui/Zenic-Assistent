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

pub mod api;
pub mod apply;
pub mod extraction;
pub mod matching;
pub mod types;

// Re-export all public types and functions so that `use crate::extractor::FieldMatch` still works
pub use api::{extractor_confidence_score, extractor_find_candidates, extractor_stats};
pub use apply::extractor_apply_matches;
pub use extraction::extractor_match_fields;
pub use matching::{
    extract_key_value_pairs_from_text, get_field_aliases, is_contains_match, is_exact_match,
    is_value_type_compatible, normalize_for_comparison, score_field_match,
};
pub use types::{
    ExtractionResult, FieldMatch, CONFIDENCE_DISPLAY, CONFIDENCE_EXACT, CONFIDENCE_HEURISTIC,
    CONFIDENCE_KEYWORD, CONFIDENCE_STEM, FIELD_ALIASES, MAX_CANDIDATES_PER_FIELD,
    MIN_CONFIDENCE_THRESHOLD,
};

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
}
