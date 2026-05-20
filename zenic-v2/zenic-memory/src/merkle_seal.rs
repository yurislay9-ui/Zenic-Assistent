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
//!
//! Phase 4 enhancements:
//! - Batch verification of multiple mappings
//! - Graph integrity verification with detailed report
//! - IntegrityReport / IntegrityDetail / IntegrityStatus types

use crate::errors::MemoryError;
use crate::graph::SemanticGraph;
use crate::types::SemanticMapping;

// ---------------------------------------------------------------------------
// IntegrityStatus
// ---------------------------------------------------------------------------

/// Status of an individual mapping integrity check.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum IntegrityStatus {
    /// The mapping hash matches the computed hash.
    Valid,
    /// The computed hash does not match the stored hash.
    HashMismatch,
    /// The mapping has no stored Merkle hash (not yet sealed).
    MissingHash,
    /// The mapping was not found in the graph.
    NotFound,
}

// ---------------------------------------------------------------------------
// IntegrityDetail
// ---------------------------------------------------------------------------

/// Detail of a single mapping's integrity check result.
#[derive(Debug, Clone)]
pub struct IntegrityDetail {
    /// The mapping identifier.
    pub mapping_id: String,
    /// The integrity check status.
    pub status: IntegrityStatus,
    /// The expected (stored) hash, if any.
    pub expected_hash: Option<String>,
    /// The actual computed hash, if verification was attempted.
    pub actual_hash: Option<String>,
}

// ---------------------------------------------------------------------------
// IntegrityReport
// ---------------------------------------------------------------------------

/// Report from a graph integrity verification.
///
/// Summarizes the results of verifying all mappings in the graph
/// against their stored Merkle hashes.
#[derive(Debug, Clone)]
pub struct IntegrityReport {
    /// Total number of mappings checked.
    pub total_mappings: u32,
    /// Number of mappings that verified successfully.
    pub verified: u32,
    /// Number of mappings that failed verification.
    pub failed: u32,
    /// Number of mappings missing a Merkle hash.
    pub missing_hash: u32,
    /// Detailed results for each mapping.
    pub details: Vec<IntegrityDetail>,
}

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
    /// Stored mapping hashes for verification: mapping_id → blake3 hex hash.
    stored_hashes: std::collections::HashMap<String, String>,
}

impl MerkleSeal {
    /// Creates a new empty Merkle seal.
    pub fn new() -> Self {
        Self {
            root_hash: [0u8; 32],
            leaf_count: 0,
            verified: true,
            stored_hashes: std::collections::HashMap::new(),
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

        // Store the hash for later verification
        self.stored_hashes
            .insert(mapping.mapping_id.clone(), hash_hex.clone());

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

    /// Verifies a batch of (mapping, expected_hash) pairs.
    ///
    /// Returns a vector of booleans, one for each pair, indicating
    /// whether the mapping matches its expected hash.
    pub fn verify_batch(
        &self,
        mappings: &[(SemanticMapping, String)],
    ) -> Vec<bool> {
        mappings
            .iter()
            .map(|(mapping, expected_hash)| {
                self.verify_mapping(mapping, expected_hash).unwrap_or(false)
            })
            .collect()
    }

    /// Verifies the integrity of all mappings in a semantic graph.
    ///
    /// Checks every mapping in the graph against its stored Merkle hash
    /// and produces a detailed report. Mappings without hashes are
    /// reported as `MissingHash`; mappings not found are `NotFound`.
    pub fn verify_graph_integrity(
        &self,
        graph: &SemanticGraph,
    ) -> Result<IntegrityReport, MemoryError> {
        let all_mappings = graph.list_all_mappings()?;

        let mut total_mappings: u32 = 0;
        let mut verified: u32 = 0;
        let mut failed: u32 = 0;
        let mut missing_hash: u32 = 0;
        let mut details = Vec::new();

        for mapping in &all_mappings {
            total_mappings += 1;

            match &mapping.merkle_hash {
                None => {
                    // No hash stored — mapping not yet sealed
                    missing_hash += 1;
                    details.push(IntegrityDetail {
                        mapping_id: mapping.mapping_id.clone(),
                        status: IntegrityStatus::MissingHash,
                        expected_hash: None,
                        actual_hash: None,
                    });
                }
                Some(expected_hash) => {
                    // Verify against stored hash
                    let computed = self.compute_mapping_hash(mapping);
                    match computed {
                        Ok(actual_hex) => {
                            if actual_hex == *expected_hash {
                                verified += 1;
                                details.push(IntegrityDetail {
                                    mapping_id: mapping.mapping_id.clone(),
                                    status: IntegrityStatus::Valid,
                                    expected_hash: Some(expected_hash.clone()),
                                    actual_hash: Some(actual_hex),
                                });
                            } else {
                                failed += 1;
                                details.push(IntegrityDetail {
                                    mapping_id: mapping.mapping_id.clone(),
                                    status: IntegrityStatus::HashMismatch,
                                    expected_hash: Some(expected_hash.clone()),
                                    actual_hash: Some(actual_hex),
                                });
                            }
                        }
                        Err(_) => {
                            failed += 1;
                            details.push(IntegrityDetail {
                                mapping_id: mapping.mapping_id.clone(),
                                status: IntegrityStatus::HashMismatch,
                                expected_hash: Some(expected_hash.clone()),
                                actual_hash: None,
                            });
                        }
                    }
                }
            }
        }

        Ok(IntegrityReport {
            total_mappings,
            verified,
            failed,
            missing_hash,
            details,
        })
    }

    /// Computes the BLAKE3 hash for a mapping (without storing it).
    fn compute_mapping_hash(
        &self,
        mapping: &SemanticMapping,
    ) -> Result<String, MemoryError> {
        let bincode_bytes = bincode::serialize(mapping)
            .map_err(|e| MemoryError::BincodeSerialization(e.to_string()))?;
        let hash = blake3::hash(&bincode_bytes);
        Ok(hex::encode(hash.as_bytes()))
    }

    /// Returns the stored hash for a mapping, if any.
    pub fn get_stored_hash(&self, mapping_id: &str) -> Option<&str> {
        self.stored_hashes.get(mapping_id).map(|s| s.as_str())
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
