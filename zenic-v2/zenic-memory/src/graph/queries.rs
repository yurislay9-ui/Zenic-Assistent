//! SemanticGraph query and mutation methods.

use rusqlite::{params, OptionalExtension};
use std::time::{SystemTime, UNIX_EPOCH};

use crate::errors::MemoryError;
use crate::types::{LearningMechanism, SemanticMapping};

use super::struct_and_schema::SemanticGraph;
use super::types::AuditEntry;

impl SemanticGraph {
    /// Inserts a new semantic mapping into the graph.
    ///
    /// Returns [`MemoryError::Duplicate`] if a mapping with the same
    /// `mapping_id` already exists.
    pub fn insert_mapping(&self, mapping: &SemanticMapping) -> Result<(), MemoryError> {
        let approved_int = if mapping.approved { 1 } else { 0 };
        let merkle = mapping.merkle_hash.as_deref().unwrap_or("");

        self.conn
            .execute(
                "INSERT INTO semantic_mappings
                    (mapping_id, origin, relation, destination, mechanism,
                     confidence, tenant_id, created_at, approved, merkle_hash)
                 VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10)",
                params![
                    mapping.mapping_id,
                    mapping.origin,
                    mapping.relation,
                    mapping.destination,
                    mapping.mechanism.as_str(),
                    mapping.confidence,
                    mapping.tenant_id,
                    mapping.created_at,
                    approved_int,
                    merkle,
                ],
            )
            .map_err(|e| {
                if e.to_string().contains("UNIQUE constraint") {
                    MemoryError::Duplicate(mapping.mapping_id.clone())
                } else {
                    MemoryError::Database(e.to_string())
                }
            })?;

