use pyo3::prelude::*;
use pyo3::types::PyDict;
use serde::{Deserialize, Serialize};

use super::config::*;
use super::types::*;

// ═══════════════════════════════════════════════════════════════
//  CertifiedBlueprint — signed, validated blueprint
// ═══════════════════════════════════════════════════════════════

/// A certified blueprint with ECDSA signature and integrity hash.
///
/// This is the final product of the certification pipeline. It
/// contains the BlueprintConfig along with:
/// - Canonical SHA-256 hash for integrity verification
/// - ECDSA signature for authenticity verification
/// - Certification timestamp and metadata
/// - Audit trail hash chain
#[pyclass(name = "CertifiedBlueprint")]
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct CertifiedBlueprint {
    pub(super) blueprint_id: String,
    pub(super) config: BlueprintConfig,
    pub(super) status: CertificationStatus,
    pub(super) content_hash: String,
    pub(super) signature: String,
    pub(super) signature_algorithm: String,
    pub(super) certified_at: String,
    pub(super) schema_version: String,
    pub(super) audit_chain: Vec<AuditEntry>,
    pub(super) warnings: Vec<String>,
    pub(super) errors: Vec<String>,
}

#[pymethods]
impl CertifiedBlueprint {
    #[getter]
    pub fn blueprint_id(&self) -> &str {
        &self.blueprint_id
    }

    #[getter]
    fn config(&self) -> &BlueprintConfig {
        &self.config
    }

    #[getter]
    fn status(&self) -> CertificationStatus {
        self.status
    }

    #[getter]
    pub fn content_hash(&self) -> &str {
        &self.content_hash
    }

    #[getter]
    pub fn signature(&self) -> &str {
        &self.signature
    }

    #[getter]
    pub fn signature_algorithm(&self) -> &str {
        &self.signature_algorithm
    }

    #[getter]
    pub fn certified_at(&self) -> &str {
        &self.certified_at
    }

    #[getter]
    pub fn schema_version(&self) -> &str {
        &self.schema_version
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
    fn has_errors(&self) -> bool {
        !self.errors.is_empty()
    }

    /// Check if this blueprint is verified (signature validated).
    pub fn is_verified(&self) -> bool {
        self.status == CertificationStatus::Verified
    }

    /// Check if this blueprint is signed (has signature).
    pub fn is_signed(&self) -> bool {
        self.status == CertificationStatus::Signed
            || self.status == CertificationStatus::Verified
    }

    /// Get the audit chain length.
    fn audit_chain_length(&self) -> usize {
        self.audit_chain.len()
    }

    /// Get a summary dict.
    fn summary(&self, py: Python<'_>) -> PyResult<Py<PyDict>> {
        let dict = PyDict::new_bound(py);
        dict.set_item("blueprint_id", &self.blueprint_id)?;
        dict.set_item("niche_id", self.config.niche_id())?;
        dict.set_item("business_name", self.config.business_name())?;
        dict.set_item("status", self.status.as_str())?;
        dict.set_item("content_hash", &self.content_hash)?;
        dict.set_item("is_signed", self.is_signed())?;
        dict.set_item("is_verified", self.is_verified())?;
        dict.set_item("certified_at", &self.certified_at)?;
        dict.set_item("schema_version", &self.schema_version)?;
        dict.set_item("audit_entries", self.audit_chain.len())?;
        dict.set_item("warnings", self.warnings.len())?;
        dict.set_item("errors", self.errors.len())?;
        Ok(dict.unbind())
    }

    fn __repr__(&self) -> String {
        format!(
            "CertifiedBlueprint(id={:?}, niche={:?}, status={}, signed={})",
            self.blueprint_id,
            self.config.niche_id(),
            self.status.as_str(),
            self.is_signed(),
        )
    }
}
