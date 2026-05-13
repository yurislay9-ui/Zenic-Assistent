//! Forensic Audit Engine — Merkle chain verification, hash generation,
//! and integrity validation for Zenic-Agents.
//!
//! This module implements the core security layer (A1) in Rust for:
//! - BLAKE3 hash generation for audit entries
//! - Merkle chain construction and verification
//! - Chain integrity validation with detailed break reporting
//! - Merkle proof generation for individual entries
//! - Atomic batch verification for high-throughput scenarios
//!
//! All operations are designed to be immutable and deterministic:
//! the same input always produces the same output.

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::{PyDict, PyList};
use std::collections::HashMap;

// ─── Hash Generation ──────────────────────────────────────────

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

// ─── Chain Verification ───────────────────────────────────────

/// Verify a Merkle chain of audit entries.
///
/// Walks the chain from genesis to the latest entry, checking that
/// each entry's parent_hash matches the hash of the preceding entry.
/// Reports detailed information about any broken links.
///
/// Parameters
/// ----------
/// entries : list[dict]
///     List of dicts, each with keys:
///     - "id": int or str (sequential identifier)
///     - "hash_sha256": str (the entry's hash)
///     - "parent_hash": str (hash of the previous entry, "GENESIS" for first)
///     - "file_path": str (entity identifier for grouping)
///     - "operation": str (the operation that was performed)
///     - "timestamp": float (Unix epoch)
///
/// Returns
/// -------
/// dict
///     {
///         "is_valid": bool,
///         "total_entries": int,
///         "valid_entries": int,
///         "broken_links": list[dict],
///         "root_hash": str
///     }
#[pyfunction]
#[pyo3(signature = (entries))]
pub fn verify_merkle_chain(py: Python<'_>, entries: &Bound<'_, PyList>) -> PyResult<Py<PyDict>> {
    let mut total_entries: usize = 0;
    let mut valid_entries: usize = 0;
    let _broken_links: Vec<Py<PyDict>> = Vec::new();
    let mut root_hash = String::new();

    if entries.is_empty() {
        let result = PyDict::new_bound(py);
        result.set_item("is_valid", true)?;
        result.set_item("total_entries", 0)?;
        result.set_item("valid_entries", 0)?;
        result.set_item("broken_links", PyList::empty_bound(py))?;
        result.set_item("root_hash", "")?;
        return Ok(result.unbind());
    }

    total_entries = entries.len();

    // Parse all entries into a structured form
    let mut parsed: Vec<(String, String, String, String, String, f64)> = Vec::with_capacity(total_entries);
    for item in entries.iter() {
        let id_val: String = item.get_item("id")?.extract()?;
        let hash_val: String = item.get_item("hash_sha256")?.extract()?;
        let parent_val: String = item.get_item("parent_hash")?.extract()?;
        let file_path_val: String = item.get_item("file_path")?.extract()?;
        let operation_val: String = item.get_item("operation")?.extract()?;
        let timestamp_val: f64 = item.get_item("timestamp")?.extract()?;
        parsed.push((id_val, hash_val, parent_val, file_path_val, operation_val, timestamp_val));
    }

    // Group by file_path for independent chain verification
    let mut file_groups: HashMap<String, Vec<usize>> = HashMap::new();
    for (i, (_, _, _, fp, _, _)) in parsed.iter().enumerate() {
        file_groups.entry(fp.clone()).or_default().push(i);
    }

    let mut broken_count: usize = 0;
    let mut broken_list: Vec<Py<PyDict>> = Vec::new();

    for (fp, indices) in &file_groups {
        // Sort indices by id (which should already be sequential)
        let mut sorted_indices = indices.clone();
        sorted_indices.sort_by(|a, b| {
            let id_a = &parsed[*a].0;
            let id_b = &parsed[*b].0;
            // Try numeric comparison first, fall back to string
            match (id_a.parse::<i64>(), id_b.parse::<i64>()) {
                (Ok(na), Ok(nb)) => na.cmp(&nb),
                _ => id_a.cmp(id_b),
            }
        });

        for (pos, &idx) in sorted_indices.iter().enumerate() {
            let (_, hash_val, parent_val, _, operation_val, ts) = &parsed[idx];

            if parent_val == "GENESIS" {
                valid_entries += 1;
                continue;
            }

            if pos == 0 {
                // First entry for this file with non-GENESIS parent
                // Check if parent exists in any group (cross-file chain)
                let parent_exists = parsed.iter().any(|(_, h, _, _, _, _)| h == parent_val);
                if parent_exists {
                    valid_entries += 1;
                } else {
                    broken_count += 1;
                    let brk = PyDict::new_bound(py);
                    brk.set_item("file_path", fp)?;
                    brk.set_item("entry_id", &parsed[idx].0)?;
                    brk.set_item("expected_parent_hash", parent_val)?;
                    brk.set_item("actual_parent_hash", parent_val)?;
                    brk.set_item("entry_hash", hash_val)?;
                    brk.set_item("operation", operation_val)?;
                    brk.set_item("timestamp", *ts)?;
                    broken_list.push(brk.unbind());
                }
                continue;
            }

            // Standard case: check parent_hash matches previous entry's hash
            let prev_idx = sorted_indices[pos - 1];
            let expected_parent = &parsed[prev_idx].1;

            if parent_val == expected_parent {
                valid_entries += 1;
            } else {
                broken_count += 1;
                let brk = PyDict::new_bound(py);
                brk.set_item("file_path", fp)?;
                brk.set_item("entry_id", &parsed[idx].0)?;
                brk.set_item("expected_parent_hash", expected_parent)?;
                brk.set_item("actual_parent_hash", parent_val)?;
                brk.set_item("entry_hash", hash_val)?;
                brk.set_item("operation", operation_val)?;
                brk.set_item("timestamp", *ts)?;
                broken_list.push(brk.unbind());
            }
        }
    }

    // Root hash is the hash of the last entry
    if !parsed.is_empty() {
        root_hash = parsed.last().unwrap().1.clone();
    }

    let is_valid = broken_count == 0;

    let broken_pylist = PyList::new_bound(py, &broken_list);
    let result = PyDict::new_bound(py);
    result.set_item("is_valid", is_valid)?;
    result.set_item("total_entries", total_entries)?;
    result.set_item("valid_entries", valid_entries)?;
    result.set_item("broken_links", broken_pylist)?;
    result.set_item("root_hash", root_hash)?;

    Ok(result.unbind())
}

