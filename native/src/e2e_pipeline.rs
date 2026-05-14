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

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};
use serde::{Deserialize, Serialize};

use crate::catalog::catalog_get_by_id;
use crate::completer::{
    CompletionSession, CompletionQuestion, CompletionResult,
};
use crate::safety_gate_extended::{ComplianceCheckResult, DomainSafetyCheckResult};

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
    pipeline_id: String,
    niche_id: String,
    niche_name: String,
    niche_category: String,
    data_sensitivity: String,
    current_step: String,
    completion_session: Option<CompletionSession>,
    template_dict_json: String,
    documents_ingested: usize,
    fields_auto_filled: usize,
    fields_manual_filled: usize,
    total_fields: usize,
    required_fields: usize,
    safety_result_json: String,
    certification_result_json: String,
    errors: Vec<String>,
    warnings: Vec<String>,
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
    fn progress_pct(&self) -> f64 {
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
    fn summary(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
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

    fn __repr__(&self) -> String {
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
fn generate_pipeline_id(niche_id: &str) -> String {
    use std::time::{SystemTime, UNIX_EPOCH};
    let ts = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_millis())
        .unwrap_or(0);
    format!("e2e-{}-{:016x}", niche_id, ts)
}

// ═══════════════════════════════════════════════════════════════
//  PyO3 Functions — Public API
// ═══════════════════════════════════════════════════════════════

/// Start a new E2E pipeline by selecting a niche.
///
/// This is step 1 of the pipeline. It:
/// 1. Looks up the niche in the compiled catalog
/// 2. Generates a template skeleton
/// 3. Creates a CompletionSession
/// 4. Returns the pipeline state with template dict
///
/// Parameters
/// ----------
/// niche_id : str
///     The niche identifier from the catalog.
///
/// Returns
/// -------
/// tuple[E2EPipelineState, dict or None]
///     (pipeline_state, template_dict) if niche found,
///     (pipeline_state, None) if niche not found.
#[pyfunction]
pub fn e2e_start(
    niche_id: &str,
    py: Python<'_>,
) -> PyResult<(E2EPipelineState, Option<Py<PyDict>>)> {
    let niche_id_trimmed = niche_id.trim();
    if niche_id_trimmed.is_empty() {
        let mut state = E2EPipelineState::new(
            "error".to_string(),
            "unknown".to_string(),
            "Unknown".to_string(),
            "unknown".to_string(),
            "low".to_string(),
            0,
            0,
        );
        state.add_error("niche_id cannot be empty".to_string());
        state.set_step(E2EPipelineStep::Error);
        return Ok((state, None));
    }

    let niche = match catalog_get_by_id(niche_id_trimmed) {
        Some(n) => n,
        None => {
            let mut state = E2EPipelineState::new(
                generate_pipeline_id(niche_id_trimmed),
                niche_id_trimmed.to_string(),
                "Unknown".to_string(),
                "unknown".to_string(),
                "low".to_string(),
                0,
                0,
            );
            state.add_error(format!("Niche '{}' not found in catalog", niche_id_trimmed));
            state.set_step(E2EPipelineStep::Error);
            return Ok((state, None));
        }
    };

    let pipeline_id = generate_pipeline_id(niche_id_trimmed);
    let total_fields = niche.total_field_count();
    let required_fields = niche.required_field_count();

    let mut state = E2EPipelineState::new(
        pipeline_id,
        niche.niche_id().to_string(),
        niche.name().to_string(),
        niche.category().as_str().to_string(),
        niche.data_sensitivity().as_str().to_string(),
        total_fields,
        required_fields,
    );

    // Generate template using Phase A function
    let template_dict = crate::template::template_generate(niche_id_trimmed, py);

    // Start completion session using Phase C function
    let (session, _) = crate::completer::completer_start_session(niche_id_trimmed, py)?;
    state.completion_session = Some(session);

    state.set_step(E2EPipelineStep::UploadDocuments);

    Ok((state, template_dict))
}

/// Upload and ingest documents into the pipeline.
///
/// This is step 2 of the pipeline. It:
/// 1. Processes uploaded documents through the ingestion pipeline
/// 2. Extracts field values using the extractor
/// 3. Auto-fills template fields
///
/// Parameters
/// ----------
/// state : E2EPipelineState
///     Current pipeline state (will be updated).
/// template_dict : dict
///     The template dict (will be modified in-place).
/// extracted_texts : list[ExtractedText]
///     Pre-extracted text objects from document ingestion.
///
/// Returns
/// -------
/// E2EPipelineState
///     Updated pipeline state.
#[pyfunction]
pub fn e2e_upload_documents(
    mut state: E2EPipelineState,
    template_dict: &Bound<'_, PyDict>,
    extracted_texts: &Bound<'_, PyList>,
    py: Python<'_>,
) -> PyResult<E2EPipelineState> {
    if let Some(ref mut session) = state.completion_session {
        let (updated_session, auto_filled) = crate::completer::completer_ingest_documents(
            session.clone(), template_dict, extracted_texts, py,
        )?;
        *session = updated_session;
        state.documents_ingested = session.documents_ingested;
        state.fields_auto_filled = auto_filled;
    } else {
        state.add_error("No completion session — call e2e_start first".to_string());
    }

    state.set_step(E2EPipelineStep::GenerateQuestions);
    Ok(state)
}

/// Get questions for missing required fields.
///
/// This is step 3 of the pipeline. It generates structured
/// questions for all required fields that don't have values yet.
///
/// Parameters
/// ----------
/// state : E2EPipelineState
///     Current pipeline state.
/// template_dict : dict
///     The template dict.
///
/// Returns
/// -------
/// list[CompletionQuestion]
///     Structured questions for missing fields.
#[pyfunction]
pub fn e2e_get_questions(
    state: &E2EPipelineState,
    template_dict: &Bound<'_, PyDict>,
    py: Python<'_>,
) -> PyResult<Vec<CompletionQuestion>> {
    match &state.completion_session {
        Some(session) => {
            crate::completer::completer_get_questions(session, template_dict, py)
        }
        None => Ok(Vec::new()),
    }
}

/// Submit a single answer for a missing field.
///
/// This is step 4 of the pipeline (single answer variant).
///
/// Parameters
/// ----------
/// state : E2EPipelineState
///     Current pipeline state (will be updated).
/// template_dict : dict
///     The template dict (will be modified in-place).
/// field_name : str
///     The field name to fill.
/// section_id : str
///     The section ID containing the field.
/// value : str
///     The value to set.
///
/// Returns
/// -------
/// tuple[E2EPipelineState, bool]
///     (updated_state, was_applied).
#[pyfunction]
pub fn e2e_submit_answer(
    mut state: E2EPipelineState,
    template_dict: &Bound<'_, PyDict>,
    field_name: &str,
    section_id: &str,
    value: &str,
    py: Python<'_>,
) -> PyResult<(E2EPipelineState, bool)> {
    match &state.completion_session {
        Some(session) => {
            let (updated_session, _result_dict) = crate::completer::completer_submit_answer(
                session.clone(), template_dict, field_name, section_id, value, py,
            )?;
            let applied = true; // If no error, the answer was processed
            state.completion_session = Some(updated_session);
            if applied {
                state.fields_manual_filled += 1;
            }
            state.set_step(E2EPipelineStep::CollectAnswers);
            Ok((state, applied))
        }
        None => {
            state.add_error("No completion session".to_string());
            Ok((state, false))
        }
    }
}

/// Submit batch answers for missing fields.
///
/// This is step 4 of the pipeline (batch variant).
///
/// Parameters
/// ----------
/// state : E2EPipelineState
///     Current pipeline state (will be updated).
/// template_dict : dict
///     The template dict (will be modified in-place).
/// answers : dict[str, str]
///     Dict of field_name → value to set.
///
/// Returns
/// -------
/// tuple[E2EPipelineState, int]
///     (updated_state, count_applied).
#[pyfunction]
pub fn e2e_submit_answers(
    mut state: E2EPipelineState,
    template_dict: &Bound<'_, PyDict>,
    answers: &Bound<'_, PyDict>,
    py: Python<'_>,
) -> PyResult<(E2EPipelineState, usize)> {
    match &state.completion_session {
        Some(session) => {
            let (updated_session, count) = crate::completer::completer_submit_answers(
                session.clone(), template_dict, answers, py,
            )?;
            state.completion_session = Some(updated_session);
            state.fields_manual_filled += count;
            state.set_step(E2EPipelineStep::CollectAnswers);
            Ok((state, count))
        }
        None => {
            state.add_error("No completion session".to_string());
            Ok((state, 0))
        }
    }
}

/// Validate template completeness.
///
/// This is step 5 of the pipeline. It checks if all required
/// fields have been filled.
///
/// Parameters
/// ----------
/// state : E2EPipelineState
///     Current pipeline state.
/// template_dict : dict
///     The template dict.
///
/// Returns
/// -------
/// dict
///     Validation result with keys: valid, total_fields, filled_fields,
///     missing_required, completion_pct, status.
#[pyfunction]
pub fn e2e_validate(
    mut state: E2EPipelineState,
    template_dict: &Bound<'_, PyDict>,
    py: Python<'_>,
) -> PyResult<(E2EPipelineState, Py<PyDict>)> {
    let validation = crate::template::template_validate(template_dict, py)?;
    state.set_step(E2EPipelineStep::SafetyCheck);
    Ok((state, validation))
}

/// Run the domain safety + compliance check.
///
/// This is step 6 of the pipeline. It runs the extended safety
/// gate including domain-specific rules and compliance validation.
///
/// Parameters
/// ----------
/// state : E2EPipelineState
///     Current pipeline state.
/// action_type : str
///     The action type (e.g., "niche_onboarding").
/// config : dict
///     Configuration dict for the safety check.
///
/// Returns
/// -------
/// tuple[E2EPipelineState, DomainSafetyCheckResult]
///     (updated_state, safety_result).
#[pyfunction]
pub fn e2e_safety_check(
    mut state: E2EPipelineState,
    action_type: &str,
    config: &Bound<'_, PyDict>,
    py: Python<'_>,
) -> PyResult<(E2EPipelineState, DomainSafetyCheckResult)> {
    let safety_result = crate::safety_gate_extended::safety_validate_extended(
        action_type,
        config,
        &state.niche_category,
        &state.data_sensitivity,
        py,
    )?;

    if !safety_result.can_proceed {
        state.add_error(format!(
            "Safety check FAILED: final_verdict={}, reason={}",
            safety_result.final_verdict, safety_result.reason,
        ));
        state.set_step(E2EPipelineStep::Error);
    } else {
        state.set_step(E2EPipelineStep::CertifyBlueprint);
    }

    Ok((state, safety_result))
}

/// Certify the blueprint.
///
/// This is step 7 of the pipeline. It converts the completed
/// template into a CertifiedBlueprint with ECDSA signature.
///
/// Parameters
/// ----------
/// state : E2EPipelineState
///     Current pipeline state.
/// template_dict : dict
///     The completed template dict.
///
/// Returns
/// -------
/// tuple[E2EPipelineState, CertificationResult]
///     (updated_state, certification_result).
#[pyfunction]
pub fn e2e_certify(
    mut state: E2EPipelineState,
    template_dict: &Bound<'_, PyDict>,
    py: Python<'_>,
) -> PyResult<(E2EPipelineState, crate::certifier::CertificationResult)> {
    let cert_result = crate::certifier::certifier_from_template(template_dict, py)?;

    if cert_result.success {
        state.set_step(E2EPipelineStep::Export);
    } else {
        state.add_error("Certification failed".to_string());
        for err in cert_result.errors.clone() {
            state.add_error(err);
        }
        state.set_step(E2EPipelineStep::Error);
    }

    Ok((state, cert_result))
}

/// Export the final YAML output.
///
/// This is step 8 of the pipeline. It serializes the completed
/// template to YAML format.
///
/// Parameters
/// ----------
/// state : E2EPipelineState
///     Current pipeline state.
/// template_dict : dict
///     The completed template dict.
///
/// Returns
/// -------
/// tuple[E2EPipelineState, str]
///     (updated_state, yaml_string).
#[pyfunction]
pub fn e2e_export(
    mut state: E2EPipelineState,
    template_dict: &Bound<'_, PyDict>,
    py: Python<'_>,
) -> PyResult<(E2EPipelineState, String)> {
    let yaml_string = crate::template::template_to_yaml(template_dict, py)?;
    state.set_step(E2EPipelineStep::Complete);
    Ok((state, yaml_string))
}

/// Get pipeline progress information.
///
/// Parameters
/// ----------
/// state : E2EPipelineState
///     Current pipeline state.
///
/// Returns
/// -------
/// dict
///     Progress info with step, percentage, and field counts.
#[pyfunction]
pub fn e2e_get_progress(state: &E2EPipelineState, py: Python<'_>) -> PyResult<Py<PyDict>> {
    let dict = PyDict::new_bound(py);
    dict.set_item("pipeline_id", &state.pipeline_id)?;
    dict.set_item("niche_id", &state.niche_id)?;
    dict.set_item("current_step", &state.current_step)?;
    dict.set_item("progress_pct", state.progress_pct())?;
    dict.set_item("documents_ingested", state.documents_ingested)?;
    dict.set_item("fields_auto_filled", state.fields_auto_filled)?;
    dict.set_item("fields_manual_filled", state.fields_manual_filled)?;
    dict.set_item("total_fields", state.total_fields)?;
    dict.set_item("required_fields", state.required_fields)?;
    dict.set_item("error_count", state.errors.len())?;
    dict.set_item("warning_count", state.warnings.len())?;

    let filled = state.fields_auto_filled + state.fields_manual_filled;
    let completion_pct = if state.total_fields > 0 {
        (filled as f64 / state.total_fields as f64) * 100.0
    } else {
        0.0
    };
    dict.set_item("template_completion_pct", completion_pct)?;

    Ok(dict.unbind())
}

// ═══════════════════════════════════════════════════════════════
//  Unit Tests
// ═══════════════════════════════════════════════════════════════

#[cfg(test)]
mod tests {
    use super::*;

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
            "FinTech".to_string(),
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
}
