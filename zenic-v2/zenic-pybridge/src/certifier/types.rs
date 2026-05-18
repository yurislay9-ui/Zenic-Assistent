use pyo3::prelude::*;
use serde::{Deserialize, Serialize};

// ═══════════════════════════════════════════════════════════════
//  Constants
// ═══════════════════════════════════════════════════════════════

/// Current certification schema version.
pub const CERTIFICATION_SCHEMA_VERSION: &str = "1.0.0";

/// Maximum number of compliance standards per blueprint.
pub const MAX_COMPLIANCE_STANDARDS: usize = 20;

/// Maximum number of monitors per blueprint.
pub const MAX_MONITORS: usize = 50;

/// Maximum number of actions per blueprint.
pub const MAX_ACTIONS: usize = 100;

/// Maximum number of database schema tables.
pub const MAX_DB_TABLES: usize = 200;

/// Hash algorithm identifier for integrity.
pub const HASH_ALGORITHM: &str = "blake3";

// ═══════════════════════════════════════════════════════════════
//  CertificationStatus — certification state machine
// ═══════════════════════════════════════════════════════════════

/// Status of a blueprint in the certification pipeline.
///
/// ======== ============ ===================================
/// Variant  Python value Description
/// ======== ============ ===================================
/// Draft    ``"draft"``  Config created but not yet signed
/// Signed   ``"signed"`` ECDSA signature applied
/// Verified ``"verified"`` Signature verified successfully
/// Revoked  ``"revoked"`` Blueprint revoked (tamper/license)
/// Error    ``"error"``  Certification failed
/// ======== ============ ===================================
#[pyclass(name = "CertificationStatus", eq, eq_int, frozen, hash)]
#[derive(Clone, Debug, PartialEq, Eq, Hash, Copy, Serialize, Deserialize)]
pub enum CertificationStatus {
    Draft,
    Signed,
    Verified,
    Revoked,
    Error,
}

impl CertificationStatus {
    /// Return the Python-enum string value.
    pub fn as_str(&self) -> &'static str {
        match self {
            CertificationStatus::Draft => "draft",
            CertificationStatus::Signed => "signed",
            CertificationStatus::Verified => "verified",
            CertificationStatus::Revoked => "revoked",
            CertificationStatus::Error => "error",
        }
    }
}

#[pymethods]
impl CertificationStatus {
    fn __str__(&self) -> &'static str {
        self.as_str()
    }

    fn __repr__(&self) -> String {
        format!("CertificationStatus.{}", self.as_str().to_uppercase())
    }
}

// ═══════════════════════════════════════════════════════════════
//  AuditEntry — single entry in the certification audit chain
// ═══════════════════════════════════════════════════════════════

/// A single entry in the certification audit chain.
///
/// Each entry records a state transition in the certification
/// pipeline with a hash that chains to the previous entry.
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct AuditEntry {
    pub(super) step: String,
    pub(super) timestamp: String,
    pub(super) hash: String,
    pub(super) details: String,
}
