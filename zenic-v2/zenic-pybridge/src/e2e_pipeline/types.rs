//! E2E Pipeline types: step enum, state struct, result struct, and helpers.

use pyo3::prelude::*;
use pyo3::types::PyDict;
use serde::{Deserialize, Serialize};

// ═══════════════════════════════════════════════════════════════
//  E2EPipelineStep — pipeline step enum
// ═══════════════════════════════════════════════════════════════

/// Step in the E2E niche onboarding pipeline.
#[pyclass(name = "E2EPipelineStep", eq, eq_int, frozen, hash)]
#[derive(Clone, Debug, PartialEq, Eq, Hash, Copy, Serialize, Deserialize)]
pub enum E2EPipelineStep {
    NotStarted,
    SelectNiche,
    UploadDocuments,
    GenerateQuestions,
    CollectAnswers,
    ValidateTemplate,
    SafetyCheck,
    CertifyBlueprint,
    Export,
    Complete,
    Error,
}

impl E2EPipelineStep {
    /// Return the Python-enum string value.
    pub fn as_str(&self) -> &'static str {
        match self {
            E2EPipelineStep::NotStarted => "not_started",
            E2EPipelineStep::SelectNiche => "select_niche",
            E2EPipelineStep::UploadDocuments => "upload_documents",
            E2EPipelineStep::GenerateQuestions => "generate_questions",
            E2EPipelineStep::CollectAnswers => "collect_answers",
            E2EPipelineStep::ValidateTemplate => "validate_template",
            E2EPipelineStep::SafetyCheck => "safety_check",
            E2EPipelineStep::CertifyBlueprint => "certify_blueprint",
            E2EPipelineStep::Export => "export",
            E2EPipelineStep::Complete => "complete",
            E2EPipelineStep::Error => "error",
        }
    }

    /// All steps in order.
    pub fn ordered() -> &'static [E2EPipelineStep] {
        &[
            E2EPipelineStep::SelectNiche,
            E2EPipelineStep::UploadDocuments,
            E2EPipelineStep::GenerateQuestions,
            E2EPipelineStep::CollectAnswers,
            E2EPipelineStep::ValidateTemplate,
            E2EPipelineStep::SafetyCheck,
            E2EPipelineStep::CertifyBlueprint,
            E2EPipelineStep::Export,
        ]
    }

    /// Progress percentage for each step (0-100).
    pub fn progress_pct(&self) -> f64 {
        match self {
            E2EPipelineStep::NotStarted => 0.0,
            E2EPipelineStep::SelectNiche => 12.5,
            E2EPipelineStep::UploadDocuments => 25.0,
            E2EPipelineStep::GenerateQuestions => 37.5,
            E2EPipelineStep::CollectAnswers => 50.0,
            E2EPipelineStep::ValidateTemplate => 62.5,
            E2EPipelineStep::SafetyCheck => 75.0,
            E2EPipelineStep::CertifyBlueprint => 87.5,
            E2EPipelineStep::Export => 95.0,
            E2EPipelineStep::Complete => 100.0,
            E2EPipelineStep::Error => 0.0,
        }
    }
}

#[pymethods]
impl E2EPipelineStep {
    fn __str__(&self) -> &'static str {
        self.as_str()
    }

    fn __repr__(&self) -> String {
        format!("E2EPipelineStep.{}", self.as_str().to_uppercase())
    }
}

// ═══════════════════════════════════════════════════════════════
//  E2EPipelineState — current pipeline state
// ═══════════════════════════════════════════════════════════════

