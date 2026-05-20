use pyo3::prelude::*;
use pyo3::types::PyDict;
use serde::{Deserialize, Serialize};

use super::blueprint::*;
use super::config::*;
use super::types::*;

// ═══════════════════════════════════════════════════════════════
//  CertificationResult — result of the certification process
// ═══════════════════════════════════════════════════════════════

/// Result of the certification process.
///
/// Contains the certified blueprint (if successful) along with
/// statistics and any warnings or errors from the process.
#[pyclass(name = "CertificationResult")]
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct CertificationResult {
    pub(super) success: bool,
    pub(super) blueprint: Option<CertifiedBlueprint>,
    pub(super) config: Option<BlueprintConfig>,
    pub(super) status: CertificationStatus,
    pub(super) content_hash: String,
    pub(super) elapsed_ms: u64,
    pub(super) warnings: Vec<String>,
    pub(super) errors: Vec<String>,
}

#[pymethods]
impl CertificationResult {
    #[getter]
    pub fn success(&self) -> bool {
        self.success
    }

    #[getter]
    fn blueprint(&self) -> Option<CertifiedBlueprint> {
        self.blueprint.clone()
    }

    #[getter]
    fn config(&self) -> Option<BlueprintConfig> {
        self.config.clone()
    }

    #[getter]
    fn status(&self) -> CertificationStatus {
        self.status
    }

    #[getter]
    fn content_hash(&self) -> &str {
        &self.content_hash
    }

    #[getter]
    fn elapsed_ms(&self) -> u64 {
        self.elapsed_ms
    }

    #[getter]
    fn warnings(&self) -> Vec<String> {
        self.warnings.clone()
    }

    #[getter]
    pub fn errors(&self) -> Vec<String> {
        self.errors.clone()
    }

    /// Get a summary dict.
    fn summary(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        let dict = PyDict::new_bound(py);
        dict.set_item("success", self.success)?;
        dict.set_item("status", self.status.as_str())?;
        dict.set_item("content_hash", &self.content_hash)?;
        dict.set_item("elapsed_ms", self.elapsed_ms)?;
        dict.set_item("warnings", self.warnings.len())?;
        dict.set_item("errors", self.errors.len())?;
        if let Some(ref bp) = self.blueprint {
            dict.set_item("blueprint_id", bp.blueprint_id())?;
        }
        Ok(dict.unbind())
    }

    fn __repr__(&self) -> String {
        format!(
            "CertificationResult(success={}, status={}, hash={:?})",
            self.success,
            self.status.as_str(),
            if self.content_hash.len() > 16 {
                &self.content_hash[..16]
            } else {
                &self.content_hash
            },
        )
    }
}
