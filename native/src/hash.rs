//! Fast native hashing operations for Zenic-Agents.
//!
//! Provides BLAKE3, xxHash64, and Merkle tree root computation.
//! These are used by the core engine for integrity verification,
//! content-addressed storage, and the Level 7 Merkle ledger.

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

/// Compute a BLAKE3 hash of the input data.
///
/// BLAKE3 is a fast, parallel cryptographic hash function that is
/// significantly faster than SHA-256 while maintaining strong security.
///
/// Parameters
/// ----------
/// data : bytes
///     The data to hash.
///
/// Returns
/// -------
/// str
///     The 64-character hex-encoded BLAKE3 hash.
///
/// Raises
/// ------
/// ValueError
///     If data is empty.
#[pyfunction]
#[pyo3(signature = (data))]
pub fn blake3_hash(data: &[u8]) -> PyResult<String> {
    if data.is_empty() {
        return Err(PyValueError::new_err("data must not be empty"));
    }
    let hash = blake3::hash(data);
    Ok(hash.to_hex().to_string())
}

/// Compute an xxHash64 hash of the input data.
///
/// xxHash64 is an extremely fast non-cryptographic hash function
/// suitable for hash tables, checksums, and data fingerprinting.
///
/// Parameters
/// ----------
/// data : bytes
///     The data to hash.
/// seed : int
///     A 64-bit seed value.
///
/// Returns
/// -------
/// int
///     The 64-bit xxHash64 hash value.
///
/// Raises
/// ------
/// ValueError
///     If data is empty.
#[pyfunction]
#[pyo3(signature = (data, seed))]
pub fn xxhash64(data: &[u8], seed: u64) -> PyResult<u64> {
    if data.is_empty() {
        return Err(PyValueError::new_err("data must not be empty"));
    }
    use xxhash_rust::xxh64::xxh64;
    Ok(xxh64(data, seed))
}

/// Compute the Merkle root of a list of leaf hashes.
///
/// Used by the Level 7 Merkle ledger for integrity verification.
/// If there is only one leaf, it is the root. The tree is built
/// by pairing adjacent hashes and computing BLAKE3 of their
/// concatenation. If the number of leaves is odd, the last leaf
/// is duplicated to complete the pair.
///
/// Parameters
/// ----------
/// leaves : list[bytes]
///     A list of leaf values (raw bytes, typically hashes themselves).
///
/// Returns
/// -------
/// str
///     The 64-character hex-encoded BLAKE3 Merkle root.
///
/// Raises
/// ------
/// ValueError
///     If the leaves list is empty.
#[pyfunction]
#[pyo3(signature = (leaves))]
pub fn merkle_root(leaves: Vec<Vec<u8>>) -> PyResult<String> {
    if leaves.is_empty() {
        return Err(PyValueError::new_err("leaves must not be empty"));
    }

    // If only one leaf, its hash is the root
    if leaves.len() == 1 {
        let hash = blake3::hash(&leaves[0]);
        return Ok(hash.to_hex().to_string());
    }

    // Build the Merkle tree bottom-up
    let mut current_level: Vec<Vec<u8>> = leaves
        .iter()
        .map(|leaf| blake3::hash(leaf).as_bytes().to_vec())
        .collect();

    while current_level.len() > 1 {
        // If odd number of nodes, duplicate the last one
        if current_level.len() % 2 != 0 {
            current_level.push(current_level.last().unwrap().clone());
        }

        let mut next_level = Vec::with_capacity(current_level.len() / 2);

        for chunk in current_level.chunks(2) {
            // Concatenate the two child hashes and hash them
            let mut combined = Vec::with_capacity(64);
            combined.extend_from_slice(&chunk[0]);
            combined.extend_from_slice(&chunk[1]);
            let parent_hash = blake3::hash(&combined);
            next_level.push(parent_hash.as_bytes().to_vec());
        }

        current_level = next_level;
    }

    // current_level[0] is already the final BLAKE3 hash bytes from the pairing loop
    let root = blake3::Hash::from_slice(&current_level[0]);
    Ok(root?.to_hex().to_string())
}

// ── Unit tests ──────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_blake3_hash_basic() {
        let result = blake3_hash(b"hello world").unwrap();
        assert_eq!(result.len(), 64); // 32 bytes = 64 hex chars
    }

    #[test]
    fn test_blake3_hash_empty_error() {
        assert!(blake3_hash(b"").is_err());
    }

    #[test]
    fn test_blake3_hash_deterministic() {
        let a = blake3_hash(b"test").unwrap();
        let b = blake3_hash(b"test").unwrap();
        assert_eq!(a, b);
    }

    #[test]
    fn test_xxhash64_basic() {
        let result = xxhash64(b"hello world", 0).unwrap();
        assert_ne!(result, 0);
    }

    #[test]
    fn test_xxhash64_different_seeds() {
        let a = xxhash64(b"test", 0).unwrap();
        let b = xxhash64(b"test", 42).unwrap();
        assert_ne!(a, b);
    }

    #[test]
    fn test_xxhash64_empty_error() {
        assert!(xxhash64(b"", 0).is_err());
    }

    #[test]
    fn test_merkle_root_single_leaf() {
        let leaves = vec![b"leaf1".to_vec()];
        let result = merkle_root(leaves).unwrap();
        assert_eq!(result.len(), 64);
    }

    #[test]
    fn test_merkle_root_two_leaves() {
        let leaves = vec![b"leaf1".to_vec(), b"leaf2".to_vec()];
        let result = merkle_root(leaves).unwrap();
        assert_eq!(result.len(), 64);
    }

    #[test]
    fn test_merkle_root_three_leaves() {
        let leaves = vec![b"a".to_vec(), b"b".to_vec(), b"c".to_vec()];
        let result = merkle_root(leaves).unwrap();
        assert_eq!(result.len(), 64);
    }

    #[test]
    fn test_merkle_root_empty_error() {
        let leaves: Vec<Vec<u8>> = vec![];
        assert!(merkle_root(leaves).is_err());
    }
}
