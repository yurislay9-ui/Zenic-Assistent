//! E2E Pipeline — Unit Tests

use super::types::*;
use super::operations::generate_pipeline_id;

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
    assert_eq!(state.total_fields, 45);
    assert_eq!(state.required_fields, 30);
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
