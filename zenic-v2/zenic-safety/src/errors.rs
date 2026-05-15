//! Error types for zenic-safety crate.

use thiserror::Error;

/// Errors that can occur during safety validation.
#[derive(Debug, Error)]
pub enum SafetyError {
    /// Unknown niche category string.
    #[error("unknown niche category: {0}")]
    UnknownCategory(String),

    /// Unknown compliance standard string.
    #[error("unknown compliance standard: {0}")]
    UnknownComplianceStandard(String),

    /// Invalid sensitivity level string.
    #[error("invalid sensitivity level: {0}")]
    InvalidSensitivity(String),

    /// Domain rule compilation error.
    #[error("domain rule regex compilation failed for rule '{name}': {error}")]
    RuleCompilationFailed {
        name: String,
        error: String,
    },

    /// Safety validation failed.
    #[error("safety validation failed: {reason}")]
    ValidationFailed {
        reason: String,
    },

    /// Compliance check failed.
    #[error("compliance check failed for standard {standard}: {violations:?}")]
    ComplianceFailed {
        standard: String,
        violations: Vec<String>,
    },

    /// Base gate returned DENY — cannot override.
    #[error("base safety gate returned DENY — domain gate cannot override")]
    BaseDenyOverride,
}