// ─── Merkle Proof ─────────────────────────────────────────────

/// Generate a Merkle inclusion proof for a specific entry within a group.
///
/// Computes the Merkle root of all sibling hashes and provides the
/// proof path (sibling hashes at each level) needed to verify that
/// a specific entry is included in the tree.
///
/// Parameters
/// ----------
/// entry_hash : str
///     The hash of the entry to prove inclusion for.
/// all_hashes : list[str]
///     All leaf hashes in the same group (including the target entry).
///
/// Returns
/// -------
/// dict
///     {
///         "merkle_root": str,
///         "proof_path": list[str],
///         "leaf_index": int,
///         "verified": bool
///     }
#[pyfunction]
#[pyo3(signature = (entry_hash, all_hashes))]
pub fn merkle_proof(py: Python<'_>, entry_hash: &str, all_hashes: &Bound<'_, PyList>) -> PyResult<Py<PyDict>> {
    if all_hashes.is_empty() {
        return Err(PyValueError::new_err("all_hashes must not be empty"));
    }

    let hashes: Vec<String> = all_hashes.extract()?;

    // Find the leaf index
    let leaf_index = hashes.iter().position(|h| h == entry_hash);
    let leaf_idx = match leaf_index {
        Some(idx) => idx,
        None => {
            let result = PyDict::new_bound(py);
            result.set_item("merkle_root", "")?;
            result.set_item("proof_path", PyList::empty_bound(py))?;
            result.set_item("leaf_index", -1i64)?;
            result.set_item("verified", false)?;
            return Ok(result.unbind());
        }
    };

    // Build the Merkle tree and extract proof path
    let (root, proof_path) = build_merkle_tree_with_proof(&hashes, leaf_idx);

    // Verify the proof
    let verified = verify_merkle_proof(entry_hash, leaf_idx, &proof_path, &root);

    let proof_pylist = PyList::new_bound(py, &proof_path);
    let result = PyDict::new_bound(py);
    result.set_item("merkle_root", &root)?;
    result.set_item("proof_path", proof_pylist)?;
    result.set_item("leaf_index", leaf_idx as i64)?;
    result.set_item("verified", verified)?;

    Ok(result.unbind())
}

/// Build a Merkle tree and extract the proof path for a given leaf index.
fn build_merkle_tree_with_proof(leaves: &[String], target_idx: usize) -> (String, Vec<String>) {
    if leaves.is_empty() {
        return (blake3::hash(b"empty").to_hex().to_string(), Vec::new());
    }

    if leaves.len() == 1 {
        return (leaves[0].clone(), Vec::new());
    }

    // Hash all leaves
    let mut current_level: Vec<String> = leaves
        .iter()
        .map(|l| blake3::hash(l.as_bytes()).to_hex().to_string())
        .collect();

    let mut proof_path: Vec<String> = Vec::new();
    let mut idx = target_idx;

    while current_level.len() > 1 {
        // Pad if odd
        if current_level.len() % 2 != 0 {
            current_level.push(current_level.last().unwrap().clone());
        }

        // Find sibling
        if idx % 2 == 0 {
            // Left node — sibling is right
            if idx + 1 < current_level.len() {
                proof_path.push(current_level[idx + 1].clone());
            }
        } else {
            // Right node — sibling is left
            proof_path.push(current_level[idx - 1].clone());
        }

        // Build next level
        let mut next_level = Vec::with_capacity(current_level.len() / 2);
        for chunk in current_level.chunks(2) {
            let mut combined = Vec::with_capacity(128);
            combined.extend_from_slice(chunk[0].as_bytes());
            combined.extend_from_slice(chunk[1].as_bytes());
            let parent = blake3::hash(&combined).to_hex().to_string();
            next_level.push(parent);
        }

        idx /= 2;
        current_level = next_level;
    }

    // Final root hash
    let root = blake3::hash(current_level[0].as_bytes()).to_hex().to_string();
    (root, proof_path)
}

