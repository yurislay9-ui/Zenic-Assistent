//! SemanticGraph struct definition, construction, and schema initialization.

use rusqlite::Connection;

use crate::errors::MemoryError;
use crate::types::SemanticMapping;

/// SQL to create the `semantic_mappings` table and its indices.
const SCHEMA_MAPPINGS: &str = r#"
CREATE TABLE IF NOT EXISTS semantic_mappings (
    mapping_id   TEXT PRIMARY KEY,
    origin       TEXT NOT NULL,
    relation     TEXT NOT NULL,
    destination  TEXT NOT NULL,
    mechanism    TEXT NOT NULL,
    confidence   INTEGER NOT NULL DEFAULT 0,
    tenant_id    TEXT NOT NULL DEFAULT '__anonymous__',
    created_at   INTEGER NOT NULL,
    approved     INTEGER NOT NULL DEFAULT 0,
    merkle_hash  TEXT
);
CREATE INDEX IF NOT EXISTS idx_origin_tenant ON semantic_mappings(origin, tenant_id);
CREATE INDEX IF NOT EXISTS idx_mechanism ON semantic_mappings(mechanism);
CREATE INDEX IF NOT EXISTS idx_approved ON semantic_mappings(approved);
"#;

/// SQL to create the `learning_audit` table.
const SCHEMA_AUDIT: &str = r#"
CREATE TABLE IF NOT EXISTS learning_audit (
    audit_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    mapping_id   TEXT NOT NULL,
    action       TEXT NOT NULL,
    performed_by TEXT NOT NULL,
    timestamp    INTEGER NOT NULL,
    details      TEXT
);
"#;

/// Deterministic Knowledge Graph backed by SQLite.
///
/// Stores [`SemanticMapping`] records with per-tenant isolation, approval
/// workflows, and a complete audit trail.
pub struct SemanticGraph {
    pub(crate) conn: Connection,
}

impl SemanticGraph {
    /// Creates or opens a SQLite database at the given path and initializes
    /// the schema.
    ///
    /// Pass `":memory:"` for an in-memory database (useful for testing).
    pub fn new(db_path: &str) -> Result<Self, MemoryError> {
        let conn = Connection::open(db_path).map_err(|e| MemoryError::Database(e.to_string()))?;

        // Enable WAL mode for better concurrent read performance.
        conn.execute_batch("PRAGMA journal_mode=WAL;")
            .map_err(|e| MemoryError::Database(e.to_string()))?;

        // Enable foreign keys.
        conn.execute_batch("PRAGMA foreign_keys=ON;")
            .map_err(|e| MemoryError::Database(e.to_string()))?;

        let mut graph = Self { conn };
        graph.init_schema()?;
        Ok(graph)
    }

    /// Initializes the database schema (idempotent).
    fn init_schema(&mut self) -> Result<(), MemoryError> {
        self.conn
            .execute_batch(SCHEMA_MAPPINGS)
            .map_err(|e| MemoryError::Database(e.to_string()))?;
        self.conn
            .execute_batch(SCHEMA_AUDIT)
            .map_err(|e| MemoryError::Database(e.to_string()))?;
        Ok(())
    }
}
