//! E2E Pipeline — Complete end-to-end niche onboarding pipeline for Zenic-Agents (Phase D).
//!
//! Ties together all Phase 6 components into a single deterministic pipeline:
//!
//! 1. SELECT_NICHE → catalog lookup + template generation (Phase A)
//! 2. UPLOAD_DOCUMENTS → document ingestion + extraction (Phase B)
//! 3. GENERATE_QUESTIONS → identify missing required fields (Phase C)
//! 4. COLLECT_ANSWERS → interactive Q&A with validation (Phase C)
//! 5. VALIDATE_TEMPLATE → completeness check (Phase A)
//! 6. SAFETY_CHECK → domain safety + compliance gate (Phase D)
//! 7. CERTIFY_BLUEPRINT → ECDSA signature + certified blueprint (Phase D)
//! 8. EXPORT → final YAML + metadata export
//!
//! # Design Decisions
//!
//! - All steps reuse existing functions from completer, certifier, safety_gate_extended
//! - Pipeline state is tracked via E2EPipelineState
//! - No `unwrap` or `panic` — all errors handled explicitly
//! - Safety check runs BEFORE certification (safety veto)
//! - Pipeline is resumable: each step can be called independently
//!
//! # PyO3 Exposed Types
//!
//! - `E2EPipelineStep` — enum of pipeline steps
//! - `E2EPipelineState` — current pipeline state
//! - `E2EPipelineResult` — result of the full pipeline
//!
//! # PyO3 Exposed Functions
//!
//! - `e2e_start(niche_id)` — start a new pipeline
//! - `e2e_upload_documents(state, documents)` — ingest documents
//! - `e2e_get_questions(state)` — get questions for missing fields
//! - `e2e_submit_answer(state, field_name, value)` — submit one answer
//! - `e2e_submit_answers(state, answers)` — batch submit answers
//! - `e2e_validate(state)` — validate template completeness
//! - `e2e_safety_check(state)` — domain safety + compliance check
//! - `e2e_certify(state)` — certify the blueprint
//! - `e2e_export(state)` — export final YAML
//! - `e2e_get_progress(state)` — get pipeline progress

pub mod stages;
pub mod types;
pub mod validation;

// ── Re-export all public types ──────────────────────────────────
pub use types::{E2EPipelineResult, E2EPipelineState, E2EPipelineStep};

// ── Re-export all public PyO3 functions ─────────────────────────
pub use stages::{
    e2e_get_questions, e2e_start, e2e_submit_answer, e2e_submit_answers, e2e_upload_documents,
};
pub use validation::{e2e_certify, e2e_export, e2e_get_progress, e2e_safety_check, e2e_validate};

// ═══════════════════════════════════════════════════════════════
//  Unit Tests
// ═══════════════════════════════════════════════════════════════

#[cfg(test)]
mod tests {
    use super::*;
    use types::generate_pipeline_id;

    #[test]
    fn test_e2e_pipeline_step_str_roundtrip() {
        assert_eq!(E2EPipelineStep::SelectNiche.as_str(), "select_niche");
        assert_eq!(E2EPipelineStep::UploadDocuments.as_str(), "upload_documents");
        assert_eq!(E2EPipelineStep::SafetyCheck.as_str(), "safety_check");
        assert_eq!(E2EPipelineStep::CertifyBlueprint.as_str(), "certify_blueprint");
        assert_eq!(E2EPipelineStep::Complete.as_str(), "complete");
    }

    #[test]
    fn test_e2e_pipeline_step_ordered_count() {
        assert_eq!(E2EPipelineStep::ordered().len(), 8);
    }

    #[test]
    fn test_e2e_pipeline_step_progress() {
        assert_eq!(E2EPipelineStep::NotStarted.progress_pct(), 0.0);
        assert_eq!(E2EPipelineStep::SelectNiche.progress_pct(), 12.5);
        assert_eq!(E2EPipelineStep::Complete.progress_pct(), 100.0);
    }

    #[test]
    fn test_e2e_pipeline_state_creation() {
        let state = E2EPipelineState::new(
            "e2e-test-001".to_string(),
            "fintech".to_string(),
            "Tecnología Financiera".to_string(),
            "fintech".to_string(),
            "high".to_string(),
            45,
            30,
        );
        assert_eq!(state.pipeline_id(), "e2e-test-001");
        assert_eq!(state.niche_id(), "fintech");
        assert_eq!(state.total_fields(), 45);
        assert_eq!(state.required_fields(), 30);
        assert_eq!(state.current_step(), "select_niche");
    }

    #[test]
    fn test_e2e_pipeline_state_progress() {
        let state = E2EPipelineState::new(
            "test".to_string(),
            "test".to_string(),
            "Test".to_string(),
            "ai_data".to_string(),
            "medium".to_string(),
            10,
            5,
        );
        assert_eq!(state.progress_pct(), 12.5);
    }

    #[test]
    fn test_generate_pipeline_id() {
        let id = generate_pipeline_id("fintech");
        assert!(id.starts_with("e2e-fintech-"));
    }
}
