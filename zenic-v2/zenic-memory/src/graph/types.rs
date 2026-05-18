//! Audit entry type for the semantic graph.

/// A single entry from the learning_audit table.
#[derive(Debug, Clone)]
pub struct AuditEntry {
    /// The auto-incremented audit ID.
    pub audit_id: i64,
    /// The mapping ID this audit entry relates to.
    pub mapping_id: String,
    /// The action that was performed.
    pub action: String,
    /// Who performed the action.
    pub performed_by: String,
    /// When the action was performed (Unix epoch millis).
    pub timestamp: i64,
    /// Additional details (JSON or free-text).
    pub details: Option<String>,
}
