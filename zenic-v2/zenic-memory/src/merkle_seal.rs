//! Merkle Seal — BLAKE3-based cryptographic integrity [T2-16, T3-4]
//!
//! Every approved mapping is sealed with a BLAKE3 hash in the MerkleLedger.
//! Uses bincode for compact persistence + BLAKE3 for hashing.
//!
//! Flow after HITL approval:
//! 1. admin_evidence_review = True     ✅
//! 2. admin_justification ≥ 50 chars   ✅
//! 3. risk_acknowledgment = True       ✅
//! 4. admin_session_id verified        ✅
//!    → 5. MerkleLedger BLAKE3 seal    → merkle_seal.rs
//!    → 6. Hot-reload in zenic-policy  → yaml_renderer.rs
//!    → 7. Cache LRU update            → cache.rs

use crate::errors::MemoryError;
use crate::types::SemanticMapping;

// ---------------------------------------------------------------------------
// MerkleSeal
// ---------------------------------------------------------------------------

/// Merkle seal that provides cryptographic integrity for the semantic graph.
///
/// Every mutation updates the seal, and any tampering is detectable.
/// Uses BLAKE3 for hashing and bincode for compact serialization.
pub struct MerkleSeal {
    /// The root hash of the Merkle tree.
    root_hash: [u8; 32],
    /// The number of leaves (sealed mappings).
    leaf_count: u64,
    /// Whether the seal has been verified since the last mutation.
    verified: bool,
}

impl MerkleSeal {
    /// Creates a new empty Merkle seal.
    pub fn new() -> Self {
        Self {
            root_hash: [0u8; 32],
            leaf_count: 0,
            verified: true,
        }
    }

    /// Seals a semantic mapping with BLAKE3(bincode bytes).
    ///
    /// This is the commit step after HITL approval.
    /// The mapping is serialized with bincode for compact representation,
    /// then hashed with BLAKE3 for integrity.
    pub fn seal_mapping(&mut self, mapping: &SemanticMapping) -> Result<String, MemoryError> {
        // Serialize with bincode for compact representation
        let bincode_bytes = bincode::serialize(mapping)
            .map_err(|e| MemoryError::BincodeSerialization(e.to_string()))?;

        // Hash with BLAKE3
        let hash = blake3::hash(&bincode_bytes);
        let hash_hex = hex::encode(hash.as_bytes());

        // Update the Merkle tree root
        self.update_root(hash.as_bytes());
        self.leaf_count += 1;
        self.verified = true;

        Ok(hash_hex)
    }

    /// Verifies a mapping against its Merkle hash.
    pub fn verify_mapping(
        &self,
        mapping: &SemanticMapping,
        expected_hash: &str,
    ) -> Result<bool, MemoryError> {
        let bincode_bytes = bincode::serialize(mapping)
            .map_err(|e| MemoryError::BincodeSerialization(e.to_string()))?;

        let computed = blake3::hash(&bincode_bytes);
        let computed_hex = hex::encode(computed.as_bytes());

        Ok(computed_hex == expected_hash)
    }

    /// Computes the seal from a slice of leaf data.
    pub fn compute(&mut self, leaves: &[Vec<u8>]) {
        self.leaf_count = leaves.len() as u64;
        let mut hasher = blake3::Hasher::new();
        for leaf in leaves {
            hasher.update(leaf);
        }
        self.root_hash = *hasher.finalize().as_bytes();
        self.verified = true;
    }

    /// Verifies the seal against the current data.
    pub fn verify(&self, leaves: &[Vec<u8>]) -> Result<bool, MemoryError> {
        let mut hasher = blake3::Hasher::new();
        for leaf in leaves {
            hasher.update(leaf);
        }
        let computed = hasher.finalize();
        Ok(*computed.as_bytes() == self.root_hash)
    }

    /// Returns the root hash.
    pub fn root_hash(&self) -> &[u8; 32] {
        &self.root_hash
    }

    /// Returns the root hash as hex string.
    pub fn root_hash_hex(&self) -> String {
        hex::encode(&self.root_hash)
    }

    /// Returns the number of sealed leaves.
    pub fn leaf_count(&self) -> u64 {
        self.leaf_count
    }

    /// Updates the root hash by incorporating a new leaf.
    fn update_root(&mut self, new_leaf_hash: &[u8; 32]) {
        let mut hasher = blake3::Hasher::new();
        hasher.update(&self.root_hash);
        hasher.update(new_leaf_hash);
        self.root_hash = *hasher.finalize().as_bytes();
    }
}

impl Default for MerkleSeal {
    fn default() -> Self {
        Self::new()
    }
}

/// Minimal hex encoding (avoids adding another dependency).
mod hex {
    pub fn encode(bytes: &[u8]) -> String {
        bytes.iter().map(|b| format!("{:02x}", b)).collect()
    }
}
