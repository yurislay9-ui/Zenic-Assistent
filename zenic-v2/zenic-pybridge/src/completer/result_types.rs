//! Result types for the Template Completion Agent.

use pyo3::prelude::*;
use pyo3::types::PyDict;
use serde::{Deserialize, Serialize};

// ═══════════════════════════════════════════════════════════════
//  CompletionRound — one round of questions and answers
// ═══════════════════════════════════════════════════════════════

/// One round of interactive Q&A in the completion process.
///
/// Tracks which questions were asked, which answers were
/// provided, and the result of applying each answer.
#[pyclass(name = "CompletionRound")]
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct CompletionRound {
    pub(crate) round_number: usize,
    pub(crate) questions_asked: usize,
    pub(crate) answers_received: usize,
    pub(crate) answers_applied: usize,
    pub(crate) answers_rejected: usize,
    pub(crate) still_missing: usize,
    pub(crate) completion_pct: f64,
}

#[pymethods]
impl CompletionRound {
    #[getter]
    fn round_number(&self) -> usize {
        self.round_number
    }

    #[getter]
    fn questions_asked(&self) -> usize {
        self.questions_asked
    }

    #[getter]
    fn answers_received(&self) -> usize {
        self.answers_received
    }

    #[getter]
    fn answers_applied(&self) -> usize {
        self.answers_applied
    }

    #[getter]
    fn answers_rejected(&self) -> usize {
        self.answers_rejected
    }

    #[getter]
    fn still_missing(&self) -> usize {
        self.still_missing
    }

    #[getter]
    fn completion_pct(&self) -> f64 {
        self.completion_pct
    }

    /// Get a summary dict.
    fn summary(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        let dict = PyDict::new_bound(py);
        dict.set_item("round_number", self.round_number)?;
        dict.set_item("questions_asked", self.questions_asked)?;
        dict.set_item("answers_received", self.answers_received)?;
        dict.set_item("answers_applied", self.answers_applied)?;
        dict.set_item("answers_rejected", self.answers_rejected)?;
        dict.set_item("still_missing", self.still_missing)?;
        dict.set_item("completion_pct", self.completion_pct)?;
        Ok(dict.unbind())
    }

    fn __repr__(&self) -> String {
        format!(
            "CompletionRound(round={}, asked={}, applied={}, rejected={}, missing={}, pct={:.1}%)",
            self.round_number,
            self.questions_asked,
            self.answers_applied,
            self.answers_rejected,
            self.still_missing,
            self.completion_pct,
        )
    }
}

// ═══════════════════════════════════════════════════════════════
//  CompletionResult — final result of the completion process
// ═══════════════════════════════════════════════════════════════

/// Final result of the template completion process.
///
/// Contains the completed template, statistics, and any
/// warnings or errors from the entire process.
#[pyclass(name = "CompletionResult")]
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct CompletionResult {
    pub(crate) session_id: String,
    pub(crate) niche_id: String,
    pub(crate) status: String,
    pub(crate) total_fields: usize,
    pub(crate) filled_fields: usize,
    pub(crate) missing_optional: usize,
    pub(crate) completion_pct: f64,
    pub(crate) total_rounds: usize,
    pub(crate) auto_filled: usize,
    pub(crate) manual_filled: usize,
    pub(crate) documents_used: usize,
    pub(crate) warnings: Vec<String>,
    pub(crate) errors: Vec<String>,
}

#[pymethods]
impl CompletionResult {
    #[getter]
    fn session_id(&self) -> &str {
        &self.session_id
    }

    #[getter]
    fn niche_id(&self) -> &str {
        &self.niche_id
    }

    #[getter]
    fn status(&self) -> &str {
        &self.status
    }

    #[getter]
    fn total_fields(&self) -> usize {
        self.total_fields
    }

    #[getter]
    fn filled_fields(&self) -> usize {
        self.filled_fields
    }

    #[getter]
    fn missing_optional(&self) -> usize {
        self.missing_optional
    }

    #[getter]
    fn completion_pct(&self) -> f64 {
        self.completion_pct
    }

    #[getter]
    fn total_rounds(&self) -> usize {
        self.total_rounds
    }

    #[getter]
    fn auto_filled(&self) -> usize {
        self.auto_filled
    }

    #[getter]
    fn manual_filled(&self) -> usize {
        self.manual_filled
    }

    #[getter]
    fn documents_used(&self) -> usize {
        self.documents_used
    }

    #[getter]
    fn warnings(&self) -> Vec<String> {
        self.warnings.clone()
    }

    #[getter]
    fn errors(&self) -> Vec<String> {
        self.errors.clone()
    }

    #[getter]
    fn is_complete(&self) -> bool {
        self.status == "complete"
    }

    /// Get a summary dict.
    fn summary(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        let dict = PyDict::new_bound(py);
        dict.set_item("session_id", &self.session_id)?;
        dict.set_item("niche_id", &self.niche_id)?;
        dict.set_item("status", &self.status)?;
        dict.set_item("total_fields", self.total_fields)?;
        dict.set_item("filled_fields", self.filled_fields)?;
        dict.set_item("missing_optional", self.missing_optional)?;
        dict.set_item("completion_pct", self.completion_pct)?;
        dict.set_item("total_rounds", self.total_rounds)?;
        dict.set_item("auto_filled", self.auto_filled)?;
        dict.set_item("manual_filled", self.manual_filled)?;
        dict.set_item("documents_used", self.documents_used)?;
        dict.set_item("is_complete", self.is_complete())?;
        dict.set_item("warning_count", self.warnings.len())?;
        dict.set_item("error_count", self.errors.len())?;
        Ok(dict.unbind())
    }

    fn __repr__(&self) -> String {
        format!(
            "CompletionResult(session={:?}, niche={:?}, status={}, pct={:.1}%)",
            self.session_id, self.niche_id, self.status, self.completion_pct,
        )
    }
}