/// State of an E2E niche onboarding pipeline.
///
/// Tracks all data across the pipeline lifecycle:
/// - Which niche was selected
/// - What documents were uploaded
/// - Current completion session
/// - Template dict (mutable across steps)
/// - Safety check result
/// - Certification result
#[pyclass(name = "E2EPipelineState")]
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct E2EPipelineState {
    pub(super) pipeline_id: String,
    pub(super) niche_id: String,
    niche_name: String,
    pub(super) niche_category: String,
    pub(super) data_sensitivity: String,
    pub(super) current_step: String,
    pub(super) completion_session: Option<crate::completer::CompletionSession>,
    template_dict_json: String,
    pub(super) documents_ingested: usize,
    pub(super) fields_auto_filled: usize,
    pub(super) fields_manual_filled: usize,
    pub(super) total_fields: usize,
    pub(super) required_fields: usize,
    safety_result_json: String,
    certification_result_json: String,
    pub(super) errors: Vec<String>,
    pub(super) warnings: Vec<String>,
    created_at: String,
    updated_at: String,
}

impl E2EPipelineState {
    /// Create a new pipeline state.
    pub fn new(
        pipeline_id: String,
        niche_id: String,
        niche_name: String,
        niche_category: String,
        data_sensitivity: String,
        total_fields: usize,
        required_fields: usize,
    ) -> Self {
        let now = chrono::Utc::now().to_rfc3339();
        E2EPipelineState {
            pipeline_id,
            niche_id,
            niche_name,
            niche_category,
            data_sensitivity,
            current_step: E2EPipelineStep::SelectNiche.as_str().to_string(),
            completion_session: None,
            template_dict_json: String::new(),
            documents_ingested: 0,
            fields_auto_filled: 0,
            fields_manual_filled: 0,
            total_fields,
            required_fields,
            safety_result_json: String::new(),
            certification_result_json: String::new(),
            errors: Vec::new(),
            warnings: Vec::new(),
            created_at: now.clone(),
            updated_at: now,
        }
    }

    /// Update the timestamp.
    pub fn touch(&mut self) {
        self.updated_at = chrono::Utc::now().to_rfc3339();
    }

    /// Add an error.
    pub fn add_error(&mut self, msg: String) {
        self.errors.push(msg);
        self.touch();
    }

    /// Add a warning.
    pub fn add_warning(&mut self, msg: String) {
        self.warnings.push(msg);
        self.touch();
    }

    /// Set the current step.
    pub fn set_step(&mut self, step: E2EPipelineStep) {
        self.current_step = step.as_str().to_string();
        self.touch();
    }
}

#[pymethods]
impl E2EPipelineState {
    #[getter]
    fn pipeline_id(&self) -> &str {
        &self.pipeline_id
    }

    #[getter]
    fn niche_id(&self) -> &str {
        &self.niche_id
    }

    #[getter]
    fn niche_name(&self) -> &str {
        &self.niche_name
    }

    #[getter]
    fn niche_category(&self) -> &str {
        &self.niche_category
    }

    #[getter]
    fn data_sensitivity(&self) -> &str {
        &self.data_sensitivity
    }

    #[getter]
    fn current_step(&self) -> &str {
        &self.current_step
    }

    #[getter]
    fn documents_ingested(&self) -> usize {
        self.documents_ingested
    }

    #[getter]
    fn fields_auto_filled(&self) -> usize {
        self.fields_auto_filled
    }

    #[getter]
    fn fields_manual_filled(&self) -> usize {
        self.fields_manual_filled
    }

    #[getter]
    fn total_fields(&self) -> usize {
        self.total_fields
    }

    #[getter]
    fn required_fields(&self) -> usize {
        self.required_fields
    }

    #[getter]
    fn errors(&self) -> Vec<String> {
        self.errors.clone()
    }

    #[getter]
    fn warnings(&self) -> Vec<String> {
        self.warnings.clone()
    }

    #[getter]
    fn has_errors(&self) -> bool {
        !self.errors.is_empty()
    }

    #[getter]
    fn created_at(&self) -> &str {
        &self.created_at
    }

    #[getter]
    fn updated_at(&self) -> &str {
        &self.updated_at
    }

