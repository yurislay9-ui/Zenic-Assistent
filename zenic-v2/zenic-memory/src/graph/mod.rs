//! Semantic Graph backed by SQLite.
//!
//! This is the Deterministic Knowledge Graph for Zenic-Agents.
//! It stores [`SemanticMapping`] records in a SQLite database with
//! per-tenant isolation, approval workflows, and audit logging.

mod types;
mod struct_and_schema;
mod queries;

pub use types::AuditEntry;
pub use struct_and_schema::SemanticGraph;
