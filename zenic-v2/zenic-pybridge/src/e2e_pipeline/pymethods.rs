//! E2E Pipeline — PyO3 method implementations.

use pyo3::prelude::*;
use pyo3::types::PyDict;

use super::types::{E2EPipelineResult, E2EPipelineState, E2EPipelineStep};

// ═══════════════════════════════════════════════════════════════
//  E2EPipelineStep — PyO3 methods
// ═══════════════════════════════════════════════════════════════

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
//  E2EPipelineState — PyO3 methods
// ═══════════════════════════════════════════════════════════════

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
//  E2EPipelineResult — PyO3 methods
// ═══════════════════════════════════════════════════════════════

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
