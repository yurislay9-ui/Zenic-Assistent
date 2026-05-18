//! Forensic hash generation functions.

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

/// Generate a BLAKE3 forensic hash from an audit entry's fields.
///
/// Concatenates all field values in a deterministic order and computes
/// the BLAKE3 hash. This is used to create tamper-evident audit entries.
///
/// Parameters
/// ----------
/// entry_id : str
/// tenant_id : str
/// event_type : str
/// description : str
/// actor : str
/// timestamp : str (ISO 8601)
/// metadata_json : str (JSON-serialized metadata)
///
/// Returns
/// -------
/// str
///     64-character hex-encoded BLAKE3 forensic hash.
#[pyfunction]
#[pyo3(signature = (entry_id, tenant_id, event_type, description, actor, timestamp, metadata_json))]
pub fn forensic_hash(
    entry_id: &str,
    tenant_id: &str,
    event_type: &str,
    description: &str,
    actor: &str,
    timestamp: &str,
    metadata_json: &str,
) -> PyResult<String> {
    if entry_id.is_empty() {
        return Err(PyValueError::new_err("entry_id must not be empty"));
    }
    if tenant_id.is_empty() {
        return Err(PyValueError::new_err("tenant_id must not be empty"));
    }
    // Deterministic concatenation order
    let mut payload = String::with_capacity(
        entry_id.len() + tenant_id.len() + event_type.len()
            + description.len() + actor.len() + timestamp.len()
            + metadata_json.len() + 7, // separators
    );
    payload.push_str(entry_id);
    payload.push('|');
    payload.push_str(tenant_id);
    payload.push('|');
    payload.push_str(event_type);
    payload.push('|');
    payload.push_str(description);
    payload.push('|');
    payload.push_str(actor);
    payload.push('|');
    payload.push_str(timestamp);
    payload.push('|');
    payload.push_str(metadata_json);

    let hash = blake3::hash(payload.as_bytes());
    Ok(hash.to_hex().to_string())
}

/// Generate a chain hash that links an entry to its parent.
///
/// The chain hash is computed as: BLAKE3(parent_hash || entry_hash).
/// This ensures each entry is cryptographically bound to its predecessor.
///
/// Parameters
/// ----------
/// parent_hash : str
///     The hash of the previous entry in the chain.
/// entry_hash : str
///     The forensic hash of the current entry.
///
/// Returns
/// -------
/// str
///     64-character hex-encoded BLAKE3 chain hash.
#[pyfunction]
#[pyo3(signature = (parent_hash, entry_hash))]
pub fn chain_hash(parent_hash: &str, entry_hash: &str) -> PyResult<String> {
    if parent_hash.is_empty() && entry_hash.is_empty() {
        return Err(PyValueError::new_err(
            "at least one of parent_hash or entry_hash must be non-empty",
        ));
    }
    let mut combined = Vec::with_capacity(parent_hash.len() + entry_hash.len());
    combined.extend_from_slice(parent_hash.as_bytes());
    combined.extend_from_slice(entry_hash.as_bytes());
    let hash = blake3::hash(&combined);
    Ok(hash.to_hex().to_string())
}
