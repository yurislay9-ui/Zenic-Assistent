//! Forensic Audit Engine — Hash generation and Merkle tree analysis.
//!
//! BLAKE3 hash generation, chain hashing, Merkle tree construction,
//! and proof verification.

use super::types::*;

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

/// Build a Merkle tree and extract the proof path for a given leaf index.
pub(crate) fn build_merkle_tree_with_proof(leaves: &[String], target_idx: usize) -> (String, Vec<String>) {
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
pub(crate) fn verify_merkle_proof(leaf_hash: &str, leaf_index: usize, proof_path: &[String], root: &str) -> bool {
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
