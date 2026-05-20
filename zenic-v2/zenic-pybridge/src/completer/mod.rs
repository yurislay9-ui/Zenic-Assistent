//! Template Completion Agent for Zenic-Agents (Phase 6.C).
//!
//! Orchestrates the interactive template completion pipeline:
//! niche selection → template generation → document ingestion →
//! field extraction → auto-fill → interactive Q&A → finalization.
//!
//! # Architecture
//!
//! The completion agent ties together Fase A and Fase B:
//!
//! 1. User selects a niche → template_generate (Fase A)
//! 2. User uploads documents → ingest + extractor (Fase B)
//! 3. Auto-fill template from extracted data
//! 4. Identify missing required fields
//! 5. Generate structured questions for the user
//! 6. Validate and apply user answers
//! 7. Repeat 4-6 until all required fields are complete
//! 8. Finalize and export YAML template
//!
//! # Design Decisions
//!
//! - CompletionSession stores template_dict as a Python dict (Py<PyDict>)
//!   because template operations (set_field, validate, missing_fields)
//!   are all PyO3 functions that operate on PyDict.
//! - Session state is tracked via a session_id (UUID v4).
//! - Each Q&A round is tracked for audit purposes.
//! - No `unwrap` or `panic` — all errors handled explicitly.
//! - All external input is validated before processing.
//!
//! # PyO3 Exposed Types
//!
//! - `CompletionSession` — interactive template completion session
//! - `CompletionQuestion` — structured question for a missing field
//! - `CompletionRound` — one round of questions and answers
//! - `CompletionResult` — final result of the completion process
//!
//! # PyO3 Exposed Functions
//!
//! - `completer_start_session(niche_id)` — create new session
//! - `completer_ingest_documents(session, texts)` — ingest and auto-fill
//! - `completer_get_questions(session)` — get questions for missing fields
//! - `completer_submit_answer(session, field_name, value)` — process one answer
//! - `completer_submit_answers(session, answers)` — batch process answers
//! - `completer_validate_answer(field_type, value)` — validate a single answer
//! - `completer_get_progress(session)` — get completion progress
//! - `completer_is_complete(session)` — check if all required fields filled
//! - `completer_finalize(session)` — produce final YAML template
//! - `completer_get_field_suggestions(field_name, field_type)` — get suggestions

pub mod api_answers;
pub mod api_finalize;
pub mod api_session;
pub mod result_types;
pub mod types;
pub mod validation;

// Re-export all public items so `crate::completer::*` works unchanged.
pub use types::{
    CompletionSession,
    CompletionQuestion,
    AUTO_ACCEPT_CONFIDENCE,
    MAX_ANSWER_LENGTH,
    MAX_QUESTIONS_PER_ROUND,
    MAX_ROUNDS,
    SUGGESTIONS_BY_TYPE,
    EMAIL_PATTERN,
    URL_PATTERN,
    PHONE_PATTERN,
    DATE_PATTERN,
    DATETIME_PATTERN,
};

pub use result_types::{
    CompletionRound,
    CompletionResult,
};

pub use validation::{
    validate_value_for_type,
    validation_hint_for_type,
    get_suggestions_for_field,
    generate_session_id,
    sanitize_value,
    get_field_type_from_template,
};

pub use api_session::{
    completer_start_session,
    completer_ingest_documents,
    completer_get_questions,
};

pub use api_answers::{
    completer_submit_answer,
    completer_submit_answers,
    completer_validate_answer,
    completer_get_progress,
    completer_is_complete,
};

pub use api_finalize::{
    completer_finalize,
    completer_get_field_suggestions,
};