        Ok(())
    }

    /// Looks up a mapping by its origin key and tenant ID.
    pub fn lookup(
        &self,
        origin: &str,
        tenant_id: &str,
    ) -> Result<Option<SemanticMapping>, MemoryError> {
        let mut stmt = self
            .conn
            .prepare(
                "SELECT mapping_id, origin, relation, destination, mechanism,
                        confidence, tenant_id, created_at, approved, merkle_hash
                 FROM semantic_mappings
                 WHERE origin = ?1 AND tenant_id = ?2
                 LIMIT 1",
            )
            .map_err(|e| MemoryError::Database(e.to_string()))?;

        let result = stmt
            .query_row(params![origin, tenant_id], |row| Ok(row_to_mapping(row)))
            .optional()
            .map_err(|e| MemoryError::Database(e.to_string()))?;

        Ok(result)
    }

    /// Finds all mappings for a given learning mechanism and tenant.
    pub fn lookup_by_mechanism(
        &self,
        mechanism: LearningMechanism,
        tenant_id: &str,
    ) -> Result<Vec<SemanticMapping>, MemoryError> {
        let mut stmt = self
            .conn
            .prepare(
                "SELECT mapping_id, origin, relation, destination, mechanism,
                        confidence, tenant_id, created_at, approved, merkle_hash
                 FROM semantic_mappings
                 WHERE mechanism = ?1 AND tenant_id = ?2",
            )
            .map_err(|e| MemoryError::Database(e.to_string()))?;

        let mappings = stmt
            .query_map(params![mechanism.as_str(), tenant_id], |row| {
                Ok(row_to_mapping(row))
            })
            .map_err(|e| MemoryError::Database(e.to_string()))?
            .collect::<Result<Vec<_>, _>>()
            .map_err(|e| MemoryError::Database(e.to_string()))?;

        Ok(mappings)
    }

    /// Marks a mapping as approved and sets its Merkle hash.
    pub fn approve_mapping(
        &self,
        mapping_id: &str,
        merkle_hash: &str,
    ) -> Result<(), MemoryError> {
        let rows_affected = self
            .conn
            .execute(
                "UPDATE semantic_mappings
                 SET approved = 1, merkle_hash = ?1
                 WHERE mapping_id = ?2",
                params![merkle_hash, mapping_id],
            )
            .map_err(|e| MemoryError::Database(e.to_string()))?;

        if rows_affected == 0 {
            return Err(MemoryError::NotFound(mapping_id.to_string()));
        }

        Ok(())
    }

    /// Removes a mapping from the graph.
    pub fn delete_mapping(&self, mapping_id: &str) -> Result<(), MemoryError> {
        let rows_affected = self
            .conn
            .execute(
                "DELETE FROM semantic_mappings WHERE mapping_id = ?1",
                params![mapping_id],
            )
            .map_err(|e| MemoryError::Database(e.to_string()))?;

        if rows_affected == 0 {
            return Err(MemoryError::NotFound(mapping_id.to_string()));
        }

        Ok(())
    }

    /// Counts the number of mappings for a given tenant.
    pub fn count_mappings(&self, tenant_id: &str) -> Result<u32, MemoryError> {
        let count: i64 = self
            .conn
            .query_row(
                "SELECT COUNT(*) FROM semantic_mappings WHERE tenant_id = ?1",
                params![tenant_id],
                |row| row.get(0),
            )
            .map_err(|e| MemoryError::Database(e.to_string()))?;

        Ok(count as u32)
    }

    /// Writes an audit entry for a mapping mutation.
    pub fn audit_log(
        &self,
        mapping_id: &str,
        action: &str,
        performed_by: &str,
        details: &str,
    ) -> Result<(), MemoryError> {
        let timestamp = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_millis() as i64;

        self.conn
            .execute(
                "INSERT INTO learning_audit
                    (mapping_id, action, performed_by, timestamp, details)
                 VALUES (?1, ?2, ?3, ?4, ?5)",
                params![mapping_id, action, performed_by, timestamp, details],
            )
            .map_err(|e| MemoryError::Database(e.to_string()))?;

        Ok(())
    }

    /// Lists all mappings in the graph.
    pub fn list_all_mappings(&self) -> Result<Vec<SemanticMapping>, MemoryError> {
        let mut stmt = self
            .conn
            .prepare(
                "SELECT mapping_id, origin, relation, destination, mechanism,
                        confidence, tenant_id, created_at, approved, merkle_hash
                 FROM semantic_mappings",
            )
            .map_err(|e| MemoryError::Database(e.to_string()))?;

        let mappings = stmt
            .query_map([], |row| Ok(row_to_mapping(row)))
            .map_err(|e| MemoryError::Database(e.to_string()))?
            .collect::<Result<Vec<_>, _>>()
            .map_err(|e| MemoryError::Database(e.to_string()))?;

        Ok(mappings)
    }

    /// Queries the audit log for entries matching a mapping_id and action.
    pub fn query_audit_log(
        &self,
        mapping_id: &str,
        action: &str,
    ) -> Result<Vec<AuditEntry>, MemoryError> {
        let mut stmt = self
            .conn
            .prepare(
                "SELECT audit_id, mapping_id, action, performed_by, timestamp, details
                 FROM learning_audit
                 WHERE mapping_id = ?1 AND action = ?2
                 ORDER BY timestamp DESC",
            )
            .map_err(|e| MemoryError::Database(e.to_string()))?;

        let entries = stmt
            .query_map(params![mapping_id, action], |row| {
                Ok(AuditEntry {
                    audit_id: row.get(0)?,
                    mapping_id: row.get(1)?,
                    action: row.get(2)?,
                    performed_by: row.get(3)?,
                    timestamp: row.get(4)?,
                    details: row.get(5)?,
                })
            })
            .map_err(|e| MemoryError::Database(e.to_string()))?
            .collect::<Result<Vec<_>, _>>()
            .map_err(|e| MemoryError::Database(e.to_string()))?;

        Ok(entries)
    }
}

/// Converts a database row into a [`SemanticMapping`].
fn row_to_mapping(row: &rusqlite::Row<'_>) -> SemanticMapping {
    let mapping_id: String = row.get_unwrap(0);
    let origin: String = row.get_unwrap(1);
    let relation: String = row.get_unwrap(2);
    let destination: String = row.get_unwrap(3);
    let mechanism_str: String = row.get_unwrap(4);
    let confidence: i32 = row.get_unwrap(5);
    let tenant_id: String = row.get_unwrap(6);
    let created_at: i64 = row.get_unwrap(7);
    let approved_int: i32 = row.get_unwrap(8);
    let merkle_hash: Option<String> = row.get_unwrap(9);

    SemanticMapping {
        mapping_id,
        origin,
        relation,
        destination,
        mechanism: LearningMechanism::from_str_lossy(&mechanism_str),
        confidence: confidence as u8,
        tenant_id,
        created_at,
        approved: approved_int != 0,
        merkle_hash,
    }
}
