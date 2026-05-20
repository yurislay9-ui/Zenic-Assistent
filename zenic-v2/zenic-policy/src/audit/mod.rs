//! Audit trail for policy decisions.
//!
//! Every policy evaluation is recorded in an [`AuditLog`] entry.
//! The audit log provides a complete history of access decisions,
//! enabling compliance reporting and security analysis.

mod types;
#[cfg(test)]
mod tests;

// Re-export all public types.
pub use types::{PolicyDecision, DenialReason, AuditEntry, AuditLog};