// ═══════════════════════════════════════════════════════════════
//  Unit Tests
// ═══════════════════════════════════════════════════════════════

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_completion_session_creation() {
        let session = CompletionSession::new(
            "test-session-001".to_string(),
            "telemedicine".to_string(),
            "Telemedicina".to_string(),
            "healthtech".to_string(),
            "critical".to_string(),
            45,
            30,
        );
        assert_eq!(session.session_id(), "test-session-001");
        assert_eq!(session.niche_id(), "telemedicine");
        assert_eq!(session.category(), "healthtech");
        assert_eq!(session.total_fields(), 45);
        assert_eq!(session.required_fields(), 30);
        assert_eq!(session.round_count(), 0);
        assert_eq!(session.status(), "initialized");
    }

    #[test]
    fn test_completion_session_tracking() {
        let mut session = CompletionSession::new(
            "test-session-002".to_string(),
            "ai_automation".to_string(),
            "Automatización IA".to_string(),
            "ai_data".to_string(),
            "high".to_string(),
            30,
            20,
        );
        session.add_documents(3);
        session.add_auto_filled(12);
        session.add_manual_filled(5);
        session.increment_round();
        session.set_status("in_progress");
        assert_eq!(session.documents_ingested(), 3);
        assert_eq!(session.fields_auto_filled(), 12);
        assert_eq!(session.fields_manual_filled(), 5);
        assert_eq!(session.round_count(), 1);
        assert_eq!(session.status(), "in_progress");
    }

    #[test]
    fn test_completion_question_creation() {
        let question = CompletionQuestion::new(
            "business_name".to_string(),
            "Business Name".to_string(),
            "text".to_string(),
            "business_identity".to_string(),
        );
        assert_eq!(question.field_name(), "business_name");
        assert_eq!(question.display_name(), "Business Name");
        assert_eq!(question.field_type(), "text");
        assert_eq!(question.section_id(), "business_identity");
        assert!(question.is_required);
    }

    #[test]
    fn test_validate_value_email() {
        let (valid, _) = validate_value_for_type("email", "user@example.com");
        assert!(valid);
        let (valid, _) = validate_value_for_type("email", "not-an-email");
        assert!(!valid);
        let (valid, _) = validate_value_for_type("email", "");
        assert!(!valid);
    }

    #[test]
    fn test_validate_value_url() {
        let (valid, _) = validate_value_for_type("url", "https://example.com");
        assert!(valid);
    }

    #[test]
    fn test_validate_value_number() {
        let (valid, _) = validate_value_for_type("number", "42");
        assert!(valid);
        let (valid, _) = validate_value_for_type("number", "3.14");
        assert!(valid);
        let (valid, _) = validate_value_for_type("number", "not-a-number");
        assert!(!valid);
    }

    #[test]
    fn test_validate_value_boolean() {
        let (valid, _) = validate_value_for_type("boolean", "true");
        assert!(valid);
        let (valid, _) = validate_value_for_type("boolean", "false");
        assert!(valid);
        let (valid, _) = validate_value_for_type("boolean", "yes");
        assert!(valid);
        let (valid, _) = validate_value_for_type("boolean", "maybe");
        assert!(!valid);
    }

    #[test]
    fn test_validate_value_percentage() {
        let (valid, _) = validate_value_for_type("percentage", "15");
        assert!(valid);
        let (valid, _) = validate_value_for_type("percentage", "15%");
        assert!(valid);
        let (valid, _) = validate_value_for_type("percentage", "not-a-pct");
        assert!(!valid);
    }

    #[test]
    fn test_validate_value_currency() {
        let (valid, _) = validate_value_for_type("currency", "1000.00");
        assert!(valid);
        let (valid, _) = validate_value_for_type("currency", "$1,000.00");
        assert!(valid);
    }

    #[test]
    fn test_validate_value_json() {
        let (valid, _) = validate_value_for_type("json", "{\"key\": \"value\"}");
        assert!(valid);
        let (valid, _) = validate_value_for_type("json", "[1, 2, 3]");
        assert!(valid);
        let (valid, _) = validate_value_for_type("json", "not json");
        assert!(!valid);
    }

    #[test]
    fn test_validate_value_date() {
        let (valid, _) = validate_value_for_type("date", "2025-01-15");
        assert!(valid);
    }

    #[test]
    fn test_validate_value_text() {
        let (valid, _) = validate_value_for_type("text", "Any text value");
        assert!(valid);
        let (valid, _) = validate_value_for_type("text", "");
        assert!(!valid);
    }

    #[test]
    fn test_validation_hint_for_type() {
        assert!(validation_hint_for_type("email").contains("email"));
        assert!(validation_hint_for_type("url").contains("URL"));
        assert!(validation_hint_for_type("boolean").contains("true"));
        assert!(validation_hint_for_type("number").contains("numeric"));
    }

    #[test]
    fn test_get_suggestions_for_field() {
        let suggestions = get_suggestions_for_field("auth_method", "enum");
        assert!(!suggestions.is_empty());
        assert!(suggestions.contains(&"oauth2".to_string()));

        let suggestions = get_suggestions_for_field("base_currency", "currency");
        assert!(!suggestions.is_empty());
        assert!(suggestions.contains(&"USD".to_string()));

        let suggestions = get_suggestions_for_field("unknown_field", "text");
        assert!(suggestions.is_empty());
    }

    #[test]
    fn test_sanitize_value() {
        assert_eq!(sanitize_value("  hello  "), "hello");
        assert_eq!(sanitize_value("normal text"), "normal text");
        // Test truncation
        let long_value = "a".repeat(MAX_ANSWER_LENGTH + 100);
        let sanitized = sanitize_value(&long_value);
        assert_eq!(sanitized.len(), MAX_ANSWER_LENGTH);
    }

    #[test]
    fn test_generate_session_id() {
        let id1 = generate_session_id();
        let id2 = generate_session_id();
        assert!(!id1.is_empty());
        assert!(!id2.is_empty());
        // IDs should be unique (at least different with high probability)
        assert_ne!(id1, id2);
    }

    #[test]
    fn test_completion_result_creation() {
        let result = CompletionResult {
            session_id: "test-session-003".to_string(),
            niche_id: "telemedicine".to_string(),
            status: "complete".to_string(),
            total_fields: 45,
            filled_fields: 45,
            missing_optional: 0,
            completion_pct: 100.0,
            total_rounds: 3,
            auto_filled: 20,
            manual_filled: 25,
            documents_used: 2,
            warnings: Vec::new(),
            errors: Vec::new(),
        };
        assert_eq!(result.session_id(), "test-session-003");
        assert_eq!(result.niche_id(), "telemedicine");
        assert!(result.is_complete());
        assert_eq!(result.auto_filled(), 20);
        assert_eq!(result.manual_filled(), 25);
    }

    #[test]
    fn test_completion_result_partial() {
        let result = CompletionResult {
            session_id: "test-session-004".to_string(),
            niche_id: "ai_automation".to_string(),
            status: "partial".to_string(),
            total_fields: 30,
            filled_fields: 25,
            missing_optional: 5,
            completion_pct: 83.3,
            total_rounds: 2,
            auto_filled: 15,
            manual_filled: 10,
            documents_used: 1,
            warnings: vec!["5 optional fields remain unfilled".to_string()],
            errors: Vec::new(),
        };
        assert!(!result.is_complete());
        assert_eq!(result.warnings().len(), 1);
    }

    #[test]
    fn test_completion_round() {
        let round = CompletionRound {
            round_number: 1,
            questions_asked: 10,
            answers_received: 8,
            answers_applied: 7,
            answers_rejected: 1,
            still_missing: 3,
            completion_pct: 75.0,
        };
        assert_eq!(round.round_number(), 1);
        assert_eq!(round.questions_asked(), 10);
        assert_eq!(round.answers_applied(), 7);
        assert_eq!(round.still_missing(), 3);
    }

    #[test]
    fn test_max_rounds_constant() {
        assert_eq!(MAX_ROUNDS, 20);
    }

    #[test]
    fn test_max_questions_per_round_constant() {
        assert_eq!(MAX_QUESTIONS_PER_ROUND, 10);
    }

    #[test]
    fn test_auto_accept_confidence_constant() {
        assert!((AUTO_ACCEPT_CONFIDENCE - 0.70).abs() < 0.001);
    }
}