/// Verify a Merkle proof.
fn verify_merkle_proof(leaf_hash: &str, leaf_index: usize, proof_path: &[String], root: &str) -> bool {
    let mut current = blake3::hash(leaf_hash.as_bytes()).to_hex().to_string();
    let mut idx = leaf_index;

    for sibling in proof_path {
        let mut combined = Vec::with_capacity(128);
        if idx % 2 == 0 {
            combined.extend_from_slice(current.as_bytes());
            combined.extend_from_slice(sibling.as_bytes());
        } else {
            combined.extend_from_slice(sibling.as_bytes());
            combined.extend_from_slice(current.as_bytes());
        }
        current = blake3::hash(&combined).to_hex().to_string();
        idx /= 2;
    }

    let computed_root = blake3::hash(current.as_bytes()).to_hex().to_string();
    computed_root == root
}

// ─── Batch Verification ───────────────────────────────────────

/// Batch-verify multiple Merkle chains in a single call.
///
/// Efficient for verifying the integrity of multiple tenants or
/// file groups simultaneously.
///
/// Parameters
/// ----------
/// chains : dict[str, list[dict]]
///     Mapping of chain_id → list of entry dicts (same format as verify_merkle_chain).
///
/// Returns
/// -------
/// dict
///     Mapping of chain_id → verification result dict.
#[pyfunction]
#[pyo3(signature = (chains))]
pub fn batch_verify_chains(py: Python<'_>, chains: &Bound<'_, PyDict>) -> PyResult<Py<PyDict>> {
    let result = PyDict::new_bound(py);

    for (key, value) in chains.iter() {
        let chain_id: String = key.extract()?;
        let entries_list: &Bound<'_, PyList> = value.downcast()?;

        match verify_merkle_chain(py, entries_list) {
            Ok(verification) => {
                result.set_item(&chain_id, verification)?;
            }
            Err(e) => {
                let error_dict = PyDict::new_bound(py);
                error_dict.set_item("is_valid", false)?;
                error_dict.set_item("error", e.to_string())?;
                result.set_item(&chain_id, error_dict.unbind())?;
            }
        }
    }

    Ok(result.unbind())
}

// ─── Unit Tests ───────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_forensic_hash_deterministic() {
        let a = forensic_hash(
            "id1", "tenant1", "CREATE", "desc", "actor", "2024-01-01", "{}",
        ).unwrap();
        let b = forensic_hash(
            "id1", "tenant1", "CREATE", "desc", "actor", "2024-01-01", "{}",
        ).unwrap();
        assert_eq!(a, b);
    }

    #[test]
    fn test_forensic_hash_different_inputs() {
        let a = forensic_hash(
            "id1", "tenant1", "CREATE", "desc", "actor", "2024-01-01", "{}",
        ).unwrap();
        let b = forensic_hash(
            "id2", "tenant1", "CREATE", "desc", "actor", "2024-01-01", "{}",
        ).unwrap();
        assert_ne!(a, b);
    }

    #[test]
    fn test_chain_hash_basic() {
        let result = chain_hash("parent123", "entry456").unwrap();
        assert_eq!(result.len(), 64);
    }

    #[test]
    fn test_chain_hash_genesis() {
        // Genesis entries have empty parent
        let result = chain_hash("", "entry456").unwrap();
        assert_eq!(result.len(), 64);
    }

    #[test]
    fn test_forensic_hash_empty_id_error() {
        assert!(forensic_hash("", "t", "e", "d", "a", "ts", "{}").is_err());
    }

    #[test]
    fn test_build_merkle_tree_with_proof_single() {
        let leaves = vec!["hash1".to_string()];
        let (root, proof) = build_merkle_tree_with_proof(&leaves, 0);
        assert!(proof.is_empty());
        assert!(!root.is_empty());
    }

    #[test]
    fn test_build_merkle_tree_with_proof_multi() {
        let leaves = vec![
            "hash1".to_string(),
            "hash2".to_string(),
            "hash3".to_string(),
            "hash4".to_string(),
        ];
        let (root, proof) = build_merkle_tree_with_proof(&leaves, 0);
        assert_eq!(proof.len(), 2); // log2(4) = 2 levels
        assert!(verify_merkle_proof("hash1", 0, &proof, &root));
    }

    #[test]
    fn test_verify_merkle_proof_tampered() {
        let leaves = vec![
            "hash1".to_string(),
            "hash2".to_string(),
            "hash3".to_string(),
            "hash4".to_string(),
        ];
        let (root, proof) = build_merkle_tree_with_proof(&leaves, 0);
        assert!(!verify_merkle_proof("tampered", 0, &proof, &root));
    }
}
