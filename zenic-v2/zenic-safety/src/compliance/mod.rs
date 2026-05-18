//! Compliance validation engine — regulatory standards checker.
//!
//! Supports 8 compliance standards:
//!   HIPAA, PCI-DSS, GDPR, SOX, AML/KYC, COPPA, ISO 27001, SOC 2
//!
//! Sub-modules:
//! - [`types`] — ComplianceStandard and ComplianceResult types
//! - [`checker`] — ComplianceEngine with all standard check implementations
//! - [`reporter`] — Report formatting and integration tests

pub mod checker;
pub mod reporter;
pub mod types;

// Convenience re-exports — preserves the original public API surface.
pub use checker::ComplianceEngine;
pub use reporter::format_compliance_report;
pub use types::{ComplianceResult, ComplianceStandard};