    /// Get pipeline progress percentage.
    pub fn progress_pct(&self) -> f64 {
        match self.current_step.as_str() {
            "not_started" => 0.0,
            "select_niche" => 12.5,
            "upload_documents" => 25.0,
            "generate_questions" => 37.5,
            "collect_answers" => 50.0,
            "validate_template" => 62.5,
            "safety_check" => 75.0,
            "certify_blueprint" => 87.5,
            "export" => 95.0,
            "complete" => 100.0,
            "error" => 0.0,
            _ => 0.0,
        }
    }

    /// Get a summary dict.
    pub fn summary(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        let dict = PyDict::new_bound(py);
        dict.set_item("pipeline_id", &self.pipeline_id)?;
        dict.set_item("niche_id", &self.niche_id)?;
        dict.set_item("niche_name", &self.niche_name)?;
        dict.set_item("current_step", &self.current_step)?;
        dict.set_item("progress_pct", self.progress_pct())?;
        dict.set_item("documents_ingested", self.documents_ingested)?;
        dict.set_item("fields_auto_filled", self.fields_auto_filled)?;
        dict.set_item("fields_manual_filled", self.fields_manual_filled)?;
        dict.set_item("total_fields", self.total_fields)?;
        dict.set_item("required_fields", self.required_fields)?;
        dict.set_item("error_count", self.errors.len())?;
        dict.set_item("warning_count", self.warnings.len())?;
        Ok(dict.unbind())
    }

    pub fn __repr__(&self) -> String {
        format!(
            "E2EPipelineState(id={:?}, niche={:?}, step={}, progress={:.1}%)",
            self.pipeline_id, self.niche_id, self.current_step, self.progress_pct(),
        )
    }
}

// ═══════════════════════════════════════════════════════════════
//  E2EPipelineResult — result of the full pipeline
// ═══════════════════════════════════════════════════════════════

/// Result of the complete E2E pipeline.
#[pyclass(name = "E2EPipelineResult")]
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct E2EPipelineResult {
    success: bool,
    pipeline_id: String,
    niche_id: String,
    final_step: String,
    progress_pct: f64,
    template_complete: bool,
    safety_passed: bool,
    blueprint_certified: bool,
    yaml_output: String,
    errors: Vec<String>,
    warnings: Vec<String>,
}

#[pymethods]
impl E2EPipelineResult {
    #[getter]
    fn success(&self) -> bool {
        self.success
    }

    #[getter]
    fn pipeline_id(&self) -> &str {
        &self.pipeline_id
    }

    #[getter]
    fn niche_id(&self) -> &str {
        &self.niche_id
    }

    #[getter]
    fn final_step(&self) -> &str {
        &self.final_step
    }

    #[getter]
    fn progress_pct(&self) -> f64 {
        self.progress_pct
    }

    #[getter]
    fn template_complete(&self) -> bool {
        self.template_complete
    }

    #[getter]
    fn safety_passed(&self) -> bool {
        self.safety_passed
    }

    #[getter]
    fn blueprint_certified(&self) -> bool {
        self.blueprint_certified
    }

    #[getter]
    fn yaml_output(&self) -> &str {
        &self.yaml_output
    }

    #[getter]
    fn errors(&self) -> Vec<String> {
        self.errors.clone()
    }

    #[getter]
    fn warnings(&self) -> Vec<String> {
        self.warnings.clone()
    }

    fn __repr__(&self) -> String {
        format!(
            "E2EPipelineResult(success={}, niche={:?}, step={}, safety={}, certified={})",
            self.success, self.niche_id, self.final_step, self.safety_passed, self.blueprint_certified,
        )
    }
}

// ═══════════════════════════════════════════════════════════════
//  Internal Helpers
// ═══════════════════════════════════════════════════════════════

/// Generate a pipeline ID.
pub(super) fn generate_pipeline_id(niche_id: &str) -> String {
    use std::time::{SystemTime, UNIX_EPOCH};
    let ts = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_millis())
        .unwrap_or(0);
    format!("e2e-{}-{:016x}", niche_id, ts)
}
